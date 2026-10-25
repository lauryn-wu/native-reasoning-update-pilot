"""Content-addressed, immutable manifests; unavailable source evidence blocks payment."""
import hashlib
import json
from pathlib import Path
from .design import SEED, make_schedule, validate_design, original_identity
from .util import atomic_json, digest, file_digest, utcnow

ROOT = Path(__file__).resolve().parents[2]


def implementation_hashes(root=ROOT):
    paths = list((root/'src').rglob('*.py')) + list((root/'sandbox').rglob('*.py')) + list((root/'tests').rglob('*.py'))
    paths += [root/'pyproject.toml'] + list((root/'docs').glob('*.md'))
    paths += [p for p in (root/'references').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    return {str(p.relative_to(root)): file_digest(p) for p in sorted(paths) if p.is_file()}


def _integrated_qualification(path, *, audit_sha256, tasks, implementation, root):
    """Validate completed evidence for this exact source/implementation snapshot."""
    if path is None:
        return None, ['Completed integrated qualification is required before source-qualified freeze']
    try:
        path = Path(path).resolve()
        raw = path.read_bytes()
        qualification = json.loads(raw)
        if not isinstance(qualification, dict):
            raise ValueError('Expected a qualification object')
    except (OSError, ValueError, TypeError) as exc:
        return None, [f'Integrated qualification is missing or invalid: {exc}']
    blockers = []
    for check in ('offline_passed', 'docker_passed', 'source_reference_passed'):
        if qualification.get(check) is not True:
            blockers.append('Integrated qualification requires '+check)
    if qualification.get('audit_sha256') != audit_sha256:
        blockers.append('Integrated qualification belongs to a different source audit')
    if qualification.get('implementation_hashes') != implementation:
        blockers.append('Integrated qualification implementation is stale or missing')
    covered = qualification.get('covered_task_ids')
    if not isinstance(covered, list) or not all(isinstance(tid, str) for tid in covered):
        covered = []
    required_ids = {task['task_id'] for task in tasks}
    missing = required_ids - set(covered)
    if missing:
        blockers.append('Integrated qualification omits required tasks: '+', '.join(sorted(missing)))
    references = qualification.get('source_references')
    if not isinstance(references, dict) or references.get('passed') is not True:
        blockers.append('Integrated qualification source-reference report is not passing')
    checks = references.get('checks', {}) if isinstance(references, dict) else {}
    if not isinstance(checks, dict):
        checks = {}
    required_checks = {'original_reference', 'updated_reference', 'original_equivalent',
                       'updated_equivalent', 'original_wrong_rejected',
                       'updated_wrong_rejected', 'stale_rejected'}
    for task in tasks:
        expected = required_checks | {'changed_answer' if task['domain']=='math' else 'changed_behavior'}
        task_checks = checks.get(task['task_id'])
        if (not isinstance(task_checks, dict) or not expected.issubset(task_checks)
                or not all(value is True for value in task_checks.values())):
            blockers.append('Integrated qualification lacks completed passing reference checks: '+task['task_id'])
    if blockers:
        return None, blockers
    root = root.resolve()
    descriptor = {'path': str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
                  'sha256': hashlib.sha256(raw).hexdigest(),
                  'audit_sha256': audit_sha256,
                  'covered_task_ids': sorted(set(covered)),
                  'implementation_hashes_sha256': digest(implementation)}
    return descriptor, []


def authentication_recovery_descriptor(root=ROOT):
    """Validate the explicit, immutable lineage without writing the live ledger."""
    from .provider import AUTHENTICATION_RECOVERY, SMOKE_AUTHORIZATION
    root = Path(root)
    path = root/'provenance/authentication_recovery_v4.json'
    record = json.loads(path.read_text())
    if record.get('recovery') != AUTHENTICATION_RECOVERY or record.get('authorization') != SMOKE_AUTHORIZATION:
        raise ValueError('Authentication recovery record does not match explicit authorization')
    previous_descriptor = record.get('prior_manifest', {})
    if previous_descriptor.get('path') != 'manifests/pilot-v3.json':
        raise ValueError('Authentication recovery requires the immutable v3 manifest')
    previous_path = root/previous_descriptor['path']
    if file_digest(previous_path) != previous_descriptor.get('sha256'):
        raise ValueError('Historical v3 manifest changed')
    previous = load_manifest(previous_path, verify_files=False, root=root)
    if (previous['manifest_sha256'] != AUTHENTICATION_RECOVERY['failed_manifest_sha256']
            or previous_descriptor.get('manifest_sha256') != previous['manifest_sha256']
            or previous['protocol_smoke_authorization']['authorization_id'] != AUTHENTICATION_RECOVERY['failed_authorization_id']):
        raise ValueError('Authentication recovery previous authorization mismatch')
    for field, frozen_name in (
            ('prior_policy', 'provenance/execution_policy.json'),
            ('prior_authorization_record', 'provenance/smoke_authorization_v3.json')):
        item = record.get(field, {})
        target = (root/item.get('path', '')).resolve()
        if (not target.is_relative_to(root.resolve()) or not target.is_file()
                or file_digest(target) != item.get('sha256')
                or item.get('sha256') != previous['provenance_hashes'][frozen_name]):
            raise ValueError('Historical authentication evidence changed: '+field)
    return {'path':str(path.relative_to(root)), 'sha256':file_digest(path)}


def freeze(destination, version, root=ROOT, *, audit_path=None, qualification_path=None):
    root = Path(root)
    audit_path = Path(audit_path or root/'provenance/audit.json')
    audit = json.loads(audit_path.read_text())
    audit_sha256 = file_digest(audit_path)
    implementation = implementation_hashes(root)
    from .data import select_tasks, SourceBlocked
    blockers = list(audit.get('blockers', []))
    tasks, smoke_task = [], None
    try:
        selection = select_tasks(audit, SEED)
        tasks, smoke_task = selection['tasks'], selection['smoke_task']
        # A stale qualified audit must not bless subsequently changed reviews.
        from .qualification import assert_ordered_prefix
        review_hashes = audit.get('review_hashes',{})
        required_reviews = {'provenance/math_review.json','provenance/coding_review.json'}
        if not required_reviews.issubset(review_hashes):
            raise SourceBlocked('Qualified audit lacks current review bindings')
        current_reviews = {}
        for name, expected in review_hashes.items():
            path = (root/name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file() or file_digest(path) != expected:
                raise SourceBlocked('Qualified audit review changed: '+name)
            document=json.loads(path.read_text())
            for record in document.get('candidates',document.get('reviewed_candidates',[])):
                current_reviews[record['task_id']]=record
        inventory=json.loads((root/'provenance/review_inventory.json').read_text())['candidates']
        assert_ordered_prefix(inventory,current_reviews,{t['task_id'] for t in tasks},smoke_task['task_id'])
    except SourceBlocked as exc:
        blockers.append(str(exc))
    if audit.get('source_lock_sha256') != file_digest(root/'provenance/source_lock.json'):
        blockers.append('Source audit does not match the pinned source lock')
    for task in tasks + ([smoke_task] if smoke_task else []):
        for field in ('original_prompt','updated_prompt','correction_prompt','qualification_evidence_sha256'):
            if not isinstance(task.get(field),str) or not task[field].strip():
                blockers.append(f"Task {task['task_id']} lacks audited {field}")
        for variant in ('original','updated'):
            spec = task.get(variant,{})
            required = 'answer' if task.get('domain')=='math' else 'tests'
            if required not in spec and not (required == 'tests' and 'test_asset' in spec):
                blockers.append(f"Task {task['task_id']} lacks {variant} {required}")
    schedule = make_schedule(tasks)
    try:
        validate_design(tasks, schedule)
    except ValueError as exc:
        blockers.append(str(exc))
    if not audit.get('pair_semantics_verified', False):
        blockers.append('No completed audit of unambiguous behavior-changing pairs and both graders')
    integrated_qualification = None
    if audit.get('status') == 'qualified':
        integrated_qualification, qualification_blockers = _integrated_qualification(
            qualification_path, audit_sha256=audit_sha256,
            tasks=tasks + ([smoke_task] if smoke_task else []),
            implementation=implementation, root=root)
        blockers.extend(qualification_blockers)
    # Do not manufacture a 24-case selection from unqualified review candidates.
    if blockers:
        tasks, schedule, smoke_task = [], [], None
    provenance = {str(p.relative_to(root)): file_digest(p)
                  for p in sorted((root/'provenance').glob('*.json'))}
    policy_path = root/'provenance/execution_policy.json'
    policy = json.loads(policy_path.read_text()) if policy_path.is_file() else {}
    from .provider import SMOKE_AUTHORIZATION
    smoke_authorization = (policy.get('protocol_smoke')
        if policy.get('paid_execution_allowed') is False
        and policy.get('protocol_smoke') == SMOKE_AUTHORIZATION
        and version == SMOKE_AUTHORIZATION['manifest_version'] and not blockers else None)
    recovery = authentication_recovery_descriptor(root) if smoke_authorization else None
    manifest = {
        'schema_version': 2, 'version': version, 'created_at': utcnow(),
        'source_audit_sha256': audit_sha256,
        'integrated_qualification': integrated_qualification,
        'source_qualified': not bool(blockers),
        'paid_execution_allowed': False,
        'protocol_smoke_authorization': smoke_authorization,
        'authentication_recovery': recovery,
        'execution_blockers': ['Explicit user hold: the 200-response pilot remains blocked'] if smoke_authorization else ['Explicit user hold: paid execution remains blocked, including smoke and retries'],
        'status': 'blocked' if blockers else 'frozen', 'blockers': sorted(set(blockers)),
        'research_question': 'Does retained native reasoning impair adaptation beyond prior visible answer?',
        'adaptation': 'New user-turn correction after completed response; not mid-reasoning interruption replication',
        'seed': SEED, 'selection_rule': audit.get('selection_rule'),
        'tasks': tasks, 'schedule': schedule, 'smoke_task': smoke_task,
        'planned_counts': {'problems':24,'math':12,'coding':12,'initial':24,
                           'updated_and_fresh':144,'unchanged':32,'responses':200,'smoke':3},
        'settings': {'model':'gpt-6.1-sol','reasoning_effort':'high','max_output_tokens':32768},
        'pricing': json.loads((root/'provenance/pricing.json').read_text()),
        'hard_budget_usd':40,
        'analysis': {'eligible':'single initial answer correct on original grader',
                     'minimum_eligible':18,'fresh_accuracy_minimum':0.75,'gap_minimum':0.10,
                     'one_sided_p_maximum':0.10,'unit':'original problem',
                     'permutation':'exact sign-flip of paired task means, repeats kept together',
                     'bootstrap_seed':SEED,'bootstrap_repeats':10000,
                     'required':'valid manipulation and complete required outcomes'},
        'provenance_hashes':provenance,'implementation_hashes':implementation,
        'tasks_sha256':digest(tasks),'schedule_sha256':digest(schedule),
    }
    from .budget import RATES
    if manifest['pricing']['rates_per_million'] != RATES:
        raise ValueError('Frozen pricing differs from budget implementation')
    if recovery:
        from .qualification_reuse import design_identity_report
        previous = load_manifest(root/'manifests/pilot-v3.json', verify_files=False, root=root)
        design_identity_report(previous, manifest)
    manifest['manifest_sha256'] = digest(manifest)
    atomic_json(destination, manifest, exclusive=True)
    return manifest


def load_manifest(path, *, verify_files=True, root=ROOT):
    manifest = json.loads(Path(path).read_text())
    claimed = manifest.pop('manifest_sha256')
    if digest(manifest) != claimed:
        raise ValueError('Manifest content hash mismatch')
    manifest['manifest_sha256'] = claimed
    if verify_files:
        for mapping in ('provenance_hashes','implementation_hashes'):
            for name, expected in manifest[mapping].items():
                path = root/name
                if not path.is_file() or file_digest(path) != expected:
                    raise ValueError(f'Frozen file changed: {name}; create a new manifest version')
        if implementation_hashes(root) != manifest['implementation_hashes']:
            raise ValueError('Implementation file set changed; create a new manifest version')
        qualification = manifest.get('integrated_qualification')
        if qualification:
            path = root/qualification['path']
            if not path.is_file() or file_digest(path) != qualification.get('sha256'):
                raise ValueError('Frozen integrated qualification changed; create a new manifest version')
    if digest(manifest['tasks']) != manifest['tasks_sha256'] or digest(manifest['schedule']) != manifest['schedule_sha256']:
        raise ValueError('Frozen task/schedule hash mismatch')
    if manifest['status'] == 'frozen':
        validate_design(manifest['tasks'],manifest['schedule'])
    return manifest


def paid_preflight(manifest, qualification, *, smoke=False):
    # A command flag cannot widen the explicit authorization. This version of the
    # executable exposes only the three-call smoke; future pilot work needs a new
    # authorization and immutable manifest.
    from .provider import SMOKE_AUTHORIZATION
    policy_path = ROOT/'provenance/execution_policy.json'
    policy = json.loads(policy_path.read_text()) if policy_path.is_file() else {}
    if (not smoke or policy.get('paid_execution_allowed') is not False
            or policy.get('protocol_smoke') != SMOKE_AUTHORIZATION):
        raise ValueError('Paid execution blocked by explicit user policy; only the authorized v4 recovery smoke may run')
    if (manifest.get('protocol_smoke_authorization') != SMOKE_AUTHORIZATION
            or manifest.get('version') != SMOKE_AUTHORIZATION['manifest_version']
            or manifest.get('paid_execution_allowed') is not False):
        raise ValueError('Frozen manifest does not authorize this scoped smoke')
    recovery = authentication_recovery_descriptor(ROOT)
    if (manifest.get('authentication_recovery') != recovery
            or manifest.get('provenance_hashes', {}).get(recovery['path']) != recovery['sha256']):
        raise ValueError('Frozen manifest lacks the exact authentication recovery binding')
    if manifest['status'] != 'frozen' or manifest['blockers']:
        raise ValueError('Paid execution blocked: ' + '; '.join(manifest['blockers']))
    validate_design(manifest['tasks'], manifest['schedule'])
    if qualification.get('manifest_sha256') != manifest['manifest_sha256']:
        raise ValueError('Qualification belongs to a different frozen manifest')
    for check in ('offline_passed','docker_passed','source_reference_passed'):
        if qualification.get(check) is not True:
            raise ValueError(f'Paid execution blocked: {check} required')
    if qualification.get('implementation_hashes') != manifest['implementation_hashes']:
        raise ValueError('Manifest-bound qualification implementation mismatch')
    integrated = manifest.get('integrated_qualification') or {}
    if qualification.get('integrated_qualification_sha256') != integrated.get('sha256'):
        raise ValueError('Manifest-bound qualification lacks frozen evidence binding')
    evidence_path = ROOT/integrated.get('path', '')
    if not evidence_path.is_file() or file_digest(evidence_path) != integrated.get('sha256'):
        raise ValueError('Frozen integrated qualification is missing or changed')
    evidence = json.loads(evidence_path.read_text())
    for field in ('source_references', 'covered_task_ids'):
        if qualification.get(field) != evidence.get(field):
            raise ValueError('Manifest-bound qualification changed '+field)
    if not manifest.get('smoke_task') or manifest['smoke_task']['task_id'] != SMOKE_AUTHORIZATION['task_id']:
        raise ValueError('Separate authorized smoke task required')
    smoke_original = original_identity(manifest['smoke_task'])
    if smoke_original in {original_identity(t) for t in manifest['tasks']}:
        raise ValueError('Smoke problem overlaps pilot')
