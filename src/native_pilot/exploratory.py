"""Prospectively bounded four-case feasibility screen, separate from full study."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .util import atomic_json, digest, file_digest, utcnow

ROOT = Path(__file__).resolve().parents[2]
TASK_IDS = ('aime2025:1042', 'aime2025:1057', 'livecodebench:299', 'livecodebench:276')
AUTHORIZATION = {
    'allowed': True,
    'authorization_id': 'user-2026-10-24-exploratory-four-case-v6',
    'manifest_version': 'pilot-v6',
    'task_ids': list(TASK_IDS),
    'max_logical_calls': 28,
    'max_transport_retries_per_call': 1,
    'additional_budget_usd': 5,
    'shared_budget_usd': 40,
    'soft_dispatch_deadline_seconds': 1800,
}
RECORD_PATH = 'provenance/exploratory_authorization_v6.json'
PRIOR_MANIFEST_PATH = 'manifests/pilot-v5.json'
PRIOR_MANIFEST_SHA256 = 'f58b073fa25721023e0ee82e0f33ba1612bba740394d73d656a8cbfb546e6d1a'
COUNTS = {'problems': 4, 'math': 2, 'coding': 2, 'initial': 4,
          'updated_and_fresh': 24, 'unchanged': 0, 'responses': 28, 'new_smoke': 0}
ANALYSIS = {
    'mode': 'descriptive_feasibility_screen',
    'initial_correctness': 'Report every initial result; never select or suppress calls by correctness',
    'branch_accuracy': 'Report correct/graded counts and missing outcomes, by task and branch, two samples each',
    'paired_comparisons': 'Report complete retained/dropped sample pairs and complete seven-call task blocks',
    'population': 'All observed tasks and a separately labeled initial-correct subset; neither is confirmatory',
    'timing': 'Wall-clock elapsed since the first reservation, including resume downtime; in-flight completion may exceed deadline',
    'spending': 'Additional charged-plus-reserved scope total and shared campaign total, including uncertain attempts',
    'full_study_significance_gate_applied': False,
    'null_result_rules_out_hypothesis': False,
    'interpretation': 'Feasibility screen only; incomplete coverage and a null difference cannot rule out the hypothesis',
}


def make_schedule(tasks):
    if [task['task_id'] for task in tasks] != list(TASK_IDS):
        raise ValueError('Exploratory tasks must follow the exact user-requested order')
    within = [('initial', 0)] + [(branch, sample) for sample in (1, 2)
        for branch in ('updated_retained', 'updated_dropped', 'fresh')]
    return [{'call_id': f'{tid}/{branch}/{sample}', 'task_id': tid,
             'condition': branch, 'sample': sample}
            for tid in TASK_IDS for branch, sample in within]


def validate_design(tasks, schedule):
    if (len(tasks) != 4 or [t.get('task_id') for t in tasks] != list(TASK_IDS)
            or [t.get('domain') for t in tasks] != ['math', 'math', 'coding', 'coding']
            or any(t.get('unchanged_control') for t in tasks)):
        raise ValueError('Need the four exact requested cases with their unchanged control flags')
    if schedule != make_schedule(tasks):
        raise ValueError('Exploratory schedule must contain exactly four complete seven-call blocks')


def _record_and_prior(manifest=None, *, root=ROOT):
    from .manifest import load_manifest
    root = Path(root)
    path = root/RECORD_PATH
    record = json.loads(path.read_text())
    if record.get('authorization') != AUTHORIZATION:
        raise ValueError('Exploratory authorization record changed')
    descriptor = {'path': RECORD_PATH, 'sha256': file_digest(path)}
    if manifest is not None and (manifest.get('exploratory_protocol') != descriptor
            or manifest.get('provenance_hashes', {}).get(RECORD_PATH) != descriptor['sha256']):
        raise ValueError('Exploratory manifest lacks the exact prospective protocol binding')
    prior_d = record.get('prior_manifest', {})
    prior_path = root/PRIOR_MANIFEST_PATH
    if (prior_d.get('path') != PRIOR_MANIFEST_PATH
            or prior_d.get('sha256') != file_digest(prior_path)
            or prior_d.get('manifest_sha256') != PRIOR_MANIFEST_SHA256):
        raise ValueError('Prior v5 manifest binding changed')
    prior = load_manifest(prior_path, verify_files=False, root=root)
    if prior['manifest_sha256'] != PRIOR_MANIFEST_SHA256 or prior['version'] != 'pilot-v5':
        raise ValueError('Historical v5 manifest changed')
    archived = record.get('prior_policy', {})
    if (archived.get('path') != 'provenance/execution_policy_v5.json'
            or archived.get('sha256') != file_digest(root/archived['path'])
            or archived['sha256'] != prior['provenance_hashes']['provenance/execution_policy.json']):
        raise ValueError('Historical v5 execution policy changed')
    smoke_d = record.get('verified_smoke', {})
    if (smoke_d.get('path') != 'docs/SMOKE_V5_LIVE_VERIFICATION.json'
            or smoke_d.get('sha256') != file_digest(root/smoke_d['path'])
            or smoke_d.get('protocol_passed') is not True):
        raise ValueError('Verified historical smoke evidence changed')
    smoke = json.loads((root/smoke_d['path']).read_text())
    if smoke.get('manifest_sha256') != PRIOR_MANIFEST_SHA256 or smoke.get('protocol_passed') is not True:
        raise ValueError('Historical smoke has not passed protocol verification')
    selected = [next(t for t in prior['tasks'] if t['task_id'] == tid) for tid in TASK_IDS]
    selection = record.get('selection', {})
    if (selection.get('task_ids') != list(TASK_IDS)
            or selection.get('model_outcomes_used_for_selection') is not False
            or selection.get('prospective') is not True
            or selection.get('task_records_sha256') != {t['task_id']: digest(t) for t in selected}):
        raise ValueError('Prospective subset or task identity changed')
    return record, prior, descriptor


def subset_identity_report(previous, current):
    selected = [next(t for t in previous['tasks'] if t['task_id'] == tid) for tid in TASK_IDS]
    if current['tasks'] != selected:
        raise ValueError('Subset task records, prompts, graders or references changed')
    for key in ('settings', 'pricing', 'hard_budget_usd', 'research_question', 'adaptation',
                'source_audit_sha256', 'smoke_task', 'seed'):
        if current.get(key) != previous.get(key):
            raise ValueError('Protected exploratory source field changed: ' + key)
    validate_design(current['tasks'], current['schedule'])
    if current.get('analysis') != ANALYSIS or current.get('planned_counts') != COUNTS:
        raise ValueError('Exploratory analysis or counts changed')
    return {'passed': True, 'task_ids': list(TASK_IDS),
            'task_records_sha256': {task['task_id']: digest(task) for task in selected},
            'settings_sha256': digest(current['settings']), 'schedule_sha256': digest(current['schedule']),
            'full_study_significance_gate_applied': False}


def validate_scope(manifest, policy):
    if (policy.get('paid_execution_allowed') is not False or policy.get('protocol_smoke') is not None
            or policy.get('exploratory_pilot') != AUTHORIZATION
            or manifest.get('execution_scope') != 'exploratory_pilot'
            or manifest.get('exploratory_authorization') != AUTHORIZATION
            or manifest.get('version') != AUTHORIZATION['manifest_version']
            or manifest.get('paid_execution_allowed') is not False
            or manifest.get('protocol_smoke_authorization') is not None
            or manifest.get('continuation_recovery') is not None
            or manifest.get('status') != 'frozen' or manifest.get('blockers')):
        raise ValueError('Only the explicitly bounded four-case exploratory scope is authorized')
    _, previous, _ = _record_and_prior(manifest)
    subset_identity_report(previous, manifest)


def verify_prior_smoke(manifest, ledger):
    """Verify unchanged historical rows and protocol; never use answer correctness."""
    from .runner import smoke_protocol_report
    record, previous, _ = _record_and_prior(manifest)
    rows = ledger.rows()
    expected = record['preservation']['historical_attempts']
    old_versions = {item['manifest_sha256'] for item in expected}
    historical = [row for row in rows if row['manifest_hash'] in old_versions]
    if len(historical) != len(expected):
        raise ValueError('Historical smoke attempts changed')
    for item in expected:
        matched = [row for row in historical if row['call_id'] == item['call_id'] and row['attempt'] == item['attempt']]
        if len(matched) != 1 or digest(matched[0]) != item['row_sha256']:
            raise ValueError('Historical smoke attempt or checkpoint changed')
    for item in record['preservation']['historical_meta']:
        value = ledger.db.execute('SELECT value FROM meta WHERE key=?', (item['key'],)).fetchone()
        if not value or value[0] != item['value']:
            raise ValueError('Historical authorization or dispatch claim changed')
    report = smoke_protocol_report(ledger, previous)
    if report.get('protocol_passed') is not True:
        raise ValueError('The existing v5 smoke protocol must pass before exploratory dispatch')
    return report


def freeze(destination, *, qualification_path, root=ROOT):
    from .manifest import _integrated_qualification, implementation_hashes
    root = Path(root)
    record, previous, descriptor = _record_and_prior(root=root)
    m = copy.deepcopy(previous)
    tasks = [copy.deepcopy(next(t for t in previous['tasks'] if t['task_id'] == tid)) for tid in TASK_IDS]
    implementation = implementation_hashes(root)
    integrated, blockers = _integrated_qualification(qualification_path,
        audit_sha256=previous['source_audit_sha256'], tasks=tasks+[previous['smoke_task']],
        implementation=implementation, root=root)
    if blockers:
        raise ValueError('Exploratory qualification incomplete: ' + '; '.join(blockers))
    m.update(version='pilot-v6', created_at=utcnow(), execution_scope='exploratory_pilot',
             exploratory_authorization=copy.deepcopy(AUTHORIZATION), exploratory_protocol=descriptor,
             protocol_smoke_authorization=None, continuation_recovery=None, paid_execution_allowed=False,
             status='frozen', blockers=[], source_qualified=True,
             execution_blockers=['The full 200-response pilot remains blocked; only the bounded four-case feasibility screen may dispatch'],
             selection_rule='Prospective explicit user subset in user-listed order; no experimental outcomes used',
             tasks=tasks, schedule=make_schedule(tasks), planned_counts=copy.deepcopy(COUNTS),
             analysis=copy.deepcopy(ANALYSIS), implementation_hashes=implementation,
             integrated_qualification=integrated,
             provenance_hashes={str(p.relative_to(root)):file_digest(p) for p in sorted((root/'provenance').glob('*.json'))})
    m['tasks_sha256']=digest(m['tasks']);m['schedule_sha256']=digest(m['schedule'])
    m.pop('manifest_sha256', None)
    subset_identity_report(previous, m)
    policy=json.loads((root/'provenance/execution_policy.json').read_text())
    if policy.get('exploratory_pilot') != AUTHORIZATION or policy.get('paid_execution_allowed') is not False:
        raise ValueError('Current policy does not authorize this bounded freeze')
    m['manifest_sha256']=digest(m)
    atomic_json(destination,m,exclusive=True)
    return m


def bind_qualification(manifest_path, prefreeze_path, *, root=ROOT):
    from .manifest import load_manifest, implementation_hashes, _integrated_qualification
    from .qualification_reuse import _fresh_checks
    root=Path(root)
    manifest=load_manifest(manifest_path,root=root)
    prefreeze=json.loads(Path(prefreeze_path).read_text())
    descriptor={'path':str(Path(prefreeze_path).resolve().relative_to(root.resolve())),
                'sha256':file_digest(prefreeze_path)}
    integrated=manifest['integrated_qualification']
    if any(integrated.get(key)!=value for key,value in descriptor.items()):
        raise ValueError('Exploratory manifest does not bind exact prefreeze evidence')
    _, previous, _ = _record_and_prior(manifest,root=root)
    reuse=prefreeze.get('reference_reuse', {})
    old_descriptor=previous['integrated_qualification']
    if (reuse.get('previous_manifest_sha256')!=previous['manifest_sha256']
            or any(reuse.get('previous_qualification',{}).get(key)!=old_descriptor.get(key) for key in ('path','sha256'))):
        raise ValueError('Exploratory reference evidence has wrong historical origin')
    old_path=root/old_descriptor['path']
    if file_digest(old_path)!=old_descriptor['sha256']:
        raise ValueError('Historical qualification changed')
    old=json.loads(old_path.read_text())
    if (prefreeze.get('source_references')!=old.get('source_references')
            or prefreeze.get('covered_task_ids')!=old.get('covered_task_ids')
            or digest(prefreeze['source_references'])!=reuse.get('source_references_sha256')):
        raise ValueError('Reused reference checks or coverage changed')
    current=implementation_hashes(root)
    _, blockers=_integrated_qualification(prefreeze_path,audit_sha256=manifest['source_audit_sha256'],
        tasks=manifest['tasks']+[manifest['smoke_task']],implementation=current,root=root)
    if blockers:raise ValueError('; '.join(blockers))
    _fresh_checks(prefreeze['fresh_checks'],current,old['docker'])
    if digest(prefreeze['fresh_checks'])!=reuse.get('fresh_checks_sha256'):
        raise ValueError('Fresh qualification digest changed')
    result=copy.deepcopy(prefreeze)
    result.update(at=utcnow(),manifest_sha256=manifest['manifest_sha256'],
        integrated_qualification_sha256=descriptor['sha256'],prefreeze_qualification=descriptor,
        scope='manifest_bound_exploratory_subset_with_unchanged_reference_evidence',
        exploratory_subset_identity=subset_identity_report(previous,manifest))
    return result
