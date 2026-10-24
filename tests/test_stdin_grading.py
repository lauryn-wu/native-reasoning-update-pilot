import io
import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from native_pilot.sandbox import DockerSandbox
from native_pilot.sandbox.stdin import evaluate_stdin, invocation_program


class StdinGradingTests(unittest.TestCase):
    def raw(self, answers):
        return {"status": "completed", "returncode": 0, "stdout": json.dumps(answers), "stderr": ""}

    def answer(self, stdout, **changes):
        return {"status": "completed", "returncode": 0, "stdout": stdout, **changes}

    def test_only_inputs_enter_docker_and_all_cases_retained(self):
        box = DockerSandbox()
        tests = [{"stdin": str(i), "stdout": f"SECRET_EXPECTED_{i}"} for i in range(19)]
        seen = []

        def run(program, inputs, **kwargs):
            self.assertNotIn("SECRET_EXPECTED", program + inputs)
            self.assertIn("start_new_session=True", program)
            self.assertIn('"-I", "-B"', program)
            group = json.loads(inputs)
            self.assertLessEqual(len(group), 8)
            seen.extend(group)
            return self.raw([self.answer(f"SECRET_EXPECTED_{i}") for i in group])

        with patch.object(box, "run", side_effect=run):
            result = evaluate_stdin(box, "pass", tests)
        self.assertTrue(result["passed"])
        self.assertEqual(seen, [str(i) for i in range(19)])
        self.assertEqual(result["container_batches"], 3)
        self.assertEqual(len(result["results"]), 19)

    def test_batch_failure_retries_each_case_with_full_deadline(self):
        box = DockerSandbox(timeout=40)
        tests = [{"stdin": str(i), "stdout": str(i)} for i in range(2)]
        calls = []

        def run(program, inputs, **kwargs):
            group = json.loads(inputs)
            calls.append((len(group), kwargs["timeout"]))
            if len(group) == 2:
                return {"status": "timeout", "returncode": 137, "stdout": "", "stderr": ""}
            return self.raw([self.answer(group[0])])

        with patch.object(box, "run", side_effect=run):
            self.assertTrue(evaluate_stdin(box, "pass", tests)["passed"])
        self.assertEqual(calls, [(2, 60), (1, 41), (1, 41)])

    def test_status_and_exit_code_cannot_self_assert_pass(self):
        box = DockerSandbox()
        tests = [{"stdin": "", "stdout": "42"}]
        for answer in [self.answer("42", returncode=1), self.answer("42", status="timeout"),
                       self.answer("42", returncode=False), {"passed": True}, self.answer("42", status="correct")]:
            with self.subTest(answer=answer), patch.object(box, "run", return_value=self.raw([answer])):
                self.assertFalse(evaluate_stdin(box, "pass", tests)["passed"])

    def test_source_is_not_executed_on_host(self):
        source = "raise RuntimeError('Docker only')"
        with patch("builtins.exec", side_effect=AssertionError("no host exec")):
            self.assertIn(source, invocation_program(source, case_timeout=1, output_limit=2048))

    def test_extended_bound_preserves_large_real_suite(self):
        box = DockerSandbox()
        tests = [{"stdin": "x", "stdout": "x"} for _ in range(1043)]
        with patch.object(box, "run", side_effect=lambda program, inputs, **kw: self.raw([self.answer(x) for x in json.loads(inputs)])):
            result = evaluate_stdin(box, "pass", tests)
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["results"]), 1043)
        with self.assertRaises(ValueError):
            evaluate_stdin(box, "pass", tests * 10)

    def test_unresponsive_cleanup_still_terminates_client(self):
        from native_pilot.sandbox import SandboxUnavailable
        process = MagicMock()
        process.stdin, process.stdout, process.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
        process.poll.return_value = None
        process.returncode = 137
        with patch("subprocess.Popen", return_value=process), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("docker rm", 15)), \
             patch("native_pilot.sandbox.runner.time.monotonic", side_effect=[0, 10]):
            with self.assertRaises(SandboxUnavailable):
                DockerSandbox(timeout=1).run("pass", "")
        process.kill.assert_called_once()

    def test_client_deadline_is_infrastructure_even_with_correct_buffered_output(self):
        from native_pilot.sandbox import SandboxUnavailable
        process = MagicMock()
        process.stdin, process.stdout, process.stderr = io.BytesIO(), io.BytesIO(b"42\n"), io.BytesIO()
        process.poll.return_value = None
        process.returncode = 0
        cleanup = subprocess.CompletedProcess(["docker", "rm"], 0)
        with patch("subprocess.Popen", return_value=process), \
             patch("subprocess.run", return_value=cleanup) as remove, \
             patch("native_pilot.sandbox.runner.time.monotonic", side_effect=[0, 10]):
            with self.assertRaisesRegex(SandboxUnavailable, "Docker client exceeded"):
                DockerSandbox(timeout=1).run("print(42)", "")
        process.kill.assert_called_once()
        self.assertEqual(remove.call_args.args[0][1:3], ["rm", "-f"])

    def test_container_deadline_exit_remains_a_candidate_execution_failure(self):
        for code in (124, 137):
            with self.subTest(returncode=code):
                process = MagicMock()
                process.stdin, process.stdout, process.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
                process.poll.return_value = code
                process.returncode = code
                with patch("subprocess.Popen", return_value=process), patch("subprocess.run") as remove:
                    result = DockerSandbox(timeout=1).run("while True: pass", "")
                self.assertEqual(result["status"], "timeout_or_resource_limit")
                self.assertEqual(result["returncode"], code)
                remove.assert_not_called()

    def test_infrastructure_deadline_is_not_retried_or_scored_as_wrong(self):
        from native_pilot.sandbox import SandboxUnavailable
        box = DockerSandbox()
        with patch.object(box, "run", side_effect=SandboxUnavailable("Docker client exceeded")) as run:
            with self.assertRaises(SandboxUnavailable):
                evaluate_stdin(box, "pass", [{"stdin": "", "stdout": "42"}] * 2)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
