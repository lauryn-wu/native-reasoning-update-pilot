"""Content-addressed, immutable manifests; unavailable source evidence blocks payment."""
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


def freeze(destination, version, root=ROOT, *, audit_path=None):
    audit = json.loads(Path(audit_path or root/'provenance/audit.json').read_text())
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
    # Do not manufacture a 24-case selection from unqualified review candidates.
    if blockers:
        tasks, schedule, smoke_task = [], [], None
    provenance = {str(p.relative_to(root)): file_digest(p)
                  for p in sorted((root/'provenance').glob('*.json'))}
    policy_path = root/'provenance/execution_policy.json'
    paid_allowed = policy_path.is_file() and json.loads(policy_path.read_text()).get('paid_execution_allowed') is True
    manifest = {
        'schema_version': 2, 'version': version, 'created_at': utcnow(),
        'source_audit_sha256': file_digest(Path(audit_path or root/'provenance/audit.json')),
        'source_qualified': not bool(blockers),
        'paid_execution_allowed': bool(paid_allowed and not blockers),
        'execution_blockers': [] if paid_allowed else ['Explicit user hold: paid execution remains blocked, including smoke and retries'],
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
        'provenance_hashes':provenance,'implementation_hashes':implementation_hashes(root),
        'tasks_sha256':digest(tasks),'schedule_sha256':digest(schedule),
    }
    from .budget import RATES
    if manifest['pricing']['rates_per_million'] != RATES:
        raise ValueError('Frozen pricing differs from budget implementation')
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
    if digest(manifest['tasks']) != manifest['tasks_sha256'] or digest(manifest['schedule']) != manifest['schedule_sha256']:
        raise ValueError('Frozen task/schedule hash mismatch')
    if manifest['status'] == 'frozen':
        validate_design(manifest['tasks'],manifest['schedule'])
    return manifest


def paid_preflight(manifest, qualification, *, smoke=False):
    policy_path = ROOT/'provenance/execution_policy.json'
    if not policy_path.is_file() or json.loads(policy_path.read_text()).get('paid_execution_allowed') is not True:
        raise ValueError('Paid execution blocked by explicit user policy; --allow-paid cannot override it')
    if manifest.get('paid_execution_allowed') is not True:
        raise ValueError('Frozen manifest does not authorize paid execution')
    if manifest['status'] != 'frozen' or manifest['blockers']:
        raise ValueError('Paid execution blocked: ' + '; '.join(manifest['blockers']))
    validate_design(manifest['tasks'], manifest['schedule'])
    if qualification.get('manifest_sha256') != manifest['manifest_sha256']:
        raise ValueError('Qualification belongs to a different frozen manifest')
    for check in ('offline_passed','docker_passed','source_reference_passed'):
        if qualification.get(check) is not True:
            raise ValueError(f'Paid execution blocked: {check} required')
    if not manifest.get('smoke_task'):
        raise ValueError('Separate qualified smoke task required')
    smoke_original = original_identity(manifest['smoke_task'])
    if smoke_original in {original_identity(t) for t in manifest['tasks']}:
        raise ValueError('Smoke problem overlaps pilot')
