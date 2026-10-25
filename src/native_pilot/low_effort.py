"""Prepare locally and run the single bounded low-effort follow-up.

Preparation binds existing private checkpoints without generating or copying
them. Historical manifests, attempts, charges and reservations remain intact.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from .exploratory import TASK_IDS
from .util import atomic_json, digest, file_digest, utcnow

ROOT = Path(__file__).resolve().parents[2]
PRIOR_MANIFEST_PATH = 'manifests/pilot-v6.json'
PRIOR_MANIFEST_SHA256 = '021676718d1d29683b2e1e69e3e5c5eefa8a41f9ed9c3a3d952404c8f14ffb7f'
MANIFEST_PATH = 'manifests/pilot-v7.json'
QUALIFICATION_PATH = 'runs/qualification-low-v7.json'
RECORD_PATH = 'provenance/low_effort_authorization_v7.json'
AUTHORIZATION = {
    'allowed': True,
    'authorization_id': 'user-2026-10-24-low-effort-followup-v7',
    'manifest_version': 'pilot-v7',
    'task_ids': list(TASK_IDS),
    'initial_generation_allowed': False,
    'max_logical_calls': 24,
    'max_transport_retries_per_call': 1,
    'additional_budget_usd': 2,
    'shared_budget_usd': 40,
    'soft_dispatch_deadline_seconds': 1800,
}


def make_schedule(tasks):
    if [t['task_id'] for t in tasks] != list(TASK_IDS):
        raise ValueError('Low-effort tasks or their fixed order changed')
    return [{'call_id': f'{tid}/{branch}/{sample}', 'task_id': tid,
             'condition': branch, 'sample': sample}
            for tid in TASK_IDS for sample in (1, 2)
            for branch in ('updated_retained', 'updated_dropped', 'fresh')]


def _prior(root):
    from .manifest import load_manifest
    value = load_manifest(root / PRIOR_MANIFEST_PATH, verify_files=False, root=root)
    if value['manifest_sha256'] != PRIOR_MANIFEST_SHA256:
        raise ValueError('Historical v6 manifest changed')
    return value


def _policy(root):
    policy = json.loads((root / 'provenance/execution_policy.json').read_text())
    record = json.loads((root / RECORD_PATH).read_text())
    if (policy.get('low_effort_followup') != AUTHORIZATION
            or policy.get('paid_execution_allowed') is not False
            or policy.get('protocol_smoke') is not None
            or record.get('authorization') != AUTHORIZATION
            or record.get('prior_manifest_sha256') != PRIOR_MANIFEST_SHA256):
        raise ValueError('Only the bounded low-effort follow-up is authorized')
    return policy


def bind_initials(ledger, tasks):
    """Read all four completed high-effort originals; correctness never selects."""
    from .provider import build_request, validate_response
    descriptors = {}
    for task in tasks:
        tid = task['task_id']
        call_id = PRIOR_MANIFEST_SHA256 + '/' + tid + '/initial/0'
        row = ledger.latest(call_id)
        if (not row or row['manifest_hash'] != PRIOR_MANIFEST_SHA256
                or row['state'] != 'completed' or not row['response'] or not row['outcome']):
            raise ValueError('Existing completed initial checkpoint required: ' + tid)
        checkpoint = {'request': json.loads(row['request']), 'response': json.loads(row['response'])}
        outcome = json.loads(row['outcome'])
        valid = validate_response(checkpoint['response'], 'current_turn', require_checkpoint=True)
        if (checkpoint['request'] != build_request(task, 'initial') or not valid['valid']
                or checkpoint['response'].get('status') != 'completed'
                or outcome.get('protocol_valid') is not True
                or outcome.get('grade', {}).get('status') not in ('correct', 'incorrect')):
            raise ValueError('Historical initial is not a usable high-effort checkpoint: ' + tid)
        descriptors[tid] = {
            'source_call_id': call_id, 'source_attempt': row['attempt'],
            'source_manifest_sha256': PRIOR_MANIFEST_SHA256,
            'row_sha256': digest(row), 'checkpoint_sha256': digest(checkpoint),
            'request_sha256': digest(checkpoint['request']),
            'response_sha256': digest(checkpoint['response']), 'outcome': outcome,
        }
    return descriptors


def verify_initials(ledger, manifest):
    expected = manifest['inherited_initials']
    actual = bind_initials(ledger, manifest['tasks'])
    if expected != actual:
        raise ValueError('An inherited checkpoint, original grade or ledger row changed')
    historical = [row for row in ledger.rows()
                  if row['manifest_hash'] != manifest['manifest_sha256']]
    if digest(historical) != manifest['historical_ledger_rows_sha256']:
        raise ValueError('Historical ledger attempts changed after preparation')
    result = {}
    for tid, descriptor in actual.items():
        row = ledger.latest(descriptor['source_call_id'])
        result[tid] = {'request': json.loads(row['request']), 'response': json.loads(row['response'])}
    return result


def load_frozen(path=None, *, root=None):
    from .manifest import implementation_hashes
    from .low_qualification import validate_evidence
    root = Path(root or ROOT).resolve()
    path = Path(path) if path is not None else root / MANIFEST_PATH
    m = json.loads(path.read_text())
    content = dict(m)
    claimed = content.pop('manifest_sha256', None)
    if claimed != digest(content):
        raise ValueError('Low-effort manifest hash mismatch')
    previous = _prior(root)
    _policy(root)
    settings = dict(previous['settings'], reasoning_effort='low')
    if (m.get('version') != 'pilot-v7' or m.get('status') != 'frozen' or m.get('blockers') != []
            or m.get('execution_scope') != 'low_effort_followup'
            or m.get('low_effort_authorization') != AUTHORIZATION
            or m.get('paid_execution_allowed') is not False or m.get('hard_budget_usd') != 40
            or m.get('tasks') != previous['tasks'] or m.get('settings') != settings
            or m.get('schedule') != make_schedule(previous['tasks'])
            or m.get('prior_manifest_sha256') != PRIOR_MANIFEST_SHA256
            or m.get('pricing') != previous['pricing']):
        raise ValueError('Frozen low-effort design changed')
    for name, sha in m['provenance_hashes'].items():
        if file_digest(root / name) != sha:
            raise ValueError('Bound provenance changed: ' + name)
    required = {'provenance/execution_policy.json', RECORD_PATH}
    if not required.issubset(m['provenance_hashes']):
        raise ValueError('Missing low-effort authorization binding')
    current = implementation_hashes(root)
    if current != m['implementation_hashes']:
        raise ValueError('Implementation changed after local preparation')
    q = m['qualification']
    if q['path'] != QUALIFICATION_PATH or file_digest(root / q['path']) != q['sha256']:
        raise ValueError('Local qualification evidence changed')
    validate_evidence(json.loads((root / q['path']).read_text()), previous, current, root)
    return m


def prepare(cache, *, root=None):
    """No credentials, network inference, reservation or timer start."""
    from .budget import Ledger
    from .low_qualification import qualify
    from .manifest import implementation_hashes
    from .runner import campaign_lock
    root = Path(root or ROOT).resolve()
    ledger_path = root / 'runs/budget.sqlite'
    if not ledger_path.is_file():
        raise ValueError('The existing shared v6 ledger is required; run in the original checkout')
    with campaign_lock(root / 'runs/campaign.lock'):
        ledger = Ledger(ledger_path)
        try:
            if (root / MANIFEST_PATH).exists():
                m = load_frozen(root=root)
                verify_initials(ledger, m)
                return m
            previous = _prior(root)
            _policy(root)
            descriptors = bind_initials(ledger, previous['tasks'])
            for call in previous['schedule']:
                row = ledger.latest(PRIOR_MANIFEST_SHA256 + '/' + call['call_id'])
                outcome = json.loads(row['outcome']) if row and row['outcome'] else {}
                if not row or row['state'] != 'completed' or outcome.get('protocol_valid') is not True:
                    raise ValueError('The completed 28-response v6 run is required before this follow-up')
            rows_before = ledger.rows()
            q = qualify(previous, Path(cache).resolve(), root)
            if ledger.rows() != rows_before:
                raise ValueError('Historical ledger changed during offline preparation')
            atomic_json(root / QUALIFICATION_PATH, q)
            m = {
                'schema_version': 1, 'version': 'pilot-v7', 'status': 'frozen', 'blockers': [],
                'created_at': utcnow(), 'execution_scope': 'low_effort_followup',
                'low_effort_authorization': copy.deepcopy(AUTHORIZATION),
                'paid_execution_allowed': False, 'hard_budget_usd': 40,
                'prior_manifest_sha256': PRIOR_MANIFEST_SHA256,
                'settings': dict(previous['settings'], reasoning_effort='low'),
                'pricing': previous['pricing'], 'tasks': previous['tasks'],
                'schedule': make_schedule(previous['tasks']), 'inherited_initials': descriptors,
                'historical_ledger_rows_sha256': digest(rows_before),
                'implementation_hashes': implementation_hashes(root),
                'qualification': {'path': QUALIFICATION_PATH, 'sha256': file_digest(root / QUALIFICATION_PATH)},
                'provenance_hashes': {str(p.relative_to(root)): file_digest(p)
                                      for p in sorted((root / 'provenance').glob('*.json'))},
                'interpretation': 'High-effort initial checkpoints followed by low-effort revisions; descriptive only',
            }
            m['manifest_sha256'] = digest(m)
            atomic_json(root / MANIFEST_PATH, m, exclusive=True)
            verified = load_frozen(root=root)
            verify_initials(ledger, verified)
            return verified
        finally:
            ledger.close()


def require_execution(**kwargs):
    from .low_authorization import require_execution as authorize
    return authorize(**kwargs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'report'))
    parser.add_argument('--asset-cache', default='data/cache')
    parser.add_argument('--allow-paid', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            m = prepare(args.asset_cache)
            print(json.dumps({'status': 'prepared', 'manifest': MANIFEST_PATH,
                              'manifest_sha256': m['manifest_sha256'], 'new_model_calls': 0}))
            return 0
        from .assets import hydrate_tasks
        from .budget import Ledger
        from .low_runner import execute, report
        from .provider import OpenAIProvider
        from .runner import campaign_lock
        m = load_frozen()
        path = ROOT / 'runs/budget.sqlite'
        if not path.is_file():
            raise ValueError('The original shared ledger is missing')
        with campaign_lock(ROOT / 'runs/campaign.lock') as guard:
            ledger = Ledger(path)
            try:
                if args.command == 'report':
                    value = report(m, ledger)
                    print(json.dumps(value, indent=2))
                    return 0
                if not args.allow_paid:
                    raise ValueError('Run requires --allow-paid; no request dispatched')
                tasks = hydrate_tasks(m['tasks'], Path(args.asset_cache).resolve())
                provider = OpenAIProvider(allow_paid=True, execution_scope='low_effort_followup',
                                         manifest=m, ledger=ledger, campaign_guard=guard)
                result = execute(m, ledger, provider, tasks=tasks, campaign_guard=guard)
                destination = ROOT / 'runs' / ('low-' + m['manifest_sha256'] + '.json')
                atomic_json(destination, result)
                r = result['feasibility_report']
                print(json.dumps({'kind': 'low_effort_followup', 'report': str(destination.relative_to(ROOT)),
                                  'completed_responses': r['completed_protocol_valid_responses'],
                                  'planned_responses': 24, 'stop_reason': result['stop_reason'],
                                  'accounting': r['accounting']}))
                return 0 if r['all_planned_calls_completed'] else 1
            finally:
                ledger.close()
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
