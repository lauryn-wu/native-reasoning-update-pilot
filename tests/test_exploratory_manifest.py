import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_pilot import exploratory
from native_pilot.manifest import ROOT, paid_preflight
from native_pilot.util import digest, file_digest


def fixture():
    prior = json.loads((ROOT/'manifests/pilot-v5.json').read_text())
    m = copy.deepcopy(prior)
    m['tasks'] = [copy.deepcopy(next(t for t in prior['tasks'] if t['task_id'] == tid))
                  for tid in exploratory.TASK_IDS]
    m.update(version='pilot-v6', execution_scope='exploratory_pilot',
             exploratory_authorization=copy.deepcopy(exploratory.AUTHORIZATION),
             exploratory_protocol={'path': exploratory.RECORD_PATH,
                                   'sha256': file_digest(ROOT/exploratory.RECORD_PATH)},
             protocol_smoke_authorization=None, continuation_recovery=None,
             analysis=copy.deepcopy(exploratory.ANALYSIS), planned_counts=copy.deepcopy(exploratory.COUNTS))
    m['schedule'] = exploratory.make_schedule(m['tasks'])
    m['provenance_hashes'][exploratory.RECORD_PATH] = m['exploratory_protocol']['sha256']
    m['tasks_sha256'] = digest(m['tasks']); m['schedule_sha256'] = digest(m['schedule'])
    return prior, m


class ExploratoryManifestTests(unittest.TestCase):
    def setUp(self):
        self.prior, self.m = fixture()
        self.policy = {'paid_execution_allowed': False, 'protocol_smoke': None,
                       'exploratory_pilot': copy.deepcopy(exploratory.AUTHORIZATION)}

    def test_exact_prospective_subset_and_complete_task_blocks(self):
        exploratory.validate_scope(self.m, self.policy)
        self.assertTrue(exploratory.subset_identity_report(self.prior, self.m)['passed'])
        self.assertEqual(len(self.m['schedule']), 28)
        for index, tid in enumerate(exploratory.TASK_IDS):
            block = self.m['schedule'][7*index:7*(index+1)]
            self.assertEqual({call['task_id'] for call in block}, {tid})
            self.assertEqual([(call['condition'], call['sample']) for call in block],
                [('initial',0), ('updated_retained',1), ('updated_dropped',1), ('fresh',1),
                 ('updated_retained',2), ('updated_dropped',2), ('fresh',2)])
        self.assertFalse(self.m['analysis']['full_study_significance_gate_applied'])
        self.assertFalse(self.m['analysis']['null_result_rules_out_hypothesis'])

    def test_changed_task_order_prompt_grader_or_settings_is_rejected(self):
        changes = []
        altered = copy.deepcopy(self.m); altered['tasks'].reverse(); changes.append(altered)
        altered = copy.deepcopy(self.m); altered['tasks'][0]['original_prompt'] += ' changed'; changes.append(altered)
        altered = copy.deepcopy(self.m); altered['tasks'][0]['updated']['answer'] = '999'; changes.append(altered)
        altered = copy.deepcopy(self.m); altered['settings']['max_output_tokens'] = 1000; changes.append(altered)
        altered = copy.deepcopy(self.m); altered['analysis'] = self.prior['analysis']; changes.append(altered)
        altered = copy.deepcopy(self.m); altered['schedule'][1], altered['schedule'][7] = altered['schedule'][7], altered['schedule'][1]; changes.append(altered)
        for altered in changes:
            with self.subTest(altered_hash=digest(altered)), self.assertRaises(ValueError):
                exploratory.validate_scope(altered, self.policy)

    def test_widened_budget_deadline_authorization_or_full_study_fails(self):
        for field, value in [('additional_budget_usd',6), ('shared_budget_usd',41),
                             ('soft_dispatch_deadline_seconds',1801), ('max_logical_calls',29),
                             ('authorization_id','new-label')]:
            altered = copy.deepcopy(self.m); altered['exploratory_authorization'][field] = value
            policy = copy.deepcopy(self.policy); policy['exploratory_pilot'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                exploratory.validate_scope(altered, policy)
        for change in ({'paid_execution_allowed':True}, {'execution_scope':'pilot'},
                       {'version':'pilot-v7'}, {'protocol_smoke_authorization':{'allowed':True}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                exploratory.validate_scope(dict(self.m, **change), self.policy)

    def test_missing_or_modified_prospective_binding_is_rejected(self):
        for key in ('exploratory_protocol','provenance_hashes'):
            altered = copy.deepcopy(self.m); altered[key] = {}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,'protocol binding'):
                exploratory.validate_scope(altered, self.policy)

    def test_preflight_requires_bound_subset_evidence_and_explicit_explore_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'provenance').mkdir()
            (root/'provenance/execution_policy.json').write_text(json.dumps(self.policy))
            evidence = {'source_references':{'checks':{}},'covered_task_ids':list(exploratory.TASK_IDS)}
            path = root/'provenance/evidence.json'; path.write_text(json.dumps(evidence))
            m = copy.deepcopy(self.m)
            m['integrated_qualification'] = {'path':'provenance/evidence.json','sha256':file_digest(path)}
            q = dict(evidence, manifest_sha256=m['manifest_sha256'],offline_passed=True,
                     docker_passed=True,source_reference_passed=True,
                     implementation_hashes=m['implementation_hashes'],
                     integrated_qualification_sha256=file_digest(path),
                     exploratory_subset_identity=exploratory.subset_identity_report(self.prior,m))
            with patch('native_pilot.manifest.ROOT',root):
                paid_preflight(m,q,execution_scope='exploratory_pilot')
                for kwargs in ({}, {'smoke':True}, {'execution_scope':'pilot'}):
                    with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                        paid_preflight(m,q,**kwargs)
                for field in ('exploratory_subset_identity','manifest_sha256','integrated_qualification_sha256',
                              'implementation_hashes','covered_task_ids'):
                    altered=copy.deepcopy(q); altered[field]=None
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        paid_preflight(m,altered,execution_scope='exploratory_pilot')


if __name__ == '__main__':
    unittest.main()
