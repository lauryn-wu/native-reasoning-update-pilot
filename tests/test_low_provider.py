"""Low-effort protocol checks use synthetic checkpoints and mocked transport only."""
import copy
import sys
import types
import unittest
from unittest.mock import Mock, patch

from native_pilot.provider import (
    OpenAIProvider, ProtocolError, ProviderFailure, _validate_dispatch_request,
    build_low_request, build_request, normalize_replay_output,
    validate_low_response, validate_response,
)
from test_provider import TASK, observed_structure_response, response


def high_checkpoint():
    return {"request": build_request(TASK, "initial"),
            "response": observed_structure_response()}


def low_response(context="current_turn"):
    value = response(context)
    value["reasoning"]["effort"] = "low"
    return value


class LowRequestTests(unittest.TestCase):
    def test_both_forks_preserve_high_checkpoint_and_only_change_requested_effort(self):
        checkpoint = high_checkpoint()
        original = copy.deepcopy(checkpoint)
        pair = []
        for branch in ("updated_retained", "updated_dropped"):
            expected = build_request(TASK, branch, checkpoint)
            expected["reasoning"]["effort"] = "low"
            actual = build_low_request(TASK, branch, checkpoint)
            self.assertEqual(actual, expected)
            self.assertEqual(actual["input"][:-1], checkpoint["request"]["input"] +
                             normalize_replay_output(checkpoint["response"]["output"]))
            self.assertEqual(sum(item.get("type") == "reasoning" for item in actual["input"]), 4)
            self.assertEqual(actual["input"][-2]["phase"], "final_answer")
            self.assertFalse(any(item.get("type") == "configuration_update" for item in actual["input"]))
            pair.append(actual)
        contexts = [item["reasoning"].pop("context") for item in pair]
        self.assertEqual(contexts, ["all_turns", "current_turn"])
        self.assertEqual(pair[0], pair[1])
        self.assertEqual(checkpoint, original)

    def test_fresh_low_has_no_checkpoint_or_previous_output(self):
        actual = build_low_request(TASK, "fresh")
        expected = build_request(TASK, "fresh")
        expected["reasoning"]["effort"] = "low"
        self.assertEqual(actual, expected)
        self.assertEqual(actual["input"], [{"role": "user", "content": TASK["updated_prompt"]}])
        with self.assertRaises(ProtocolError):
            build_low_request(TASK, "fresh", high_checkpoint())

    def test_initial_unchanged_and_invalid_checkpoint_are_rejected(self):
        for branch in ("initial", "unchanged_retained", "unchanged_dropped", "invalid"):
            with self.subTest(branch=branch), self.assertRaises(ProtocolError):
                build_low_request(TASK, branch)
        with self.assertRaises(ProtocolError):
            build_low_request(TASK, "updated_retained")
        for field in ("request", "response"):
            checkpoint = high_checkpoint()
            checkpoint[field]["reasoning"]["effort"] = "low"
            with self.subTest(field=field), self.assertRaises(ProtocolError):
                build_low_request(TASK, "updated_retained", checkpoint)

    def test_configuration_update_cannot_override_the_requested_low_effort(self):
        checkpoint = high_checkpoint()
        checkpoint["response"]["output"].append({
            "type": "configuration_update", "reasoning": {"effort": "high"}})
        with self.assertRaisesRegex(ProtocolError, "configuration-update"):
            build_low_request(TASK, "updated_retained", checkpoint)

    def test_dispatch_low_is_explicit_and_other_frozen_parameters_remain_checked(self):
        request = build_low_request(TASK, "fresh")
        _validate_dispatch_request(request, expected_effort="low")
        with self.assertRaises(ProtocolError):
            _validate_dispatch_request(request)
        for key, value in (("model", "another-model"), ("max_output_tokens", 1000),
                           ("service_tier", "flex"), ("temperature", 0)):
            changed = copy.deepcopy(request)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ProtocolError):
                _validate_dispatch_request(changed, expected_effort="low")
        changed = copy.deepcopy(request)
        changed["input"].insert(0, {"type": "configuration_update", "reasoning": {"effort": "high"}})
        with self.assertRaisesRegex(ProtocolError, "configuration-update"):
            _validate_dispatch_request(changed, expected_effort="low")
        changed = copy.deepcopy(request)
        changed["input"][0]["prompt_cache_breakpoint"] = {}
        with self.assertRaisesRegex(ProtocolError, "cache breakpoints"):
            _validate_dispatch_request(changed, expected_effort="low")


