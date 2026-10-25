import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from native_pilot.provider import (
    DEFAULT_SETTINGS, OpenAIProvider, ProtocolError, ProviderFailure,
    UNCHANGED_REQUEST, build_request, extract_visible_answer, validate_response,
    AUTHENTICATION_RECOVERY, AUTHENTICATION_RECOVERY_PATH, SMOKE_AUTHORIZATION,
    _read_authentication_recovery_record as read_authentication_recovery_record,
)
from native_pilot.budget import Ledger, reservation
from native_pilot.util import digest, file_digest


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


def scoped_smoke_fixture():
    """Synthetic gate test only; private readers are patched, never source data."""
    task = dict(copy.deepcopy(TASK), task_id="livecodebench:337", domain="math",
                original={"answer": "42"}, updated={"answer": "43"})
    return {"manifest_sha256": "a" * 64, "version": SMOKE_AUTHORIZATION['manifest_version'], "status": "frozen",
            "blockers": [], "hard_budget_usd": 40, "paid_execution_allowed": False,
            "protocol_smoke_authorization": copy.deepcopy(SMOKE_AUTHORIZATION),
            "settings": copy.deepcopy(DEFAULT_SETTINGS), "smoke_task": task,
            "tasks": [], "schedule": []}


def seed_authentication_recovery(ledger, manifest):
    """Seed only a caller's temporary test ledger, never the campaign database."""
    from native_pilot.provider import SHARED_LEDGER_PATH
    if ledger.path.resolve() == SHARED_LEDGER_PATH.resolve():
        raise ValueError('Synthetic predecessor cannot be written to the campaign ledger')
    recovery = copy.deepcopy(AUTHENTICATION_RECOVERY)
    request = build_request(manifest['smoke_task'], 'initial', settings=manifest['settings'])
    attempt = ledger.reserve(recovery['failed_call_id'], recovery['failed_manifest_sha256'], request,
                             reservation(request)['micro_usd'], 'smoke')
    ledger.dispatched(recovery['failed_call_id'], attempt)
    ledger.provider_failure(recovery['failed_call_id'], attempt, 'provider_failure', {
        'call_id':'smoke/livecodebench:337/initial/0', 'task_id':'livecodebench:337',
        'condition':'initial', 'sample':0, 'status':'provider_failure', 'protocol_valid':False,
        'error_kind':'provider_failure', 'provider_error':{
            'kind':'provider_failure','retryable':False,'uncertain_charge':False,'status_code':401}})
    failed = ledger.latest(recovery['failed_call_id'])
    recovery['failed_attempt_sha256'] = digest(failed)
    recovery['retained_reservation_micro_usd'] = failed['reserved']
    with ledger.transaction():
        for key in ('execution_authorization/' + recovery['failed_authorization_id'],
                    'provider_dispatch/' + recovery['failed_call_id'] + '/' + str(attempt)):
            ledger.db.execute('INSERT INTO meta VALUES (?,?)', (key, recovery['failed_manifest_sha256']))
    manifest['authentication_recovery'] = {'path':AUTHENTICATION_RECOVERY_PATH,'sha256':'c'*64}
    manifest['provenance_hashes'] = {AUTHENTICATION_RECOVERY_PATH:'c'*64}
    return recovery


class ScopedProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Ledger(Path(self.temp.name) / "budget.sqlite")
        self.addCleanup(self.ledger.close)
        from native_pilot.runner import campaign_lock
        self.lock = campaign_lock(Path(self.temp.name) / "campaign.lock")
        self.guard = self.lock.__enter__()
        self.addCleanup(self.lock.__exit__, None, None, None)
        self.manifest = scoped_smoke_fixture()
        self.recovery = seed_authentication_recovery(self.ledger, self.manifest)
        self.policy = {"paid_execution_allowed": False,
                       "protocol_smoke": copy.deepcopy(SMOKE_AUTHORIZATION)}
        for target, value in (("SHARED_LEDGER_PATH", self.ledger.path),
                              ("_read_frozen_smoke_manifest", self.manifest),
                              ("_read_execution_policy", self.policy),
                              ("AUTHENTICATION_RECOVERY", self.recovery),
                              ("_read_authentication_recovery_record", self.recovery)):
            patcher = (patch("native_pilot.provider." + target, value) if target.isupper()
                       else patch("native_pilot.provider." + target, return_value=value))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = Mock()
        self.client.responses.create.return_value = response()

    def provider(self, **changes):
        options = dict(allow_paid=True, client=self.client, execution_scope="protocol_smoke",
                       manifest=self.manifest, ledger=self.ledger, campaign_guard=self.guard)
        options.update(changes)
        return OpenAIProvider(**options)

    def reserve_initial(self):
        from native_pilot.runner import smoke_schedule
        call = smoke_schedule(self.manifest["smoke_task"])[0]
        request = build_request(self.manifest["smoke_task"], "initial")
        context = dict(call, manifest_sha256=self.manifest["manifest_sha256"],
                       call_id=self.manifest["manifest_sha256"] + "/" + call["call_id"], attempt=1)
        self.ledger.reserve(context["call_id"], self.manifest["manifest_sha256"], request,
                            reservation(request)["micro_usd"], "smoke")
        self.ledger.dispatched(context["call_id"], 1)
        return request, context

    def test_scope_manifest_and_shared_ledger_are_required_for_injected_clients(self):
        for scope in (None, "pilot", "smoke"):
            with self.subTest(scope=scope), self.assertRaises(ProviderFailure):
                self.provider(execution_scope=scope)
        for field, value in (("version", "pilot-v5"), ("manifest_sha256", "b" * 64),
                             ("paid_execution_allowed", True)):
            altered = dict(self.manifest, **{field: value})
            with self.subTest(field=field), self.assertRaises(ProviderFailure):
                self.provider(manifest=altered)
        with self.assertRaises(ProviderFailure):
            self.provider(ledger=None)
        self.client.responses.create.assert_not_called()

    def test_inactive_missing_or_foreign_lock_cannot_authorize_dispatch(self):
        from native_pilot.runner import campaign_lock
        with self.assertRaisesRegex(ProviderFailure, "active_campaign_lock_required"):
            self.provider(campaign_guard=None)
        with campaign_lock(Path(self.temp.name) / "other.lock") as foreign:
            with self.assertRaisesRegex(ProviderFailure, "active_campaign_lock_required"):
                self.provider(campaign_guard=foreign)
        provider = self.provider()
        request, context = self.reserve_initial()
        self.lock.__exit__(None, None, None)
        with self.assertRaisesRegex(ProviderFailure, "active_campaign_lock_required"):
            provider.create(request, execution_context=context)
        self.client.responses.create.assert_not_called()

    def test_authorized_dispatch_requires_reservation_context_and_frozen_request(self):
        provider = self.provider()
        request, context = self.reserve_initial()
        for change in ({"task_id": "livecodebench:338"}, {"sample": 2}, {"attempt": 3},
                       {"call_id": context["call_id"].replace("initial/0", "fresh/1")},
                       {"manifest_sha256": "b" * 64}):
            with self.subTest(change=change), self.assertRaises(ProviderFailure):
                provider.create(request, execution_context=dict(context, **change))
        with self.assertRaises(ProviderFailure):
            provider.create(request)
        changed = copy.deepcopy(request)
        changed["input"][-1]["content"] += " unauthorized change"
        with self.assertRaises(ProviderFailure):
            provider.create(changed, execution_context=context)
        self.client.responses.create.assert_not_called()
        self.assertEqual(provider.create(request, execution_context=context), response())
        with self.assertRaisesRegex(ProviderFailure, "already_dispatched"):
            provider.create(request, execution_context=context)
        self.client.responses.create.assert_called_once()

    def test_unreserved_request_and_different_physical_ledger_are_rejected(self):
        from native_pilot.runner import smoke_schedule
        provider = self.provider()
        call = smoke_schedule(self.manifest["smoke_task"])[0]
        context = dict(call, call_id=self.manifest["manifest_sha256"] + "/" + call["call_id"],
                       manifest_sha256=self.manifest["manifest_sha256"], attempt=1)
        with self.assertRaisesRegex(ProviderFailure, "reservation_required"):
            provider.create(build_request(self.manifest["smoke_task"], "initial"), execution_context=context)
        other = Ledger(Path(self.temp.name) / "other.sqlite")
        try:
            other.path = self.ledger.path
            with self.assertRaisesRegex(ProviderFailure, "shared_budget_ledger_required"):
                self.provider(ledger=other)
        finally:
            other.close()
        self.client.responses.create.assert_not_called()

    def test_one_authorization_cannot_bind_to_another_manifest_hash(self):
        self.provider()
        other = dict(self.manifest, manifest_sha256="b" * 64)
        with patch("native_pilot.provider._read_frozen_smoke_manifest", return_value=other):
            with self.assertRaisesRegex(ProviderFailure, "already_bound"):
                self.provider(manifest=other)
        self.client.responses.create.assert_not_called()

    def test_reinstated_policy_stops_before_sdk_dispatch(self):
        provider = self.provider()
        request, context = self.reserve_initial()
        with patch("native_pilot.provider._read_execution_policy", return_value={"paid_execution_allowed": False}):
            with self.assertRaisesRegex(ProviderFailure, "policy_hold"):
                provider.create(request, execution_context=context)
        self.client.responses.create.assert_not_called()

    def test_explicit_recovery_preserves_failed_auth_attempt_and_reservation(self):
        before = copy.deepcopy(self.ledger.rows(self.recovery['failed_manifest_sha256']))
        provider = self.provider()
        request, context = self.reserve_initial()
        provider.create(request, execution_context=context)
        self.assertEqual(self.ledger.rows(self.recovery['failed_manifest_sha256']), before)
        self.assertEqual(before[0]['state'], 'provider_failure')
        self.assertIsNone(before[0]['charged'])
        self.assertEqual(self.ledger.total(), before[0]['reserved'] + reservation(request)['micro_usd'])
        self.assertEqual(context['attempt'], 1)
        self.assertNotEqual(context['call_id'], self.recovery['failed_call_id'])

    def test_new_provider_failure_stops_direct_dispatch_of_later_continuation(self):
        from native_pilot.runner import smoke_schedule
        class APIError(Exception):
            status_code = 401
        self.client.responses.create.side_effect = [response(), APIError('private authentication body')]
        provider = self.provider()
        request, context = self.reserve_initial()
        initial_response = provider.create(request, execution_context=context)
        self.ledger.finish(context['call_id'], 1, initial_response,
                           {'status':'correct','protocol_valid':True})
        state = {'request':request, 'response':initial_response}
        for call in smoke_schedule(self.manifest['smoke_task'])[1:]:
            continuation = build_request(self.manifest['smoke_task'], call['condition'], state)
            scoped = dict(call, call_id=self.manifest['manifest_sha256']+'/'+call['call_id'],
                          manifest_sha256=self.manifest['manifest_sha256'], attempt=1)
            self.ledger.reserve(scoped['call_id'], self.manifest['manifest_sha256'], continuation,
                                reservation(continuation,state)['micro_usd'], 'smoke')
            self.ledger.dispatched(scoped['call_id'], 1)
            if call['condition'] == 'updated_retained':
                with self.assertRaises(ProviderFailure) as caught:
                    provider.create(continuation, execution_context=scoped)
                self.assertEqual(caught.exception.status_code, 401)
                self.ledger.provider_failure(scoped['call_id'], 1, 'provider_failure', {
                    'status':'provider_failure','protocol_valid':False,
                    'provider_error':caught.exception.as_dict()})
            else:
                with self.assertRaisesRegex(ProviderFailure, 'smoke_stopped_after_provider_failure'):
                    provider.create(continuation, execution_context=scoped)
        self.assertEqual(self.client.responses.create.call_count, 2)

    def test_missing_changed_or_extended_predecessor_cannot_recover(self):
        row = self.ledger.latest(self.recovery['failed_call_id'])
        for field, value in (('state','transport_uncertain'), ('reserved',row['reserved']+1),
                             ('charged',0), ('response','{}'), ('outcome','{}')):
            with self.ledger.transaction():
                self.ledger.db.execute('UPDATE attempts SET '+field+'=? WHERE call_id=?',
                                       (value,row['call_id']))
            with self.subTest(field=field), self.assertRaisesRegex(ProviderFailure, 'predecessor_changed'):
                self.provider()
            with self.ledger.transaction():
                self.ledger.db.execute('UPDATE attempts SET '+field+'=? WHERE call_id=?',
                                       (row[field],row['call_id']))
        request = build_request(self.manifest['smoke_task'], 'initial')
        self.ledger.reserve(row['call_id']+'/extra', row['manifest_hash'], request,
                            reservation(request)['micro_usd'], 'smoke')
        with self.assertRaisesRegex(ProviderFailure, 'predecessor_changed'):
            self.provider()
        self.client.responses.create.assert_not_called()

    def test_preserved_v3_authorization_and_dispatch_claims_are_required(self):
        for key in ('execution_authorization/'+self.recovery['failed_authorization_id'],
                    'provider_dispatch/'+self.recovery['failed_call_id']+'/1'):
            with self.ledger.transaction():
                self.ledger.db.execute('DELETE FROM meta WHERE key=?', (key,))
            with self.subTest(key=key), self.assertRaisesRegex(ProviderFailure, 'prior_authorization_changed'):
                self.provider()
            with self.ledger.transaction():
                self.ledger.db.execute('INSERT INTO meta VALUES (?,?)',
                                       (key,self.recovery['failed_manifest_sha256']))
        self.client.responses.create.assert_not_called()

    def test_new_authorization_label_cannot_reset_global_recovery_assignment(self):
        self.provider()
        authorization = dict(SMOKE_AUTHORIZATION, authorization_id='unauthorized-additional-recovery')
        other = dict(self.manifest, manifest_sha256='b'*64, protocol_smoke_authorization=authorization)
        policy = dict(self.policy, protocol_smoke=authorization)
        with patch('native_pilot.provider.SMOKE_AUTHORIZATION', authorization), \
             patch('native_pilot.provider._read_execution_policy', return_value=policy), \
             patch('native_pilot.provider._read_frozen_smoke_manifest', return_value=other):
            with self.assertRaisesRegex(ProviderFailure, 'already_bound'):
                self.provider(manifest=other)
        self.assertIsNone(self.ledger.db.execute('SELECT value FROM meta WHERE key=?',
            ('execution_authorization/'+authorization['authorization_id'],)).fetchone())
        self.client.responses.create.assert_not_called()

    def test_recovery_record_requires_exact_core_and_both_frozen_hash_bindings(self):
        root = Path(self.temp.name)
        path = root/AUTHENTICATION_RECOVERY_PATH
        path.parent.mkdir()
        record = {'recovery':self.recovery, 'note':'Synthetic offline record'}
        path.write_text(json.dumps(record))
        manifest = copy.deepcopy(self.manifest)
        sha = file_digest(path)
        manifest['authentication_recovery']['sha256'] = sha
        manifest['provenance_hashes'][AUTHENTICATION_RECOVERY_PATH] = sha
        with patch('native_pilot.provider.ROOT', root):
            self.assertEqual(read_authentication_recovery_record(manifest), self.recovery)
            for field in ('authentication_recovery', 'provenance_hashes'):
                altered = copy.deepcopy(manifest); altered[field] = {}
                with self.subTest(field=field), self.assertRaisesRegex(ProviderFailure, 'record_unverified'):
                    read_authentication_recovery_record(altered)
            record['recovery'] = dict(self.recovery, max_recoveries=2)
            path.write_text(json.dumps(record))
            sha = file_digest(path)
            manifest['authentication_recovery']['sha256'] = sha
            manifest['provenance_hashes'][AUTHENTICATION_RECOVERY_PATH] = sha
            with self.assertRaisesRegex(ProviderFailure, 'record_unverified'):
                read_authentication_recovery_record(manifest)


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

    def test_actual_policy_hold_blocks_injected_callable_client(self):
        # Do not patch or modify the actual user policy in this regression.
        client = Mock()
        client.responses.create.return_value = response()
        with self.assertRaises(ProviderFailure) as caught:
            OpenAIProvider(allow_paid=True, client=client).create(build_request(TASK, "initial"))
        self.assertEqual(caught.exception.kind, "paid_execution_policy_hold")
        self.assertFalse(caught.exception.uncertain_charge)
        client.responses.create.assert_not_called()

    def test_reinstated_hold_blocks_an_existing_injected_client(self):
        client = Mock()
        with patch("native_pilot.provider._require_paid_execution_policy", side_effect=[
                None, ProviderFailure("paid_execution_policy_hold", uncertain_charge=False)]):
            provider = OpenAIProvider(allow_paid=True, client=client)
            with self.assertRaises(ProviderFailure) as caught:
                provider.create(build_request(TASK, "initial"))
        self.assertEqual(caught.exception.kind, "paid_execution_policy_hold")
        self.assertFalse(caught.exception.uncertain_charge)
        client.responses.create.assert_not_called()

    @patch("native_pilot.provider._require_paid_execution_policy")
    def test_mock_provider_serializes_without_losing_output_metadata(self, _policy):
        client = Mock()
        client.responses.create.return_value = response()
        provider = OpenAIProvider(allow_paid=True, client=client)
        self.assertEqual(provider.create(build_request(TASK, "initial")), response())
        client.responses.create.assert_called_once()

    @patch("native_pilot.provider._require_paid_execution_policy")
    def test_forbidden_parameters_block_before_dispatch(self, _policy):
        client = Mock()
        provider = OpenAIProvider(allow_paid=True, client=client)
        request = build_request(TASK, "initial")
        request["previous_response_id"] = "forbidden"
        with self.assertRaises(ProtocolError):
            provider.create(request)
        client.responses.create.assert_not_called()

    @patch("native_pilot.provider._require_paid_execution_policy")
    def test_safe_transport_failure_and_no_sdk_retry(self, _policy):
        client = Mock()
        client.responses.create.side_effect = ConnectionError("SECRET api key body")
        provider = OpenAIProvider(allow_paid=True, client=client)
        with self.assertRaises(ProviderFailure) as caught:
            provider.create(build_request(TASK, "initial"))
        self.assertTrue(caught.exception.retryable)
        self.assertTrue(caught.exception.uncertain_charge)
        self.assertNotIn("SECRET", str(caught.exception))
        client.responses.create.assert_called_once()

    @patch("native_pilot.provider._require_paid_execution_policy")
    def test_invalid_request_status_is_protocol_failure_without_retry(self, _policy):
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
    @patch("native_pilot.provider._require_paid_execution_policy")
    def test_actual_pinned_sdk_serialization_with_offline_http_transport(self, _policy):
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
