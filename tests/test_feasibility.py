"""Offline descriptive-report fixtures, never selectable research cases."""
import copy
import json
import unittest

from native_pilot.feasibility import describe_exploratory


def fixture_manifest():
    tasks = [{'task_id': f'fixture:{i}', 'domain': 'math' if i < 2 else 'coding'} for i in range(4)]
    schedule = [dict(call_id=f"{task['task_id']}/{condition}/{sample}",task_id=task['task_id'],
                     condition=condition,sample=sample)
                for task in tasks for condition,sample in (
                    ('initial',0),('updated_retained',1),('updated_dropped',1),('fresh',1),
                    ('updated_retained',2),('updated_dropped',2),('fresh',2))]
    return {'manifest_sha256':'fixture-feasibility','execution_scope':'exploratory_pilot',
            'tasks':tasks,'schedule':schedule}


def outcome(call, status='correct', *, protocol_valid=True, response_status='completed'):
    return dict(call, status=status, protocol_valid=protocol_valid,response_status=response_status,
                grade={'status':status,'correct':status=='correct','parsed_answer':'NEVER PUBLIC'})


class FeasibilityTests(unittest.TestCase):
    def test_complete_four_case_report_is_descriptive_and_initial_subset_is_separate(self):
        manifest=fixture_manifest()
        values=[outcome(call) for call in manifest['schedule']]
        values[0]=outcome(manifest['schedule'][0], 'incorrect')
        values[1]=outcome(manifest['schedule'][1], 'old_answer_match')
        report=describe_exploratory(manifest,values, accounting={'scope':{'elapsed_seconds':1234}})
        self.assertTrue(report['all_planned_calls_completed'])
        self.assertEqual(report['completed_task_blocks'],4)
        self.assertEqual(report['completed_retained_dropped_sample_pairs'],8)
        self.assertEqual(report['all_selected_tasks']['n_tasks'],4)
        self.assertEqual(report['initial_correct_subset']['task_ids'],['fixture:1','fixture:2','fixture:3'])
        retained=report['all_selected_tasks']['by_condition']['updated_retained']
        self.assertEqual((retained['correct_n'],retained['graded_n'],retained['planned_n']),(7,8,8))
        self.assertEqual(retained['accuracy'],7/8)
        self.assertEqual(report['per_task'][0]['by_condition']['updated_retained']['accuracy'],0.5)
        public=json.dumps(report)
        self.assertNotIn('NEVER PUBLIC',public)
        for key in ('analysis','decision','criteria','one_sided_p','continuation_gate_passed','bootstrap_95_percent_interval'):
            self.assertNotIn(key,report)
        self.assertEqual(report['accounting']['scope']['elapsed_seconds'],1234)

    def test_missing_calls_are_not_wrong_and_partial_pairs_blocks_stay_visible(self):
        manifest=fixture_manifest()
        values=[outcome(call) for call in manifest['schedule'][:2]]
        report=describe_exploratory(manifest,values)
        self.assertFalse(report['all_planned_calls_completed'])
        self.assertEqual(report['completed_task_blocks'],0)
        self.assertEqual(report['completed_retained_dropped_sample_pairs'],0)
        first=report['per_task'][0]
        retained=first['by_condition']['updated_retained']
        self.assertEqual((retained['accuracy'],retained['graded_n'],retained['planned_n'],retained['missing_n']),(1,1,2,1))
        self.assertIsNone(first['by_condition']['updated_dropped']['accuracy'])
        self.assertIsNone(report['per_task'][1]['initial_correct'])
        self.assertEqual(report['initial_correct_subset']['task_ids'],['fixture:0'])
        self.assertEqual(sum(call['status']=='unassigned' for call in report['calls']),26)

    def test_protocol_failures_and_budget_stops_are_separate_from_returned_incorrect(self):
        manifest=fixture_manifest()
        values=[outcome(manifest['schedule'][0]),
                dict(manifest['schedule'][1],status='protocol_failure',protocol_valid=False),
                dict(manifest['schedule'][2],status='budget_stopped',protocol_valid=False),
                outcome(manifest['schedule'][3],'truncated_no_answer',response_status='incomplete')]
        report=describe_exploratory(manifest,values,stop_reason='deadline elapsed')
        row=report['per_task'][0]
        retained=row['by_condition']['updated_retained']
        self.assertEqual(retained['graded_n'],0)
        self.assertEqual(retained['unavailable_or_protocol_invalid_n'],1)
        self.assertEqual(retained['missing_n'],1)
        dropped=row['by_condition']['updated_dropped']
        self.assertEqual(dropped['missing_n'],2)
        fresh=row['by_condition']['fresh']
        self.assertEqual((fresh['graded_n'],fresh['accuracy'],fresh['missing_n']),(1,0,1))
        self.assertEqual(report['completed_protocol_valid_responses'],1)
        self.assertEqual(report['protocol']['invalid_call_ids'],[manifest['schedule'][1]['call_id']])
        self.assertEqual(report['stop_reason'],'deadline elapsed')

    def test_pairs_count_by_sample_and_complete_blocks_require_all_seven(self):
        manifest=fixture_manifest()
        values=[outcome(call) for call in manifest['schedule'][:7]]
        values += [outcome(call) for call in manifest['schedule'][7:10]]
        report=describe_exploratory(manifest,values)
        self.assertEqual(report['completed_task_ids'],['fixture:0'])
        self.assertEqual(report['completed_retained_dropped_sample_pairs'],3)
        self.assertEqual(report['per_task'][1]['completed_retained_dropped_sample_pairs'],1)
        self.assertFalse(report['per_task'][1]['task_block_complete'])

    def test_duplicate_or_unexpected_outcomes_cannot_claim_completion(self):
        manifest=fixture_manifest()
        complete=[outcome(call) for call in manifest['schedule']]
        for extra in (complete[0], dict(complete[0],call_id='unexpected')):
            with self.subTest(extra=extra['call_id']):
                report=describe_exploratory(manifest,complete+[copy.deepcopy(extra)])
                self.assertFalse(report['all_planned_calls_completed'])
                self.assertTrue(report['protocol']['duplicate_outcome_call_ids'] or
                                report['protocol']['unexpected_outcome_call_ids'])

    def test_public_diagnostics_keep_sanitized_http_error_without_arbitrary_fields(self):
        manifest=fixture_manifest()
        failure=dict(manifest['schedule'][0],status='protocol_failure',protocol_valid=False,
                     error_kind='protocol_failure',provider_error={
                         'kind':'protocol_failure','status_code':400,'retryable':False,
                         'uncertain_charge':False,'body':'NEVER PUBLIC',
                         'api_error':{'type':'invalid_request_error','param':'input[1].status',
                                      'explanation':'The provider rejected an unsupported request field.',
                                      'raw_message':'NEVER PUBLIC'}})
        public=describe_exploratory(manifest,[failure])
        error=public['calls'][0]['provider_error']
        self.assertEqual(error['status_code'],400)
        self.assertEqual(error['api_error']['param'],'input[1].status')
        self.assertNotIn('NEVER PUBLIC',json.dumps(public))


if __name__ == '__main__': unittest.main()