class LowResponseTests(unittest.TestCase):
    def test_returned_low_required_and_high_default_unchanged(self):
        value = low_response()
        self.assertTrue(validate_low_response(value, "current_turn")["valid"])
        self.assertFalse(validate_response(value, "current_turn")["valid"])
        self.assertTrue(validate_response(response(), "current_turn")["valid"])
        self.assertFalse(validate_low_response(response(), "current_turn")["valid"])
        value["reasoning"].pop("effort")
        self.assertFalse(validate_low_response(value, "current_turn")["valid"])

    def test_low_still_checks_context_mode_usage_and_incomplete_status(self):
        value = low_response("all_turns")
        self.assertFalse(validate_low_response(value, "current_turn")["valid"])
        self.assertTrue(validate_low_response(value, "all_turns")["valid"])
        value["reasoning"]["mode"] = "pro"
        self.assertFalse(validate_low_response(value, "all_turns")["valid"])
        value = low_response()
        value["usage"]["input_tokens_details"]["cached_tokens"] = 1
        self.assertFalse(validate_low_response(value, "current_turn")["valid"])
        value = low_response()
        value.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
        self.assertTrue(validate_low_response(value, "current_turn")["valid"])
        self.assertFalse(validate_response(value, "current_turn", expected_effort=None)["valid"])


class LowDelegationTests(unittest.TestCase):
    """The low module owns frozen identity and ledger enforcement, not the SDK."""
    def setUp(self):
        self.task = dict(copy.deepcopy(TASK), task_id="aime2025:1042")
        self.manifest = {"tasks": [self.task], "manifest_sha256": "synthetic-low"}
        self.schedule = [{"task_id": self.task["task_id"], "condition": "fresh", "sample": 1}]
        self.module = types.ModuleType("native_pilot.low_effort")
        self.module.make_schedule = Mock(return_value=self.schedule)
        self.module.require_execution = Mock()
        self.modules = patch.dict(sys.modules, {"native_pilot.low_effort": self.module})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.policy = {"synthetic": True}
        self.reader = patch("native_pilot.provider._read_execution_policy", return_value=self.policy)
        self.reader.start()
        self.addCleanup(self.reader.stop)
        self.client = Mock()
        self.client.responses.create.return_value = low_response()
        self.ledger, self.guard = object(), object()

    def provider(self):
        return OpenAIProvider(allow_paid=True, client=self.client,
            execution_scope="low_effort_followup", manifest=self.manifest,
            ledger=self.ledger, campaign_guard=self.guard)

    def test_scope_guard_runs_on_initialization_and_again_before_send(self):
        provider = self.provider()
        self.module.require_execution.assert_called_once_with(policy=self.policy,
            manifest=self.manifest, ledger=self.ledger, campaign_guard=self.guard,
            request=None, execution_context=None)
        request, context = build_low_request(self.task, "fresh"), {"synthetic": "assignment"}
        self.assertEqual(provider.create(request, execution_context=context), low_response())
        self.module.require_execution.assert_called_with(policy=self.policy,
            manifest=self.manifest, ledger=self.ledger, campaign_guard=self.guard,
            request=request, execution_context=context)
        self.module.require_execution.side_effect = ProviderFailure("paid_execution_policy_hold", uncertain_charge=False)
        with self.assertRaises(ProviderFailure):
            provider.create(request, execution_context=context)
        self.client.responses.create.assert_called_once()

    def test_guard_rejection_prevents_injected_client_use(self):
        self.module.require_execution.side_effect = ProviderFailure("low_scope_rejected", uncertain_charge=False)
        with self.assertRaises(ProviderFailure):
            self.provider()
        self.client.responses.create.assert_not_called()

    def test_schedule_and_hydrated_task_changes_cannot_bypass_guard(self):
        provider = self.provider()
        provider.authorize_schedule(self.manifest, self.ledger, self.schedule,
            [self.task], execution_scope="low_effort_followup", campaign_guard=self.guard)
        changed = [dict(self.schedule[0], condition="initial")]
        with self.assertRaises(ProviderFailure):
            provider.authorize_schedule(self.manifest, self.ledger, changed,
                [self.task], execution_scope="low_effort_followup", campaign_guard=self.guard)
        altered = dict(self.task, correction_prompt="changed")
        with self.assertRaisesRegex(ProviderFailure, "task_not_frozen"):
            provider.authorize_schedule(self.manifest, self.ledger, self.schedule,
                [altered], execution_scope="low_effort_followup", campaign_guard=self.guard)
        self.client.responses.create.assert_not_called()

    def test_low_provider_rejects_high_request_before_send(self):
        provider = self.provider()
        with self.assertRaises(ProtocolError):
            provider.create(build_request(self.task, "fresh"), execution_context={})
        self.client.responses.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
