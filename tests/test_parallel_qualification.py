import contextlib
import io
import threading
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

from native_pilot.cli import main, qualification
from native_pilot.grading import qualify_references
from native_pilot.sandbox import SandboxUnavailable


class ParallelReferenceTests(unittest.TestCase):
    @staticmethod
    def task(task_id):
        return {
            "task_id": task_id, "domain": "coding", "timeout_seconds": 60,
            "original": {"mode": "stdin", "offline_reference": {
                "kind": "compiled_gold_v1", "label": task_id},
                "tests": [{"stdin": "shared", "stdout": "1"},
                          {"stdin": "all original cases retained", "stdout": "2"}]},
            "updated": {"mode": "stdin", "reference_solution": "print('updated')",
                "tests": [{"stdin": "shared", "stdout": "9"},
                          {"stdin": "all updated cases retained", "stdout": "10"}]} }

    def test_out_of_order_completion_preserves_all_checks_and_evidence_in_input_order(self):
        tasks = [self.task(name) for name in ("slow", "fast", "last")]
        released = threading.Event()
        lock = threading.Lock()
        calls, replays, completions, progress = [], [], [], []

        def replay(spec, tests):
            task_id = spec["offline_reference"]["label"]
            with lock:
                replays.append((task_id, tests))
            if task_id == "slow":
                self.assertTrue(released.wait(5), "A second task must run concurrently")
            return {"passed": True, "outputs": [case["stdout"] for case in tests],
                    "execution": {"task_id": task_id, "cases": len(tests)}}

        def grade(task, variant, source, **kwargs):
            self.assertIsNone(kwargs["sandbox"])
            self.assertEqual(task["timeout_seconds"], 60)
            self.assertEqual(len(task[variant]["tests"]), 2)
            with lock:
                calls.append(task["task_id"])
                if variant == "original":
                    completions.append(task["task_id"])
            if task["task_id"] == "fast" and variant == "original":
                released.set()
            correct = variant == "updated" and "deliberately wrong" not in source
            return {"status": "correct" if correct else "incorrect", "correct": correct}

        with patch("native_pilot.gold_qualification._replay", side_effect=replay), \
             patch("native_pilot.grading.grade_response", side_effect=grade):
            result = qualify_references(tasks, workers=2, progress=progress.append)
        ids = [task["task_id"] for task in tasks]
        self.assertTrue(result["passed"])
        self.assertEqual(result["reference_workers"], 2)
        self.assertEqual(list(result["checks"]), ids)
        self.assertEqual(list(result["reference_methods"]), ids)
        self.assertEqual(list(result["reference_executions"]), ids)
        self.assertEqual(Counter(progress), Counter(ids))
        self.assertEqual(Counter(task_id for task_id, _ in replays), Counter(ids))
        self.assertEqual(Counter(calls), Counter({task_id: 4 for task_id in ids}))
        self.assertLess(completions.index("fast"), completions.index("slow"))
        for task in tasks:
            task_id = task["task_id"]
            self.assertEqual(result["reference_executions"][task_id], [{"task_id": task_id, "cases": 2}])
            self.assertEqual(len(result["checks"][task_id]), 8)
            self.assertTrue(all(result["checks"][task_id].values()))
            self.assertEqual(dict(replays)[task_id], task["original"]["tests"])

    def test_actual_serial_and_parallel_checkers_agree_including_failures(self):
        tasks = [{"task_id": "valid", "domain": "math", "original": {"answer": "5"},
                  "updated": {"answer": "7"}},
                 {"task_id": "unchanged", "domain": "math", "original": {"answer": "8"},
                  "updated": {"answer": "8"}},
                 {"task_id": "missing", "domain": "coding", "original": {}, "updated": {}}]
        serial = qualify_references(tasks)
        parallel = qualify_references(tasks, workers=4)
        self.assertFalse(parallel["passed"])
        self.assertEqual(serial.pop("reference_workers"), 1)
        self.assertEqual(parallel.pop("reference_workers"), 4)
        self.assertEqual(serial, parallel)

    def test_infrastructure_failure_remains_blocked_and_unexpected_failure_propagates(self):
        tasks = [self.task("failed"), self.task("also-failed")]
        with patch("native_pilot.gold_qualification._replay", side_effect=SandboxUnavailable("unavailable")):
            result = qualify_references(tasks, workers=2)
        self.assertFalse(result["passed"])
        self.assertEqual(list(result["checks"]), ["failed", "also-failed"])
        self.assertEqual(len(result["blockers"]), 2)
        self.assertTrue(all("unavailable" in blocker for blocker in result["blockers"]))
        with patch("native_pilot.gold_qualification._replay", side_effect=OSError("unexpected failure")):
            with self.assertRaisesRegex(OSError, "unexpected failure"):
                qualify_references(tasks, workers=2)

    def test_invalid_workers_and_shared_sandbox_rejected_before_checking(self):
        for workers in (0, 5, -1, True, 1.5, "2", None):
            with self.subTest(workers=workers), patch("native_pilot.grading._qualify_references_serial") as serial:
                with self.assertRaises(ValueError):
                    qualify_references([self.task("unused")], workers=workers)
                serial.assert_not_called()
        with self.assertRaisesRegex(ValueError, "cannot share"):
            qualify_references([self.task("unused")], workers=2, sandbox=object())
        self.assertFalse(qualify_references([], workers=4)["passed"])
        duplicate = {"task_id": "same", "domain": "math", "original": {"answer": "1"}, "updated": {"answer": "2"}}
        self.assertFalse(qualify_references([duplicate, duplicate], workers=2)["passed"])


