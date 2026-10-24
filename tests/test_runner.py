"""Synthetic software fixtures; these are never selectable research problems."""
import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import Mock

from native_pilot.budget import CAP_MICRO_USD, Ledger, reservation, usage_cost
from native_pilot.design import make_schedule
from native_pilot.provider import DEFAULT_SETTINGS, ProviderFailure, UNCHANGED_REQUEST, build_request
from native_pilot.runner import execute
from test_provider import TASK, response


def fixture_manifest(*, controls=True):
    task = dict(copy.deepcopy(TASK), task_id="software-fixture", domain="math",
                original={"answer": "42"}, updated={"answer": "43"},
                unchanged_control=controls)
    return {"tasks": [task], "settings": copy.deepcopy(DEFAULT_SETTINGS),
            "schedule": make_schedule([task]), "manifest_sha256": "software-fixture-v1"}


class FixtureProvider:
    def __init__(self, behavior=None):
        self.requests = []
        self.behavior = behavior

    def create(self, request):
        self.requests.append(copy.deepcopy(request))
        index = len(self.requests)
        if self.behavior is not None:
            special = self.behavior(request, index)
            if special is not None:
                return special
        value = response(request["reasoning"]["context"], id=f"resp_software_{index}")
        original = request["input"][-1]["content"] in (TASK["original_prompt"], UNCHANGED_REQUEST)
        value["output"][-1]["content"][0]["text"] = "42" if original else "43"
        return value


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.temp.name) / "ledger.sqlite")

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def test_exactly_two_continuations_replay_same_immutable_initial(self):
        manifest = fixture_manifest()
        provider = FixtureProvider()
        result = execute(manifest, self.ledger, provider)
        self.assertIsNone(result["stop_reason"])
        self.assertEqual(len(provider.requests), 11)
        self.assertEqual(Counter(r["condition"] for r in result["outcomes"]), {
            "initial": 1, "updated_retained": 2, "updated_dropped": 2,
            "fresh": 2, "unchanged_retained": 2, "unchanged_dropped": 2})
        self.assertTrue(all(o["status"] == "correct" for o in result["outcomes"]))
        initial_row = self.ledger.rows()[0]
        initial_response = json.loads(initial_row["response"])
        initial_input = json.loads(initial_row["request"])["input"]
        paired = {}
        for row in self.ledger.rows()[1:]:
            call = json.loads(row["outcome"])
            request = json.loads(row["request"])
            if call["condition"] == "fresh":
                self.assertEqual(len(request["input"]), 1)
                continue
            self.assertEqual(request["input"][:-1], initial_input + initial_response["output"])
            key = (call["condition"].split("_")[0], call["sample"])
            request["reasoning"].pop("context")
            if key in paired:
                self.assertEqual(request, paired[key])
            else:
                paired[key] = request

    def test_resume_completed_calls_never_redispatches_or_recharges(self):
        manifest = fixture_manifest()
        provider = FixtureProvider()
        first = execute(manifest, self.ledger, provider)
        rows_before = copy.deepcopy(self.ledger.rows())
        charge_before = self.ledger.total()
        resumed_provider = FixtureProvider()
        second = execute(manifest, self.ledger, resumed_provider)
        self.assertEqual(resumed_provider.requests, [])
        self.assertEqual(self.ledger.rows(), rows_before)
        self.assertEqual(self.ledger.total(), charge_before)
        self.assertEqual(first["outcomes"], second["outcomes"])

    def test_one_transport_retry_has_separate_attempt_and_uncertain_reservation(self):
        manifest = fixture_manifest()
        manifest["schedule"] = manifest["schedule"][:1]
        def transient(request, index):
            if index == 1:
                raise ProviderFailure("transport_failure", retryable=True, uncertain_charge=True)
        provider = FixtureProvider(transient)
        result = execute(manifest, self.ledger, provider)
        self.assertEqual(len(provider.requests), 2)
        rows = self.ledger.rows()
        self.assertEqual([r["attempt"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["state"], "transport_uncertain")
        self.assertIsNone(rows[0]["charged"])
        self.assertEqual(rows[1]["state"], "completed")
        self.assertEqual(result["outcomes"][0]["status"], "correct")
        self.assertEqual(self.ledger.total(), rows[0]["reserved"] + rows[1]["charged"])
        self.assertEqual(provider.requests[0], provider.requests[1])

    def test_second_transport_failure_exhausts_retry_even_after_resume(self):
        manifest = fixture_manifest()
        manifest["schedule"] = manifest["schedule"][:1]
        def always_fails(request, index):
            raise ProviderFailure("transport_failure", retryable=True, uncertain_charge=True)
        provider = FixtureProvider(always_fails)
        result = execute(manifest, self.ledger, provider)
        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(result["outcomes"][0]["status"], "provider_failure")
        spent = self.ledger.total()
        resume = FixtureProvider()
        execute(manifest, self.ledger, resume)
        self.assertEqual(resume.requests, [])
        self.assertEqual(self.ledger.total(), spent)

    def test_refusal_and_truncation_are_not_retried(self):
        manifest = fixture_manifest()
        initial = manifest["schedule"][0]
        updated = [r for r in manifest["schedule"] if r["condition"] == "updated_retained"]
        manifest["schedule"] = [initial] + updated
        def unsuccessful(request, index):
            if index == 2:
                value = response("all_turns")
                value["output"][-1]["content"] = [{"type": "refusal", "refusal": "Fixture refusal"}]
                return value
            if index == 3:
                return response("all_turns", status="incomplete", incomplete_details={"reason": "max_output_tokens"})
        provider = FixtureProvider(unsuccessful)
        result = execute(manifest, self.ledger, provider)
        self.assertEqual(len(provider.requests), 3)
        self.assertTrue(all(row["attempt"] == 1 for row in self.ledger.rows()))
        self.assertTrue(all(o["status"] in {"invalid_output", "truncated_no_answer"} for o in result["outcomes"][1:]))

    def test_wrong_initial_is_not_regenerated_and_assignments_still_run(self):
        manifest = fixture_manifest(controls=False)
        def wrong_initial(request, index):
            if index == 1:
                value = response("current_turn")
                value["output"][-1]["content"][0]["text"] = "99"
                return value
        provider = FixtureProvider(wrong_initial)
        result = execute(manifest, self.ledger, provider)
        self.assertEqual(result["outcomes"][0]["status"], "incorrect")
        self.assertEqual(len(provider.requests), 7)
        self.assertTrue(all(row["attempt"] == 1 for row in self.ledger.rows()))

    def test_mismatched_effective_context_stops_campaign_and_resume(self):
        manifest = fixture_manifest()
        def bad_context(request, index):
            if index == 1:
                return response("all_turns")
        provider = FixtureProvider(bad_context)
        result = execute(manifest, self.ledger, provider)
        self.assertEqual(result["stop_reason"], "protocol_failure")
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(result["outcomes"][0]["status"], "protocol_failure")
        resumed = FixtureProvider()
        execute(manifest, self.ledger, resumed)
        self.assertEqual(resumed.requests, [])

    def test_unsupported_api_manipulation_stops_without_later_dispatch(self):
        manifest = fixture_manifest()
        def rejected(request, index):
            raise ProviderFailure("protocol_failure", status_code=400, uncertain_charge=False)
        provider = FixtureProvider(rejected)
        result = execute(manifest, self.ledger, provider)
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(result["stop_reason"], "protocol_failure")
        self.assertEqual(result["outcomes"][0]["status"], "protocol_failure")
        resumed = FixtureProvider()
        execute(manifest, self.ledger, resumed)
        self.assertEqual(resumed.requests, [])

    def test_returned_failed_or_cancelled_is_availability_failure_without_grading(self):
        for status in ("failed", "cancelled"):
            with self.subTest(status=status):
                ledger = Ledger(Path(self.temp.name) / (status + ".sqlite"))
                try:
                    manifest = fixture_manifest()
                    manifest["schedule"] = manifest["schedule"][:1]
                    value = response("current_turn", status=status, output=[])
                    grader = Mock(side_effect=AssertionError("Unavailable answer must not be graded"))
                    provider = FixtureProvider(lambda request, index: value)
                    result = execute(manifest, ledger, provider, grader=grader)
                    self.assertEqual(result["outcomes"][0]["status"], "provider_failure")
                    grader.assert_not_called()
                    self.assertEqual(len(provider.requests), 1)
                finally:
                    ledger.close()

    def test_budget_refusal_before_any_dispatch(self):
        manifest = fixture_manifest()
        request = build_request(manifest["tasks"][0], "initial")
        attempt = self.ledger.reserve("prior-smoke", "other-manifest", request, CAP_MICRO_USD, "smoke")
        self.ledger.dispatched("prior-smoke", attempt)
        self.ledger.uncertain("prior-smoke", attempt)
        provider = FixtureProvider()
        result = execute(manifest, self.ledger, provider)
        self.assertEqual(provider.requests, [])
        self.assertIn("budget", result["stop_reason"].lower())
        self.assertEqual(self.ledger.total(), CAP_MICRO_USD)
        self.assertTrue(all(o["status"] == "budget_stopped" for o in result["outcomes"]))

    def test_terminal_failure_with_missing_usage_stays_availability_failure(self):
        manifest = fixture_manifest()
        manifest["schedule"] = manifest["schedule"][:1]
        value = response("current_turn", status="failed", usage=None, output=[])
        provider = FixtureProvider(lambda request, index: value)
        grader = Mock(side_effect=AssertionError("Unavailable answer must not be graded"))
        result = execute(manifest, self.ledger, provider, grader=grader)
        self.assertEqual(result["outcomes"][0]["status"], "provider_failure")
        grader.assert_not_called()
        row = self.ledger.rows()[0]
        self.assertIsNone(row["charged"])
        self.assertEqual(self.ledger.total(), row["reserved"])

    def test_missing_cache_usage_keeps_full_uncertain_reservation(self):
        manifest = fixture_manifest()
        manifest["schedule"] = manifest["schedule"][:1]
        value = response("current_turn")
        value["usage"]["input_tokens_details"] = {}
        provider = FixtureProvider(lambda request, index: value)
        result = execute(manifest, self.ledger, provider)
        self.assertEqual(result["outcomes"][0]["status"], "protocol_failure")
        row = self.ledger.rows()[0]
        self.assertIsNone(row["charged"])
        self.assertEqual(self.ledger.total(), row["reserved"])

    def test_unexpected_provider_tier_does_not_reconcile_at_standard_rates(self):
        manifest = fixture_manifest()
        manifest["schedule"] = manifest["schedule"][:1]
        value = response("current_turn", service_tier="priority")
        provider = FixtureProvider(lambda request, index: value)
        result = execute(manifest, self.ledger, provider)
        self.assertEqual(result["outcomes"][0]["status"], "protocol_failure")
        row = self.ledger.rows()[0]
        self.assertIsNone(row["charged"])
        self.assertEqual(self.ledger.total(), row["reserved"])

    def test_crash_after_dispatch_keeps_reservation_and_allows_only_one_retry(self):
        manifest = fixture_manifest()
        manifest["schedule"] = manifest["schedule"][:1]
        request = build_request(manifest["tasks"][0], "initial")
        call_id = manifest["manifest_sha256"] + "/" + manifest["schedule"][0]["call_id"]
        reserved = reservation(request)["micro_usd"]
        attempt = self.ledger.reserve(call_id, manifest["manifest_sha256"], request, reserved)
        self.ledger.dispatched(call_id, attempt)
        provider = FixtureProvider()
        result = execute(manifest, self.ledger, provider)
        rows = self.ledger.rows()
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual([r["attempt"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["error_kind"], "interrupted_unknown_charge")
        self.assertEqual(self.ledger.total(), reserved + usage_cost(json.loads(rows[1]["response"])["usage"]))
        self.assertEqual(result["outcomes"][0]["status"], "correct")


if __name__ == "__main__":
    unittest.main()
