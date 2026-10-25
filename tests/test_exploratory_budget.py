"""Persistent scope limits use temporary databases and a controlled wall clock."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_pilot.budget import (
    BudgetRefused, CAP_MICRO_USD, EXPLORATORY_CAP_MICRO_USD,
    EXPLORATORY_DURATION_SECONDS, EXPLORATORY_SCOPE_ID, Ledger,
)


class ExploratoryBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'budget.sqlite'
        self.ledger = Ledger(self.path)
        self.addCleanup(lambda: self.ledger.close())
        self.now = 1_800_000_000.0
        clock = patch('native_pilot.budget._wall_time', side_effect=lambda: self.now)
        clock.start(); self.addCleanup(clock.stop)
        self.manifest = 'a'*64
        self.scope = EXPLORATORY_SCOPE_ID
        self.request = {'input': [{'role': 'user', 'content': 'offline fixture'}]}

    def bind(self):
        self.ledger.bind_scope(self.scope, self.manifest)

    def reserve(self, name, amount=100, **changes):
        options = {'scope_id': self.scope}; options.update(changes)
        return self.ledger.reserve(self.manifest+'/'+name, self.manifest,
                                   self.request, amount, 'exploratory', **options)

    def reopen(self):
        self.ledger.close()
        self.ledger = Ledger(self.path)

    def test_unbound_status_is_read_only_and_binding_does_not_start_clock(self):
        before = self.path.read_bytes()
        self.assertIsNone(self.ledger.scope_status(self.scope))
        self.assertEqual(self.path.read_bytes(), before)
        self.bind()
        before = self.path.read_bytes()
        self.now += 100_000
        status = self.ledger.scope_status(self.scope)
        self.assertEqual(status['status'], 'not_started')
        self.assertIsNone(status['started_at'])
        self.assertIsNone(status['deadline_at'])
        self.assertEqual(status['remaining_seconds'], 1800)
        self.assertEqual(status['attempts'], 0)
        self.assertEqual(self.path.read_bytes(), before)
        self.bind()
        self.assertEqual(self.ledger.scope_status(self.scope), status)

    def test_first_reservation_starts_clock_and_resume_cannot_reset_it(self):
        self.bind(); self.reserve('initial')
        initial = self.ledger.scope_status(self.scope)
        self.assertEqual(initial['started_at_epoch_seconds'], self.now)
        self.assertEqual(initial['deadline_epoch_seconds'], self.now + 1800)
        self.now += 100
        self.reopen(); self.bind(); self.reserve('fresh')
        resumed = self.ledger.scope_status(self.scope)
        self.assertEqual(resumed['started_at'], initial['started_at'])
        self.assertEqual(resumed['deadline_at'], initial['deadline_at'])
        self.assertEqual(resumed['elapsed_seconds'], 100)
        self.assertEqual(resumed['remaining_seconds'], 1700)

    def test_new_id_manifest_or_wider_cap_cannot_reset_authorization(self):
        self.bind(); self.reserve('initial')
        for scope, manifest, cap, duration in (
                (self.scope+'-new', self.manifest, 5_000_000, 1800),
                (self.scope, 'b'*64, 5_000_000, 1800),
                (self.scope, self.manifest, 5_000_001, 1800),
                (self.scope, self.manifest, 5_000_000, 1801)):
            before = self.path.read_bytes()
            with self.subTest(scope=scope, manifest=manifest, cap=cap, duration=duration), self.assertRaises(BudgetRefused):
                self.ledger.bind_scope(scope, manifest, cap_micro_usd=cap, duration_seconds=duration)
            self.assertEqual(self.path.read_bytes(), before)

    def test_binding_after_unscoped_attempt_and_unscoped_bound_reservation_rejected(self):
        self.ledger.reserve('legacy', self.manifest, self.request, 10)
        with self.assertRaisesRegex(BudgetRefused, 'unscoped attempts'):
            self.bind()
        self.assertIsNone(self.ledger.scope_status(self.scope))
        self.manifest = 'b'*64
        self.bind()
        for options in ({'scope_id': None}, {'scope_id': 'unknown'}):
            with self.subTest(options=options), self.assertRaises(BudgetRefused):
                self.reserve('wrong', **options)
        self.assertEqual(len(self.ledger.rows()), 1)

    def test_additional_cap_is_atomic_and_old_rows_are_preserved(self):
        self.ledger.reserve('old', 'old-manifest', self.request, 900_000, 'smoke')
        old = self.ledger.rows()
        self.bind(); self.reserve('all-scope-budget', EXPLORATORY_CAP_MICRO_USD)
        self.ledger.dispatched(self.manifest+'/all-scope-budget', 1)
        self.ledger.assert_scope_dispatch(self.scope, self.manifest, self.manifest+'/all-scope-budget', 1)
        with self.assertRaisesRegex(BudgetRefused, r'additional \$5'):
            self.reserve('overflow', 1)
        self.assertEqual(self.ledger.rows('old-manifest'), old)
        status = self.ledger.scope_status(self.scope)
        self.assertEqual(status['accounted_micro_usd'], 5_000_000)
        self.assertEqual(status['shared_accounted_micro_usd'], 5_900_000)
        self.assertEqual(status['remaining_unreserved_micro_usd'], 0)
        self.assertEqual(status['attempts'], 1)

    def test_shared_cap_still_applies_and_failed_first_reservation_does_not_start(self):
        self.ledger.reserve('old', 'old-manifest', self.request, CAP_MICRO_USD - 50)
        self.bind()
        with self.assertRaisesRegex(BudgetRefused, r'hard \$40'):
            self.reserve('too-large', 51)
        self.assertIsNone(self.ledger.scope_status(self.scope)['started_at'])
        self.reserve('fits', 50)
        self.assertEqual(self.ledger.total(), CAP_MICRO_USD)

    def test_reconciled_usage_replaces_reservation_but_unknown_retry_remains(self):
        self.bind(); self.reserve('call', 2_000_000)
        cid = self.manifest+'/call'
        self.ledger.dispatched(cid, 1); self.ledger.uncertain(cid, 1)
        self.assertEqual(self.reserve('call', 2_000_000), 2)
        self.ledger.dispatched(cid, 2)
        response = {'model': 'gpt-6.1-sol', 'service_tier': 'default', 'reasoning': {'mode': 'standard'},
                    'usage': {'input_tokens': 100, 'output_tokens': 20,
                              'input_tokens_details': {'cached_tokens': 0, 'cache_write_tokens': 0}}}
        self.ledger.finish(cid, 2, response, {'status': 'incorrect'})
        status = self.ledger.scope_status(self.scope)
        self.assertEqual(status['known_charges_micro_usd'], 400)
        self.assertEqual(status['outstanding_reservations_micro_usd'], 2_000_000)
        self.assertEqual(status['accounted_micro_usd'], 2_000_400)
        self.assertEqual(status['attempts'], 2)
        with self.assertRaisesRegex(BudgetRefused, 'already assigned'):
            self.reserve('call')

    def test_retry_cannot_exceed_scope_cap(self):
        self.bind(); self.reserve('call', 3_000_000)
        cid = self.manifest+'/call'
        self.ledger.dispatched(cid, 1); self.ledger.uncertain(cid, 1)
        with self.assertRaisesRegex(BudgetRefused, r'additional \$5'):
            self.reserve('call', 3_000_000)
        self.assertEqual(len(self.ledger.rows()), 1)
        self.assertEqual(self.ledger.total(), 3_000_000)

    def test_deadline_checked_before_reservation_and_latched_across_resume(self):
        self.bind(); self.reserve('first')
        self.now += EXPLORATORY_DURATION_SECONDS
        before = self.ledger.rows()
        with self.assertRaisesRegex(BudgetRefused, 'deadline elapsed'):
            self.reserve('late')
        self.assertEqual(self.ledger.rows(), before)
        self.now -= 1000
        self.reopen(); self.bind()
        with self.assertRaisesRegex(BudgetRefused, 'deadline elapsed'):
            self.reserve('rewound')
        self.assertEqual(self.ledger.scope_status(self.scope)['status'], 'deadline_elapsed')

    def test_deadline_between_reservation_and_dispatch_preserves_pending_reservation(self):
        self.bind(); self.reserve('pending', 700)
        cid = self.manifest+'/pending'
        self.ledger.dispatched(cid, 1)
        before = self.ledger.rows()
        self.now += 1800
        with self.assertRaisesRegex(BudgetRefused, 'deadline elapsed'):
            self.ledger.assert_scope_dispatch(self.scope, self.manifest, cid, 1)
        self.assertEqual(self.ledger.rows(), before)
        self.assertEqual(self.ledger.total(), 700)
        self.assertEqual(self.ledger.scope_status(self.scope)['outstanding_reservations_micro_usd'], 700)

    def test_backward_clock_fails_closed_and_cannot_be_reset(self):
        self.bind(); self.reserve('first')
        self.now += 60
        self.reserve('pending')
        cid = self.manifest+'/pending'; self.ledger.dispatched(cid, 1)
        self.now -= 1
        with self.assertRaisesRegex(BudgetRefused, 'clock moved backwards'):
            self.ledger.assert_scope_dispatch(self.scope, self.manifest, cid, 1)
        self.now += 100
        self.reopen(); self.bind()
        with self.assertRaisesRegex(BudgetRefused, 'clock moved backwards'):
            self.reserve('after-clock-recovers')

    def test_invalid_clock_never_starts_scope_or_inserts_attempt(self):
        self.bind(); self.now = float('nan')
        with self.assertRaisesRegex(BudgetRefused, 'clock is invalid'):
            self.reserve('bad-time')
        self.assertEqual(self.ledger.rows(), [])
        self.now = 1_800_000_000
        with self.assertRaisesRegex(BudgetRefused, 'clock is invalid'):
            self.reserve('later')

    def test_dispatch_requires_matching_live_reserved_attempt(self):
        self.bind(); self.reserve('first')
        cid = self.manifest+'/first'
        for scope, manifest, call, attempt in ((self.scope, self.manifest, cid, 1),
                (self.scope, 'b'*64, cid, 1), (self.scope, self.manifest, cid, 2)):
            with self.subTest(manifest=manifest, attempt=attempt), self.assertRaises(BudgetRefused):
                self.ledger.assert_scope_dispatch(scope, manifest, call, attempt)
        self.ledger.dispatched(cid, 1)
        self.ledger.assert_scope_dispatch(self.scope, self.manifest, cid, 1)

    def test_independent_connections_cannot_overallocate_last_scope_budget(self):
        self.bind(); self.reserve('first', 4_000_000)
        other = Ledger(self.path)
        try:
            other.bind_scope(self.scope, self.manifest)
            other.reserve(self.manifest+'/second', self.manifest, self.request, 1_000_000,
                          'exploratory', scope_id=self.scope)
            with self.assertRaisesRegex(BudgetRefused, r'additional \$5'):
                self.reserve('third', 1)
            self.assertEqual(other.total(), 5_000_000)
        finally:
            other.close()


if __name__ == '__main__':
    unittest.main()
