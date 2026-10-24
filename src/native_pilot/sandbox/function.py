"""Function-call adaptation: arguments in Docker, authoritative answers outside.

The wrapper is merely an invocation protocol. It contains no expected answers,
checker, or pass/fail logic. Candidate code is only compiled/executed in Docker.
"""
from __future__ import annotations

import json
import keyword
import math


# Preserve the released evaluator's standard-library convenience environment.
# These imports are text inserted in a Docker-only program, never host-executed.
SOURCE_PRELUDE = """from string import *
from re import *
from datetime import *
from collections import *
from heapq import *
from bisect import *
from copy import *
from math import *
from random import *
from statistics import *
from itertools import *
from functools import *
from operator import *
from io import *
from sys import *
from json import *
from builtins import *
from typing import *
import string, re, datetime, collections, heapq, bisect, copy, math, random
import statistics, itertools, functools, operator, io, sys, json
sys.setrecursionlimit(50000)
"""


def validate_json_value(value, *, depth=0):
    if depth > 100:
        raise ValueError("JSON value exceeds nesting limit")
    if value is None or type(value) in (bool, str, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            validate_json_value(item, depth=depth + 1)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            validate_json_value(item, depth=depth + 1)
        return
    raise ValueError("Expected finite, ordinary JSON value")


def exact_json_equal(actual, expected):
    """Exact numeric equality with no tolerance; booleans are not integers.

    Matches the released ordinary numeric equality (including 1.0 == 1),
    without inheriting Python's misleading True == 1 behavior.
    """
    if type(actual) in (int, float) and type(expected) in (int, float):
        return actual == expected
    if type(actual) is not type(expected):
        return False
    if type(expected) is list:
        return len(actual) == len(expected) and all(exact_json_equal(a, e) for a, e in zip(actual, expected))
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(exact_json_equal(actual[k], expected[k]) for k in expected)
    return actual == expected


def validate_entrypoint(entrypoint):
    if not isinstance(entrypoint, dict) or set(entrypoint) not in ({"class", "method"}, {"function"}):
        raise ValueError("Entrypoint must identify a class/method or a function")
    for value in entrypoint.values():
        if not isinstance(value, str) or not value.isidentifier() or keyword.iskeyword(value) or value.startswith("__"):
            raise ValueError("Entrypoint names must be ordinary Python identifiers")


def invocation_program(code, entrypoint):
    validate_entrypoint(entrypoint)
    # Strings are escaped as Python literals, never evaluated on the host.
    # The submitted module and a fresh class instance are initialized anew per
    # case; only JSON inputs, never expected outputs, enter this process.
    return f'''import json as _json, sys as _sys
_inputs = _json.loads(_sys.stdin.read())
_source = {code!r}
_prelude = {SOURCE_PRELUDE!r}
_entrypoint = {entrypoint!r}
_compile = compile
_execute = exec
_getattr = getattr
_serialize = _json.dumps
_write = _sys.stdout.write
_diagnostics = _sys.stderr
_results = []
for _arguments in _inputs:
    _scope = {{"__name__": "submission"}}
    _saved_stdout = _sys.stdout
    _sys.stdout = _diagnostics
    try:
        _execute(_compile(_prelude, "<benchmark-prelude>", "exec"), _scope)
        _execute(_compile(_source, "<submission>", "exec"), _scope)
        if "class" in _entrypoint:
            _target = _getattr(_scope[_entrypoint["class"]](), _entrypoint["method"])
        else:
            _target = _scope[_entrypoint["function"]]
        _results.append(_target(*_arguments))
    finally:
        _sys.stdout = _saved_stdout
_write(_serialize(_results, allow_nan=False, separators=(",", ":")))
'''


def evaluate_function(sandbox, code, tests, entrypoint):
    validate_entrypoint(entrypoint)
    if not isinstance(tests, list) or not tests or len(tests) > 1000:
        raise ValueError("A nonempty bounded function test suite is required")
    batches = []
    batch = []
    input_bytes, expected_bytes = 2, 2
    for test in tests:
        if not isinstance(test, dict) or not isinstance(test.get("args"), list) or "expected" not in test:
            raise ValueError("Function tests require positional args and expected JSON result")
        validate_json_value(test["args"])
        validate_json_value(test["expected"])
        size = len(json.dumps(test["args"], ensure_ascii=False, allow_nan=False).encode()) + 1
        output_size = len(json.dumps(test["expected"], ensure_ascii=False, allow_nan=False).encode()) + 1
        if size > 3_900_000 or output_size > sandbox.output_limit - 100:
            raise ValueError("Individual authoritative test exceeds qualified sandbox I/O bounds")
        if batch and (len(batch) >= 8 or input_bytes + size > 2_500_000
                      or expected_bytes + output_size > sandbox.output_limit // 2):
            batches.append(batch)
            batch, input_bytes, expected_bytes = [], 2, 2
        batch.append(test)
        input_bytes += size
        expected_bytes += output_size
    if batch:
        batches.append(batch)
    results = []
    program = invocation_program(code, entrypoint)
    for batch in batches:
        arguments = [test["args"] for test in batch]
        raw = sandbox.run(program, json.dumps(arguments, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
        failure = {"passed": False, "status": raw["status"], "returncode": raw["returncode"]}
        if raw["status"] != "completed" or raw["returncode"] != 0:
            results.extend(dict(failure) for _ in batch)
            continue
        try:
            answers = json.loads(raw["stdout"], parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
            validate_json_value(answers)
            if not isinstance(answers, list) or len(answers) != len(batch):
                raise ValueError("Wrong result count")
        except (ValueError, TypeError, RecursionError):
            failure["status"] = "invalid_function_output"
            results.extend(dict(failure) for _ in batch)
            continue
        results.extend({"passed": exact_json_equal(answer, test["expected"]), "status": "completed", "returncode": 0}
                       for answer, test in zip(answers, batch))
    return {"passed": all(result["passed"] for result in results), "results": results,
            "mode": "function", "container_batches": len(batches)}
