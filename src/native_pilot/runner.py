"""Sequential interleaved scheduler, durable checkpoints, at-most-one transport retry."""
import fcntl
import json
from contextlib import contextmanager
from pathlib import Path
from .budget import Ledger, BudgetRefused, reservation
from .util import utcnow


@contextmanager
def campaign_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another campaign/smoke process owns the budget ledger') from exc
        yield


def smoke_schedule(task):
    tid = task['task_id']
    return [{'call_id':f'smoke/{tid}/{condition}/{sample}','task_id':tid,
             'condition':condition,'sample':sample}
            for condition,sample in [('initial',0),('updated_retained',1),('updated_dropped',1)]]


def outcomes_from_ledger(ledger, manifest, schedule=None):
    schedule = manifest['schedule'] if schedule is None else schedule
    output = []
    prefix = manifest['manifest_sha256'] + '/'
    for call in schedule:
        row = ledger.latest(prefix+call['call_id'])
        result = dict(call, status='unassigned', protocol_valid=False)
        if row:
            result['attempt'] = row['attempt']
            result['started_at'] = row['started']
            result['finished_at'] = row['finished']
            if row['outcome']:
                result.update(json.loads(row['outcome']))
            else:
                result.update(status='provider_failure', error_kind=row['error_kind'],
                              uncertain_charge=row['charged'] is None)
        output.append(result)
    return output


def execute(manifest, ledger, provider, *, schedule=None, tasks=None, grader=None):
    """Internal execution core, injection supports entirely offline mock qualification.

    Public CLI must pass paid_preflight before constructing a real provider.
    No initial answer correctness is used to choose or suppress assignments.
    """
    from .provider import build_request, validate_response, extract_visible_answer, ProviderFailure
    if grader is None:
        from .grading import grade_response
        grader = grade_response
    schedule = manifest['schedule'] if schedule is None else schedule
    tasks = manifest['tasks'] if tasks is None else tasks
    by_id = {task['task_id']:task for task in tasks}
    prefix = manifest['manifest_sha256']+'/'
    initial_ids = {c['task_id']:prefix+c['call_id'] for c in schedule if c['condition']=='initial'}
    ledger.recover_interrupted()
    stop_reason = None
    for call in schedule:
        call_id = prefix+call['call_id']
        previous = ledger.latest(call_id)
        if previous and previous['state'] in ('completed','provider_failure'):
            if previous['outcome'] and json.loads(previous['outcome']).get('status') == 'protocol_failure':
                stop_reason = 'protocol_failure'
                break
            continue
        if previous and previous['attempt'] >= 2:
            continue
        branch = call['condition']
        checkpoint = None
        if branch not in ('initial','fresh'):
            initial = ledger.latest(initial_ids[call['task_id']])
            if not initial or not initial.get('response'):
                continue
            checkpoint = {'request':json.loads(initial['request']), 'response':json.loads(initial['response'])}
            validity = validate_response(checkpoint['response'],
                         checkpoint['request']['reasoning']['context'],require_checkpoint=True)
            if not validity['valid']:
                stop_reason = 'initial_checkpoint_unusable'
                break
        request = build_request(by_id[call['task_id']],branch,checkpoint,manifest['settings'])
        while True:
            try:
                bounds = reservation(request, checkpoint)
                attempt = ledger.reserve(call_id, manifest['manifest_sha256'], request,
                                         bounds['micro_usd'], 'smoke' if call['call_id'].startswith('smoke/') else 'pilot')
            except BudgetRefused as exc:
                stop_reason = str(exc)
                break
            ledger.dispatched(call_id,attempt)
            try:
                response = provider.create(request)
            except ProviderFailure as exc:
                if exc.retryable:
                    ledger.uncertain(call_id,attempt,exc.kind)
                    if attempt < 2:
                        continue
                else:
                    failure = dict(call, status='protocol_failure' if exc.kind=='protocol_failure' else 'provider_failure',
                                   protocol_valid=False,error_kind=exc.kind)
                    ledger.provider_failure(call_id,attempt,exc.kind,failure)
                    if exc.kind=='protocol_failure':
                        stop_reason='protocol_failure'
                break
            except Exception:
                # Never stringify arbitrary exceptions (SDK errors can contain
                # request data). Unknown dispatch outcome stays charged at max.
                ledger.uncertain(call_id,attempt,'unclassified_transport_failure')
                stop_reason = 'Unclassified provider failure; inspect redacted attempt metadata'
                break
            validity = validate_response(response, request['reasoning']['context'],
                                         require_checkpoint=(branch=='initial' and response.get('status')=='completed'))
            outcome = dict(call, protocol_valid=validity['valid'],
                           returned_model=response.get('model'), response_status=response.get('status'),
                           stop_reason=response.get('incomplete_details'), usage=response.get('usage'),
                           input_tokens_bound=bounds['input_tokens_bound'], timestamp=utcnow())
            if response.get('status') in ('failed','cancelled'):
                outcome.update(status='provider_failure',error_kind='terminal_'+response['status'],
                               protocol_errors=validity['errors'])
            elif not validity['valid']:
                outcome.update(status='protocol_failure',protocol_errors=validity['errors'])
            else:
                variant = 'original' if branch in ('initial','unchanged_retained','unchanged_dropped') else 'updated'
                try:
                    grade = grader(by_id[call['task_id']],variant,extract_visible_answer(response),
                                   response_status=response.get('status','invalid'))
                    outcome.update(status=grade['status'],grade=grade)
                except Exception:
                    outcome.update(status='protocol_failure', protocol_valid=False,
                                   protocol_errors=['Grading infrastructure failed; outcome unavailable'])
            ledger.finish(call_id,attempt,response,outcome)
            if not outcome['protocol_valid']:
                stop_reason = outcome['status']
            break
        if stop_reason:
            break
    outcomes = outcomes_from_ledger(ledger,manifest,schedule)
    if stop_reason and ('budget' in stop_reason.lower() or 'cap' in stop_reason.lower()):
        for result in outcomes:
            if result['status']=='unassigned':
                result['status']='budget_stopped'
    return {'outcomes':outcomes,'stop_reason':stop_reason,
            'accounted_usd':ledger.total()/1_000_000,'attempts':len(ledger.rows(manifest['manifest_sha256']))}
