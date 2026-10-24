import copy
import itertools
import unittest

from native_pilot.analysis import analyze, bootstrap_interval, sign_flip_pvalue


def campaign():
    tasks, schedule, outcomes = [], [], []
    for i in range(24):
        task_id = f"problem-{i}"
        control = i < 4 or 12 <= i < 16
        tasks.append({"task_id": task_id, "domain": "math" if i < 12 else "coding", "unchanged_control": control})
        conditions = ["initial", "updated_retained", "updated_dropped", "fresh"]
        if control:
            conditions += ["unchanged_retained", "unchanged_dropped"]
        for condition in conditions:
            for sample in range(1 if condition == "initial" else 2):
                call_id = f"{task_id}/{condition}/{sample}"
                schedule.append({"call_id": call_id, "task_id": task_id, "condition": condition, "sample": sample})
                grade = "incorrect" if condition == "updated_retained" and i < 6 else "correct"
                outcomes.append({"call_id": call_id, "status": "completed", "protocol_valid": True, "grade": {"status": grade}})
    return {"tasks": tasks, "schedule": schedule, "source_qualified": True}, outcomes


class StatisticsTests(unittest.TestCase):
    def test_known_exact_sign_flip_examples(self):
        self.assertEqual(sign_flip_pvalue([1, 1, 1, 1]), 1 / 16)
        self.assertEqual(sign_flip_pvalue([1, 0, 0, 0]), 1 / 2)
        self.assertEqual(sign_flip_pvalue([0, 0]), 1)
        self.assertEqual(sign_flip_pvalue([-1, -1]), 1)
        self.assertIsNone(sign_flip_pvalue([]))
        with self.assertRaises(ValueError):
            sign_flip_pvalue([0.25])

    def test_dp_matches_explicit_problem_level_enumeration(self):
        values = [1, -0.5, 0.5, 0, -1, 1]
        expected = sum(sum(s * abs(v) for s, v in zip(signs, values)) >= sum(values)
                       for signs in itertools.product((-1, 1), repeat=len(values))) / 2 ** len(values)
        self.assertEqual(sign_flip_pvalue(values), expected)
        self.assertEqual(bootstrap_interval(values), bootstrap_interval(values))


class AnalysisTests(unittest.TestCase):
    def test_complete_gate_and_task_unit(self):
        manifest, outcomes = campaign()
        result = analyze(manifest, outcomes)
        self.assertEqual(result["required_responses"], 200)
        self.assertTrue(result["continuation_gate_passed"])
        self.assertEqual(result["primary"]["n_problems"], 24)
        self.assertEqual(result["primary"]["dropped_minus_retained"], 0.25)
        self.assertEqual(result["primary"]["one_sided_p"], 1 / 64)
        self.assertEqual(result["unchanged_controls"]["all_preselected"]["n_problems"], 8)

    def test_eligibility_uses_initial_only(self):
        manifest, outcomes = campaign()
        for outcome in outcomes:
            if outcome["call_id"] == "problem-0/initial/0":
                outcome["grade"]["status"] = "incorrect"
        result = analyze(manifest, outcomes)
        self.assertEqual(result["primary"]["n_problems"], 23)
        self.assertEqual(result["secondary"]["n_problems"], 24)
        self.assertAlmostEqual(result["primary"]["dropped_minus_retained"], 5 / 23)
        # Arbitrary post-treatment success changes must not change eligibility.
        changed = copy.deepcopy(outcomes)
        for outcome in changed:
            if "/initial/" not in outcome["call_id"]:
                outcome["grade"]["status"] = "incorrect"
        other = analyze(manifest, changed)
        self.assertEqual([r["task_id"] for r in result["primary"]["per_problem"]],
                         [r["task_id"] for r in other["primary"]["per_problem"]])

    def test_fewer_than_18_inconclusive(self):
        manifest, outcomes = campaign()
        for outcome in outcomes:
            if "/initial/" in outcome["call_id"] and int(outcome["call_id"].split("/")[0].split("-")[1]) >= 17:
                outcome["grade"]["status"] = "incorrect"
        result = analyze(manifest, outcomes)
        self.assertEqual(result["decision"], "inconclusive")
        self.assertFalse(result["continuation_gate_passed"])

    def test_missing_and_protocol_failures_cannot_pass(self):
        manifest, outcomes = campaign()
        result = analyze(manifest, outcomes[:-1])
        self.assertFalse(result["continuation_gate_passed"])
        self.assertIsNone(result["primary"]["fresh_accuracy"])
        outcomes[3]["protocol_valid"] = False
        result = analyze(manifest, outcomes)
        self.assertFalse(result["continuation_gate_passed"])
        self.assertIsNone(result["primary"]["dropped_minus_retained"])

    def test_returned_invalid_and_truncation_count_as_unsuccessful(self):
        manifest, outcomes = campaign()
        for outcome in outcomes:
            if outcome["call_id"] in ("problem-23/updated_dropped/0", "problem-23/updated_dropped/1"):
                outcome["grade"]["status"] = "truncated_no_answer" if outcome["call_id"].endswith("/0") else "invalid_output"
        result = analyze(manifest, outcomes)
        self.assertEqual(result["availability"]["returned_protocol_valid"], 200)
        row = result["primary"]["per_problem"][-1]
        self.assertEqual(row["dropped_accuracy"], 0)
        self.assertEqual(result["returned_classifications"]["truncated_no_answer"], 1)

    def test_dataset_and_shape_blockers_are_enforced(self):
        manifest, outcomes = campaign()
        manifest["source_qualified"] = False
        self.assertFalse(analyze(manifest, outcomes)["continuation_gate_passed"])
        manifest["source_qualified"] = True
        manifest["schedule"][1]["sample"] = manifest["schedule"][2]["sample"]
        self.assertFalse(analyze(manifest, outcomes)["criteria"]["frozen_design_valid"])
        empty = analyze({"tasks": [], "schedule": []}, [])
        self.assertEqual(empty["decision"], "inconclusive")

    def test_duplicate_outcomes_cannot_pass(self):
        manifest, outcomes = campaign()
        self.assertFalse(analyze(manifest, outcomes + [outcomes[0]])["continuation_gate_passed"])

    def test_unexpected_or_unrecognized_outcomes_cannot_pass(self):
        manifest, outcomes = campaign()
        stray = dict(outcomes[0], call_id="unknown-call")
        self.assertFalse(analyze(manifest, outcomes + [stray])["continuation_gate_passed"])
        outcomes[0]["status"] = "unknown_status"
        self.assertFalse(analyze(manifest, outcomes)["continuation_gate_passed"])


if __name__ == "__main__":
    unittest.main()
