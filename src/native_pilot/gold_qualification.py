"""Qualification of certified offline outputs, separate from candidate limits.

No generated lookup program is constructed. A compiled reference is replayed by
the offline runner; actual Python submissions continue through the normal grader.
"""
from __future__ import annotations

from .sandbox.stdin import compare_stdin


def _replay(spec, tests):
    from .reference_construction import replay_reference
    return replay_reference(spec, tests)


def qualify_compiled_gold(task, grade, *, execution_records=None):
    """Return boolean checks; ``grade(variant, code)`` uses candidate limits.

    Full source binding, compiler/budget binding, independent review and replay
    are enforced by reference_construction. This layer compares returned plain
    outputs using the exact same comparator as submitted stdin programs.
    """
    old, new = task["original"], task["updated"]
    if old.get("offline_reference", {}).get("kind") != "compiled_gold_v1" or new.get("offline_reference"):
        raise ValueError("Offline gold qualification currently requires compiled original and Python updated")
    if any(spec.get("mode", "stdin") != "stdin" for spec in (old, new)):
        raise ValueError("Offline compiled gold requires stdin variants")
    for spec in (old, new):
        if not isinstance(spec.get("tests"), list) or not spec["tests"]:
            raise ValueError("Both complete authoritative test suites are required")
        if type(spec.get("case_insensitive", False)) is not bool:
            raise ValueError("Invalid case comparison flag")
        if any(not isinstance(t, dict) or not isinstance(t.get("stdin"), str)
               or not isinstance(t.get("stdout"), str) for t in spec["tests"]):
            raise ValueError("Malformed authoritative stdin suite")
    replay = _replay(old, old["tests"])
    if execution_records is not None:
        execution_records.append(replay.get("execution"))
    if replay.get("passed") is not True:
        return {"original_reference": False}
    outputs = replay.get("outputs")
    if (not isinstance(outputs, list) or len(outputs) != len(old["tests"])
            or not all(isinstance(output, str) for output in outputs)):
        raise ValueError("Compiled replay must return exactly one text output per input")
    insensitive = old.get("case_insensitive", False)
    checks = {}
    checks["original_reference"] = all(
        compare_stdin(output, test["stdout"], case_insensitive=insensitive)
        for output, test in zip(outputs, old["tests"]))
    checks["original_equivalent"] = all(
        compare_stdin(" \t" + "\n ".join(output.split()) + "\n", test["stdout"], case_insensitive=insensitive)
        for output, test in zip(outputs, old["tests"]))
    checks["original_wrong_rejected"] = all(
        not compare_stdin(output + " __deliberately_wrong__", test["stdout"], case_insensitive=insensitive)
        for output, test in zip(outputs, old["tests"]))

    # Independent fixtures can differ between variants (e.g. positive
    # translations). A single shared-input mismatch proves the old reference
    # fails the updated suite; its entire own suite is nevertheless replayed.
    by_input = {}
    for test, output in zip(old["tests"], outputs):
        if test["stdin"] in by_input and not compare_stdin(by_input[test["stdin"]], output, case_insensitive=insensitive):
            raise ValueError("Inconsistent compiled outputs for duplicate input")
        by_input[test["stdin"]] = output
    checks["stale_rejected"] = any(
        test["stdin"] in by_input and not compare_stdin(by_input[test["stdin"]], test["stdout"],
                                                       case_insensitive=new.get("case_insensitive", False))
        for test in new["tests"])
    reference = new["reference_solution"]
    if not isinstance(reference, str):
        raise ValueError("Updated Python reference is missing")
    checks["updated_reference"] = grade("updated", reference)["status"] == "correct"
    checks["updated_equivalent"] = grade("updated", "\n" + reference + "\n")["status"] == "correct"
    checks["updated_wrong_rejected"] = grade("updated", "raise RuntimeError('deliberately wrong')")["status"] != "correct"
    checks["changed_behavior"] = grade("original", reference)["status"] != "correct"
    return checks
