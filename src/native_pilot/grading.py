"""Exact, non-executing math parsing and externally adjudicated coding grades.

Released benchmark evaluation code is deliberately not imported: it executes
Python on the host and its mathematical number extraction is too permissive.
"""
from __future__ import annotations

import ast
import re
from fractions import Fraction
from typing import Any


RETURNED_GRADES = {
    "correct", "incorrect", "old_answer_match", "truncated_no_answer", "invalid_output"
}


class InvalidAnswer(ValueError):
    pass


def _boxed_answers(text: str) -> list[str]:
    answers = []
    cursor = 0
    while True:
        match = re.search(r"\\(?:boxed|fbox)\s*\{", text[cursor:])
        if match is None:
            return answers
        start = cursor + match.end()
        depth = 1
        end = start
        while end < len(text) and depth:
            depth += (text[end] == "{") - (text[end] == "}")
            end += 1
        if depth:
            raise InvalidAnswer("Unclosed final answer box")
        answers.append(text[start:end - 1])
        cursor = end


def exact_answer(text: str) -> Fraction:
    """Accept a final box, final explicit answer line, or standalone rational.

    Never searches arbitrary prose for a matching number. All arithmetic is
    bounded exact rational arithmetic. No eval, sympify, or user function calls.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > 1_000_000:
        raise InvalidAnswer("Missing or oversized answer")
    boxes = _boxed_answers(text)
    if boxes:
        expression = boxes[-1]
    else:
        expression = text.strip()
        last_line = expression.splitlines()[-1].strip()
        explicit = re.fullmatch(r"(?:final\s+)?answer\s*(?:is\s+|:\s*|=\s*)(.+)", last_line, re.I)
        if explicit:
            expression = explicit.group(1)
    expression = expression.strip().strip("$").strip()
    expression = expression.replace(r"\left", "").replace(r"\right", "")
    expression = expression.replace(r"\,", "").replace(r"\dfrac", r"\frac")
    # Bounded simple LaTeX fractions, including successive nested reductions.
    for _ in range(12):
        updated = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"((\1)/(\2))", expression)
        if updated == expression:
            break
        expression = updated
    expression = expression.replace("^", "**").strip()
    if re.fullmatch(r"[+-]?\d+", expression) and len(expression) <= 100:
        expression = str(int(expression))
    if len(expression) > 256 or not re.fullmatch(r"[0-9eE+*/().\s-]+", expression):
        raise InvalidAnswer("Final answer is not a supported exact rational")
    # Decimal tokens are parsed from source text, not binary floating point.
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise InvalidAnswer("Invalid arithmetic") from exc
    if sum(1 for _ in ast.walk(tree)) > 80:
        raise InvalidAnswer("Expression too complex")

    def value(node: ast.AST) -> Fraction:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            token = ast.get_source_segment(expression, node)
            if token is None or len(token) > 100:
                raise InvalidAnswer("Numeric token too long")
            exp = re.search(r"[eE]([+-]?\d+)", token)
            if exp and abs(int(exp.group(1))) > 100:
                raise InvalidAnswer("Decimal exponent too large")
            try:
                result = Fraction(token)
            except (ValueError, OverflowError) as exc:
                raise InvalidAnswer("Invalid numeric literal") from exc
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = value(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp):
            left, right = value(node.left), value(node.right)
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            elif isinstance(node.op, ast.Div) and right:
                result = left / right
            elif isinstance(node.op, ast.Pow) and right.denominator == 1 and abs(right) <= 20:
                if not left and right < 0:
                    raise InvalidAnswer("Zero to negative power")
                result = left ** int(right)
            else:
                raise InvalidAnswer("Unsupported arithmetic")
        else:
            raise InvalidAnswer("Unsupported expression")
        if max(result.numerator.bit_length(), result.denominator.bit_length()) > 4096:
            raise InvalidAnswer("Arithmetic too large")
        return result

    return value(tree.body)


def extract_python(text: str) -> str:
    if not isinstance(text, str) or not text.strip() or len(text.encode()) > 512_000:
        raise InvalidAnswer("Missing or oversized program")
    blocks = re.findall(r"```([^\n`]*)\n(.*?)```", text, re.S)
    if blocks:
        if len(blocks) != 1 or blocks[0][0].strip().lower() not in ("", "python", "python3", "py"):
            raise InvalidAnswer("Expected exactly one Python code block")
        code = blocks[0][1]
    elif "```" in text:
        raise InvalidAnswer("Unclosed code fence")
    else:
        code = text
    try:
        ast.parse(code)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise InvalidAnswer("Invalid Python syntax") from exc
    return code


def grade_response(task: dict[str, Any], variant: str, text: str,
                   response_status: str = "completed", *, sandbox=None) -> dict[str, Any]:
    """Grade only returned responses; provider/protocol failures belong upstream.

    Coding tests support stdin/stdout and explicitly named Python functions. Missing grading
    assets fail closed; test pass/fail is determined outside the container.
    """
    if variant not in ("original", "updated"):
        raise ValueError("variant must be original or updated")
    if response_status in ("incomplete", "truncated", "max_output_tokens") or not text.strip():
        return {"status": "truncated_no_answer", "correct": False}
    if response_status != "completed":
        raise ValueError("Provider and protocol failures cannot be graded")
    spec = task.get(variant, {})
    domain = task.get("domain")
    if domain == "math":
        if "answer" not in spec:
            raise ValueError("Missing authoritative math answer")
        from .exact_math import parse_exact, exact_equal
        expected = parse_exact(str(spec["answer"]))
        try:
            answer = parse_exact(text)
        except InvalidAnswer as exc:
            return {"status": "invalid_output", "correct": False, "detail": str(exc)}
        status = "correct" if exact_equal(answer, expected) else "incorrect"
        if status == "incorrect" and variant == "updated" and "answer" in task.get("original", {}):
            old = parse_exact(str(task["original"]["answer"]))
            if not exact_equal(old, expected) and exact_equal(answer, old):
                status = "old_answer_match"
        return {"status": status, "correct": status == "correct", "parsed_answer": str(answer)}
    if domain != "coding":
        raise ValueError("Unknown domain")
    tests = spec.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("Missing authoritative coding tests")
    try:
        code = extract_python(text)
    except InvalidAnswer as exc:
        return {"status": "invalid_output", "correct": False, "detail": str(exc)}
    if sandbox is None:
        from .sandbox import DockerSandbox
        sandbox = DockerSandbox(timeout=task.get("timeout_seconds", 5.0),
                                memory_mb=task.get("memory_mb",256),
                                output_limit=task.get("output_limit",1_000_000))

    def evaluate_variant(which):
        grading_spec = task[which]
        if grading_spec.get("mode", "stdin") == "stdin":
            if grading_spec.get("case_insensitive") is True:
                return sandbox.evaluate(code, grading_spec["tests"], case_insensitive=True)
            return sandbox.evaluate(code, grading_spec["tests"])
        return sandbox.evaluate(code, grading_spec["tests"], mode=grading_spec["mode"],
                                entrypoint=grading_spec.get("entrypoint"))

    result = evaluate_variant(variant)
    status = "correct" if result["passed"] else "incorrect"
    old_result = None
    if status != "correct" and variant == "updated" and task.get("original", {}).get("tests"):
        old_result = evaluate_variant("original")
        if old_result["passed"]:
            status = "old_answer_match"
    return {"status": status, "correct": status == "correct", "tests": result,
            "old_tests": old_result}


def validate_reference_workers(workers: int) -> int:
    """Bound offline task concurrency independently of candidate limits."""
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("reference workers must be an integer from 1 to 4")
    return workers


def qualify_references(tasks: list[dict], *, sandbox=None, progress=None,
                       workers: int = 1) -> dict:
    """Run each full serial task checker, optionally across bounded threads.

    A caller-owned sandbox cannot be shared across concurrent tasks. Individual
    grading calls retain their normal Docker construction and resource limits.
    Results, including blockers and execution evidence, follow input order even
    when tasks complete out of order. Progress callbacks run on worker threads.
    """
    validate_reference_workers(workers)
    if workers > 1 and sandbox is not None:
        raise ValueError("parallel reference qualification cannot share a caller sandbox")
    if workers == 1 or not tasks:
        result = _qualify_references_serial(tasks, sandbox=sandbox, progress=progress)
    else:
        from concurrent.futures import ThreadPoolExecutor

        def check(task):
            return _qualify_references_serial([task], progress=progress)

        # map yields in input order and propagates unexpected worker failures;
        # expected grading failures remain blocked results from the same checker.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(check, tasks))
        result = {"checks": {}, "blockers": [], "reference_methods": {},
                  "reference_executions": {}}
        ids = [task.get("task_id") for task in tasks]
        if None in ids or len(set(ids)) != len(ids):
            result["blockers"].append("Missing or duplicate task IDs")
        for item in results:
            for key in ("checks", "reference_methods", "reference_executions"):
                result[key].update(item[key])
            result["blockers"].extend(item["blockers"])
        result["passed"] = all(item["passed"] is True for item in results) and not result["blockers"]
        result["status"] = "passed" if result["passed"] else "blocked"
    result["reference_workers"] = workers
    return result


def _qualify_references_serial(tasks: list[dict], *, sandbox=None, progress=None) -> dict:
    """Validate both authoritative variants; missing assets always block.

    This function does not establish provenance or resolve ambiguous updates.
    Those are independent source-audit gates. All coding execution uses Docker.
    """
    checks, blockers = {}, []
    reference_methods, reference_executions = {}, {}
    if not tasks:
        blockers.append("No source-qualified tasks with original and updated grading assets")
    ids = [task.get("task_id") for task in tasks]
    if None in ids or len(set(ids)) != len(ids):
        blockers.append("Missing or duplicate task IDs")
    for task in tasks:
        task_id = task.get("task_id", "unknown")
        if progress is not None:
            progress(task_id)
        task_checks = {}
        try:
            if task.get("domain") == "math":
                from .exact_math import parse_exact, exact_equal
                old = parse_exact(str(task["original"]["answer"]))
                new = parse_exact(str(task["updated"]["answer"]))
                task_checks["changed_answer"] = not exact_equal(old,new)
                for variant, answer in (("original", old), ("updated", new)):
                    task_checks[variant + "_reference"] = grade_response(task, variant, str(answer))["status"] == "correct"
                    equiv = f"(({answer})*2)/2"
                    task_checks[variant + "_equivalent"] = grade_response(task, variant, equiv)["status"] == "correct"
                    task_checks[variant + "_wrong_rejected"] = grade_response(task, variant, str(answer + 1))["status"] != "correct"
                task_checks["stale_rejected"] = grade_response(task, "updated", str(old))["status"] == "old_answer_match"
            elif task.get("domain") == "coding":
                if task.get("original", {}).get("offline_reference"):
                    from .gold_qualification import qualify_compiled_gold
                    reference_methods[task_id] = {"original": "compiled_gold_v1_offline_replay",
                                                  "updated": "python_candidate_sandbox"}
                    reference_executions[task_id] = []
                    task_checks = qualify_compiled_gold(task, lambda variant, reference:
                        grade_response(task, variant, reference, sandbox=sandbox),
                        execution_records=reference_executions[task_id])
                else:
                    for variant in ("original", "updated"):
                        reference = task[variant]["reference_solution"]
                        task_checks[variant + "_reference"] = grade_response(task, variant, reference, sandbox=sandbox)["status"] == "correct"
                        task_checks[variant + "_wrong_rejected"] = grade_response(task, variant, "raise RuntimeError('deliberately wrong')", sandbox=sandbox)["status"] != "correct"
                        # Source-preserving whitespace is an equivalent program;
                        # output-whitespace equivalence is separately unit-tested.
                        task_checks[variant + "_equivalent"] = grade_response(task, variant, "\n" + reference + "\n", sandbox=sandbox)["status"] == "correct"
                    task_checks["stale_rejected"] = grade_response(task, "updated", task["original"]["reference_solution"], sandbox=sandbox)["status"] == "old_answer_match"
                    task_checks["changed_behavior"] = not grade_response(task, "original", task["updated"]["reference_solution"], sandbox=sandbox)["correct"]
            else:
                raise ValueError("Unknown domain")
            if not task_checks or not all(task_checks.values()):
                blockers.append(f"{task_id}: reference or update checks failed")
        except (KeyError, ValueError, RuntimeError) as exc:
            blockers.append(f"{task_id}: missing or unqualified grading assets ({exc})")
        checks[task_id] = task_checks
    return {"passed": bool(tasks) and not blockers, "status": "passed" if tasks and not blockers else "blocked",
            "checks": checks, "blockers": blockers, "reference_methods": reference_methods,
            "reference_executions": reference_executions}
