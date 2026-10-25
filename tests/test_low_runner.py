"""Offline low-effort runner tests: temporary ledgers and synthetic outputs only."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_pilot.budget import Ledger, LOW_EFFORT_SCOPE_ID, reservation
from native_pilot.exploratory import TASK_IDS
from native_pilot.low_runner import execute, report
from native_pilot.provider import ProviderFailure, build_request, normalize_replay_output
from native_pilot.util import digest
from test_provider import TASK, response


class LowFixtureProvider:
    def __init__(self, behavior=None):
        self.requests = []
        self.behavior = behavior

    def create(self, request):
        self.requests.append(copy.deepcopy(request))
        if self.behavior:
            override = self.behavior(request, len(self.requests))
            if override is not None:
                return override
        value = response(request['reasoning']['context'])
        value['reasoning']['effort'] = 'low'
        value['output'][-1]['content'][0]['text'] = '43'
        return value


class LowRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Ledger(Path(self.temp.name) / 'budget.sqlite')
        self.addCleanup(self.ledger.close)
        self.now = [1000000.0]
        clock = patch('native_pilot.budget._wall_time', side_effect=lambda: self.now[0])
        clock.start()
        self.addCleanup(clock.stop)
        tasks = [dict(copy.deepcopy(TASK), task_id=tid, domain='math', unchanged_control=False,
                      original={'answer': '42'}, updated={'answer': '43'}) for tid in TASK_IDS]
        self.checkpoints, inherited = {}, {}
        for index, task in enumerate(tasks):
            tid = task['task_id']
            request = build_request(task, 'initial')
            value = response()
            value['output'][0]['status'] = None
            correct = index != 3
            if not correct:
                value['output'][-1]['content'][0]['text'] = '999'
            outcome = {'status': 'correct' if correct else 'incorrect',
                       'protocol_valid': True, 'response_status': 'completed',
                       'grade': {'status': 'correct' if correct else 'incorrect', 'correct': correct}}
            source_id = 'synthetic-v6/' + tid + '/initial/0'
            attempt = self.ledger.reserve(source_id, 'synthetic-v6', request,
                                          reservation(request)['micro_usd'], 'exploratory_pilot')
            self.ledger.dispatched(source_id, attempt)
            self.ledger.finish(source_id, attempt, value, outcome)
            self.checkpoints[tid] = {'request': request, 'response': value}
            inherited[tid] = {'outcome': outcome, 'source_call_id': source_id,
                              'source_attempt': attempt, 'source_manifest_sha256': 'synthetic-v6',
                              'checkpoint_sha256': digest(self.checkpoints[tid])}
        self.manifest = {'manifest_sha256': 'synthetic-low-v7', 'tasks': tasks,
                         'settings': {'model': 'gpt-6.1-sol', 'reasoning_effort': 'low',
                                      'max_output_tokens': 32768},
                         'inherited_initials': inherited,
                         'schedule': [{'call_id': f'{tid}/{branch}/{sample}', 'task_id': tid,
                                       'condition': branch, 'sample': sample}
                                      for tid in TASK_IDS for sample in (1, 2)
                                      for branch in ('updated_retained', 'updated_dropped', 'fresh')]}
        verification = patch('native_pilot.low_effort.verify_initials', return_value=self.checkpoints)
        verification.start()
        self.addCleanup(verification.stop)
        self.prior_rows = copy.deepcopy(self.ledger.rows())

    def test_24_calls_inherit_exact_checkpoints_and_resume_without_new_initials(self):
        provider = LowFixtureProvider()
        result = execute(self.manifest, self.ledger, provider)
        self.assertIsNone(result['stop_reason'])
        self.assertEqual(len(provider.requests), 24)
        self.assertEqual(self.ledger.rows('synthetic-v6'), self.prior_rows)
        self.assertEqual(len(self.ledger.rows(self.manifest['manifest_sha256'])), 24)
        for task_index, tid in enumerate(TASK_IDS):
            block = provider.requests[task_index * 6:task_index * 6 + 6]
            checkpoint = self.checkpoints[tid]
            expected = checkpoint['request']['input'] + normalize_replay_output(checkpoint['response']['output'])
            for position in (0, 1, 3, 4):
                self.assertEqual(block[position]['input'][:-1], expected)
                self.assertEqual(block[position]['reasoning']['effort'], 'low')
            for position in (2, 5):
                self.assertEqual(len(block[position]['input']), 1)
            for left, right in ((0, 1), (3, 4)):
                retained, dropped = copy.deepcopy(block[left]), copy.deepcopy(block[right])
                self.assertEqual(retained['reasoning'].pop('context'), 'all_turns')
                self.assertEqual(dropped['reasoning'].pop('context'), 'current_turn')
                self.assertEqual(retained, dropped)
        detail = result['feasibility_report']
        self.assertTrue(detail['all_planned_calls_completed'])
        self.assertEqual(detail['completed_task_blocks'], 4)
        self.assertEqual(detail['initial_correct_subset']['n_tasks'], 3)
        self.assertEqual(detail['initial_correct_subset']['by_condition']['updated_retained']['correct_n'], 6)
        self.assertEqual(detail['all_selected_tasks']['by_condition']['updated_retained']['correct_n'], 8)
        self.assertEqual(len(detail['calls']), 24)
        self.assertTrue(all(call['usage']['output_tokens_details']['reasoning_tokens'] == 25
                            for call in detail['calls']))
        self.assertNotIn('encrypted_content', json.dumps(detail))
        before = copy.deepcopy(self.ledger.rows())
        start = self.ledger.scope_status(LOW_EFFORT_SCOPE_ID)['started_at']
        self.now[0] += 3600
        resumed = LowFixtureProvider()
        self.assertTrue(execute(self.manifest, self.ledger, resumed)['feasibility_report']['all_planned_calls_completed'])
        self.assertEqual(resumed.requests, [])
        self.assertEqual(self.ledger.rows(), before)
        self.assertEqual(self.ledger.scope_status(LOW_EFFORT_SCOPE_ID)['started_at'], start)

    def test_incorrect_revision_does_not_suppress_later_calls(self):
        def wrong(request, index):
            if index == 1:
                value = response(request['reasoning']['context'])
                value['reasoning']['effort'] = 'low'
                value['output'][-1]['content'][0]['text'] = '999'
                return value
        provider = LowFixtureProvider(wrong)
        result = execute(self.manifest, self.ledger, provider)
        self.assertIsNone(result['stop_reason'])
        self.assertEqual(len(provider.requests), 24)
        self.assertEqual(result['feasibility_report']['all_selected_tasks']['by_condition']['updated_retained']['correct_n'], 7)

    def test_wrong_returned_effort_is_terminal_and_resume_never_redispatches(self):
        provider = LowFixtureProvider(lambda request, _: response(request['reasoning']['context']))
        result = execute(self.manifest, self.ledger, provider)
        self.assertEqual(result['stop_reason'], 'protocol_failure')
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(result['feasibility_report']['completed_protocol_valid_responses'], 0)
        resumed = LowFixtureProvider()
        self.assertEqual(execute(self.manifest, self.ledger, resumed)['stop_reason'], 'protocol_failure')
        self.assertEqual(resumed.requests, [])

    def test_grading_failure_preserves_response_without_resampling(self):
        provider = LowFixtureProvider()
        def broken(*args, **kwargs):
            raise RuntimeError('synthetic grader infrastructure failure')
        result = execute(self.manifest, self.ledger, provider, grader=broken)
        self.assertEqual(result['stop_reason'], 'protocol_failure')
        rows = self.ledger.rows(self.manifest['manifest_sha256'])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['response'])
        self.assertIsNotNone(rows[0]['charged'])
        resumed = LowFixtureProvider()
        execute(self.manifest, self.ledger, resumed)
        self.assertEqual(resumed.requests, [])

    def test_only_one_transport_retry_preserves_uncertain_charge(self):
        def once(request, index):
            if index == 1:
                raise ProviderFailure('transport_failure', retryable=True, uncertain_charge=True)
        provider = LowFixtureProvider(once)
        result = execute(self.manifest, self.ledger, provider)
        self.assertIsNone(result['stop_reason'])
        self.assertEqual(len(provider.requests), 25)
        rows = self.ledger.rows(self.manifest['manifest_sha256'])
        self.assertEqual(rows[0]['state'], 'transport_uncertain')
        self.assertIsNone(rows[0]['charged'])
        self.assertEqual(rows[1]['attempt'], 2)
        self.assertEqual(result['feasibility_report']['accounting']['transport_retries_this_manifest'], 1)
        def always(request, index):
            raise ProviderFailure('transport_failure', retryable=True, uncertain_charge=True)
        # A separate fresh fixture is exercised by another test; this completed
        # scope must never dispatch again, regardless of provider behavior.
        resumed = LowFixtureProvider(always)
        execute(self.manifest, self.ledger, resumed)
        self.assertEqual(resumed.requests, [])

    def test_second_transport_failure_stops_and_does_not_get_a_third_attempt(self):
        def always(request, index):
            raise ProviderFailure('transport_failure', retryable=True, uncertain_charge=True)
        provider = LowFixtureProvider(always)
        first = execute(self.manifest, self.ledger, provider)
        self.assertEqual(first['stop_reason'], 'transport_retry_exhausted')
        self.assertEqual(len(provider.requests), 2)
        execute(self.manifest, self.ledger, provider)
        self.assertEqual(len(provider.requests), 2)

    def test_deadline_is_persistent_and_only_v7_interrupted_rows_are_recovered(self):
        old_request = build_request(self.manifest['tasks'][0], 'fresh')
        attempt = self.ledger.reserve('other-version/pending', 'other-version', old_request,
                                      reservation(old_request)['micro_usd'])
        self.ledger.dispatched('other-version/pending', attempt)
        old_row = copy.deepcopy(self.ledger.latest('other-version/pending'))
        def elapsed(request, index):
            if index == 6:
                self.now[0] += 1800
        provider = LowFixtureProvider(elapsed)
        first = execute(self.manifest, self.ledger, provider)
        self.assertIn('deadline elapsed', first['stop_reason'])
        self.assertEqual(len(provider.requests), 6)
        self.assertEqual(first['feasibility_report']['completed_task_blocks'], 1)
        self.assertEqual(self.ledger.latest('other-version/pending'), old_row)
        self.assertEqual(self.ledger.rows('synthetic-v6'), self.prior_rows)
        self.now[0] += 1000
        resumed = LowFixtureProvider()
        again = execute(self.manifest, self.ledger, resumed)
        self.assertEqual(resumed.requests, [])
        self.assertIn('deadline elapsed', again['stop_reason'])

    def test_additional_two_dollar_cap_preserves_partial_coverage(self):
        def costly(request, index):
            value = response(request['reasoning']['context'])
            value['reasoning']['effort'] = 'low'
            value['usage']['output_tokens'] = 32000
            value['usage']['total_tokens'] = 32020
            value['output'][-1]['content'][0]['text'] = '43'
            return value
        provider = LowFixtureProvider(costly)
        result = execute(self.manifest, self.ledger, provider)
        self.assertIn('additional $2', result['stop_reason'])
        self.assertGreater(len(provider.requests), 0)
        self.assertLess(len(provider.requests), 24)
        detail = result['feasibility_report']
        self.assertLessEqual(detail['accounting']['scope']['accounted_micro_usd'], 2000000)
        self.assertFalse(detail['all_planned_calls_completed'])
        self.assertGreater(sum(row['by_condition']['fresh']['missing_n'] for row in detail['per_task']), 0)

    def test_report_before_execution_has_no_new_rows_or_started_scope(self):
        before = copy.deepcopy(self.ledger.rows())
        detail = report(self.manifest, self.ledger)
        self.assertEqual(detail['planned_calls'], 24)
        self.assertEqual(detail['completed_protocol_valid_responses'], 0)
        self.assertFalse(detail['accounting']['scope']['bound'])
        self.assertEqual(self.ledger.rows(), before)


if __name__ == '__main__':
    unittest.main()
