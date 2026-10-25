"""Reuse v6 reference evidence after a narrow, freshly checked v7 code change.

No function here runs reference solutions or model calls. Qualification runs the
current unit suite and Docker checks; loading stored evidence only verifies it.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .assets import checked_path
from .manifest import ROOT, _integrated_qualification, implementation_hashes
from .qualification_reuse import _asset_bindings, _fresh_checks, run_current_checks
from .util import atomic_json, digest, utcnow


_CHANGED_SOURCE = frozenset({
    'src/native_pilot/provider.py', 'src/native_pilot/budget.py',
})
_ADDED_SOURCE = frozenset({
    'src/native_pilot/low_effort.py', 'src/native_pilot/low_runner.py',
    'src/native_pilot/low_authorization.py', 'src/native_pilot/low_qualification.py',
})


def _historical(previous, root):
    if (previous.get('version') != 'pilot-v6' or previous.get('status') != 'frozen'
            or previous.get('source_qualified') is not True or previous.get('blockers')
            or digest({k: v for k, v in previous.items() if k != 'manifest_sha256'})
            != previous.get('manifest_sha256')):
        raise ValueError('Reference reuse requires the intact frozen v6 manifest')
    descriptor = previous.get('integrated_qualification')
    old_path = checked_path(root, descriptor)
    old = json.loads(old_path.read_text())
    tasks = previous['tasks'] + [previous['smoke_task']]
    verified, blockers = _integrated_qualification(
        old_path, audit_sha256=previous['source_audit_sha256'], tasks=tasks,
        implementation=previous['implementation_hashes'], root=root)
    if blockers or verified != descriptor:
        raise ValueError('Historical v6 reference qualification is invalid: ' + '; '.join(blockers))
    covered = old.get('covered_task_ids', [])
    references = old.get('source_references', {})
    required_ids = {task['task_id'] for task in tasks}
    if (len(covered) != len(set(covered)) or not required_ids.issubset(covered)
            or set(references.get('checks', {})) != set(covered)
            or references.get('status') != 'passed' or references.get('blockers')):
        raise ValueError('Historical reference coverage does not include the required tasks and smoke')
    return old


def _dependencies(previous, current, root):
    before = previous['implementation_hashes']
    for name in sorted(set(before) | set(current)):
        if name.startswith(('tests/', 'docs/')):
            continue
        if name in _CHANGED_SOURCE and name in before and name in current:
            continue
        if name in _ADDED_SOURCE and name not in before and name in current:
            continue
        if before.get(name) != current.get(name) or name not in before or name not in current:
            raise ValueError('Immutable v6 reference dependency changed: ' + name)
    for name, expected in previous['provenance_hashes'].items():
        if name != 'provenance/execution_policy.json':
            checked_path(root, {'path': name, 'sha256': expected})


def _expected_asset_bindings(tasks, root):
    """Rebuild bound descriptors without requiring the external source cache.

    Qualification checks the cached bytes. Frozen-load validation rechecks root
    assets and every descriptor; ordinary hydration checks cached bytes again.
    """
    bindings = {}

    def add(asset, scope):
        key = scope + ':' + asset['path']
        value = {'scope': scope, 'path': asset['path'], 'sha256': asset['sha256']}
        if key in bindings and bindings[key] != value:
            raise ValueError('Conflicting asset hashes: ' + key)
        if scope == 'root':
            checked_path(root, asset)
        bindings[key] = value

    def visit(value):
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                add(value, 'cache' if str(value['path']).startswith('lcb/') else 'root')
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(tasks)
    lock = json.loads((root/'provenance/source_lock.json').read_text())
    if not lock.get('artifacts'):
        raise ValueError('Source lock has no pinned artifacts')
    for asset in lock['artifacts']:
        add(asset, 'cache')
    return [bindings[key] for key in sorted(bindings)]


def qualify(previous, cache, root=ROOT):
    """Return fresh software evidence plus the unchanged historical references."""
    root, cache = Path(root).resolve(), Path(cache).resolve()
    old = _historical(previous, root)
    current = implementation_hashes(root)
    _dependencies(previous, current, root)
    tasks = previous['tasks'] + [previous['smoke_task']]
    assets = _asset_bindings(tasks, cache, root)
    fresh = run_current_checks(root=root)
    # Retain the actual diagnostics before applying the qualification gate.
    # This local record is not qualification evidence or an authorization.
    diagnostic_path = 'runs/low-preparation-checks.json'
    atomic_json(root / diagnostic_path, fresh)
    try:
        _fresh_checks(fresh, current, old['docker'])
    except ValueError as exc:
        raise ValueError(
            f'{exc}; unit exit={fresh.get("test_returncode")}, '
            f'Docker={fresh.get("docker", {}).get("status", "unknown")}, '
            f'files changed={fresh.get("implementation_changed_during_qualification")}. '
            f'Details: {diagnostic_path}') from exc
    if (fresh.get('source_references_executed') is not False
            or fresh.get('paid_calls') != 0):
        raise ValueError('Fresh qualification must not execute references or paid calls')
    if implementation_hashes(root) != current:
        raise ValueError('Implementation changed during low-effort qualification')
    result = {
        'schema_version': 1, 'at': utcnow(), 'passed': True,
        'scope': 'low_effort_followup_unchanged_v6_references_fresh_software_checks',
        'prior_manifest_sha256': previous['manifest_sha256'],
        'historical_qualification': copy.deepcopy(previous['integrated_qualification']),
        'audit_sha256': previous['source_audit_sha256'],
        'implementation_hashes': current,
        'covered_task_ids': copy.deepcopy(old['covered_task_ids']),
        'source_references': copy.deepcopy(old['source_references']),
        'source_references_executed': False, 'paid_calls': 0,
        'source_reference_passed': True, 'offline_passed': True, 'docker_passed': True,
        'paid_execution_allowed': False,
        'docker': copy.deepcopy(fresh['docker']),
        'fresh_checks': copy.deepcopy(fresh), 'fresh_checks_sha256': digest(fresh),
        'asset_bindings': assets,
    }
    validate_evidence(result, previous, current, root)
    return result


def validate_evidence(q, previous, current, root=ROOT):
    """Validate stored qualification without rerunning units, Docker or references.

    ``current`` may be the implementation hash mapping or a frozen v7 manifest
    containing that mapping. The caller binds the entire record's file hash.
    """
    root = Path(root).resolve()
    if isinstance(current, dict) and 'implementation_hashes' in current:
        current = current['implementation_hashes']
    if current != implementation_hashes(root):
        raise ValueError('Current implementation hashes do not match files on disk')
    old = _historical(previous, root)
    _dependencies(previous, current, root)
    if (not isinstance(q, dict) or q.get('schema_version') != 1 or q.get('passed') is not True
            or q.get('prior_manifest_sha256') != previous['manifest_sha256']
            or q.get('historical_qualification') != previous['integrated_qualification']
            or q.get('audit_sha256') != previous['source_audit_sha256']
            or q.get('implementation_hashes') != current
            or q.get('covered_task_ids') != old['covered_task_ids']
            or q.get('source_references') != old['source_references']
            or q.get('source_references_executed') is not False or q.get('paid_calls') != 0
            or q.get('source_reference_passed') is not True
            or q.get('offline_passed') is not True or q.get('docker_passed') is not True
            or q.get('paid_execution_allowed') is not False):
        raise ValueError('Low-effort qualification evidence or historical binding changed')
    fresh = q.get('fresh_checks', {})
    _fresh_checks(fresh, current, old['docker'])
    if (q.get('fresh_checks_sha256') != digest(fresh) or q.get('docker') != fresh.get('docker')
            or fresh.get('source_references_executed') is not False
            or fresh.get('paid_calls') != 0):
        raise ValueError('Fresh software evidence changed or exceeded its scope')
    expected = _expected_asset_bindings(previous['tasks'] + [previous['smoke_task']], root)
    if q.get('asset_bindings') != expected:
        raise ValueError('Source or grading asset bindings changed')
    return True
