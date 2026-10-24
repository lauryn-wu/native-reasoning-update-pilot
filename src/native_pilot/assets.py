"""Verify and load frozen grading assets; never execute reference source here."""
from __future__ import annotations
import copy
import json
from pathlib import Path
from .util import file_digest

ROOT = Path(__file__).resolve().parents[2]


def checked_path(base, asset):
    if not isinstance(asset, dict) or not isinstance(asset.get('path'), str):
        raise ValueError('Missing grading asset descriptor')
    base = Path(base).resolve()
    path = (base / asset['path']).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError('Grading asset missing or outside its allowed root: ' + asset['path'])
    if file_digest(path) != asset.get('sha256'):
        raise ValueError('Frozen grading asset checksum mismatch: ' + asset['path'])
    return path


def hydrate_tasks(tasks, cache, *, root=ROOT):
    """Hydration does not change frozen task identities or the manifest hash."""
    result = copy.deepcopy(tasks)
    for task in result:
        if task.get('domain') != 'coding':
            continue
        for variant in ('original', 'updated'):
            spec = task[variant]
            if 'test_asset' in spec:
                spec['tests'] = json.loads(checked_path(cache, spec['test_asset']).read_text())
            if 'reference_asset' in spec:
                spec['reference_solution'] = checked_path(root, spec['reference_asset']).read_text()
            if not isinstance(spec.get('tests'), list) or not spec['tests']:
                raise ValueError('Coding task has no verified tests: ' + task['task_id'])
    return result
