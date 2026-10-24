import copy
import importlib.util
import json
import unittest
from unittest.mock import Mock

from native_pilot.provider import (
    DEFAULT_SETTINGS, OpenAIProvider, ProtocolError, ProviderFailure,
    UNCHANGED_REQUEST, build_request, extract_visible_answer, validate_response,
)


TASK = {"id": "unit-only", "original_prompt": "Original published task placeholder.",
        "updated_prompt": "Updated published task placeholder.",
        "correction_prompt": "A legitimate correction from the frozen fixture."}


def response(context="current_turn", **overrides):
    """Synthetic protocol fixture only; never a pilot or smoke case."""
    value = {
        "id": "resp_fixture", "model": "gpt-6.1-sol-2026-10-20",
        "status": "completed", "service_tier": "default",
        "reasoning": {"context": context, "effort": "high", "mode": "standard"},
        "output": [
            {"id": "rs_fixture", "type": "reasoning", "summary": [],
             "encrypted_content": "opaque-test-fixture-not-native-state"},
            {"id": "msg_commentary", "type": "message", "role": "assistant",
             "phase": "commentary", "status": "completed",
             "content": [{"type": "output_text", "text": "Working...", "annotations": []}]},
            {"id": "msg_final", "type": "message", "role": "assistant",
             "phase": "final_answer", "status": "completed",
             "content": [{"type": "output_text", "text": "42", "annotations": []}]},
        ],
        "usage": {"input_tokens": 20, "output_tokens": 30, "total_tokens": 50,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 25}},
    }
    value.update(overrides)
    return value


def checkpoint():
    return {"request": build_request(TASK, "initial"), "response": response()}


