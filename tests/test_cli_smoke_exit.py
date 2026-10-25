import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from native_pilot.cli import main


class SmokeCliExitTests(unittest.TestCase):
    def invoke(self, result):
        # Every operation is mocked or uses a temporary directory; no actual
        # ledger, provider, Docker process, or repository artifact is touched.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = {'manifest_sha256': 'fixture', 'tasks': [], 'schedule': [],
                        'smoke_task': {'task_id': 'fixture:smoke'}}
            ledger = Mock()
            with patch('native_pilot.cli.ROOT', root), \
                 patch('native_pilot.cli.load_manifest', return_value=manifest), \
                 patch('native_pilot.cli.paid_preflight'), \
                 patch('native_pilot.cli.atomic_json'), \
                 patch('native_pilot.cli.show') as show, \
                 patch('native_pilot.budget.Ledger', return_value=ledger), \
                 patch('native_pilot.runner.campaign_lock', return_value=contextlib.nullcontext(object())), \
                 patch('native_pilot.runner.execute', return_value=result) as execute, \
                 patch('native_pilot.provider.OpenAIProvider') as provider, \
                 patch('native_pilot.assets.hydrate_tasks', return_value=[]):
                code = main(['smoke', '--allow-paid'])
            ledger.close.assert_called_once()
            provider.assert_called_once()
            self.assertEqual(execute.call_args.kwargs['execution_scope'], 'protocol_smoke')
            return code, show.call_args.args[0]

    @staticmethod
    def result(passed, stop_reason=None):
        return {'stop_reason': stop_reason, 'attempts': 1, 'accounted_usd': 0.4,
                'protocol_report': {'protocol_passed': passed, 'calls': [],
                    'accounting': {'outstanding_reservations_usd_all_versions': 0.4}}}

    def test_incomplete_smoke_without_stop_reason_is_nonzero(self):
        code, summary = self.invoke(self.result(False))
        self.assertEqual(code, 1)
        self.assertFalse(summary['protocol_passed'])

    def test_missing_smoke_report_is_nonzero(self):
        result = self.result(True); result.pop('protocol_report')
        self.assertEqual(self.invoke(result)[0], 1)

    def test_completed_valid_smoke_is_zero(self):
        self.assertEqual(self.invoke(self.result(True))[0], 0)

    def test_successful_recovery_summary_preserves_prior401_and_reservation(self):
        result = self.result(True)
        prior = {'call_id': 'old-v3/initial/0', 'attempt': 1, 'http_status': 401,
                 'attempt_sha256': 'fixture-hash', 'reserved_usd': 0.4,
                 'charged_micro_usd': None, 'preservation_verified': True}
        result['protocol_report']['authentication_recovery_prior_failure'] = prior
        code, summary = self.invoke(result)
        self.assertEqual(code, 0)
        self.assertEqual(summary['authentication_recovery_prior_failure'], prior)
        self.assertEqual(summary['outstanding_reservations_usd_all_versions'], 0.4)

    def test_http401_and_unreconciled_reservation_are_visible_in_summary(self):
        result = self.result(False, 'provider_failure_http_401')
        result['protocol_report']['calls'] = [{'call_id': 'fixture/initial/0',
            'provider_error': {'kind': 'provider_failure', 'status_code': 401,
                               'retryable': False, 'uncertain_charge': False}}]
        code, summary = self.invoke(result)
        self.assertEqual(code, 1)
        self.assertEqual(summary['stop_reason'], 'provider_failure_http_401')
        self.assertEqual(summary['provider_errors'][0]['status_code'], 401)
        self.assertEqual(summary['outstanding_reservations_usd_all_versions'], 0.4)


if __name__ == '__main__':
    unittest.main()
