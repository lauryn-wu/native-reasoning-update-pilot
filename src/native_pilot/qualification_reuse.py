"""Reuse completed reference checks only across unchanged grading dependencies.

The fresh unit suite and Docker restriction checks are executed separately.
These functions never execute a reference, invoke a model, or grant payment.
Returned records must be saved to new paths by the caller.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

from .assets import checked_path
from .design import SEED, make_schedule, validate_design
from .manifest import ROOT, implementation_hashes, load_manifest, _integrated_qualification
from .util import digest, file_digest, utcnow


# These modules control authorization, transport and orchestration. Changes are
# recorded, not silently treated as identical. Actual graders, asset loading,
# selection, analysis, references, runtime dependencies and sandbox stay frozen.
RECHECKED_ORCHESTRATION = frozenset({
    'src/native_pilot/cli.py', 'src/native_pilot/manifest.py',
    'src/native_pilot/provider.py', 'src/native_pilot/runner.py',
    'src/native_pilot/budget.py', 'src/native_pilot/qualification_reuse.py',
})
DESIGN_KEYS = (
    'research_question', 'adaptation', 'seed', 'selection_rule', 'tasks',
    'schedule', 'smoke_task', 'planned_counts', 'settings', 'pricing',
    'hard_budget_usd', 'analysis', 'tasks_sha256', 'schedule_sha256',
)


def _read(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError('Expected an evidence object: ' + str(path))
    return value


def _descriptor(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Evidence must be inside the repository: ' + str(path))
    return {'path': str(path.relative_to(root)), 'sha256': file_digest(path)}


def _rechecked(name):
    return name in RECHECKED_ORCHESTRATION or name.startswith(('tests/', 'docs/'))


def design_identity_report(previous, current):
    """Compare the complete prospective design, including full task records."""
    missing = [key for key in DESIGN_KEYS if key not in previous or key not in current]
    changed = [key for key in DESIGN_KEYS if previous.get(key) != current.get(key)]
    if missing or changed:
        raise ValueError('Research design changed: ' + ', '.join(sorted(set(missing + changed))))
    validate_design(current['tasks'], current['schedule'])
    return {'passed': True, 'fields': list(DESIGN_KEYS),
            'design_sha256': digest({key: current[key] for key in DESIGN_KEYS})}


def run_current_checks(*, root=ROOT):
    """Run current units and Docker software qualification, without references."""
    root = Path(root)
    before = implementation_hashes(root)
    process = subprocess.run(
        [sys.executable, '-m', 'unittest', 'discover', '-s', str(root/'tests'), '-v'],
        cwd=root, capture_output=True, text=True)
    docker = {'status': 'not_run', 'passed': False}
    if process.returncode == 0:
        from .sandbox import qualify_docker
        docker = qualify_docker()
    after = implementation_hashes(root)
    stable = before == after
    return {'at': utcnow(), 'scope': 'fresh_units_and_docker_only_no_reference_execution',
            'offline_passed': process.returncode == 0 and stable,
            'docker_passed': docker.get('passed') is True and stable,
            'test_returncode': process.returncode,
            'test_output': process.stdout + process.stderr, 'docker': docker,
            'implementation_hashes': before, 'implementation_hashes_after': after,
            'implementation_changed_during_qualification': not stable,
            'source_reference_passed': False, 'source_references_executed': False,
            'paid_calls': 0}


def _fresh_checks(fresh, current, old_docker):
    if (fresh.get('offline_passed') is not True or fresh.get('docker_passed') is not True
            or fresh.get('test_returncode') != 0
            or fresh.get('implementation_hashes') != current
            or fresh.get('implementation_hashes_after') != current
            or fresh.get('implementation_changed_during_qualification') is not False):
        raise ValueError('Fresh unit/Docker checks do not bind the stable current implementation')
    docker = fresh.get('docker', {})
    if docker.get('passed') is not True:
        raise ValueError('Fresh Docker checks did not pass')
    for key in ('image', 'image_id', 'architecture', 'os', 'docker_version'):
        if not old_docker.get(key) or docker.get(key) != old_docker[key]:
            raise ValueError('Docker runtime identity changed: ' + key)
    old_checks, new_checks = old_docker.get('checks', {}), docker.get('checks', {})
    if (not old_checks or not new_checks or not all(value is True for value in old_checks.values())
            or not set(old_checks).issubset(new_checks)
            or not all(value is True for value in new_checks.values())):
        raise ValueError('Fresh Docker report omits or fails a required restriction check')


def _asset_bindings(tasks, cache, root):
    """Verify every grading/proof asset descriptor without executing its content."""
    bindings = {}

    def visit(value):
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                scope = 'cache' if str(value['path']).startswith('lcb/') else 'root'
                base = cache if scope == 'cache' else root
                checked_path(base, value)
                key = scope + ':' + value['path']
                if key in bindings and bindings[key]['sha256'] != value['sha256']:
                    raise ValueError('Conflicting asset hashes: ' + key)
                bindings[key] = {'scope': scope, 'path': value['path'], 'sha256': value['sha256']}
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(tasks)
    lock = _read(root/'provenance/source_lock.json')
    if not lock.get('artifacts'):
        raise ValueError('Source lock has no pinned artifacts')
    for asset in lock['artifacts']:
        checked_path(cache, asset)
        bindings['cache:' + asset['path']] = {
            'scope': 'cache', 'path': asset['path'], 'sha256': asset['sha256']}
    return [bindings[key] for key in sorted(bindings)]


def reuse_reference_qualification(previous_manifest_path, audit_path, fresh_checks,
                                  *, cache, root=ROOT):
    """Return an audit-bound prefreeze record; preserve all historical evidence.

    The prior content-addressed frozen manifest supplies the trust anchor for its
    exact completed qualification file. Current authorization changes are not
    reference changes, but all such code changes are explicitly reported.
    """
    root, cache = Path(root).resolve(), Path(cache).resolve()
    previous = load_manifest(previous_manifest_path, verify_files=False, root=root)
    if previous.get('status') != 'frozen' or previous.get('source_qualified') is not True or previous.get('blockers'):
        raise ValueError('Previous manifest was not source-qualified and frozen')
    old_descriptor = previous.get('integrated_qualification')
    old_path = checked_path(root, old_descriptor)
    old = _read(old_path)
    tasks = previous['tasks'] + [previous['smoke_task']]
    _, blockers = _integrated_qualification(
        old_path, audit_sha256=previous['source_audit_sha256'], tasks=tasks,
        implementation=previous['implementation_hashes'], root=root)
    if blockers:
        raise ValueError('Previous reference qualification invalid: ' + '; '.join(blockers))
    required_ids = {task['task_id'] for task in tasks}
    if (set(old['covered_task_ids']) != required_ids or len(old['covered_task_ids']) != len(required_ids)
            or set(old['source_references']['checks']) != required_ids
            or old['source_references'].get('status') != 'passed'
            or old['source_references'].get('blockers')):
        raise ValueError('Previous qualification does not exactly cover the required tasks')
    if digest(old['implementation_hashes']) != old_descriptor.get('implementation_hashes_sha256'):
        raise ValueError('Previous qualification implementation binding changed')

    audit = _read(audit_path)
    audit_hash = file_digest(audit_path)
    if (audit_hash != previous['source_audit_sha256'] or audit_hash != old.get('audit_sha256')
            or audit.get('status') != 'qualified' or audit.get('pair_semantics_verified') is not True):
        raise ValueError('Source audit changed or is not qualified')
    from .data import select_tasks
    selection = select_tasks(audit, SEED)
    if selection['tasks'] != previous['tasks'] or selection['smoke_task'] != previous['smoke_task']:
        raise ValueError('Selected tasks or separate smoke task changed')
    if make_schedule(selection['tasks'], previous['seed']) != previous['schedule']:
        raise ValueError('Frozen schedule changed')

    current = implementation_hashes(root)
    before = previous['implementation_hashes']
    immutable = {}
    changes = []
    for name in sorted(set(before) | set(current)):
        if not _rechecked(name):
            if before.get(name) != current.get(name) or name not in before:
                raise ValueError('Reference dependency changed: ' + name)
            immutable[name] = current[name]
        elif before.get(name) != current.get(name):
            changes.append({'path': name, 'previous_sha256': before.get(name),
                            'current_sha256': current.get(name),
                            'verification': 'current full unit suite and explicit orchestration review'})
    # Existing provenance remains immutable except the separately authorized
    # payment policy. New provenance is bound by the subsequent v3 freeze.
    provenance = {}
    for name, expected in previous['provenance_hashes'].items():
        if name == 'provenance/execution_policy.json':
            continue
        checked_path(root, {'path': name, 'sha256': expected})
        provenance[name] = expected
    assets = _asset_bindings(tasks, cache, root)
    _fresh_checks(fresh_checks, current, old['docker'])
    if implementation_hashes(root) != current:
        raise ValueError('Implementation changed during reference evidence reuse')
    design = design_identity_report(previous, previous)
    reuse = {
        'method': 'exact_dependency_bound_reference_evidence_reuse_v1',
        'source_references_executed': False,
        'previous_manifest': _descriptor(previous_manifest_path, root),
        'previous_manifest_sha256': previous['manifest_sha256'],
        'previous_qualification': _descriptor(old_path, root),
        'source_references_sha256': digest(old['source_references']),
        'unchanged_implementation_dependencies': immutable,
        'unchanged_provenance_dependencies': provenance,
        'verified_source_and_grading_assets': assets,
        'current_orchestration_changes': changes,
        'design_identity': design,
        'fresh_checks_sha256': digest(fresh_checks),
    }
    return {
        'at': utcnow(), 'audit_sha256': audit_hash,
        'scope': 'prefreeze_reuse_of_complete_unchanged_reference_checks_with_fresh_units_and_docker',
        'offline_passed': True, 'docker_passed': True, 'source_reference_passed': True,
        'implementation_hashes': current, 'covered_task_ids': copy.deepcopy(old['covered_task_ids']),
        'source_references': copy.deepcopy(old['source_references']),
        'reference_workers': old.get('reference_workers', 1),
        'reference_workers_note': 'Historical reference run concurrency; no references rerun for reuse',
        'source_selection_complete': True, 'paid_execution_allowed': False,
        'test_output': fresh_checks['test_output'], 'docker': copy.deepcopy(fresh_checks['docker']),
        'fresh_checks': copy.deepcopy(fresh_checks), 'reference_reuse': reuse,
    }


def bind_manifest_qualification(manifest_path, prefreeze_path, *, root=ROOT):
    """Return a separate manifest-bound wrapper after freeze, avoiding a cycle."""
    root = Path(root).resolve()
    manifest = load_manifest(manifest_path, root=root)
    prefreeze = _read(prefreeze_path)
    descriptor = _descriptor(prefreeze_path, root)
    bound = manifest.get('integrated_qualification', {})
    if descriptor.get('sha256') != bound.get('sha256') or descriptor.get('path') != bound.get('path'):
        raise ValueError('Manifest does not bind this exact prefreeze qualification')
    reuse = prefreeze.get('reference_reuse', {})
    previous_path = checked_path(root, reuse.get('previous_manifest'))
    previous = load_manifest(previous_path, verify_files=False, root=root)
    historical = previous.get('integrated_qualification', {})
    if (reuse.get('previous_manifest_sha256') != previous['manifest_sha256']
            or any(reuse.get('previous_qualification', {}).get(key) != historical.get(key)
                   for key in ('path', 'sha256'))):
        raise ValueError('Reuse provenance does not match the historical manifest binding')
    old_q = _read(checked_path(root, reuse.get('previous_qualification')))
    if (digest(prefreeze.get('source_references')) != reuse.get('source_references_sha256')
            or prefreeze.get('source_references') != old_q.get('source_references')
            or prefreeze.get('covered_task_ids') != old_q.get('covered_task_ids')):
        raise ValueError('Reused source checks or coverage changed')
    current = implementation_hashes(root)
    _, blockers = _integrated_qualification(
        prefreeze_path, audit_sha256=manifest['source_audit_sha256'],
        tasks=manifest['tasks'] + [manifest['smoke_task']], implementation=current, root=root)
    if blockers:
        raise ValueError('Prefreeze qualification invalid: ' + '; '.join(blockers))
    report = design_identity_report(previous, manifest)
    if report != reuse.get('design_identity'):
        raise ValueError('Reused design identity binding changed')
    _fresh_checks(prefreeze['fresh_checks'], current, old_q['docker'])
    if digest(prefreeze['fresh_checks']) != reuse.get('fresh_checks_sha256'):
        raise ValueError('Fresh checks digest changed')
    result = copy.deepcopy(prefreeze)
    result.update(at=utcnow(), manifest_sha256=manifest['manifest_sha256'],
                  integrated_qualification_sha256=descriptor['sha256'],
                  scope='manifest_bound_wrapper_of_verified_prefreeze_reference_reuse',
                  prefreeze_qualification=descriptor)
    return result
