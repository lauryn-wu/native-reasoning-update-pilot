"""Sequential interleaved scheduler, durable checkpoints, at-most-one transport retry."""
import fcntl
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from .budget import Ledger, BudgetRefused, reservation
from .util import utcnow


class _CampaignGuard:
    def __init__(self, path, handle):
        self.path, self.handle, self.active = path.resolve(), handle, True
        self.execution_mutex = threading.Lock()


def require_campaign_lock(guard, ledger):
    expected = ledger.path.resolve().parent / 'campaign.lock'
    if (not isinstance(guard, _CampaignGuard) or not guard.active or
            guard.handle.closed or guard.path != expected):
        raise RuntimeError('An active campaign lock for the shared budget ledger is required')


@contextmanager
def campaign_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another campaign/smoke process owns the budget ledger') from exc
        guard = _CampaignGuard(path, handle)
        try:
            yield guard
        finally:
            guard.active = False


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


def smoke_protocol_report(ledger, manifest):
    """Public diagnostics only: no answers, prompts, or opaque reasoning values."""
    from .budget import CAP_MICRO_USD
    from .provider import validate_response
    from .util import digest
    import copy
    schedule = smoke_schedule(manifest['smoke_task'])
    outcomes = outcomes_from_ledger(ledger, manifest, schedule)
    prefix = manifest['manifest_sha256'] + '/'
    rows = [ledger.latest(prefix + call['call_id']) for call in schedule]
    initial = rows[0]
    checkpoint = None
    if initial and initial['request'] and initial['response']:
        checkpoint = {'request': json.loads(initial['request']),
                      'response': json.loads(initial['response'])}
    initial_valid = bool(checkpoint and validate_response(
        checkpoint['response'], 'current_turn', require_checkpoint=True)['valid'])
    full_replay = []
    paired = []
    for row in rows[1:]:
        request = json.loads(row['request']) if row and row['request'] else None
        paired.append(request)
        full_replay.append(bool(initial_valid and request and request['input'][:-1] ==
                               checkpoint['request']['input'] + checkpoint['response']['output']))
    context_only = False
    if all(paired):
        retained, dropped = copy.deepcopy(paired)
        contexts = [retained['reasoning'].pop('context'), dropped['reasoning'].pop('context')]
        context_only = contexts == ['all_turns', 'current_turn'] and retained == dropped
    all_rows = ledger.rows()
    smoke_rows = [row for row in all_rows if row['call_id'] in {prefix+c['call_id'] for c in schedule}]
    known = sum(row['charged'] for row in all_rows if row['charged'] is not None)
    outstanding = sum(row['reserved'] for row in all_rows if row['charged'] is None)
    token_totals = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0,
                    'reasoning_tokens': 0, 'cached_tokens': 0, 'cache_write_tokens': 0}
    usage_records = 0
    for row in smoke_rows:
        value = json.loads(row['response']) if row['response'] else {}
        usage = value.get('usage') or {}
        if not isinstance(usage, dict):
            continue
        values = {key:usage.get(key) for key in ('input_tokens','output_tokens','total_tokens')}
        for container, keys in (('input_tokens_details', ('cached_tokens','cache_write_tokens')),
                                ('output_tokens_details', ('reasoning_tokens',))):
            detail = usage.get(container)
            values.update({key:detail.get(key) if isinstance(detail,dict) else None for key in keys})
        if all(type(value) is int and value >= 0 for value in values.values()):
            usage_records += 1
            for key, value in values.items():
                token_totals[key] += value
    calls = [{key:outcome.get(key) for key in (
        'call_id','task_id','condition','sample','attempt','status','protocol_valid',
        'returned_model','returned_reasoning','returned_service_tier','response_status',
        'error_kind','provider_error','protocol_errors','usage')} for outcome in outcomes]
    for call, outcome in zip(calls, outcomes):
        grade = outcome.get('grade')
        if isinstance(grade, dict):
            sanitized = {key:grade.get(key) for key in ('status','correct')}
            for field in ('tests', 'old_tests'):
                suite = grade.get(field)
                if isinstance(suite, dict) and isinstance(suite.get('results'), list):
                    sanitized[field] = {'cases':len(suite['results']),
                        'passed_cases':sum(item.get('passed') is True for item in suite['results']),
                        'passed':suite.get('passed') is True}
            call['grade'] = sanitized
        else:
            call['grade'] = None
        if isinstance(call['returned_reasoning'], dict):
            call['returned_reasoning'] = {key:call['returned_reasoning'].get(key)
                                         for key in ('context','effort','mode')}
    attempts = [{key:row.get(key) for key in ('call_id','attempt','state','error_kind','started','finished')}
                | {'reserved_usd':row['reserved']/1_000_000,
                   'known_charge_usd':row['charged']/1_000_000 if row['charged'] is not None else None,
                   'outstanding_reservation_usd':row['reserved']/1_000_000 if row['charged'] is None else 0}
                for row in smoke_rows]
    complete = all(outcome.get('response_status') == 'completed' for outcome in outcomes)
    return {'schema_version':1, 'execution_scope':'protocol_smoke',
            'manifest_sha256':manifest['manifest_sha256'], 'task_id':manifest['smoke_task']['task_id'],
            'requested_settings':manifest['settings'], 'logical_calls':len(schedule),
            'attempts':len(smoke_rows), 'completed_three_responses':complete,
            'protocol_passed':bool(complete and initial_valid and all(full_replay) and context_only and
                                   all(outcome.get('protocol_valid') is True for outcome in outcomes)),
            'initial_checkpoint_sha256':digest(checkpoint) if checkpoint else None,
            'initial_checkpoint_usable':initial_valid,
            'full_initial_output_replayed':dict(zip(('updated_retained','updated_dropped'),full_replay)),
            'paired_requests_differ_only_in_reasoning_context':context_only,
            'same_initial_checkpoint_for_both_branches':all(full_replay), 'calls':calls,
            'attempt_records':attempts,
            'known_usage_records':usage_records, 'known_smoke_token_totals':token_totals,
            'accounting':{'shared_cap_usd':CAP_MICRO_USD/1_000_000,
                          'known_charges_usd_all_versions':known/1_000_000,
                          'outstanding_reservations_usd_all_versions':outstanding/1_000_000,
                          'accounted_usd_all_versions':(known+outstanding)/1_000_000,
                          'remaining_unreserved_usd':(CAP_MICRO_USD-known-outstanding)/1_000_000}}