class ProviderTests(unittest.TestCase):
    def test_paired_payloads_differ_only_in_context(self):
        for prefix in ("updated", "unchanged"):
            retained = build_request(TASK, prefix + "_retained", checkpoint())
            dropped = build_request(TASK, prefix + "_dropped", checkpoint())
            self.assertEqual(retained["reasoning"].pop("context"), "all_turns")
            self.assertEqual(dropped["reasoning"].pop("context"), "current_turn")
            self.assertEqual(retained, dropped)

    def test_independent_samples_preserve_entire_initial_output(self):
        original = checkpoint()
        before = copy.deepcopy(original)
        first = build_request(TASK, "updated_retained", original)
        second = build_request(TASK, "updated_retained", original)
        self.assertEqual(first, second)
        self.assertEqual(first["input"][1:-1], original["response"]["output"])
        first["input"][1]["encrypted_content"] = "changed"
        self.assertEqual(second["input"][1]["encrypted_content"], before["response"]["output"][0]["encrypted_content"])
        self.assertEqual(original, before)

    def test_continuation_cannot_be_used_as_second_samples_checkpoint(self):
        bad = {"request": build_request(TASK, "updated_retained", checkpoint()),
               "response": response("all_turns")}
        with self.assertRaises(ProtocolError):
            build_request(TASK, "updated_retained", bad)

    def test_fresh_has_only_complete_updated_problem(self):
        fresh = build_request(TASK, "fresh")
        self.assertEqual(fresh["input"], [{"role": "user", "content": TASK["updated_prompt"]}])
        with self.assertRaises(ProtocolError):
            build_request(TASK, "fresh", checkpoint())

    def test_ordinary_new_user_turn_and_neutral_unchanged_wording(self):
        updated = build_request(TASK, "updated_dropped", checkpoint())
        self.assertEqual(updated["input"][-1], {"role": "user", "content": TASK["correction_prompt"]})
        unchanged = build_request(TASK, "unchanged_dropped", checkpoint())
        self.assertEqual(unchanged["input"][-1]["content"], UNCHANGED_REQUEST)

    def test_settings_are_frozen_and_sampling_options_forbidden(self):
        request = build_request(TASK, "initial")
        self.assertFalse(request["store"])
        self.assertNotIn("previous_response_id", request)
        self.assertNotIn("temperature", request)
        self.assertEqual(request["max_output_tokens"], 32768)
        for invalid in ({"model": "different"}, {"reasoning_effort": "low"},
                        {"max_output_tokens": 256}, {"temperature": 0}):
            with self.assertRaises(ProtocolError):
                build_request(TASK, "initial", settings=invalid)

    def test_effective_context_is_required_for_all_calls(self):
        for branch in ("initial", "fresh", "updated_retained", "updated_dropped"):
            expected = "all_turns" if branch.endswith("_retained") else "current_turn"
            valid = response(expected)
            self.assertTrue(validate_response(valid, expected)["valid"])
            del valid["reasoning"]["context"]
            self.assertFalse(validate_response(valid, expected)["valid"])
        self.assertFalse(validate_response(response("current_turn"), "all_turns")["valid"])

    def test_missing_native_reasoning_blocks_initial_checkpoint(self):
        value = response()
        value["output"][0]["encrypted_content"] = None
        self.assertFalse(validate_response(value, "current_turn", True)["valid"])
        with self.assertRaises(ProtocolError):
            build_request(TASK, "updated_retained", {"request": build_request(TASK, "initial"), "response": value})

    def test_truncation_is_not_automatically_a_manipulation_failure(self):
        value = response(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
        self.assertTrue(validate_response(value, "current_turn")["valid"])
        self.assertFalse(validate_response(value, "current_turn", True)["valid"])

    def test_final_phase_only_is_scored(self):
        self.assertEqual(extract_visible_answer(response()), "42")
        self.assertEqual(extract_visible_answer({"output": None}), "")
        self.assertEqual(extract_visible_answer({"output": [{"type": "message", "content": None}]}), "")

    def test_unexpected_pricing_and_invalid_usage_are_protocol_failures(self):
        for changes in ({"service_tier": "priority"}, {"model": "gpt-6-astra"}, {"usage": None}):
            self.assertFalse(validate_response(response(**changes), "current_turn")["valid"])
        value = response()
        value["usage"]["input_tokens_details"]["cache_write_tokens"] = 10
        self.assertFalse(validate_response(value, "current_turn")["valid"])

    def test_paid_flag_is_required_even_with_injected_client(self):
        client = Mock()
        with self.assertRaises(ProviderFailure) as caught:
            OpenAIProvider(client=client)
        self.assertFalse(caught.exception.uncertain_charge)
        client.responses.create.assert_not_called()

    def test_mock_provider_serializes_without_losing_output_metadata(self):
        client = Mock()
        client.responses.create.return_value = response()
        provider = OpenAIProvider(allow_paid=True, client=client)
        self.assertEqual(provider.create(build_request(TASK, "initial")), response())
        client.responses.create.assert_called_once()

    def test_forbidden_parameters_block_before_dispatch(self):
        client = Mock()
        provider = OpenAIProvider(allow_paid=True, client=client)
        request = build_request(TASK, "initial")
        request["previous_response_id"] = "forbidden"
        with self.assertRaises(ProtocolError):
            provider.create(request)
        client.responses.create.assert_not_called()

    def test_safe_transport_failure_and_no_sdk_retry(self):
        client = Mock()
        client.responses.create.side_effect = ConnectionError("SECRET api key body")
        provider = OpenAIProvider(allow_paid=True, client=client)
        with self.assertRaises(ProviderFailure) as caught:
            provider.create(build_request(TASK, "initial"))
        self.assertTrue(caught.exception.retryable)
        self.assertTrue(caught.exception.uncertain_charge)
        self.assertNotIn("SECRET", str(caught.exception))
        client.responses.create.assert_called_once()

    def test_invalid_request_status_is_protocol_failure_without_retry(self):
        class APIError(Exception):
            status_code = 400
        client = Mock()
        client.responses.create.side_effect = APIError("Sensitive unsupported settings body")
        with self.assertRaises(ProviderFailure) as caught:
            OpenAIProvider(allow_paid=True, client=client).create(build_request(TASK, "initial"))
        self.assertEqual(caught.exception.kind, "protocol_failure")
        self.assertFalse(caught.exception.retryable)
        self.assertNotIn("Sensitive", str(caught.exception))

    @unittest.skipUnless(importlib.util.find_spec("openai"), "optional pinned SDK not installed")
    def test_actual_pinned_sdk_serialization_with_offline_http_transport(self):
        import openai
        import httpx2
        self.assertEqual(openai.__version__, "3.37.0")
        seen = []
        def handle(request):
            # MockTransport never opens a socket or contacts OpenAI.
            payload = json.loads(request.content)
            seen.append(payload)
            value = response(payload["reasoning"]["context"])
            value.update({"object": "response", "created_at": 1})
            return httpx2.Response(200, json=value)
        with openai.OpenAI(api_key="offline-unit-placeholder", max_retries=0,
                           http_client=httpx2.Client(transport=httpx2.MockTransport(handle))) as client:
            provider = OpenAIProvider(allow_paid=True, client=client)
            initial_request = build_request(TASK, "initial")
            initial = provider.create(initial_request)
            self.assertTrue(validate_response(initial, "current_turn", True)["valid"])
            state = {"request": initial_request, "response": initial}
            for branch in ("updated_retained", "updated_dropped"):
                result = provider.create(build_request(TASK, branch, state))
                self.assertTrue(validate_response(result, seen[-1]["reasoning"]["context"])["valid"])
            self.assertEqual(client.max_retries, 0)
        retained, dropped = seen[1:]
        retained["reasoning"]["context"] = dropped["reasoning"]["context"]
        self.assertEqual(retained, dropped)
        self.assertEqual(seen[1]["input"][1:-1], initial["output"])


if __name__ == "__main__":
    unittest.main()
