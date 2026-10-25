"""Offline synthetic checks of the scoped 28-call SDK boundary; never live data."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from native_pilot.budget import BudgetRefused, Ledger, reservation
from native_pilot.exploratory import AUTHORIZATION, ANALYSIS, COUNTS, TASK_IDS, make_schedule
from native_pilot.provider import (DEFAULT_SETTINGS, OpenAIProvider, ProviderFailure, build_request,
    _read_frozen_exploratory_manifest as read_frozen_exploratory_manifest)
from native_pilot.runner import campaign_lock
from test_provider import TASK, observed_structure_response


def fixture():
    tasks = [dict(copy.deepcopy(TASK), task_id=task_id,
                  domain='math' if index < 2 else 'coding', unchanged_control=False,
                  original={'answer':'42'}, updated={'answer':'43'})
             for index, task_id in enumerate(TASK_IDS)]
    return {'manifest_sha256':'e'*64, 'version':'pilot-v6', 'status':'frozen',
            'blockers':[], 'hard_budget_usd':40, 'paid_execution_allowed':False,
            'execution_scope':'exploratory_pilot', 'exploratory_authorization':copy.deepcopy(AUTHORIZATION),
            'protocol_smoke_authorization':None, 'continuation_recovery':None,
            'settings':copy.deepcopy(DEFAULT_SETTINGS), 'tasks':tasks, 'schedule':make_schedule(tasks),
            'analysis':copy.deepcopy(ANALYSIS), 'planned_counts':copy.deepcopy(COUNTS)}


class ExploratoryProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Ledger(Path(self.temp.name)/'budget.sqlite')
        self.addCleanup(self.ledger.close)
        self.lock = campaign_lock(Path(self.temp.name)/'campaign.lock')
        self.guard = self.lock.__enter__()
        self.addCleanup(self.lock.__exit__,None,None,None)
        self.manifest = fixture()
        self.policy = {'paid_execution_allowed':False, 'protocol_smoke':None,
                       'exploratory_pilot':copy.deepcopy(AUTHORIZATION)}
        self.clock = patch('native_pilot.budget._wall_time',return_value=1000).start()
        self.addCleanup(patch.stopall)
        patch('native_pilot.provider.SHARED_LEDGER_PATH',self.ledger.path).start()
        patch('native_pilot.provider._read_frozen_exploratory_manifest',return_value=self.manifest).start()
        patch('native_pilot.provider._read_execution_policy',return_value=self.policy).start()
        patch('native_pilot.exploratory._record_and_prior',
              return_value=({},copy.deepcopy(self.manifest),{})).start()
        self.smoke = patch('native_pilot.exploratory.verify_prior_smoke',return_value={'protocol_passed':True}).start()
        self.client = Mock()
        self.client.responses.create.side_effect = lambda **request: observed_structure_response(request['reasoning']['context'])
        self.provider = self.new_provider()

    def new_provider(self, **changes):
        args = dict(allow_paid=True,client=self.client,execution_scope='exploratory_pilot',
                    manifest=self.manifest,ledger=self.ledger,campaign_guard=self.guard)
        args.update(changes)
        return OpenAIProvider(**args)

    def key(self,index):
        return self.manifest['manifest_sha256']+'/'+self.manifest['schedule'][index]['call_id']

    def prepare(self,index,*,amount=None):
        call = self.manifest['schedule'][index]
        task = next(t for t in self.manifest['tasks'] if t['task_id']==call['task_id'])
        checkpoint = None
        if call['condition'] not in ('initial','fresh'):
            initial = self.ledger.latest(self.manifest['manifest_sha256']+'/'+task['task_id']+'/initial/0')
            checkpoint = {'request':json.loads(initial['request']),'response':json.loads(initial['response'])}
        request = build_request(task,call['condition'],checkpoint,self.manifest['settings'])
        attempt = self.ledger.reserve(self.key(index),self.manifest['manifest_sha256'],request,
            amount or reservation(request,checkpoint)['micro_usd'],'exploratory_pilot',
            scope_id=AUTHORIZATION['authorization_id'])
        self.ledger.dispatched(self.key(index),attempt)
        return request,dict(call,call_id=self.key(index),manifest_sha256=self.manifest['manifest_sha256'],attempt=attempt)

    def send(self,index,*,status='incorrect',value=None):
        request,context = self.prepare(index)
        result = self.provider.create(request,execution_context=context)
        if value is not None:
            result=value
        call=self.manifest['schedule'][index]
        self.ledger.finish(self.key(index),context['attempt'],result,
            dict(call,status=status,protocol_valid=True,grade={'correct':status=='correct','status':status}))
        return request,result

    def test_all_28_follow_order_using_one_raw_initial_despite_incorrect_grade(self):
        sent=[]
        for index in range(28):
            sent.append(self.send(index))
        self.assertEqual(self.client.responses.create.call_count,28)
        self.assertTrue(all(json.loads(row['outcome'])['status']=='incorrect' for row in self.ledger.rows()))
        for base in (0,7,14,21):
            initial=self.ledger.latest(self.key(base))
            raw=json.loads(initial['response'])['output']
            self.assertEqual(sum(item.get('status','missing') is None for item in raw),4)
            first=copy.deepcopy(sent[base+1][0]); second=copy.deepcopy(sent[base+2][0])
            second['reasoning']['context']='all_turns'
            self.assertEqual(first,second)
            self.assertEqual(sent[base+1][0],sent[base+4][0])
            self.assertEqual(sent[base+2][0],sent[base+5][0])
            self.assertEqual(sent[base+3][0],sent[base+6][0])
            self.assertEqual(len(sent[base+3][0]['input']),1)
        self.new_provider().authorize_schedule(self.manifest,self.ledger,self.manifest['schedule'],
            self.manifest['tasks'],execution_scope='exploratory_pilot',campaign_guard=self.guard)
        self.assertEqual(self.client.responses.create.call_count,28)

    def test_same_request_uses_frozen_task_initial_not_a_previous_continuation(self):
        self.send(0); self.send(1)
        request,context=self.prepare(2)
        request['input'][1]['encrypted_content']='synthetic-replacement-not-a-real-ciphertext'
        with self.assertRaisesRegex(ProviderFailure,'request_not_frozen'):
            self.provider.create(request,execution_context=context)
        self.assertEqual(self.client.responses.create.call_count,2)

    def test_out_of_order_next_task_is_rejected(self):
        request,context=self.prepare(7)
        with self.assertRaisesRegex(ProviderFailure,'schedule_not_a_prefix'):
            self.provider.create(request,execution_context=context)
        self.client.responses.create.assert_not_called()

    def test_preassigned_future_call_invalidates_prefix(self):
        request,context=self.prepare(0)
        self.prepare(7)
        with self.assertRaisesRegex(ProviderFailure,'schedule_not_a_prefix'):
            self.provider.create(request,execution_context=context)
        self.client.responses.create.assert_not_called()

    def test_direct_duplicate_dispatch_cannot_reach_client_twice(self):
        request,context=self.prepare(0)
        self.provider.create(request,execution_context=context)
        with self.assertRaisesRegex(ProviderFailure,'attempt_already_dispatched'):
            self.provider.create(request,execution_context=context)
        self.assertEqual(self.client.responses.create.call_count,1)

    def test_only_single_transport_retry_uses_same_assignment_and_request(self):
        request,context=self.prepare(0)
        self.client.responses.create.side_effect=TimeoutError
        with self.assertRaises(ProviderFailure) as failure:
            self.provider.create(request,execution_context=context)
        self.assertTrue(failure.exception.retryable)
        self.ledger.uncertain(context['call_id'],1,'transport_failure')
        again,context2=self.prepare(0)
        self.assertEqual(again,request)
        self.assertEqual(context2['attempt'],2)
        with self.assertRaises(ProviderFailure):
            self.provider.create(again,execution_context=context2)
        self.ledger.uncertain(context['call_id'],2,'transport_failure')
        with self.assertRaises(BudgetRefused):
            self.prepare(0)
        self.assertEqual(self.client.responses.create.call_count,2)

    def test_unclaimed_transport_row_cannot_be_used_to_mint_retry(self):
        request,context=self.prepare(0)
        self.ledger.uncertain(context['call_id'],1)
        request,context=self.prepare(0)
        with self.assertRaisesRegex(ProviderFailure,'transport_retry_not_authorized'):
            self.provider.create(request,execution_context=context)
        self.client.responses.create.assert_not_called()

    def test_failure_status_stops_later_dispatch(self):
        for status in ('provider_failure','protocol_failure'):
            with self.subTest(status=status):
                if not self.ledger.latest(self.key(0)):
                    self.send(0,status=status)
                else:
                    self.ledger.db.execute('UPDATE attempts SET outcome=? WHERE call_id=?',
                        (json.dumps({'status':status,'protocol_valid':False}),self.key(0)))
                    self.ledger.db.commit()
                # Initial native state exists, but failure status is decisive.
                if not self.ledger.latest(self.key(1)):
                    request,context=self.prepare(1)
                with self.assertRaisesRegex(ProviderFailure,'stopped_after_'+status):
                    self.provider.create(request,execution_context=context)
        self.assertEqual(self.client.responses.create.call_count,1)

    def test_deadline_between_reserve_and_dispatch_is_durable_across_resume(self):
        request,context=self.prepare(0)
        before=self.ledger.latest(context['call_id'])
        self.clock.return_value=2800
        with self.assertRaisesRegex(BudgetRefused,'deadline elapsed'):
            self.provider.create(request,execution_context=context)
        self.clock.return_value=1001
        with self.assertRaisesRegex(BudgetRefused,'deadline elapsed'):
            self.new_provider().create(request,execution_context=context)
        self.assertEqual(self.ledger.latest(context['call_id']),before)
        self.client.responses.create.assert_not_called()

    def test_scope_cap_counts_uncertain_attempt_before_retry(self):
        request,context=self.prepare(0,amount=5_000_000)
        self.provider.create(request,execution_context=context)
        self.ledger.uncertain(context['call_id'],1)
        with self.assertRaisesRegex(BudgetRefused,'additional.*5'):
            self.prepare(0)
        self.assertEqual(self.ledger.scope_status(AUTHORIZATION['authorization_id'])['accounted_micro_usd'],5_000_000)
        self.assertEqual(self.client.responses.create.call_count,1)

    def test_under_reserved_dispatch_is_refused(self):
        request,context=self.prepare(0,amount=1)
        with self.assertRaisesRegex(ProviderFailure,'dispatch_reservation_required'):
            self.provider.create(request,execution_context=context)
        self.client.responses.create.assert_not_called()

    def test_extra_call_metadata_or_wrong_sample_is_refused(self):
        request,context=self.prepare(0)
        for changes in ({'sample':1},{'sample':False},{'call_id':'not-authorized'}, {'condition':'unchanged_retained'}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ProviderFailure,'call_not_authorized'):
                    self.provider.create(request,execution_context=dict(context,**changes))
        with self.assertRaisesRegex(ProviderFailure,'metadata_required'):
            self.provider.create(request,execution_context=dict(context,extra=True))
        self.client.responses.create.assert_not_called()

    def test_wrong_schedule_or_full_pilot_scope_is_refused(self):
        for schedule in (self.manifest['schedule'][:-1],self.manifest['schedule'][::-1]):
            with self.assertRaisesRegex(ProviderFailure,'schedule_not_authorized'):
                self.provider.authorize_schedule(self.manifest,self.ledger,schedule,self.manifest['tasks'],
                    execution_scope='exploratory_pilot',campaign_guard=self.guard)
        for scope in ('pilot','protocol_smoke',None):
            with self.assertRaisesRegex(ProviderFailure,'policy_hold'):
                self.new_provider(execution_scope=scope)
        self.client.responses.create.assert_not_called()

    def test_schedule_cannot_replace_task_prompts_or_grading(self):
        for field in ('original_prompt','original'):
            tasks=copy.deepcopy(self.manifest['tasks'])
            tasks[0][field]='changed' if field.endswith('prompt') else {'answer':'changed'}
            with self.assertRaisesRegex(ProviderFailure,'task_not_frozen'):
                self.provider.authorize_schedule(self.manifest,self.ledger,self.manifest['schedule'],tasks,
                    execution_scope='exploratory_pilot',campaign_guard=self.guard)
        self.client.responses.create.assert_not_called()

    def test_prior_smoke_must_still_be_verified_on_every_send(self):
        request,context=self.prepare(0)
        self.smoke.side_effect=ValueError('synthetic history mismatch')
        with self.assertRaisesRegex(ProviderFailure,'prior_smoke_protocol_unverified'):
            self.provider.create(request,execution_context=context)
        self.client.responses.create.assert_not_called()

    def test_no_new_manifest_can_reset_scope_and_binding_starts_no_clock(self):
        status=self.ledger.scope_status(AUTHORIZATION['authorization_id'])
        self.assertIsNone(status['started_at'])
        self.assertEqual(status['attempts'],0)
        with self.assertRaisesRegex(BudgetRefused,'another manifest'):
            self.ledger.bind_scope(AUTHORIZATION['authorization_id'],'f'*64)
        with self.assertRaisesRegex(ProviderFailure,'manifest_not_authorized'):
            self.new_provider(manifest=dict(self.manifest,manifest_sha256='f'*64))
        self.client.responses.create.assert_not_called()

    def test_policy_reinstatement_and_missing_lock_block_injected_client(self):
        with self.assertRaisesRegex(ProviderFailure,'active_campaign_lock_required'):
            self.new_provider(campaign_guard=None)
        request,context=self.prepare(0)
        self.policy['exploratory_pilot']=None
        with self.assertRaisesRegex(ProviderFailure,'policy_hold'):
            self.provider.create(request,execution_context=context)
        self.client.responses.create.assert_not_called()

    def test_frozen_reader_missing_qualification_fails_closed(self):
        with patch('native_pilot.manifest.load_manifest',side_effect=ValueError('stale evidence')):
            with self.assertRaisesRegex(ProviderFailure,'qualification_unverified'):
                read_frozen_exploratory_manifest()



if __name__=='__main__':
    unittest.main()
