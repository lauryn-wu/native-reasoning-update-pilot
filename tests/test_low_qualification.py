"""Synthetic historical evidence exercises reuse without Docker or references."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_qualification_reuse as fixtures
from native_pilot.low_qualification import qualify, validate_evidence
from native_pilot.manifest import implementation_hashes
from native_pilot.util import digest, file_digest


class LowQualificationTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.QualificationReuseTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root, self.cache = fixture.root, fixture.cache
        self.previous = copy.deepcopy(fixture.old)
        self.previous.update(version='pilot-v6', tasks=[copy.deepcopy(fixture.tasks[i]) for i in (0, 1, 12, 13)])
        for name in ('budget.py', 'cli.py'):
            (self.root/'src/native_pilot'/name).write_text('# frozen v6 code\n')
        self.old_q = copy.deepcopy(fixture.old_q)
        self.refresh_historical_bindings()
        self.runner = patch('native_pilot.low_qualification.run_current_checks', side_effect=self.fresh)
        self.run_checks = self.runner.start()
        self.addCleanup(self.runner.stop)

    def refresh_historical_bindings(self):
        hashes = implementation_hashes(self.root)
        self.previous['implementation_hashes'] = hashes
        self.old_q['implementation_hashes'] = copy.deepcopy(hashes)
        self.fixture.write(str(self.fixture.qpath.relative_to(self.root)), self.old_q)
        self.previous['integrated_qualification'].update(
            sha256=file_digest(self.fixture.qpath),
            covered_task_ids=sorted(set(self.old_q['covered_task_ids'])),
            implementation_hashes_sha256=digest(hashes))
        self.previous['provenance_hashes'] = {
            str(p.relative_to(self.root)): file_digest(p)
            for p in (self.root/'provenance').glob('*.json')}
        self.previous.pop('manifest_sha256', None)
        self.previous['manifest_sha256'] = digest(self.previous)

    def fresh(self, *, root):
        self.assertEqual(root.resolve(), self.root.resolve())
        current = implementation_hashes(self.root)
        return {'offline_passed': True, 'docker_passed': True, 'test_returncode': 0,
                'implementation_hashes': current, 'implementation_hashes_after': current,
                'implementation_changed_during_qualification': False,
                'test_output': 'synthetic passing units', 'docker': copy.deepcopy(self.fixture.docker),
                'source_references_executed': False, 'paid_calls': 0}

    def qualify(self):
        with patch('native_pilot.grading.qualify_references', side_effect=AssertionError('No reference execution')):
            return qualify(self.previous, self.cache, self.root)

    def test_reuses_all_25_checks_for_four_cases_and_smoke_without_mutation(self):
        previous = copy.deepcopy(self.previous)
        historical = self.fixture.qpath.read_bytes()
        result = self.qualify()
        self.assertTrue(result['passed'])
        self.assertEqual(result['prior_manifest_sha256'], self.previous['manifest_sha256'])
        self.assertEqual(len(result['covered_task_ids']), 25)
        self.assertEqual(result['source_references'], self.old_q['source_references'])
        self.assertEqual(result['historical_qualification'], self.previous['integrated_qualification'])
        self.assertEqual(result['paid_calls'], 0)
        self.assertFalse(result['source_references_executed'])
        self.assertEqual(self.fixture.qpath.read_bytes(), historical)
        self.assertEqual(self.previous, previous)
        self.run_checks.assert_called_once_with(root=self.root.resolve())
        result['source_references']['checks'].clear()
        self.assertTrue(self.old_q['source_references']['checks'])

    def test_symlinked_temporary_root_qualifies_the_same_directory(self):
        original = self.root
        with tempfile.TemporaryDirectory() as parent:
            alias = Path(parent) / 'alias'
            alias.symlink_to(original.resolve(), target_is_directory=True)
            self.root = alias
            try:
                self.assertTrue(self.qualify()['passed'])
                self.run_checks.assert_called_once_with(root=original.resolve())
            finally:
                self.root = original

    def test_failed_fresh_checks_are_saved_for_local_diagnosis(self):
        fresh = self.fresh(root=self.root)
        fresh.update(offline_passed=False, docker_passed=False, test_returncode=1,
                     test_output='synthetic qualification test failure',
                     docker={'passed': False, 'status': 'not_run'})
        self.run_checks.side_effect = None
        self.run_checks.return_value = fresh
        with self.assertRaisesRegex(ValueError, 'runs/low-preparation-checks.json'):
            self.qualify()
        saved = json.loads((self.root / 'runs/low-preparation-checks.json').read_text())
        self.assertEqual(saved, fresh)
        self.assertFalse(saved['source_references_executed'])
        self.assertEqual(saved['paid_calls'], 0)

    def test_allows_only_named_source_edits_additions_and_fresh_tests_docs(self):
        for name in ('provider.py', 'budget.py', 'low_effort.py', 'low_runner.py',
                     'low_authorization.py', 'low_qualification.py'):
            (self.root/'src/native_pilot'/name).write_text('# freshly qualified change\n')
        for name in ('tests/test_new.py', 'docs/LOW_EFFORT.md'):
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# fresh evidence\n')
        self.fixture.write('provenance/execution_policy.json', {'scope': 'new explicit authorization'})
        result = self.qualify()
        self.assertEqual(result['implementation_hashes'], implementation_hashes(self.root))

    def test_immutable_source_references_sandbox_and_dependency_changes_block(self):
        for name in ('src/native_pilot/cli.py', 'src/native_pilot/grading.py',
                     'src/native_pilot/sandbox/runner.py', 'src/native_pilot/manifest.py',
                     'references/fixture.py', 'pyproject.toml', 'src/native_pilot/unapproved.py'):
            path = self.root/name
            old = path.read_bytes() if path.exists() else None
            path.write_text('# changed dependency\n')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Immutable v6 reference dependency'):
                self.qualify()
            if old is None:
                path.unlink()
            else:
                path.write_bytes(old)
        self.run_checks.assert_not_called()

    def test_deleting_allowed_existing_source_is_not_an_authorized_change(self):
        (self.root/'src/native_pilot/provider.py').unlink()
        with self.assertRaisesRegex(ValueError, 'Immutable v6 reference dependency'):
            self.qualify()

    def test_historical_provenance_cannot_change(self):
        (self.root/'provenance/pricing.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.qualify()
        self.run_checks.assert_not_called()

    def test_historical_manifest_and_qualification_hashes_are_required(self):
        self.previous['version'] = 'pilot-v5'
        with self.assertRaisesRegex(ValueError, 'intact frozen v6'):
            self.qualify()
        self.previous['version'] = 'pilot-v6'
        self.fixture.qpath.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.qualify()

    def test_missing_required_check_or_smoke_coverage_blocks_reuse(self):
        tid = self.previous['smoke_task']['task_id']
        del self.old_q['source_references']['checks'][tid]['updated_reference']
        self.refresh_historical_bindings()
        with self.assertRaisesRegex(ValueError, 'Historical v6 reference qualification'):
            self.qualify()

    def test_historical_coverage_can_be_exactly_required_five(self):
        ids = {t['task_id'] for t in self.previous['tasks'] + [self.previous['smoke_task']]}
        self.old_q['covered_task_ids'] = sorted(ids)
        self.old_q['source_references']['checks'] = {
            key: value for key, value in self.old_q['source_references']['checks'].items() if key in ids}
        self.refresh_historical_bindings()
        self.assertEqual(len(self.qualify()['covered_task_ids']), 5)

    def test_cached_grading_and_source_assets_are_checked_without_execution(self):
        for name in ('source.json', 'lcb/test.json'):
            path = self.cache/name
            old = path.read_bytes()
            path.write_text('changed asset')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                self.qualify()
            path.write_bytes(old)
        self.run_checks.assert_not_called()

    def test_failed_stale_or_runtime_mismatched_fresh_checks_block(self):
        variants = []
        fresh = self.fresh(root=self.root)
        for key, value in (('offline_passed', False), ('docker_passed', False),
                           ('test_returncode', 1), ('implementation_hashes_after', {}),
                           ('source_references_executed', True), ('paid_calls', 1)):
            altered = copy.deepcopy(fresh)
            altered[key] = value
            variants.append(altered)
        altered = copy.deepcopy(fresh)
        altered['docker']['image_id'] = 'sha256:changed'
        variants.append(altered)
        altered = copy.deepcopy(fresh)
        altered['docker']['checks']['network_denied'] = False
        variants.append(altered)
        for index, changed in enumerate(variants):
            self.run_checks.side_effect = None
            self.run_checks.return_value = changed
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.qualify()

    def test_validation_does_not_rerun_checks_and_accepts_hash_mapping_or_manifest(self):
        result = self.qualify()
        self.run_checks.reset_mock()
        current = implementation_hashes(self.root)
        self.assertTrue(validate_evidence(result, self.previous, current, self.root))
        self.assertTrue(validate_evidence(result, self.previous, {'implementation_hashes': current}, self.root))
        self.run_checks.assert_not_called()

    def test_load_validation_rejects_changed_evidence_or_current_code(self):
        result = self.qualify()
        for field, value in (('passed', False), ('source_references', {}),
                             ('historical_qualification', {}), ('covered_task_ids', []),
                             ('asset_bindings', []), ('fresh_checks_sha256', 'bad'),
                             ('paid_calls', 1)):
            altered = copy.deepcopy(result)
            altered[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_evidence(altered, self.previous, implementation_hashes(self.root), self.root)
        (self.root/'src/native_pilot/provider.py').write_text('# changed after tests\n')
        with self.assertRaisesRegex(ValueError, 'Current implementation hashes'):
            validate_evidence(result, self.previous, result['implementation_hashes'], self.root)
        with self.assertRaisesRegex(ValueError, 'evidence or historical binding changed'):
            validate_evidence(result, self.previous, implementation_hashes(self.root), self.root)


if __name__ == '__main__':
    unittest.main()
