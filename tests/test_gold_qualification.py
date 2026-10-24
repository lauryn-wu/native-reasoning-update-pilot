import copy
import unittest
from unittest.mock import Mock, patch

from native_pilot.gold_qualification import qualify_compiled_gold
from native_pilot.grading import qualify_references
from native_pilot.sandbox import DockerSandbox, SandboxUnavailable
from native_pilot.sandbox.stdin import compare_stdin


class CompiledGoldQualificationTests(unittest.TestCase):
    def setUp(self):
        self.task = {
            "task_id": "software:compiled-gold", "domain": "coding", "timeout_seconds": 60,
            "original": {"mode": "stdin", "offline_reference": {"kind": "compiled_gold_v1"},
                         "tests": [{"stdin": "shared", "stdout": "1\n"},
                                   {"stdin": "initial-only signed fixture", "stdout": "2\n"}]},
            "updated": {"mode": "stdin", "reference_solution": "print('updated reference')",
                        "tests": [{"stdin": "shared", "stdout": "9\n"},
                                  {"stdin": "updated-only translated fixture", "stdout": "10\n"}]}}
        self.replay = {"passed": True, "outputs": ["1", "2"], "execution": {"source_sha256": "bound-by-offline-loader"}}
        self.required = {"original_reference", "original_equivalent", "original_wrong_rejected",
                         "updated_reference", "updated_equivalent", "updated_wrong_rejected",
                         "stale_rejected", "changed_behavior"}

    @staticmethod
    def grade(variant, source):
        correct = variant == "updated" and "deliberately wrong" not in source
        return {"status": "correct" if correct else "incorrect", "correct": correct}

    def test_compiled_gold_is_replayed_and_python_stays_in_candidate_grader(self):
        grade = Mock(side_effect=self.grade)
        executions = []
        with patch("native_pilot.gold_qualification._replay", return_value=self.replay) as replay:
            checks = qualify_compiled_gold(self.task, grade, execution_records=executions)
        self.assertEqual(set(checks), self.required)
        self.assertTrue(all(value is True for value in checks.values()))
        replay.assert_called_once_with(self.task["original"], self.task["original"]["tests"])
        self.assertEqual([call.args[0] for call in grade.call_args_list], ["updated", "updated", "updated", "original"])
        self.assertEqual(executions, [self.replay["execution"]])
        self.assertNotIn("reference_solution", self.task["original"])

    def test_shared_comparator_keeps_whitespace_but_rejects_numeric_changes(self):
        self.assertTrue(compare_stdin(" \t1\n 2 ", "1 2"))
        self.assertFalse(compare_stdin("1.0", "1"))
        self.assertFalse(compare_stdin("true", "True"))
        self.assertTrue(compare_stdin("fEnNeC", "Fennec", case_insensitive=True))
        replay = dict(self.replay, outputs=["\n1 \t", " 2\n"])
        with patch("native_pilot.gold_qualification._replay", return_value=replay):
            self.assertTrue(all(qualify_compiled_gold(self.task, self.grade).values()))
        replay = dict(self.replay, outputs=["1.0", "2"])
        with patch("native_pilot.gold_qualification._replay", return_value=replay):
            self.assertFalse(qualify_compiled_gold(self.task, self.grade)["original_reference"])

    def test_all_original_cases_are_required_even_when_only_one_is_shared(self):
        for outputs in [["1"], ["1", 2], ["1", "2", "3"]]:
            with self.subTest(outputs=outputs), patch("native_pilot.gold_qualification._replay", return_value=dict(self.replay, outputs=outputs)):
                with self.assertRaises(ValueError):
                    qualify_compiled_gold(self.task, self.grade)
        task = copy.deepcopy(self.task)
        task["updated"]["tests"][0]["stdin"] = "no shared input"
        with patch("native_pilot.gold_qualification._replay", return_value=self.replay):
            self.assertFalse(qualify_compiled_gold(task, self.grade)["stale_rejected"])

    def test_failed_or_unavailable_replay_cannot_be_promoted_to_a_pass(self):
        grade = Mock(side_effect=self.grade)
        with patch("native_pilot.gold_qualification._replay", return_value={"passed": False}):
            self.assertEqual(qualify_compiled_gold(self.task, grade), {"original_reference": False})
        grade.assert_not_called()
        with patch("native_pilot.gold_qualification._replay", side_effect=SandboxUnavailable("compiler unavailable")):
            result = qualify_references([self.task])
        self.assertFalse(result["passed"])
        self.assertIn("compiler unavailable", result["blockers"][0])

    def test_integrated_result_labels_offline_method_and_preserves_sandbox(self):
        box = DockerSandbox(timeout=60)
        def grade(task, variant, source, **kwargs):
            self.assertIs(kwargs["sandbox"], box)
            return self.grade(variant, source)
        with patch("native_pilot.gold_qualification._replay", return_value=self.replay), \
             patch("native_pilot.grading.grade_response", side_effect=grade):
            result = qualify_references([self.task], sandbox=box)
        self.assertTrue(result["passed"])
        self.assertEqual(result["reference_methods"][self.task["task_id"]]["original"], "compiled_gold_v1_offline_replay")
        self.assertEqual(result["reference_executions"][self.task["task_id"]], [self.replay["execution"]])
        self.assertEqual(box.timeout, 60)


if __name__ == "__main__":
    unittest.main()
