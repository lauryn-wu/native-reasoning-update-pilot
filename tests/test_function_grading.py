import json
import unittest
from unittest.mock import patch

from native_pilot.grading import grade_response
from native_pilot.sandbox import DockerSandbox
from native_pilot.sandbox.function import evaluate_function, exact_json_equal, invocation_program


class FunctionGradingTests(unittest.TestCase):
    def setUp(self):
        self.box = DockerSandbox()
        self.entry = {"class": "Solution", "method": "double"}
        self.tests = [{"args": [3], "expected": 6}, {"args": [4], "expected": 8}]

    def raw(self, text):
        return {"status": "completed", "returncode": 0, "stdout": text, "stderr": ""}

    def test_expected_answers_never_enter_docker(self):
        secret = "AUTHORITATIVE_EXPECTATION_NEVER_IN_CONTAINER"
        tests = [{"args": [3], "expected": secret}]
        with patch.object(self.box, "run", return_value=self.raw(json.dumps([secret]))) as run:
            self.assertTrue(evaluate_function(self.box, "class Solution: pass", tests, self.entry)["passed"])
            program, stdin = run.call_args.args
            self.assertNotIn(secret, program)
            self.assertNotIn(secret, stdin)
            self.assertEqual(json.loads(stdin), [[3]])

    def test_exact_numeric_and_nested_comparison(self):
        self.assertTrue(exact_json_equal([6.0, {"x": 8}], [6, {"x": 8}]))
        self.assertFalse(exact_json_equal(True, 1))
        self.assertFalse(exact_json_equal([1], [True]))
        self.assertFalse(exact_json_equal(6.00000001, 6))
        self.assertFalse(exact_json_equal("6", 6))
        with patch.object(self.box, "run", return_value=self.raw("[6,8]")):
            self.assertTrue(evaluate_function(self.box, "pass", self.tests, self.entry)["passed"])
        with patch.object(self.box, "run", return_value=self.raw("[6,9]")):
            result = evaluate_function(self.box, "pass", self.tests, self.entry)
            self.assertFalse(result["passed"])
            self.assertEqual([r["passed"] for r in result["results"]], [True, False])

    def test_invalid_output_and_self_asserted_pass_are_rejected(self):
        for text in ["PASS", '{"passed":true}', "[6]", "[6,8,10]", "[NaN,8]", "debug\n[6,8]"]:
            with self.subTest(text=text), patch.object(self.box, "run", return_value=self.raw(text)):
                self.assertFalse(evaluate_function(self.box, "pass", self.tests, self.entry)["passed"])

    def test_entrypoint_cannot_inject_wrapper(self):
        for entry in [{"class": "Solution", "method": "x); malicious()"}, {"function": "__import__"},
                      {"class": "Solution"}, {"function": "f", "extra": "g"}]:
            with self.assertRaises(ValueError):
                invocation_program("pass", entry)

    def test_no_host_execution_when_constructing_program(self):
        code = "raise RuntimeError('must only run inside Docker')"
        with patch("builtins.exec", side_effect=AssertionError("host exec forbidden")):
            self.assertIn(code, invocation_program(code, self.entry))

    def test_function_grade_uses_variant_method_and_reordered_args(self):
        task = {"domain": "coding", "original": {"mode": "function", "entrypoint": {"class": "Solution", "method": "old"}, "tests": [{"args": [2, 3], "expected": 5}]},
                "updated": {"mode": "function", "entrypoint": {"class": "Solution", "method": "new"}, "tests": [{"args": [3, 2], "expected": 5}]}}
        with patch.object(self.box, "evaluate", side_effect=[{"passed": False}, {"passed": True}]) as evaluate:
            result = grade_response(task, "updated", "class Solution: pass", sandbox=self.box)
            self.assertEqual(result["status"], "old_answer_match")
            self.assertEqual(evaluate.call_args_list[0].kwargs["entrypoint"]["method"], "new")
            self.assertEqual(evaluate.call_args_list[1].kwargs["entrypoint"]["method"], "old")

    def test_chunking_keeps_every_case_and_order(self):
        tests = [{"args": [i], "expected": i} for i in range(19)]
        seen = []

        def fake_run(program, stdin):
            arguments = json.loads(stdin)
            seen.extend(args[0] for args in arguments)
            return self.raw(json.dumps([args[0] for args in arguments]))

        with patch.object(self.box, "run", side_effect=fake_run):
            result = evaluate_function(self.box, "pass", tests, self.entry)
        self.assertTrue(result["passed"])
        self.assertEqual(seen, list(range(19)))
        self.assertEqual(len(result["results"]), 19)
        self.assertGreater(result["container_batches"], 1)


if __name__ == "__main__":
    unittest.main()
