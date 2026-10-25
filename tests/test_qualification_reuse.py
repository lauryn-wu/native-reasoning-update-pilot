import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from native_pilot.design import SEED, make_schedule
from native_pilot.manifest import implementation_hashes
from native_pilot.qualification_reuse import (
    bind_manifest_qualification, design_identity_report,
    reuse_reference_qualification, run_current_checks,
)
from native_pilot.util import digest, file_digest


class QualificationReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root/'work/cache'
        for name, text in {
            'src/native_pilot/grading.py': '# immutable grader\n',
            'src/native_pilot/sandbox/runner.py': '# immutable sandbox\n',
            'src/native_pilot/provider.py': '# prior transport\n',
            'src/native_pilot/manifest.py': '# prior authorization\n',
            'references/fixture.py': '# fixture; never executed\n',
            'pyproject.toml': '# pinned dependencies\n',
            'work/cache/source.json': '{"released":"fixture"}',
            'work/cache/lcb/test.json': '[{"stdin":"1","stdout":"2"}]',
        }.items():
            path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
        self.write('provenance/source_lock.json', {'artifacts': [{
            'path': 'source.json', 'sha256': file_digest(self.cache/'source.json')}]})
        self.write('provenance/execution_policy.json', {'paid_execution_allowed': False})
        self.write('provenance/pricing.json', {'fixture': 'unchanged'})
        reference = {'path': 'references/fixture.py', 'sha256': file_digest(self.root/'references/fixture.py')}
        tests = {'path': 'lcb/test.json', 'sha256': file_digest(self.cache/'lcb/test.json')}
        self.tasks = []
        for domain in ('math', 'coding'):
            for index in range(12):
                tid = f'fixture:{domain}:{index}'
                spec = {'answer': '1'} if domain == 'math' else {'reference_asset': reference, 'test_asset': tests}
                self.tasks.append({'task_id': tid, 'domain': domain, 'original_identity': tid,
                                   'original_prompt': 'initial '+tid, 'updated_prompt': 'updated '+tid,
                                   'correction_prompt': 'correction '+tid,
                                   'original': copy.deepcopy(spec), 'updated': copy.deepcopy(spec),
                                   'unchanged_control': index < 4})
        self.smoke = dict(copy.deepcopy(self.tasks[-1]), task_id='fixture:smoke', original_identity='fixture:smoke')
        self.selection = {'tasks': self.tasks, 'smoke_task': self.smoke}
        self.audit = self.write('provenance/qualification_audit.json', {
            'status': 'qualified', 'pair_semantics_verified': True,
            'source_lock_sha256': file_digest(self.root/'provenance/source_lock.json')})
        keys = {'original_reference', 'updated_reference', 'original_equivalent', 'updated_equivalent',
                'original_wrong_rejected', 'updated_wrong_rejected', 'stale_rejected'}
        checks = {t['task_id']: {k: True for k in keys | {
            'changed_answer' if t['domain'] == 'math' else 'changed_behavior'}} for t in self.tasks+[self.smoke]}
        self.docker = {'passed': True, 'image': 'pinned@sha256:fixture', 'image_id': 'sha256:fixture',
                       'architecture': 'arm64', 'os': 'linux', 'docker_version': '29',
                       'checks': {'network_denied': True, 'read_only': True}}
        self.old_q = {'offline_passed': True, 'docker_passed': True, 'source_reference_passed': True,
                      'audit_sha256': file_digest(self.audit), 'implementation_hashes': implementation_hashes(self.root),
                      'covered_task_ids': sorted(checks), 'reference_workers': 4,
                      'docker': self.docker, 'source_references': {'passed': True, 'status': 'passed',
                          'blockers': [], 'checks': checks, 'reference_methods': {'fixture': 'retained'},
                          'reference_executions': {'fixture': [{'evidence': 'unchanged'}]}}}
        self.qpath = self.write('provenance/integrated_qualification.json', self.old_q)
        self.old = {
            'status': 'frozen', 'source_qualified': True, 'blockers': [], 'version': 'v2',
            'source_audit_sha256': file_digest(self.audit), 'tasks': self.tasks, 'smoke_task': self.smoke,
            'schedule': make_schedule(self.tasks), 'seed': SEED, 'selection_rule': 'fixture',
            'research_question': 'unchanged', 'adaptation': 'unchanged',
            'planned_counts': {'responses': 200, 'smoke': 3}, 'settings': {'model': 'unchanged'},
            'pricing': {'unchanged': True}, 'hard_budget_usd': 40, 'analysis': {'unchanged': True},
            'implementation_hashes': implementation_hashes(self.root),
            'provenance_hashes': {str(p.relative_to(self.root)): file_digest(p) for p in (self.root/'provenance').glob('*.json')},
            'integrated_qualification': {'path': str(self.qpath.relative_to(self.root)), 'sha256': file_digest(self.qpath),
                'audit_sha256': file_digest(self.audit), 'covered_task_ids': sorted(checks),
                'implementation_hashes_sha256': digest(self.old_q['implementation_hashes'])}}
        self.old['tasks_sha256'] = digest(self.tasks)
        self.old['schedule_sha256'] = digest(self.old['schedule'])
        self.oldpath = self.write_manifest('manifests/v2.json', self.old)

    def write(self, name, value):
        path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True, indent=2)+'\n')
        return path

    def write_manifest(self, name, value):
        value.pop('manifest_sha256', None)
        value['manifest_sha256'] = digest(value)
        return self.write(name, value)

    def fresh(self):
        current = implementation_hashes(self.root)
        return {'offline_passed': True, 'docker_passed': True, 'test_returncode': 0,
                'implementation_hashes': current, 'implementation_hashes_after': current,
                'implementation_changed_during_qualification': False,
                'test_output': 'current units passed', 'docker': copy.deepcopy(self.docker)}

    def reuse(self, fresh=None):
        with patch('native_pilot.data.select_tasks', return_value=self.selection), \
             patch('native_pilot.grading.qualify_references', side_effect=AssertionError('No reference rerun')):
            return reuse_reference_qualification(self.oldpath, self.audit, fresh or self.fresh(),
                                                 cache=self.cache, root=self.root)

    def test_allowed_authorization_changes_reuse_exact_source_evidence_without_mutation(self):
        before = self.qpath.read_bytes()
        (self.root/'src/native_pilot/provider.py').write_text('# audited authorization update\n')
        self.write('provenance/execution_policy.json', {'paid_execution_allowed': True, 'scope': 'smoke_only'})
        result = self.reuse()
        self.assertEqual(self.qpath.read_bytes(), before)
        self.assertEqual(result['source_references'], self.old_q['source_references'])
        self.assertEqual(result['covered_task_ids'], self.old_q['covered_task_ids'])
        self.assertEqual(result['implementation_hashes'], implementation_hashes(self.root))
        self.assertFalse(result['paid_execution_allowed'])
        self.assertNotIn('manifest_sha256', result)
        self.assertFalse(result['reference_reuse']['source_references_executed'])
        self.assertEqual(result['reference_reuse']['current_orchestration_changes'][0]['path'], 'src/native_pilot/provider.py')
        result['source_references']['checks'].clear()
        self.assertTrue(self.old_q['source_references']['checks'])

    def test_changed_grading_sandbox_reference_dependency_or_file_set_rejected(self):
        for name in ('src/native_pilot/grading.py', 'src/native_pilot/sandbox/runner.py',
                     'references/fixture.py', 'pyproject.toml', 'src/native_pilot/new_dependency.py'):
            path = self.root/name
            previous = path.read_bytes() if path.exists() else None
            with self.subTest(name=name):
                path.write_text('changed\n')
                with self.assertRaisesRegex(ValueError, 'Reference dependency changed'):
                    self.reuse()
            if previous is None: path.unlink()
            else: path.write_bytes(previous)

    def test_changed_original_qualification_audit_sources_and_test_assets_rejected(self):
        for path in (self.qpath, self.audit, self.cache/'source.json', self.cache/'lcb/test.json',
                     self.root/'provenance/pricing.json'):
            previous = path.read_bytes()
            with self.subTest(path=path):
                path.write_bytes(previous+b'\n')
                with self.assertRaises(ValueError): self.reuse()
            path.write_bytes(previous)

    def test_changed_selection_rejected_even_if_ids_same(self):
        changed = copy.deepcopy(self.tasks)
        changed[0]['original_prompt'] += ' alteration'
        self.selection['tasks'] = changed
        with self.assertRaisesRegex(ValueError, 'Selected tasks'):
            self.reuse()

    def test_stale_failed_or_incomplete_fresh_checks_rejected(self):
        variants = []
        fresh = self.fresh(); fresh['offline_passed'] = False; variants.append(fresh)
        fresh = self.fresh(); fresh['implementation_hashes_after'] = {}; variants.append(fresh)
        fresh = self.fresh(); fresh['docker']['image_id'] = 'changed'; variants.append(fresh)
        fresh = self.fresh(); del fresh['docker']['checks']['network_denied']; variants.append(fresh)
        for fresh in variants:
            with self.subTest(fresh=fresh), self.assertRaises(ValueError): self.reuse(fresh)
        fresh = self.fresh()
        (self.root/'src/native_pilot/provider.py').write_text('# changed after fresh checks\n')
        with self.assertRaisesRegex(ValueError, 'stable current implementation'):
            self.reuse(fresh)

    def test_incomplete_old_source_checks_cannot_be_reused_even_if_rehashed(self):
        del self.old_q['source_references']['checks']['fixture:smoke']['updated_reference']
        self.write(str(self.qpath.relative_to(self.root)), self.old_q)
        self.old['integrated_qualification']['sha256'] = file_digest(self.qpath)
        self.write_manifest('manifests/v2.json', self.old)
        with self.assertRaisesRegex(ValueError, 'Previous reference qualification invalid'):
            self.reuse()

    def test_postfreeze_binding_uses_separate_record_and_rejects_changed_design(self):
        prefreeze = self.reuse()
        path = self.write('provenance/integrated-v3.json', prefreeze)
        current = copy.deepcopy(self.old)
        current['version'] = 'v3'
        current['integrated_qualification'].update(path=str(path.relative_to(self.root)), sha256=file_digest(path))
        manifest = self.write_manifest('manifests/v3.json', current)
        bound = bind_manifest_qualification(manifest, path, root=self.root)
        self.assertEqual(bound['manifest_sha256'], current['manifest_sha256'])
        self.assertEqual(bound['integrated_qualification_sha256'], file_digest(path))
        self.assertEqual(bound['source_references'], prefreeze['source_references'])
        self.assertNotIn('manifest_sha256', json.loads(path.read_text()))
        current['settings']['model'] = 'changed'
        self.write_manifest('manifests/v3.json', current)
        with self.assertRaisesRegex(ValueError, 'Research design changed'):
            bind_manifest_qualification(manifest, path, root=self.root)

    def test_design_report_binds_budget_analysis_and_all_task_bytes(self):
        for key in ('hard_budget_usd', 'analysis', 'smoke_task', 'settings', 'schedule'):
            changed = copy.deepcopy(self.old); changed[key] = None
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Research design changed'):
                design_identity_report(self.old, changed)

    def test_wrapper_rejects_replacement_history_even_when_new_manifest_binds_it(self):
        prefreeze = self.reuse()
        replacement = self.write('provenance/replacement.json', self.old_q)
        prefreeze['reference_reuse']['previous_qualification'] = {
            'path': str(replacement.relative_to(self.root)), 'sha256': file_digest(replacement)}
        path = self.write('provenance/integrated-v3.json', prefreeze)
        current = copy.deepcopy(self.old)
        current['integrated_qualification'].update(path=str(path.relative_to(self.root)), sha256=file_digest(path))
        manifest = self.write_manifest('manifests/v3.json', current)
        with self.assertRaisesRegex(ValueError, 'historical manifest binding'):
            bind_manifest_qualification(manifest, path, root=self.root)

    def test_fresh_checks_only_execute_units_and_docker_and_detect_changes(self):
        process = SimpleNamespace(returncode=0, stdout='suite passed', stderr='')
        with patch('native_pilot.qualification_reuse.subprocess.run', return_value=process) as units, \
             patch('native_pilot.sandbox.qualify_docker', return_value=self.docker) as docker, \
             patch('native_pilot.grading.qualify_references', side_effect=AssertionError('references forbidden')):
            result = run_current_checks(root=self.root)
        self.assertTrue(result['offline_passed']); self.assertTrue(result['docker_passed'])
        self.assertFalse(result['source_references_executed'])
        self.assertFalse(result['source_reference_passed'])
        units.assert_called_once(); docker.assert_called_once()
        with patch('native_pilot.qualification_reuse.implementation_hashes', side_effect=[{'before': 'x'}, {'after': 'y'}]), \
             patch('native_pilot.qualification_reuse.subprocess.run', return_value=process), \
             patch('native_pilot.sandbox.qualify_docker', return_value=self.docker):
            result = run_current_checks(root=self.root)
        self.assertFalse(result['offline_passed']); self.assertFalse(result['docker_passed'])


if __name__ == '__main__':
    unittest.main()
