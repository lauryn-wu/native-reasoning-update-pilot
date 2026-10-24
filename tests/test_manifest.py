"""Freezing and approval barriers; no real provider is ever instantiated."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from native_pilot.cli import main, dry_run, qualification
from native_pilot.manifest import ROOT, freeze, load_manifest, paid_preflight, implementation_hashes
from native_pilot.util import file_digest


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        shutil.copytree(ROOT/'provenance',self.root/'provenance')
        (self.root/'docs').mkdir()
        (self.root/'docs/PROTOCOL.md').write_text('Software test protocol')
        (self.root/'src').mkdir()
        (self.root/'src/module.py').write_text('VALUE = 1\n')
        (self.root/'tests').mkdir()
        (self.root/'tests/test_fixture.py').write_text('# frozen qualification\n')
        shutil.copy(ROOT/'pyproject.toml',self.root/'pyproject.toml')
        self.path=self.root/'blocked.json'
    def tearDown(self):
        self.temp.cleanup()
    def test_source_block_is_not_filled_with_fake_tasks(self):
        manifest=freeze(self.path,'software-test',self.root)
        self.assertEqual(manifest['status'],'blocked')
        self.assertEqual(manifest['tasks'],[])
        self.assertEqual(manifest['schedule'],[])
        self.assertEqual(manifest['planned_counts']['responses'],200)
        with self.assertRaises(ValueError):
            paid_preflight(manifest,{'offline_passed':True,'docker_passed':True,'source_reference_passed':True})
        self.assertEqual(dry_run(manifest)['actual_frozen_tasks'],0)
    def test_frozen_manifest_never_overwritten(self):
        freeze(self.path,'software-test',self.root)
        with self.assertRaises(FileExistsError):
            freeze(self.path,'different-version',self.root)
    def test_changed_source_or_qualification_test_rejected(self):
        freeze(self.path,'software-test',self.root)
        load_manifest(self.path,root=self.root)
        (self.root/'tests/test_fixture.py').write_text('# modified\n')
        with self.assertRaisesRegex(ValueError,'Frozen file changed'):
            load_manifest(self.path,root=self.root)
    def test_changed_manifest_rejected(self):
        freeze(self.path,'software-test',self.root)
        content=json.loads(self.path.read_text())
        content['hard_budget_usd']=400
        self.path.write_text(json.dumps(content))
        with self.assertRaisesRegex(ValueError,'content hash mismatch'):
            load_manifest(self.path,root=self.root)
    def test_paid_cli_requires_flag_even_before_source_preflight(self):
        manifest=freeze(self.path,'software-test',self.root)
        with patch('native_pilot.cli.load_manifest',return_value=manifest):
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                code=main(['--manifest',str(self.path),'run'])
        self.assertEqual(code,2)
        self.assertIn('--allow-paid',stderr.getvalue())
    def test_explicit_paid_flag_cannot_override_source_block(self):
        manifest=freeze(self.path,'software-test',self.root)
        with patch('native_pilot.cli.load_manifest',return_value=manifest):
            with patch('native_pilot.provider.OpenAIProvider') as provider:
                with contextlib.redirect_stderr(io.StringIO()):
                    code=main(['--manifest',str(self.path),'smoke','--allow-paid'])
        self.assertEqual(code,2)
        provider.assert_not_called()

class ExplicitHoldTests(unittest.TestCase):
    def test_source_qualification_does_not_remove_user_hold(self):
        with self.assertRaisesRegex(ValueError,'explicit user policy'):
            paid_preflight({'paid_execution_allowed':True,'status':'frozen','blockers':[]},
                           {'offline_passed':True,'docker_passed':True,'source_reference_passed':True})
    def test_real_provider_initialization_cannot_override_hold(self):
        from native_pilot.provider import OpenAIProvider, ProviderFailure
        with self.assertRaises(ProviderFailure) as result:
            OpenAIProvider(allow_paid=True)
        self.assertEqual(result.exception.kind,'paid_execution_policy_hold')

class StaleReviewTests(unittest.TestCase):
    def test_stale_qualified_audit_cannot_freeze_current_changed_reviews(self):
        from native_pilot.util import file_digest
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            shutil.copytree(ROOT/'provenance',root/'provenance')
            shutil.copy(ROOT/'pyproject.toml',root/'pyproject.toml')
            bindings={name:file_digest(root/name) for name in
                      ('provenance/math_review.json','provenance/coding_review.json')}
            audit={'status':'qualified','blockers':[], 'review_hashes':bindings,
                   'source_lock_sha256':file_digest(root/'provenance/source_lock.json'),
                   'pair_semantics_verified':True}
            audit_path=root/'audit.json';audit_path.write_text(json.dumps(audit))
            (root/'provenance/math_review.json').write_text('{"candidates":[]}')
            selection={'tasks':[], 'smoke_task':{'task_id':'unit-smoke'}}
            with patch('native_pilot.data.select_tasks',return_value=selection):
                frozen=freeze(root/'new.json','unit',root,audit_path=audit_path)
            self.assertEqual(frozen['status'],'blocked')
            self.assertEqual(frozen['tasks'],[])
            self.assertTrue(any('review changed' in item for item in frozen['blockers']))


class IntegratedQualificationTests(unittest.TestCase):
    setUp=ManifestTests.setUp
    tearDown=ManifestTests.tearDown

    def fixture(self):
        # Synthetic software fixtures isolate the freeze barrier; these never
        # enter a production source registry or invoke a reference/provider.
        tasks=[]
        for domain in ('math','coding'):
            for index in range(12):
                tid=f'unit-{domain}-{index}'
                spec=({'answer':'1'} if domain=='math' else {'tests':[{'stdin':'','stdout':'1'}]})
                tasks.append({'task_id':tid,'domain':domain,'original_identity':tid,
                    'original_prompt':'Initial '+tid,'updated_prompt':'Updated '+tid,
                    'correction_prompt':'Correction '+tid,'qualification_evidence_sha256':'unit-evidence',
                    'original':spec,'updated':spec,'unchanged_control':index<4})
        smoke={**tasks[-1],'task_id':'unit-smoke','original_identity':'unit-smoke'}
        self.selection={'tasks':tasks,'smoke_task':smoke}
        self.audit_path=self.root/'qualified-audit.json'
        self.audit_path.write_text(json.dumps({'status':'qualified','blockers':[],
            'review_hashes':{name:file_digest(self.root/name) for name in
                ('provenance/math_review.json','provenance/coding_review.json')},
            'source_lock_sha256':file_digest(self.root/'provenance/source_lock.json'),
            'pair_semantics_verified':True}))
        keys={'original_reference','updated_reference','original_equivalent','updated_equivalent',
              'original_wrong_rejected','updated_wrong_rejected','stale_rejected'}
        checks={t['task_id']:{key:True for key in keys |
                    {'changed_answer' if t['domain']=='math' else 'changed_behavior'}}
                for t in tasks+[smoke]}
        self.completed={'offline_passed':True,'docker_passed':True,'source_reference_passed':True,
            'audit_sha256':file_digest(self.audit_path),'implementation_hashes':implementation_hashes(self.root),
            'covered_task_ids':sorted(checks),'source_references':{'passed':True,'checks':checks}}
        self.qualification_path=self.root/'completed-qualification.json'
        self.save_qualification()

    def save_qualification(self):
        self.qualification_path.write_text(json.dumps(self.completed))

    def freeze_fixture(self, *, provide_qualification=True):
        with patch('native_pilot.data.select_tasks',return_value=self.selection), \
             patch('native_pilot.qualification.assert_ordered_prefix'):
            return freeze(self.path,'unit-integrated',self.root,audit_path=self.audit_path,
                          qualification_path=self.qualification_path if provide_qualification else None)

    def test_current_complete_evidence_freezes_but_retains_paid_hold(self):
        self.fixture()
        frozen=self.freeze_fixture()
        self.assertEqual(frozen['status'],'frozen')
        self.assertTrue(frozen['source_qualified'])
        self.assertFalse(frozen['paid_execution_allowed'])
        self.assertEqual(len(frozen['tasks']),24)
        self.assertEqual(frozen['integrated_qualification']['sha256'],file_digest(self.qualification_path))
        load_manifest(self.path,root=self.root)
        self.qualification_path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'integrated qualification changed'):
            load_manifest(self.path,root=self.root)

    def test_missing_integrated_evidence_keeps_selection_empty(self):
        self.fixture()
        frozen=self.freeze_fixture(provide_qualification=False)
        self.assertEqual(frozen['status'],'blocked')
        self.assertEqual(frozen['tasks'],[])
        self.assertTrue(any('required before' in b for b in frozen['blockers']))

    def test_stale_implementation_cannot_reuse_passing_evidence(self):
        self.fixture()
        (self.root/'src/module.py').write_text('VALUE = 2\n')
        frozen=self.freeze_fixture()
        self.assertFalse(frozen['source_qualified'])
        self.assertEqual(frozen['schedule'],[])
        self.assertTrue(any('implementation is stale' in b for b in frozen['blockers']))

    def test_missing_smoke_coverage_cannot_freeze(self):
        self.fixture()
        self.completed['covered_task_ids'].remove('unit-smoke')
        self.save_qualification()
        frozen=self.freeze_fixture()
        self.assertEqual(frozen['status'],'blocked')
        self.assertTrue(any('omits required tasks: unit-smoke' in b for b in frozen['blockers']))

    def test_incomplete_required_task_checks_cannot_freeze(self):
        self.fixture()
        del self.completed['source_references']['checks']['unit-coding-0']['updated_equivalent']
        self.save_qualification()
        frozen=self.freeze_fixture()
        self.assertEqual(frozen['status'],'blocked')
        self.assertTrue(any('passing reference checks: unit-coding-0' in b for b in frozen['blockers']))

    def test_stale_audit_cannot_reuse_passing_evidence(self):
        self.fixture()
        audit=json.loads(self.audit_path.read_text());audit['revision']='changed'
        self.audit_path.write_text(json.dumps(audit))
        frozen=self.freeze_fixture()
        self.assertEqual(frozen['status'],'blocked')
        self.assertTrue(any('different source audit' in b for b in frozen['blockers']))

    def test_cli_passes_explicit_qualification_path(self):
        with patch('native_pilot.cli.freeze',return_value={
                'manifest_sha256':'unit','status':'blocked','blockers':[]}) as called:
            with contextlib.redirect_stdout(io.StringIO()):
                result=main(['freeze','--version','unit','--out',str(self.path),
                             '--qualification',str(self.root/'qualification.json')])
        self.assertEqual(result,0)
        self.assertEqual(called.call_args.kwargs['qualification_path'],self.root/'qualification.json')

    def test_qualification_binds_checked_ids_and_detects_midrun_changes(self):
        class Process:
            returncode=0;stdout='';stderr=''
        view={'manifest_sha256':'unit','tasks':[{'task_id':'unit-case'}],'smoke_task':None}
        before={'src/module.py':'before'};after={'src/module.py':'after'}
        with patch('native_pilot.cli.subprocess.run',return_value=Process()), \
             patch('native_pilot.cli.implementation_hashes',side_effect=[before,after]), \
             patch('native_pilot.sandbox.qualify_docker',return_value={'passed':True}), \
             patch('native_pilot.assets.hydrate_tasks',side_effect=lambda tasks,cache:tasks), \
             patch('native_pilot.grading.qualify_references',return_value={
                 'passed':True,'checks':{'unit-case':{'original_reference':True}}}):
            result=qualification(view,docker=True,cache=self.root)
        self.assertEqual(result['implementation_hashes'],before)
        self.assertEqual(result['covered_task_ids'],['unit-case'])
        self.assertFalse(result['offline_passed'])
        self.assertTrue(result['implementation_changed_during_qualification'])
