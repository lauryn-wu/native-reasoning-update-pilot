"""Real temporary ledgers, synthetic checkpoints, and no provider dispatch."""
import copy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from native_pilot.budget import BudgetRefused, Ledger, LOW_EFFORT_SCOPE_ID, reservation
from native_pilot.low_authorization import require_execution
from native_pilot.provider import ProviderFailure, build_low_request, build_request
from native_pilot.runner import campaign_lock
from test_low_provider import low_response
from test_provider import TASK, observed_structure_response


TASK_IDS = ("aime2025:1042", "aime2025:1057", "livecodebench:299", "livecodebench:276")


def schedule_for(tasks):
    return [{"call_id": f"{task['task_id']}/{branch}/{sample}", "task_id": task["task_id"],
             "condition": branch, "sample": sample}
            for task in tasks for sample in (1, 2)
            for branch in ("updated_retained", "updated_dropped", "fresh")]


class LowAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = Ledger(self.root / "budget.sqlite")
        self.addCleanup(self.ledger.close)
        self.lock = campaign_lock(self.root / "campaign.lock")
        self.guard = self.lock.__enter__()
        self.addCleanup(self.lock.__exit__, None, None, None)
        self.tasks = [dict(copy.deepcopy(TASK), task_id=tid,
                           original_prompt=TASK["original_prompt"] + " " + tid) for tid in TASK_IDS]
        self.by_id = {task["task_id"]: task for task in self.tasks}
        self.checkpoints = {task["task_id"]: {"request": build_request(task, "initial"),
                            "response": observed_structure_response()} for task in self.tasks}
        authorization = {"allowed": True, "authorization_id": LOW_EFFORT_SCOPE_ID,
                         "manifest_version": "pilot-v7", "task_ids": list(TASK_IDS),
                         "max_logical_calls": 24, "max_transport_retries_per_call": 1,
                         "additional_budget_usd": 2, "shared_budget_usd": 40,
                         "soft_dispatch_deadline_seconds": 1800}
        self.manifest = {"manifest_sha256": "e" * 64, "version": "pilot-v7", "status": "frozen",
                         "execution_scope": "low_effort_followup", "low_effort_authorization": authorization,
                         "paid_execution_allowed": False, "hard_budget_usd": 40, "blockers": [],
                         "settings": {"model": "gpt-6.1-sol", "reasoning_effort": "low", "max_output_tokens": 32768},
                         "tasks": self.tasks, "schedule": schedule_for(self.tasks)}
        self.policy = {"paid_execution_allowed": False, "protocol_smoke": None,
                       "low_effort_followup": authorization,
                       "exploratory_pilot": {"historical": "preserved"}}
        self.module = types.ModuleType("native_pilot.low_effort")
        self.module.AUTHORIZATION = authorization
        self.module.ROOT = self.root
        self.module.TASK_IDS = TASK_IDS
        self.module.make_schedule = schedule_for
        self.module.load_frozen = Mock(return_value=self.manifest)
        self.module.verify_initials = Mock(return_value=self.checkpoints)
        for patcher in (
                patch.dict(sys.modules, {"native_pilot.low_effort": self.module}),
                patch("native_pilot.low_authorization.SHARED_LEDGER_PATH", self.ledger.path),
                patch("native_pilot.budget._wall_time", return_value=1000.0)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def gate(self, request=None, context=None, **changes):
        args = dict(policy=self.policy, manifest=self.manifest, ledger=self.ledger,
                    campaign_guard=self.guard, request=request, execution_context=context)
        args.update(changes)
        return require_execution(**args)

    def reserve(self, index=0, *, amount=None):
        call = self.manifest["schedule"][index]
        checkpoint = None if call["condition"] == "fresh" else self.checkpoints[call["task_id"]]
        request = build_low_request(self.by_id[call["task_id"]], call["condition"], checkpoint)
        call_id = self.manifest["manifest_sha256"] + "/" + call["call_id"]
        amount = reservation(request, checkpoint)["micro_usd"] if amount is None else amount
        attempt = self.ledger.reserve(call_id, self.manifest["manifest_sha256"], request, amount,
            "low_effort_followup", scope_id=LOW_EFFORT_SCOPE_ID)
        self.ledger.dispatched(call_id, attempt)
        return request, dict(call, call_id=call_id, manifest_sha256=self.manifest["manifest_sha256"], attempt=attempt)

    def finish(self, request, context, *, correct=False, returned_effort="low", status="completed"):
        value = low_response(request["reasoning"]["context"])
        value["reasoning"]["effort"] = returned_effort
        value["status"] = status
        outcome = {"status": "correct" if correct else "wrong", "protocol_valid": True,
                   "grade": {"correct": correct}}
        self.ledger.finish(context["call_id"], context["attempt"], value, outcome)

    def test_binding_has_no_calls_or_clock_and_rechecks_initials(self):
        self.gate()
        self.gate()
        self.assertEqual(self.ledger.rows(), [])
        self.assertIsNone(self.ledger.scope_status(LOW_EFFORT_SCOPE_ID)["started_at"])
        self.assertEqual(self.module.verify_initials.call_count, 2)
        self.module.load_frozen.assert_called_with(self.root / "manifests/pilot-v7.json")

    def test_all_24_requests_keep_same_high_initials_despite_wrong_answers(self):
        original = copy.deepcopy(self.checkpoints)
        self.gate()
        for index in range(24):
            request, context = self.reserve(index)
            self.gate(request, context)
            self.finish(request, context, correct=False)
        self.assertEqual(self.checkpoints, original)
        self.assertEqual(len(self.ledger.rows()), 24)
        self.assertFalse(any("/initial/" in row["call_id"] for row in self.ledger.rows()))
        self.assertEqual(self.module.verify_initials.call_count, 25)

    def test_policy_scope_or_frozen_design_changes_are_rejected_before_binding(self):
        for policy in (dict(self.policy, paid_execution_allowed=True),
                       dict(self.policy, low_effort_followup=None),
                       dict(self.policy, protocol_smoke={"allowed": True})):
            with self.subTest(policy=policy), self.assertRaises(ProviderFailure):
                self.gate(policy=policy)
        for key, value in (("execution_scope", "pilot"), ("hard_budget_usd", 41), ("version", "pilot-v8")):
            with self.subTest(key=key), self.assertRaises(ProviderFailure):
                self.gate(manifest=dict(self.manifest, **{key: value}))
        self.assertIsNone(self.ledger.scope_status(LOW_EFFORT_SCOPE_ID))

    def test_missing_qualification_or_historical_verification_stops_before_binding(self):
        self.module.load_frozen.side_effect = ValueError("private fixture details")
        with self.assertRaisesRegex(ProviderFailure, "manifest_not_authorized"):
            self.gate()
        self.module.load_frozen.side_effect = None
        self.module.verify_initials.side_effect = ValueError("private checkpoint details")
        with self.assertRaisesRegex(ProviderFailure, "initials_unverified"):
            self.gate()
        self.assertIsNone(self.ledger.scope_status(LOW_EFFORT_SCOPE_ID))

    def test_wrong_or_inactive_ledger_lock_and_physical_database_are_rejected(self):
        with self.assertRaisesRegex(ProviderFailure, "active_campaign_lock"):
            self.gate(campaign_guard=None)
        other = Ledger(self.root / "other.sqlite")
        self.addCleanup(other.close)
        other.path = self.ledger.path
        with self.assertRaisesRegex(ProviderFailure, "shared_budget_ledger"):
            self.gate(ledger=other)
        self.lock.__exit__(None, None, None)
        with self.assertRaisesRegex(ProviderFailure, "active_campaign_lock"):
            self.gate()

    def test_one_scope_cannot_bind_a_new_manifest_after_resume(self):
        self.gate()
        changed = dict(self.manifest, manifest_sha256="d" * 64)
        self.module.load_frozen.return_value = changed
        with self.assertRaises(BudgetRefused):
            self.gate(manifest=changed)

    def test_metadata_wrong_order_and_changed_request_are_rejected(self):
        self.gate()
        request, context = self.reserve()
        for change in ({"sample": True}, {"attempt": 3}, {"condition": "initial"},
                       {"task_id": "different"}, {"manifest_sha256": "different"}, {"extra": 1}):
            with self.subTest(change=change), self.assertRaises(ProviderFailure):
                self.gate(request, dict(context, **change))
        altered = copy.deepcopy(request)
        altered["input"][-1]["content"] += " changed"
        with self.assertRaisesRegex(ProviderFailure, "request_not_frozen"):
            self.gate(altered, context)
        with self.assertRaises(ProviderFailure):
            self.gate(request, None)
        self.gate(request, context)

    def test_uncompleted_predecessor_or_preassigned_future_row_blocks_dispatch(self):
        self.gate()
        later_request, later_context = self.reserve(1)
        with self.assertRaisesRegex(ProviderFailure, "not_a_prefix"):
            self.gate(later_request, later_context)
        request, context = self.reserve(0)
        with self.assertRaisesRegex(ProviderFailure, "not_a_prefix"):
            self.gate(request, context)

    def test_duplicate_and_underreserved_dispatch_are_blocked(self):
        self.gate()
        request, context = self.reserve(amount=1)
        with self.assertRaisesRegex(ProviderFailure, "reservation_required"):
            self.gate(request, context)
        with self.ledger.transaction():
            required = reservation(request, self.checkpoints[context["task_id"]])["micro_usd"]
            self.ledger.db.execute("UPDATE attempts SET reserved=?", (required,))
        self.gate(request, context)
        with self.assertRaisesRegex(ProviderFailure, "already_dispatched"):
            self.gate(request, context)

    def test_only_one_claimed_transport_retry_is_allowed(self):
        self.gate()
        request, context = self.reserve()
        self.gate(request, context)
        self.ledger.uncertain(context["call_id"], 1)
        retried, retry_context = self.reserve()
        self.assertEqual(retried, request)
        self.assertEqual(retry_context["attempt"], 2)
        self.gate(retried, retry_context)
        self.ledger.uncertain(context["call_id"], 2)
        with self.assertRaises(BudgetRefused):
            self.reserve()

    def test_unclaimed_transport_row_cannot_mint_a_retry(self):
        self.gate()
        _, context = self.reserve()
        self.ledger.uncertain(context["call_id"], 1)
        request, context = self.reserve()
        with self.assertRaisesRegex(ProviderFailure, "transport_retry_not_authorized"):
            self.gate(request, context)

    def test_provider_failure_blocks_later_calls_without_retry_or_grade_selection(self):
        self.gate()
        request, context = self.reserve()
        self.gate(request, context)
        self.ledger.provider_failure(context["call_id"], 1, "provider_failure",
            {"status": "provider_failure", "protocol_valid": False})
        later, later_context = self.reserve(1)
        with self.assertRaisesRegex(ProviderFailure, "stopped_after_provider_failure"):
            self.gate(later, later_context)

    def test_a_high_effort_echo_cannot_be_accepted_as_a_prior_low_response(self):
        self.gate()
        request, context = self.reserve()
        self.gate(request, context)
        self.finish(request, context, returned_effort="high")
        later, later_context = self.reserve(1)
        with self.assertRaisesRegex(ProviderFailure, "history_unverified"):
            self.gate(later, later_context)

    def test_altered_prior_wire_request_or_missing_claim_cannot_continue(self):
        self.gate()
        request, context = self.reserve()
        self.gate(request, context)
        self.finish(request, context)
        later, later_context = self.reserve(1)
        with self.ledger.transaction():
            self.ledger.db.execute("DELETE FROM meta WHERE key=?", (
                "provider_dispatch/" + context["call_id"] + "/1",))
        with self.assertRaisesRegex(ProviderFailure, "history_unverified"):
            self.gate(later, later_context)

    def test_deadline_is_rechecked_and_latched_before_any_dispatch_claim(self):
        self.gate()
        request, context = self.reserve()
        with patch("native_pilot.budget._wall_time", return_value=2800.0):
            with self.assertRaisesRegex(BudgetRefused, "deadline elapsed"):
                self.gate(request, context)
        with self.assertRaisesRegex(BudgetRefused, "deadline elapsed"):
            self.gate(request, context)
        self.assertIsNone(self.ledger.db.execute("SELECT value FROM meta WHERE key=?", (
            "provider_dispatch/" + context["call_id"] + "/1",)).fetchone())


if __name__ == "__main__":
    unittest.main()
