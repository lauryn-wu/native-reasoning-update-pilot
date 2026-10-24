import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from native_pilot.grading import InvalidAnswer, exact_answer, extract_python, grade_response, qualify_references
from native_pilot.sandbox import DEFAULT_IMAGE, DockerSandbox, SandboxUnavailable
from native_pilot.sandbox.runner import normalize_output


class MathGradingTests(unittest.TestCase):
    def setUp(self):
        self.task = {"task_id": "software-only", "domain": "math", "original": {"answer": "42"}, "updated": {"answer": "21"}}

    def test_equivalent_exact_answers(self):
        for answer in ["21", "021", "21.000", "42/2", r"\boxed{\frac{42}{2}}", "Work: 999\nFinal answer: 21", r"Earlier \boxed{42} corrected to \boxed{21}"]:
            with self.subTest(answer=answer):
                self.assertEqual(grade_response(self.task, "updated", answer)["status"], "correct")
        self.assertEqual(exact_answer("0.1 + 0.2"), Fraction(3, 10))

    def test_wrong_stale_and_invalid_distinct(self):
        self.assertEqual(grade_response(self.task, "updated", "42")["status"], "old_answer_match")
        self.assertEqual(grade_response(self.task, "updated", "41")["status"], "incorrect")
        self.assertEqual(grade_response(self.task, "updated", "We tried 21, but no answer.")["status"], "invalid_output")
        self.assertEqual(grade_response(self.task, "updated", "", "incomplete")["status"], "truncated_no_answer")
        self.assertEqual(grade_response(self.task, "updated", "21", "incomplete")["status"], "truncated_no_answer")
        with self.assertRaises(ValueError):
            grade_response(self.task, "updated", "21", "provider_failure")

    def test_no_permissive_number_extraction(self):
        for text in ["The problem has 21 students", "21 or 42", "[21]", "x=21", "2/21", r"\boxed{42} \boxed{22}"]:
            self.assertNotEqual(grade_response(self.task, "updated", text)["status"], "correct")

    def test_malicious_expression_never_executes(self):
        with patch("builtins.eval", side_effect=AssertionError("eval forbidden")):
            for answer in ["__import__('os').system('true')", "2**999999999", "1e99999999", "1/0", "True", "[21][0]", r"\boxed{21", "(" * 300 + "21"]:
                with self.subTest(answer=answer), self.assertRaises(InvalidAnswer):
                    exact_answer(answer)

    def test_reference_qualification_does_not_fill_missing_source(self):
        self.assertFalse(qualify_references([])["passed"])
        self.assertTrue(qualify_references([self.task])["passed"])
        unchanged = dict(self.task, updated={"answer": "42"})
        self.assertFalse(qualify_references([unchanged])["passed"])
        missing = {"task_id": "missing", "domain": "coding", "original": {}, "updated": {}}
        self.assertFalse(qualify_references([missing])["passed"])


class CodingGradingTests(unittest.TestCase):
    def test_extraction_is_parse_only(self):
        self.assertEqual(extract_python("```python\nprint(1)\n```"), "print(1)\n")
        with self.assertRaises(InvalidAnswer):
            extract_python("```python\nprint(1)\n```\n```python\nprint(2)\n```")
        with self.assertRaises(InvalidAnswer):
            extract_python("not valid Python ^")

    def test_no_host_fallback(self):
        box = DockerSandbox()
        with patch("subprocess.Popen", side_effect=FileNotFoundError("docker absent")):
            with self.assertRaises(SandboxUnavailable):
                box.run("print('must never run on host')", "")

    def test_sandbox_mounts_only_program_and_sets_limits(self):
        with tempfile.TemporaryDirectory() as path:
            command = DockerSandbox().command(Path(path), "qualification")
        for token in ["--read-only", "--network", "none", "65534:65534", "--cap-drop", "ALL",
                      "no-new-privileges", "--cpus", "--memory", "--pids-limit", "--pull=never"]:
            self.assertIn(token, command)
        self.assertEqual(command.count("--mount"), 1)
        self.assertIn("readonly", command[command.index("--mount") + 1])
        self.assertIn(DEFAULT_IMAGE, command)
        self.assertIn("/usr/bin/timeout", command)
        self.assertIn("--signal=KILL", command)
        with self.assertRaises(ValueError):
            DockerSandbox(image="python:latest")

    def test_stdout_exact_comparison_outside_container(self):
        box = DockerSandbox()
        tests = [{"stdin": "3", "stdout": "9\n"}]
        with patch.object(box, "run", return_value={"status": "completed", "returncode": 0, "stdout": " 9 \n", "stderr": ""}):
            self.assertTrue(box.evaluate("arbitrary", tests)["passed"])
        for stdout in ["True", "9.0", "PASS", "9 10", "9e0"]:
            with patch.object(box, "run", return_value={"status": "completed", "returncode": 0, "stdout": stdout, "stderr": ""}):
                self.assertFalse(box.evaluate("arbitrary", tests)["passed"])
        self.assertEqual(normalize_output("a\n b"), "a b")

    def test_stale_coding_requires_passing_original_tests(self):
        task = {"domain": "coding", "original": {"tests": [{"stdin": "3", "stdout": "6"}]},
                "updated": {"tests": [{"stdin": "3", "stdout": "9"}]}}
        box = DockerSandbox()
        with patch.object(box, "evaluate", side_effect=[{"passed": False}, {"passed": True}]):
            self.assertEqual(grade_response(task, "updated", "print(6)", sandbox=box)["status"], "old_answer_match")


if __name__ == "__main__":
    unittest.main()
