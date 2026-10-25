import contextlib
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from native_pilot.cli import main, report, dry_run
from native_pilot.budget import Ledger
from test_exploratory_runner import fixture_manifest


class ExploratoryCliTests(unittest.TestCase):
    def invoke(self,result,*,allow=True):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); manifest=fixture_manifest(); ledger=Mock()
            with patch('native_pilot.cli.ROOT',root), \
                 patch('native_pilot.cli.load_manifest',return_value=manifest), \
                 patch('native_pilot.cli.paid_preflight') as preflight, \
                 patch('native_pilot.cli.atomic_json') as write, \
                 patch('native_pilot.cli.show') as show, \
                 patch('native_pilot.budget.Ledger',return_value=ledger), \
                 patch('native_pilot.runner.campaign_lock',return_value=contextlib.nullcontext(object())), \
                 patch('native_pilot.runner.execute',return_value=result) as execute, \
                 patch('native_pilot.provider.OpenAIProvider') as provider, \
                 patch('native_pilot.assets.hydrate_tasks',return_value=manifest['tasks']), \
                 patch('native_pilot.analysis.analyze',side_effect=AssertionError('Inferential analysis must not run')):
                code=main(['explore']+(['--allow-paid'] if allow else []))
            if allow:
                preflight.assert_called_once_with(manifest,{},execution_scope='exploratory_pilot')
                self.assertEqual(provider.call_args.kwargs['execution_scope'],'exploratory_pilot')
                self.assertEqual(execute.call_args.kwargs['execution_scope'],'exploratory_pilot')
                self.assertIsNone(execute.call_args.kwargs['schedule'])
                self.assertEqual(execute.call_args.kwargs['tasks'],manifest['tasks'])
                self.assertEqual(write.call_args.args[0].name,'explore-synthetic-exploratory-runner.json')
                ledger.close.assert_called_once()
            else:
                execute.assert_not_called(); provider.assert_not_called(); preflight.assert_not_called()
            return code,show.call_args.args[0] if show.called else None

    def test_explore_requires_explicit_allow_paid_even_with_valid_frozen_manifest(self):
        self.assertEqual(self.invoke({},allow=False)[0],2)

    def test_complete_exploration_uses_separate_scope_and_descriptive_report(self):
        result={'stop_reason':None,'attempts':28,'accounted_usd':2,
                'feasibility_report':{'all_planned_calls_completed':True,'completed_task_blocks':4,
                                      'report_type':'descriptive_feasibility'}}
        code,summary=self.invoke(result)
        self.assertEqual(code,0)
        self.assertEqual(summary['feasibility'],result['feasibility_report'])
        self.assertNotIn('analysis',summary)

    def test_partial_or_missing_report_never_exits_successfully(self):
        for state in ({},{'all_planned_calls_completed':False}):
            with self.subTest(state=state):
                result={'stop_reason':None,'attempts':7,'accounted_usd':1,'feasibility_report':state}
                self.assertEqual(self.invoke(result)[0],1)
        result={'stop_reason':'deadline elapsed','attempts':7,'accounted_usd':1,
                'feasibility_report':{'all_planned_calls_completed':False}}
        self.assertEqual(self.invoke(result)[0],1)

    def test_report_before_start_is_descriptive_without_binding_or_starting_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'budget.sqlite'
            with patch('native_pilot.analysis.analyze',side_effect=AssertionError('No inferential analysis')):
                absent=report(fixture_manifest(),path)
                self.assertFalse(path.exists())
                ledger=Ledger(path)
                before=[tuple(row) for row in ledger.db.execute('SELECT * FROM meta ORDER BY key')]
                ledger.close()
                empty=report(fixture_manifest(),path)
                ledger=Ledger(path)
                self.assertEqual([tuple(row) for row in ledger.db.execute('SELECT * FROM meta ORDER BY key')],before)
                ledger.close()
            for value in (absent,empty):
                self.assertEqual(value['report_type'],'descriptive_feasibility')
                self.assertEqual(value['planned_calls'],28)
                self.assertEqual(value['completed_protocol_valid_responses'],0)
                self.assertFalse(value['accounting']['scope']['bound'])
                self.assertEqual(value['accounting']['scope']['elapsed_seconds'],0)
                self.assertEqual(value['accounting']['scope']['remaining_unreserved_usd'],5)
                self.assertIsNone(value['all_selected_tasks']['by_condition']['initial']['accuracy'])

    def test_dry_run_describes_scope_cap_and_deadline_without_old_gate(self):
        manifest=fixture_manifest(); manifest.update(status='frozen',planned_counts={'responses':28})
        value=dry_run(manifest)
        self.assertEqual(value['budget']['additional_scope_usd'],5)
        self.assertEqual(value['budget']['hard_total_usd'],40)
        self.assertEqual(value['budget']['dispatch_deadline_seconds_from_first_reservation'],1800)
        self.assertEqual(value['assignments'],manifest['schedule'])
        self.assertEqual(value['analysis'],'descriptive_feasibility')


if __name__=='__main__': unittest.main()
