import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_pilot.budget import Ledger, reservation
from native_pilot import low_effort as low
from native_pilot.provider import build_request
from native_pilot.util import digest
from test_provider import TASK, response


class LowCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Ledger(Path(self.temp.name) / 'budget.sqlite')
        self.addCleanup(self.ledger.close)
        self.tasks = [dict(copy.deepcopy(TASK), task_id=tid) for tid in low.TASK_IDS]
        for index, task in enumerate(self.tasks):
            request = build_request(task, 'initial')
            call_id = low.PRIOR_MANIFEST_SHA256 + '/' + task['task_id'] + '/initial/0'
            attempt = self.ledger.reserve(call_id, low.PRIOR_MANIFEST_SHA256, request,
                                          reservation(request)['micro_usd'], 'exploratory_pilot')
            self.ledger.dispatched(call_id, attempt)
            status = 'incorrect' if index == 3 else 'correct'
            self.ledger.finish(call_id, attempt, response(), {
                'protocol_valid': True, 'status': status, 'response_status': 'completed',
                'grade': {'status': status}})
        self.m = {'manifest_sha256': 'new-v7', 'tasks': self.tasks,
                  'inherited_initials': low.bind_initials(self.ledger, self.tasks),
                  'historical_ledger_rows_sha256': digest(self.ledger.rows())}

    def test_all_four_bound_including_incorrect_without_new_rows(self):
        before = self.ledger.rows()
        got = low.verify_initials(self.ledger, self.m)
        self.assertEqual(list(got), list(low.TASK_IDS))
        self.assertEqual(self.m['inherited_initials'][low.TASK_IDS[-1]]['outcome']['grade']['status'], 'incorrect')
        self.assertEqual(self.ledger.rows(), before)
        self.assertEqual(len(low.make_schedule(self.tasks)), 24)
        self.assertFalse(any(c['condition'] == 'initial' for c in low.make_schedule(self.tasks)))

    def test_changed_original_grade_is_rejected(self):
        self.m['inherited_initials'][low.TASK_IDS[0]]['outcome']['grade']['status'] = 'incorrect'
        with self.assertRaisesRegex(ValueError, 'grade or ledger'):
            low.verify_initials(self.ledger, self.m)

    def test_changed_encrypted_checkpoint_is_rejected(self):
        row = self.ledger.rows()[0]
        value = json.loads(row['response'])
        value['output'][0]['encrypted_content'] = 'tampered'
        with self.ledger.transaction():
            self.ledger.db.execute('UPDATE attempts SET response=? WHERE call_id=?',
                                   (json.dumps(value), row['call_id']))
        with self.assertRaises(ValueError):
            low.verify_initials(self.ledger, self.m)

    def test_initial_request_effort_cannot_be_rewritten_low(self):
        row = self.ledger.rows()[0]
        value = json.loads(row['request'])
        value['reasoning']['effort'] = 'low'
        with self.ledger.transaction():
            self.ledger.db.execute('UPDATE attempts SET request=? WHERE call_id=?',
                                   (json.dumps(value), row['call_id']))
        with self.assertRaisesRegex(ValueError, 'usable high-effort'):
            low.bind_initials(self.ledger, self.tasks)

    def test_historical_reservation_mutation_is_rejected(self):
        with self.ledger.transaction():
            self.ledger.db.execute('UPDATE attempts SET reserved=reserved+1')
        with self.assertRaises(ValueError):
            low.verify_initials(self.ledger, self.m)

    def test_new_scope_rows_do_not_change_historical_binding(self):
        request = build_request(self.tasks[0], 'initial')
        self.ledger.reserve('new-v7/synthetic', 'new-v7', request,
                            reservation(request)['micro_usd'], 'low_effort_followup')
        self.assertEqual(len(low.verify_initials(self.ledger, self.m)), 4)

    def test_missing_ledger_preparation_never_creates_or_dispatches(self):
        root = Path(self.temp.name) / 'missing'
        with patch('native_pilot.provider.OpenAIProvider') as provider:
            with self.assertRaisesRegex(ValueError, 'existing shared v6 ledger'):
                low.prepare(root / 'cache', root=root)
            provider.assert_not_called()
        self.assertFalse((root / 'runs/budget.sqlite').exists())

    def test_preparation_reuses_frozen_manifest_without_requalifying(self):
        root = Path(self.temp.name)
        (root / 'runs').mkdir()
        (root / 'manifests').mkdir()
        existing = Ledger(root / 'runs/budget.sqlite')
        existing.close()
        (root / low.MANIFEST_PATH).write_text('{}')
        with patch.object(low, 'load_frozen', return_value=self.m), \
                patch.object(low, 'verify_initials') as verify, \
                patch('native_pilot.low_qualification.qualify') as qualify, \
                patch('native_pilot.provider.OpenAIProvider') as provider:
            self.assertEqual(low.prepare(root / 'cache', root=root), self.m)
            verify.assert_called_once()
            qualify.assert_not_called()
            provider.assert_not_called()


if __name__ == '__main__':
    unittest.main()
