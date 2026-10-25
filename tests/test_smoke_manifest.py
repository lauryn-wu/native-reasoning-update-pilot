"""Scope and evidence binding regressions; all requests remain offline."""
import copy
import json
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from native_pilot.manifest import ROOT, paid_preflight
from native_pilot.util import file_digest


class SmokeManifestTests(unittest.TestCase):
    def setUp(self):
        from native_pilot.provider import SMOKE_AUTHORIZATION
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'provenance').mkdir()
        self.m = json.loads((ROOT/'manifests/pilot-v2.json').read_text())
        self.m.update(version='pilot-v5', protocol_smoke_authorization=copy.deepcopy(SMOKE_AUTHORIZATION))
        for name in ('provenance/continuation_recovery_v5.json',
                     'provenance/execution_policy_v4.json', 'provenance/authentication_recovery_v4.json',
                     'manifests/pilot-v4.json'):
            target=self.root/name; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy(ROOT/name,target)
        recovery={'path':'provenance/continuation_recovery_v5.json',
                  'sha256':file_digest(self.root/'provenance/continuation_recovery_v5.json')}
        self.m['continuation_recovery']=recovery
        self.m['provenance_hashes'][recovery['path']]=recovery['sha256']
        self.policy = {'paid_execution_allowed':False,'protocol_smoke':copy.deepcopy(SMOKE_AUTHORIZATION)}
        (self.root/'provenance/execution_policy.json').write_text(json.dumps(self.policy))
        evidence = json.loads((ROOT/'provenance/integrated_qualification.json').read_text())
        ep = self.root/'provenance/evidence.json'
        ep.write_text(json.dumps(evidence))
        self.m['integrated_qualification'] = {'path':'provenance/evidence.json','sha256':file_digest(ep)}
        self.q = dict(evidence,manifest_sha256=self.m['manifest_sha256'],
                      implementation_hashes=self.m['implementation_hashes'],
                      integrated_qualification_sha256=file_digest(ep))
        self.patch = patch('native_pilot.manifest.ROOT',self.root)
        self.patch.start()
    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()
    def test_only_matching_smoke_authorized(self):
        paid_preflight(self.m,self.q,smoke=True)
        with self.assertRaisesRegex(ValueError,'explicit user policy'):
            paid_preflight(self.m,self.q,smoke=False)
    def test_different_version_task_or_scope_rejected(self):
        for change in ({'version':'pilot-v6'}, {'paid_execution_allowed':True},
                       {'protocol_smoke_authorization':None},
                       {'smoke_task':dict(self.m['smoke_task'],task_id='livecodebench:338')}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                paid_preflight(dict(self.m,**change),self.q,smoke=True)
    def test_flags_alone_are_not_qualification(self):
        for key in ('manifest_sha256','implementation_hashes','integrated_qualification_sha256',
                    'covered_task_ids','source_references'):
            q=copy.deepcopy(self.q); q.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                paid_preflight(self.m,q,smoke=True)
    def test_replaced_or_changed_evidence_rejected(self):
        path=self.root/'provenance/evidence.json'; path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'missing or changed'):
            paid_preflight(self.m,self.q,smoke=True)
    def test_policy_reinstatement_or_expansion_cannot_widen_scope(self):
        for policy in ({'paid_execution_allowed':False},
                       dict(self.policy,paid_execution_allowed=True),
                       dict(self.policy,protocol_smoke=dict(self.policy['protocol_smoke'],max_logical_calls=4))):
            (self.root/'provenance/execution_policy.json').write_text(json.dumps(policy))
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                paid_preflight(self.m,self.q,smoke=True)

    def test_missing_recovery_or_changed_historical_authorization_rejected(self):
        changed=copy.deepcopy(self.m); changed.pop('continuation_recovery')
        with self.assertRaisesRegex(ValueError,'recovery binding'):
            paid_preflight(changed,self.q,smoke=True)
        (self.root/'provenance/authentication_recovery_v4.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Historical continuation evidence'):
            paid_preflight(self.m,self.q,smoke=True)

    def test_changed_recovery_origin_rejected(self):
        path=self.root/'provenance/continuation_recovery_v5.json'
        record=json.loads(path.read_text()); record['recovery']['failed_attempt']=2
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError,'explicit authorization'):
            paid_preflight(self.m,self.q,smoke=True)
