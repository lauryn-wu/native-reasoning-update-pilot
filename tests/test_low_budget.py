"""The low-effort follow-up gets one durable $2 scope in the existing ledger."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_pilot.budget import (
    BudgetRefused, CAP_MICRO_USD, EXPLORATORY_SCOPE_ID, Ledger,
    LOW_EFFORT_CAP_MICRO_USD, LOW_EFFORT_DURATION_SECONDS, LOW_EFFORT_SCOPE_ID,
)


class LowBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'budget.sqlite'
        self.ledger = Ledger(self.path)
        self.addCleanup(lambda: self.ledger.close())
        self.manifest = '7'*64
        self.now = 1_800_000_000.0
        clock = patch('native_pilot.budget._wall_time', side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def bind(self, **changes):
        options = {'cap_micro_usd': LOW_EFFORT_CAP_MICRO_USD,
                   'duration_seconds': LOW_EFFORT_DURATION_SECONDS}
        options.update(changes)
        self.ledger.bind_scope(LOW_EFFORT_SCOPE_ID, self.manifest, **options)

    def reserve(self, name, amount=100):
        return self.ledger.reserve(self.manifest+'/'+name, self.manifest, {}, amount,
                                   'low_effort_followup', scope_id=LOW_EFFORT_SCOPE_ID)

    def reopen(self):
        self.ledger.close()
        self.ledger = Ledger(self.path)

    def test_fixed_registry_rejects_new_labels_caps_durations_and_rebinding(self):
        with self.assertRaises(BudgetRefused):
            self.ledger.bind_scope(LOW_EFFORT_SCOPE_ID, self.manifest)
        for changes in ({'cap_micro_usd': 2_000_001}, {'duration_seconds': 1801},
                        {'cap_micro_usd': 5_000_000}):
            with self.subTest(changes=changes), self.assertRaises(BudgetRefused):
                self.bind(**changes)
        with self.assertRaises(BudgetRefused):
            self.ledger.bind_scope(LOW_EFFORT_SCOPE_ID+'-retry', self.manifest,
                                   cap_micro_usd=2_000_000, duration_seconds=1800)
        self.bind()
        self.manifest = '8'*64
        with self.assertRaises(BudgetRefused):
            self.bind()

    def test_old_scope_and_rows_are_untouched_by_new_scope(self):
        self.ledger.reserve('legacy/failed', 'v3', {}, 354210, 'smoke')
        self.ledger.dispatched('legacy/failed', 1)
        self.ledger.provider_failure('legacy/failed', 1, 'provider_failure')
        self.ledger.bind_scope(EXPLORATORY_SCOPE_ID, 'v6')
        self.ledger.reserve('v6/old', 'v6', {}, 4000, 'exploratory',
                            scope_id=EXPLORATORY_SCOPE_ID)
        self.ledger.dispatched('v6/old', 1)
        old_rows = self.ledger.rows()
        old_meta = list(map(tuple, self.ledger.db.execute('SELECT * FROM meta ORDER BY key')))
        self.now += 100
        self.bind()
        self.reserve('new', 1000)
        self.ledger.recover_interrupted(manifest_hash=self.manifest)
        self.assertEqual(self.ledger.rows('v3'), old_rows[:1])
        self.assertEqual(self.ledger.rows('v6'), old_rows[1:])
        new_meta = dict(self.ledger.db.execute('SELECT * FROM meta'))
        for key, value in old_meta:
            self.assertEqual(new_meta[key], value)
        status = self.ledger.scope_status(LOW_EFFORT_SCOPE_ID)
        self.assertEqual(status['accounted_micro_usd'], 1000)
        self.assertEqual(status['shared_accounted_micro_usd'], 359210)

    def test_manifest_cannot_be_rebound_under_another_known_scope(self):
        self.ledger.bind_scope(EXPLORATORY_SCOPE_ID, self.manifest)
        with self.assertRaisesRegex(BudgetRefused, 'another exploratory scope'):
            self.bind()
        self.assertIsNone(self.ledger.scope_status(LOW_EFFORT_SCOPE_ID))

    def test_bound_manifest_cannot_omit_or_substitute_its_scope(self):
        self.bind()
        for scope in (None, EXPLORATORY_SCOPE_ID, LOW_EFFORT_SCOPE_ID+'-new'):
            with self.subTest(scope=scope), self.assertRaises(BudgetRefused):
                self.ledger.reserve('wrong', self.manifest, {}, 1, scope_id=scope)
        self.assertEqual(self.ledger.rows(), [])

    def test_new_scope_cap_is_shared_across_connections_and_resume(self):
        self.bind()
        self.reserve('first', 1_000_000)
        other = Ledger(self.path)
        try:
            other.bind_scope(LOW_EFFORT_SCOPE_ID, self.manifest,
                             cap_micro_usd=2_000_000, duration_seconds=1800)
            other.reserve('second', self.manifest, {}, 1_000_000,
                          scope_id=LOW_EFFORT_SCOPE_ID)
            with self.assertRaisesRegex(BudgetRefused, r'additional \$2'):
                self.reserve('overflow', 1)
        finally:
            other.close()
        self.reopen()
        self.bind()
        with self.assertRaisesRegex(BudgetRefused, r'additional \$2'):
            self.reserve('after-resume', 1)
        self.assertEqual(self.ledger.total(), 2_000_000)

    def test_shared_40_dollar_cap_still_limits_the_new_scope(self):
        self.ledger.reserve('historical', 'old', {}, CAP_MICRO_USD-50)
        self.bind()
        with self.assertRaisesRegex(BudgetRefused, r'hard \$40'):
            self.reserve('fails', 51)
        self.assertIsNone(self.ledger.scope_status(LOW_EFFORT_SCOPE_ID)['started_at'])
        self.reserve('fits', 50)
        self.assertEqual(self.ledger.total(), CAP_MICRO_USD)

    def test_charges_and_uncertain_retry_reservations_share_the_two_dollars(self):
        self.bind()
        self.reserve('call', 1_000_000)
        cid = self.manifest+'/call'
        self.ledger.dispatched(cid, 1)
        self.ledger.uncertain(cid, 1)
        self.assertEqual(self.reserve('call', 1_000_000), 2)
        self.ledger.dispatched(cid, 2)
        response = {'model': 'gpt-6.1-sol', 'service_tier': 'default',
                    'reasoning': {'mode': 'standard'},
                    'usage': {'input_tokens': 100, 'output_tokens': 20,
                              'input_tokens_details': {'cached_tokens': 0, 'cache_write_tokens': 0}}}
        self.ledger.finish(cid, 2, response, {'status': 'incorrect'})
        status = self.ledger.scope_status(LOW_EFFORT_SCOPE_ID)
        self.assertEqual(status['known_charges_micro_usd'], 400)
        self.assertEqual(status['outstanding_reservations_micro_usd'], 1_000_000)
        self.assertEqual(status['accounted_micro_usd'], 1_000_400)
        with self.assertRaisesRegex(BudgetRefused, r'additional \$2'):
            self.reserve('too-large', 1_000_000)
        self.reserve('fits', 999_600)
        self.assertEqual(self.ledger.total(), 2_000_000)

    def test_deadline_starts_at_first_reservation_and_never_resets_on_resume(self):
        self.bind()
        self.now += 5000
        self.assertEqual(self.ledger.scope_status(LOW_EFFORT_SCOPE_ID)['status'], 'not_started')
        self.reserve('first')
        deadline = self.now + 1800
        self.now += 60
        self.reopen()
        self.bind()
        self.reserve('second')
        self.assertEqual(self.ledger.scope_status(LOW_EFFORT_SCOPE_ID)['deadline_epoch_seconds'], deadline)
        self.now = deadline
        with self.assertRaisesRegex(BudgetRefused, 'deadline elapsed'):
            self.reserve('late')
        self.now -= 100
        self.reopen()
        self.bind()
        with self.assertRaisesRegex(BudgetRefused, 'deadline elapsed'):
            self.reserve('rewound')

    def test_deadline_dispatch_check_preserves_reservation(self):
        self.bind()
        self.reserve('pending', 123)
        cid = self.manifest+'/pending'
        self.ledger.dispatched(cid, 1)
        self.now += 1800
        with self.assertRaisesRegex(BudgetRefused, 'deadline elapsed'):
            self.ledger.assert_scope_dispatch(LOW_EFFORT_SCOPE_ID, self.manifest, cid, 1)
        self.assertEqual(self.ledger.total(), 123)
        self.assertEqual(self.ledger.latest(cid)['state'], 'dispatched')

    def test_backward_clock_latches_across_resume(self):
        self.bind()
        self.reserve('first')
        self.now += 10
        self.reserve('second')
        self.now -= 1
        with self.assertRaisesRegex(BudgetRefused, 'clock moved backwards'):
            self.reserve('backwards')
        self.now += 100
        self.reopen()
        self.bind()
        with self.assertRaisesRegex(BudgetRefused, 'clock moved backwards'):
            self.reserve('recovered-clock')

    def test_invalid_clock_latches_without_starting_or_spending(self):
        self.bind()
        self.now = float('nan')
        with self.assertRaisesRegex(BudgetRefused, 'clock is invalid'):
            self.reserve('invalid')
        self.assertEqual(self.ledger.rows(), [])
        self.now = 1_800_000_000.0
        self.reopen()
        with self.assertRaisesRegex(BudgetRefused, 'clock is invalid'):
            self.reserve('recovered-clock')

    def test_targeted_recovery_only_changes_its_manifest_and_retains_charges(self):
        self.ledger.reserve('old', 'old', {}, 1000)
        self.bind()
        self.reserve('reserved', 100)
        self.reserve('dispatched', 200)
        self.ledger.dispatched(self.manifest+'/dispatched', 1)
        old = self.ledger.rows('old')
        self.ledger.recover_interrupted(self.manifest)
        self.assertEqual(self.ledger.rows('old'), old)
        self.assertEqual({row['state'] for row in self.ledger.rows(self.manifest)}, {'transport_uncertain'})
        self.assertEqual(self.ledger.total(), 1300)
        with self.assertRaises(ValueError):
            self.ledger.recover_interrupted('')
        self.assertEqual(self.ledger.rows('old'), old)


if __name__ == '__main__':
    unittest.main()
