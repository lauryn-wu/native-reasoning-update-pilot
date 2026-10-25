"""Bounded exploratory runner tests use only synthetic responses and temp ledgers."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_pilot.budget import Ledger, EXPLORATORY_SCOPE_ID
from native_pilot.exploratory import TASK_IDS, make_schedule
from native_pilot.provider import DEFAULT_SETTINGS, ProviderFailure
from native_pilot.runner import execute
from test_provider import TASK, response
from test_runner import FixtureProvider


def fixture_manifest():
    tasks = [dict(copy.deepcopy(TASK), task_id=task_id, domain='math', unchanged_control=False,
                  original={'answer':'42'}, updated={'answer':'43'}) for task_id in TASK_IDS]
    return {'manifest_sha256':'synthetic-exploratory-runner', 'execution_scope':'exploratory_pilot',
            'tasks':tasks, 'schedule':make_schedule(tasks), 'settings':copy.deepcopy(DEFAULT_SETTINGS)}


class ExploratoryRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger=Ledger(Path(self.temp.name)/'budget.sqlite')
        self.addCleanup(self.ledger.close)
        self.manifest=fixture_manifest()
        self.now=[1000000.0]
        patcher=patch('native_pilot.budget._wall_time',side_effect=lambda:self.now[0])
        patcher.start(); self.addCleanup(patcher.stop)

    def run_fixture(self, provider):
        return execute(self.manifest,self.ledger,provider,execution_scope='exploratory_pilot')

    def test_seven_call_blocks_checkpoint_forks_and_resume_remain_unchanged(self):
        provider=FixtureProvider()
        first=self.run_fixture(provider)
        self.assertIsNone(first['stop_reason'])
        self.assertEqual(len(provider.requests),28)
        rows=self.ledger.rows()
        self.assertTrue(all(row['kind']=='exploratory_pilot' for row in rows))
        self.assertEqual([json.loads(row['outcome'])['condition'] for row in rows],
                         ['initial','updated_retained','updated_dropped','fresh',
                          'updated_retained','updated_dropped','fresh']*4)
        for offset in range(0,28,7):
            initial={'request':json.loads(rows[offset]['request']),'response':json.loads(rows[offset]['response'])}
            for branch in (1,2,4,5):
                request=json.loads(rows[offset+branch]['request'])
                self.assertEqual(request['input'][:-1],initial['request']['input']+initial['response']['output'])
            for branch in (3,6):
                self.assertEqual(len(json.loads(rows[offset+branch]['request'])['input']),1)
        report=first['feasibility_report']
        self.assertEqual(report['completed_task_blocks'],4)
        self.assertEqual(report['completed_retained_dropped_sample_pairs'],8)
        before=copy.deepcopy(rows),self.ledger.total(),self.ledger.scope_status(EXPLORATORY_SCOPE_ID)['started_at']
        self.now[0]+=600
        resumed=FixtureProvider()
        result=self.run_fixture(resumed)
        self.assertEqual(resumed.requests,[])
        self.assertEqual((self.ledger.rows(),self.ledger.total(),self.ledger.scope_status(EXPLORATORY_SCOPE_ID)['started_at']),before)
        self.assertEqual(result['feasibility_report']['accounting']['scope']['elapsed_seconds'],600)

    def test_additional_cap_stops_partial_block_without_counting_missing_as_wrong(self):
        def costly(request,index):
            value=response(request['reasoning']['context'])
            value['usage']['output_tokens']=32000
            value['usage']['total_tokens']=32020
            value['output'][-1]['content'][0]['text']='42' if index%7==1 else '43'
            return value
        provider=FixtureProvider(costly)
        result=self.run_fixture(provider)
        self.assertIn('additional $5',result['stop_reason'])
        self.assertEqual(len(provider.requests),15)
        report=result['feasibility_report']
        self.assertEqual(report['completed_task_blocks'],2)
        self.assertEqual(report['completed_protocol_valid_responses'],15)
        self.assertEqual(report['per_task'][2]['by_condition']['updated_retained']['graded_n'],0)
        self.assertIsNone(report['per_task'][2]['by_condition']['updated_retained']['accuracy'])
        self.assertLessEqual(report['accounting']['scope']['accounted_micro_usd'],5000000)
        self.assertEqual(report['accounting']['scope']['attempts'],15)
        again=FixtureProvider()
        self.run_fixture(again)
        self.assertEqual(again.requests,[])

    def test_deadline_after_first_complete_block_includes_resume_downtime(self):
        def elapsed(request,index):
            if index==7: self.now[0]+=1800
        provider=FixtureProvider(elapsed)
        result=self.run_fixture(provider)
        self.assertIn('deadline elapsed',result['stop_reason'])
        self.assertEqual(len(provider.requests),7)
        self.assertEqual(result['feasibility_report']['completed_task_blocks'],1)
        scope=self.ledger.scope_status(EXPLORATORY_SCOPE_ID)
        self.assertEqual(scope['elapsed_seconds'],1800)
        self.now[0]+=3600
        before=copy.deepcopy(self.ledger.rows())
        resumed=FixtureProvider()
        again=self.run_fixture(resumed)
        self.assertEqual(resumed.requests,[])
        self.assertEqual(self.ledger.rows(),before)
        self.assertEqual(again['feasibility_report']['accounting']['scope']['elapsed_seconds'],5400)
        self.assertEqual(again['feasibility_report']['accounting']['scope']['started_at'],scope['started_at'])

    def test_deadline_between_reserve_and_dispatch_preserves_reservation_without_retry(self):
        original=self.ledger.dispatched
        def delayed(call_id,attempt):
            original(call_id,attempt)
            self.now[0]+=1800
        provider=FixtureProvider()
        with patch.object(self.ledger,'dispatched',side_effect=delayed):
            first=self.run_fixture(provider)
        self.assertEqual(provider.requests,[])
        self.assertIn('deadline elapsed',first['stop_reason'])
        row=self.ledger.rows()[0]
        self.assertEqual(row['state'],'provider_failure')
        self.assertIsNone(row['charged'])
        self.assertEqual(self.ledger.total(),row['reserved'])
        second=self.run_fixture(provider)
        self.assertEqual(provider.requests,[])
        self.assertEqual(second['stop_reason'],first['stop_reason'])
        self.assertEqual(self.ledger.rows(),[row])

    def test_transport_uncertainty_cannot_retry_after_deadline(self):
        def failure(request,index):
            self.now[0]+=1800
            raise ProviderFailure('transport_failure',retryable=True,uncertain_charge=True)
        provider=FixtureProvider(failure)
        result=self.run_fixture(provider)
        self.assertEqual(len(provider.requests),1)
        self.assertIn('deadline elapsed',result['stop_reason'])
        rows=self.ledger.rows()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['state'],'transport_uncertain')
        self.assertEqual(result['feasibility_report']['accounting']['scope']['outstanding_reservations_micro_usd'],rows[0]['reserved'])

    def test_wrong_initial_does_not_suppress_any_selected_assignment(self):
        def wrong_initial(request,index):
            if index%7==1:
                value=response(); value['output'][-1]['content'][0]['text']='999'
                return value
        provider=FixtureProvider(wrong_initial)
        report=self.run_fixture(provider)['feasibility_report']
        self.assertEqual(len(provider.requests),28)
        self.assertEqual(report['completed_task_blocks'],4)
        self.assertEqual(report['initial_correct_subset']['n_tasks'],0)
        self.assertEqual(report['all_selected_tasks']['by_condition']['updated_retained']['graded_n'],8)


if __name__ == '__main__': unittest.main()