def execute(manifest, ledger, provider, *, schedule=None, tasks=None, grader=None,
            execution_scope=None, campaign_guard=None):
    """Serialize real dispatch and interrupted recovery, including within one process."""
    from .provider import OpenAIProvider
    real = isinstance(provider, OpenAIProvider)
    if real:
        require_campaign_lock(campaign_guard, ledger)
        if not campaign_guard.execution_mutex.acquire(blocking=False):
            raise RuntimeError('Another execution is using this campaign lock')
    try:
        return _execute(manifest, ledger, provider, schedule=schedule, tasks=tasks,
                        grader=grader, execution_scope=execution_scope, campaign_guard=campaign_guard)
    finally:
        if real:
            campaign_guard.execution_mutex.release()


def _execute(manifest, ledger, provider, *, schedule=None, tasks=None, grader=None,
             execution_scope=None, campaign_guard=None):
    """Internal execution core, injection supports entirely offline mock qualification.

    Public CLI must pass paid_preflight before constructing a real provider.
    No initial answer correctness is used to choose or suppress assignments.
    """
    from .provider import (build_request, validate_response, extract_visible_answer,
                           OpenAIProvider, ProviderFailure)
    if grader is None:
        from .grading import grade_response
        grader = grade_response
    schedule = manifest['schedule'] if schedule is None else schedule
    tasks = manifest['tasks'] if tasks is None else tasks
    scoped_provider = isinstance(provider, OpenAIProvider)
    if scoped_provider:
        require_campaign_lock(campaign_guard, ledger)
        provider.authorize_schedule(manifest, ledger, schedule, tasks,
                                    execution_scope=execution_scope, campaign_guard=campaign_guard)
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
                if scoped_provider:
                    response = provider.create(request, execution_context={
                        'manifest_sha256':manifest['manifest_sha256'],
                        'task_id':call['task_id'], 'call_id':call_id,
                        'condition':call['condition'], 'sample':call['sample'],
                        'attempt':attempt})
                else:
                    response = provider.create(request)
            except ProviderFailure as exc:
                if exc.retryable:
                    ledger.uncertain(call_id,attempt,exc.kind)
                    if attempt < 2:
                        continue
                else:
                    failure = dict(call, status='protocol_failure' if exc.kind=='protocol_failure' else 'provider_failure',
                                   protocol_valid=False,error_kind=exc.kind,provider_error=exc.as_dict())
                    ledger.provider_failure(call_id,attempt,exc.kind,failure)
                    if exc.kind=='protocol_failure':
                        stop_reason='protocol_failure'
                    elif not exc.uncertain_charge and exc.status_code is None:
                        # Local scope/policy failures must stop before later
                        # assignments can reserve or attempt another call.
                        stop_reason=exc.kind
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
                           returned_reasoning=response.get('reasoning'),
                           returned_service_tier=response.get('service_tier'),
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
    result = {'outcomes':outcomes,'stop_reason':stop_reason, 'execution_scope':execution_scope,
              'accounted_usd':ledger.total()/1_000_000,'attempts':len(ledger.rows(manifest['manifest_sha256']))}
    if execution_scope == 'protocol_smoke':
        result['protocol_report'] = smoke_protocol_report(ledger, manifest)
    return result