class QualificationWorkersCliTests(unittest.TestCase):
    def test_qualification_forwards_workers_and_records_metadata(self):
        view = {"manifest_sha256": "test", "tasks": [{"task_id": "task"}],
                "smoke_task": {"task_id": "smoke"}}
        source = {"passed": True, "checks": {"task": {}, "smoke": {}}, "reference_workers": 3}
        with patch("native_pilot.cli.implementation_hashes", return_value={}), \
             patch("native_pilot.cli.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")), \
             patch("native_pilot.sandbox.qualify_docker", return_value={"passed": True}), \
             patch("native_pilot.assets.hydrate_tasks", side_effect=lambda tasks, cache: tasks), \
             patch("native_pilot.grading.qualify_references", return_value=source) as checker:
            result = qualification(view, docker=True, workers=3)
        self.assertEqual(checker.call_args.args[0], view["tasks"] + [view["smoke_task"]])
        self.assertEqual(checker.call_args.kwargs["workers"], 3)
        self.assertEqual(result["reference_workers"], 3)
        self.assertIs(result["source_references"], source)
        self.assertTrue(result["source_reference_passed"])

    def test_invalid_workers_rejected_before_offline_commands(self):
        with patch("native_pilot.cli.subprocess.run") as run:
            with self.assertRaises(ValueError):
                qualification({}, workers=0)
        run.assert_not_called()
        for command in ("qualify", "qualify-reviewed"):
            for workers in ("0", "5", "2.5"):
                with self.subTest(command=command, workers=workers), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        main([command, "--workers", workers])
                    self.assertEqual(raised.exception.code, 2)

    def test_both_cli_commands_forward_requested_workers(self):
        outcome = {"offline_passed": True, "docker_passed": True, "source_reference_passed": True,
                   "test_output": "", "manifest_sha256": "test"}
        audit = {"qualified_tasks": [], "status": "qualified"}
        for command in ("qualify", "qualify-reviewed"):
            with self.subTest(command=command), \
                 patch("native_pilot.cli.load_manifest", return_value={"manifest_sha256": "test"}), \
                 patch("native_pilot.cli.read_json", return_value=audit), \
                 patch("native_pilot.cli.file_digest", return_value="test"), \
                 patch("native_pilot.cli.atomic_json"), \
                 patch("native_pilot.cli.show"), \
                 patch("native_pilot.cli.qualification", return_value=dict(outcome)) as qualify, \
                 contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([command, "--docker", "--workers", "4"]), 0)
                self.assertEqual(qualify.call_args.kwargs["workers"], 4)
                self.assertTrue(qualify.call_args.kwargs["docker"])


if __name__ == "__main__":
    unittest.main()
