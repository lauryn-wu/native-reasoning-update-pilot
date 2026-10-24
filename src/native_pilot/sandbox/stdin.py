"""Batch stdin invocations in Docker; compare authoritative answers on the host.

Each invocation is a fresh isolated Python subprocess. The container receives
only candidate source and input strings, never expected outputs or a checker.
"""
from __future__ import annotations

import json


def compare_stdin(actual: str, expected: str, *, case_insensitive=False) -> bool:
    """The shared authoritative comparison for candidates and offline gold."""
    if not isinstance(actual, str) or not isinstance(expected, str) or type(case_insensitive) is not bool:
        raise ValueError("Text outputs and an explicit boolean case flag are required")
    actual, expected = " ".join(actual.split()), " ".join(expected.split())
    if case_insensitive:
        actual, expected = actual.casefold(), expected.casefold()
    return actual == expected


def invocation_program(code: str, *, case_timeout: float, output_limit: int) -> str:
    # This string is executable only within Docker. The read-only mount carries
    # both harness and candidate; no mutable program file is shared by cases.
    return f'''import json, os, signal, subprocess, sys, tempfile, threading, time
_SOURCE = {code!r}
if len(sys.argv) == 2 and sys.argv[1] == "--case":
    sys.argv = ["/submission/main.py"]
    exec(compile(_SOURCE, "<submission>", "exec"), {{"__name__": "__main__", "__file__": "/submission/main.py"}})
    raise SystemExit(0)
_INPUTS = json.loads(sys.stdin.read())
_RESULTS = []
for _text in _INPUTS:
    with tempfile.TemporaryDirectory(prefix="case-", dir="/tmp") as _cwd:
        _process = subprocess.Popen([sys.executable, "-I", "-B", "/submission/main.py", "--case"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=_cwd, start_new_session=True)
        _buffers = {{"stdout": bytearray(), "stderr": bytearray()}}
        _exceeded = threading.Event()
        def _drain(stream, key, buffers=_buffers, exceeded=_exceeded):
            while True:
                chunk = stream.read(8192)
                if not chunk: break
                remaining = {output_limit} - len(buffers[key])
                buffers[key].extend(chunk[:max(0, remaining)])
                if len(chunk) > remaining: exceeded.set()
        def _feed(process=_process, text=_text):
            try:
                process.stdin.write(text.encode())
                process.stdin.close()
            except (BrokenPipeError, OSError): pass
        _workers = [threading.Thread(target=_drain, args=(_process.stdout, "stdout"), daemon=True),
                    threading.Thread(target=_drain, args=(_process.stderr, "stderr"), daemon=True),
                    threading.Thread(target=_feed, daemon=True)]
        for _worker in _workers: _worker.start()
        _deadline = time.monotonic() + {case_timeout!r}
        _status = "completed"
        while _process.poll() is None:
            if _exceeded.is_set():
                _status = "output_limit"; break
            if time.monotonic() >= _deadline:
                _status = "timeout"; break
            time.sleep(0.005)
        # Remove descendants too, including a child that outlives its parent.
        try: os.killpg(_process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        _process.wait(timeout=1)
        for _worker in _workers: _worker.join(timeout=0.2)
        if _exceeded.is_set(): _status = "output_limit"
        _RESULTS.append({{"stdout": _buffers["stdout"].decode("utf-8", errors="replace"),
                         "status": _status, "returncode": _process.returncode}})
sys.stdout.write(json.dumps(_RESULTS, ensure_ascii=False, separators=(",", ":")))
'''


def evaluate_stdin(sandbox, code, tests, *, case_insensitive=False):
    if not isinstance(tests, list) or not tests or len(tests) > 10_000:
        raise ValueError("Nonempty stdin suite of at most 10000 tests required")
    batches, batch = [], []
    input_bytes, expected_bytes = 2, 2
    for test in tests:
        if not isinstance(test, dict) or not isinstance(test.get("stdin"), str) or not isinstance(test.get("stdout"), str):
            raise ValueError("Only plain-text stdin/stdout test format is qualified")
        size = len(json.dumps(test["stdin"], ensure_ascii=False).encode()) + 1
        expected_size = len(json.dumps(test["stdout"], ensure_ascii=False).encode()) + 100
        if size > 3_900_000 or expected_size > sandbox.output_limit - 100:
            raise ValueError("Individual authoritative test exceeds qualified sandbox I/O bounds")
        if batch and (len(batch) >= 8 or input_bytes + size > 2_500_000
                      or expected_bytes + expected_size > sandbox.output_limit // 2):
            batches.append(batch)
            batch, input_bytes, expected_bytes = [], 2, 2
        batch.append(test)
        input_bytes += size
        expected_bytes += expected_size
    if batch:
        batches.append(batch)
    program = invocation_program(code, case_timeout=sandbox.timeout, output_limit=sandbox.output_limit)
    invocations = 0

    def invoke(group):
        nonlocal invocations
        invocations += 1
        inputs = json.dumps([test["stdin"] for test in group], ensure_ascii=False, separators=(",", ":"))
        raw = sandbox.run(program, inputs, timeout=min(60, sandbox.timeout * len(group) + 1))
        failure = {"passed": False, "status": raw["status"], "returncode": raw["returncode"]}
        if raw["status"] != "completed" or raw["returncode"] != 0:
            # A batch's aggregate resource deadline must not shorten the
            # promised per-case deadline. Isolate each case on batch failure.
            if len(group) > 1:
                return [item for test in group for item in invoke([test])]
            return [failure]
        try:
            answers = json.loads(raw["stdout"])
            if not isinstance(answers, list) or len(answers) != len(group):
                raise ValueError("Wrong result count")
            for answer in answers:
                if (not isinstance(answer, dict) or set(answer) != {"stdout", "status", "returncode"}
                        or not isinstance(answer["stdout"], str)
                        or answer["status"] not in {"completed", "timeout", "output_limit"}
                        or type(answer["returncode"]) is not int):
                    raise ValueError("Invalid subprocess result")
        except (ValueError, TypeError, RecursionError):
            if len(group) > 1:
                return [item for test in group for item in invoke([test])]
            return [{**failure, "status": "invalid_stdin_output"}]
        results = []
        for answer, test in zip(answers, group):
            results.append({"passed": answer["status"] == "completed" and answer["returncode"] == 0
                            and compare_stdin(answer["stdout"], test["stdout"], case_insensitive=case_insensitive),
                            "status": answer["status"], "returncode": answer["returncode"]})
        return results

    results = [result for batch in batches for result in invoke(batch)]
    return {"passed": all(result["passed"] for result in results), "results": results,
            "mode": "stdin", "container_batches": invocations}
