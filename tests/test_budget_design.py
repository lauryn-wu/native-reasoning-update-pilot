import json
import tempfile
import unittest
from pathlib import Path
from native_pilot.budget import Ledger, BudgetRefused, reservation, usage_cost, CAP_MICRO_USD
from native_pilot.design import make_schedule, validate_design


def response_usage(inp=100,out=10):
    return {'model':'gpt-6.1-sol','service_tier':'default','reasoning':{'mode':'standard'},
            'usage':{'input_tokens':inp,'output_tokens':out,
                     'input_tokens_details':{'cached_tokens':0,'cache_write_tokens':0}}}


def tasks24():
    return [{'task_id':f'{domain}-{i}', 'domain':domain,'original_prompt':f'software fixture {domain}{i}',
             'unchanged_control':i<4} for domain in ('math','coding') for i in range(12)]


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.temp.name)/'budget.sqlite')
    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()
    def test_refuse_before_dispatch(self):
        self.ledger.reserve('a','m',{},CAP_MICRO_USD)
        with self.assertRaises(BudgetRefused):
            self.ledger.reserve('b','m',{},1)
        self.assertEqual(len(self.ledger.rows()),1)
    def test_resume_and_actual_charge(self):
        attempt=self.ledger.reserve('a','m',{},1000)
        self.ledger.dispatched('a',attempt)
        response=response_usage()
        self.ledger.finish('a',attempt,response,{'status':'correct'})
        self.assertEqual(self.ledger.total(),300)
        with self.assertRaises(BudgetRefused):
            self.ledger.reserve('a','m',{},1000)
        self.assertEqual(self.ledger.total(),300)
    def test_uncertain_attempt_charged_and_only_one_retry(self):
        for attempt in (1,2):
            self.assertEqual(self.ledger.reserve('a','m',{},1000),attempt)
            self.ledger.dispatched('a',attempt)
            self.ledger.uncertain('a',attempt)
        with self.assertRaises(BudgetRefused):
            self.ledger.reserve('a','m',{},1000)
        self.assertEqual(self.ledger.total(),2000)
    def test_crash_recovery_does_not_erase_reservation(self):
        self.ledger.reserve('a','m',{},1000)
        self.ledger.recover_interrupted()
        self.assertEqual(self.ledger.latest('a')['state'],'transport_uncertain')
        self.assertEqual(self.ledger.total(),1000)
    def test_malformed_usage_preserves_full_reservation(self):
        n=self.ledger.reserve('a','m',{},1000)
        self.ledger.dispatched('a',n)
        self.ledger.finish('a',n,{}, {'status':'protocol_failure'})
        self.assertEqual(self.ledger.total(),1000)
    def test_cache_and_output_including_reasoning(self):
        usage={'input_tokens':1000,'output_tokens':100,'input_tokens_details':{'cached_tokens':200,'cache_write_tokens':100},
               'output_tokens_details':{'reasoning_tokens':90}}
        self.assertEqual(usage_cost(usage),2920)
    def test_checkpoint_tokens_are_in_reservation(self):
        req={'input':[],'max_output_tokens':32768}
        base=reservation(req)
        more=reservation(req,{'response':{'usage':{'output_tokens':30000}}})
        self.assertEqual(more['input_tokens_bound']-base['input_tokens_bound'],30000)
    def test_shared_versions_share_cap(self):
        self.ledger.reserve('v1/smoke','v1',{},CAP_MICRO_USD)
        with self.assertRaises(BudgetRefused):
            self.ledger.reserve('v2/pilot','v2',{},1)
    def test_accounting_violation_halts_future_dispatch(self):
        n=self.ledger.reserve('a','m',{},1)
        self.ledger.dispatched('a',n)
        self.ledger.finish('a',n,response_usage(), {'status':'correct'})
        with self.assertRaises(BudgetRefused):
            self.ledger.reserve('b','m',{},1000)


class DesignTests(unittest.TestCase):
    def test_exact_200_balanced_independent_repeats(self):
        tasks=tasks24()
        schedule=make_schedule(tasks)
        validate_design(tasks,schedule)
        self.assertEqual(len(schedule),200)
        self.assertEqual(sum(c['condition']=='initial' for c in schedule),24)
        for task in tasks:
            for branch in ('updated_retained','updated_dropped','fresh'):
                self.assertEqual(sorted(c['sample'] for c in schedule if c['task_id']==task['task_id'] and c['condition']==branch),[1,2])
        self.assertEqual(schedule,make_schedule(tasks))
        self.assertNotEqual(schedule,make_schedule(tasks,42))
    def test_duplicate_original_rejected(self):
        tasks=tasks24()
        tasks[0]['original_prompt']=tasks[1]['original_prompt']
        with self.assertRaises(ValueError):
            validate_design(tasks,make_schedule(tasks))

if __name__=='__main__':
    unittest.main()
