"""Freezing and approval barriers; no real provider is ever instantiated."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from native_pilot.cli import main, dry_run
from native_pilot.manifest import ROOT, freeze, load_manifest, paid_preflight


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
