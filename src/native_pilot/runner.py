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


def continuation_schedule(task):
    """Only the two authorized forks; never regenerate an initial response."""
    return smoke_schedule(task)[1:]


def _inherited_initial(ledger, manifest):
    """Read the exact verified historical attempt without copying ledger rows."""
    from .provider import _read_continuation_recovery_record, _verify_continuation_recovery
    _verify_continuation_recovery(manifest, ledger)
    recovery = _read_continuation_recovery_record(manifest)
    matches = [row for row in ledger.rows(recovery['prior_manifest_sha256'])
               if row['call_id'] == recovery['initial_call_id']
               and row['attempt'] == recovery['initial_attempt']]
    if len(matches) != 1:
        raise RuntimeError('Verified initial checkpoint is missing or ambiguous')
    return matches[0], recovery


def _replay_preservation(raw, normalized):
    """Independently verify that only null reasoning-status keys were omitted."""
    import copy
    from .util import digest
    expected = copy.deepcopy(raw)
    removed = []
    if isinstance(expected, list):
        for index, item in enumerate(expected):
            if (isinstance(item, dict) and item.get('type') == 'reasoning'
                    and 'status' in item and item['status'] is None):
                del item['status']
                removed.append(index)
    return {'verified': isinstance(raw, list) and expected == normalized,
            'rule': 'omit_status_only_when_reasoning_item_status_is_none',
            'removed_status_item_indices': removed,
            'output_items': len(raw) if isinstance(raw, list) else None,
            'reasoning_items': sum(isinstance(item, dict) and item.get('type') == 'reasoning'
                                   for item in raw) if isinstance(raw, list) else None,
            'raw_output_sha256': digest(raw), 'normalized_output_sha256': digest(normalized)}


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


def _provider_stop_reason(outcome, error_kind=None):
    """A safe, persistent failure reason; never include a provider error body."""
    if outcome.get('scope_limit_reason'):
        return outcome['scope_limit_reason']
    error = outcome.get('provider_error') or {}
    kind = (outcome.get('error_kind') or error_kind or
            ('protocol_failure' if outcome.get('status') == 'protocol_failure' else 'provider_failure'))
    status_code = error.get('status_code') if isinstance(error, dict) else None
    if type(status_code) is int:
        return f'{kind}_http_{status_code}'
    return kind


def smoke_protocol_report(ledger, manifest):
    """Public diagnostics only: no answers, prompts, or opaque reasoning values."""
    from .budget import CAP_MICRO_USD
    from .provider import validate_response, normalize_replay_output
    from .util import digest
    import copy
    inherited = bool(manifest.get('continuation_recovery'))
    schedule = (continuation_schedule(manifest['smoke_task']) if inherited
                else smoke_schedule(manifest['smoke_task']))
    outcomes = outcomes_from_ledger(ledger, manifest, schedule)
    prefix = manifest['manifest_sha256'] + '/'
    rows = [ledger.latest(prefix + call['call_id']) for call in schedule]
    lineage = None
    continuation_record = None
    if inherited:
        initial, recovery = _inherited_initial(ledger, manifest)
        continuation_record = recovery
        initial_outcome = dict(smoke_schedule(manifest['smoke_task'])[0],
                               **{'attempt': initial['attempt'], 'status': 'unassigned', 'protocol_valid': False})
        if initial['outcome']:
            initial_outcome.update(json.loads(initial['outcome']))
        outcomes.insert(0, initial_outcome)
        rows.insert(0, initial)
        lineage = {'source_manifest_sha256': initial['manifest_hash'],
                   'source_call_id': initial['call_id'], 'source_attempt': initial['attempt'],
                   'source_attempt_sha256': digest(initial),
                   'source_response_sha256': digest(json.loads(initial['response'])),
                   'authorized_checkpoint_sha256': recovery['initial_checkpoint_sha256'],
                   'prior_failed_call_id': recovery['failed_call_id'],
                   'prior_failed_attempt_sha256': recovery['failed_attempt_sha256'],
                   'ledger_row_copied': False, 'new_initial_dispatched': False}
    else:
        initial = rows[0]
    checkpoint = None
    if initial and initial['request'] and initial['response']:
        checkpoint = {'request': json.loads(initial['request']),
                      'response': json.loads(initial['response'])}
    initial_valid = bool(checkpoint and validate_response(
        checkpoint['response'], 'current_turn', require_checkpoint=True)['valid'])
    raw_output = checkpoint['response'].get('output') if checkpoint else None
    normalized_output = normalize_replay_output(raw_output) if initial_valid else None
    normalization = _replay_preservation(raw_output, normalized_output)
    if lineage:
        lineage['checkpoint_sha256'] = digest(checkpoint)
        lineage['verified'] = lineage['checkpoint_sha256'] == lineage['authorized_checkpoint_sha256']
    full_replay = []
    paired = []
    for row in rows[1:]:
        request = json.loads(row['request']) if row and row['request'] else None
        paired.append(request)
        full_replay.append(bool(initial_valid and normalization['verified'] and request
                               and request['input'][:-1] == checkpoint['request']['input'] + normalized_output))
    context_only = False
    if all(paired):
        retained, dropped = copy.deepcopy(paired)
        contexts = [retained['reasoning'].pop('context'), dropped['reasoning'].pop('context')]
        context_only = contexts == ['all_turns', 'current_turn'] and retained == dropped
    all_rows = ledger.rows()
    prior_failure = None
    authentication_manifest = manifest
    if inherited:
        from .provider import _read_continuation_prior_manifest
        authentication_manifest = _read_continuation_prior_manifest(manifest)
    if authentication_manifest.get('authentication_recovery'):
        from .provider import _read_authentication_recovery_record, ProviderFailure
        try:
            recovery = _read_authentication_recovery_record(authentication_manifest)
            prior = [row for row in all_rows
                     if row['call_id'] == recovery['failed_call_id']
                     and row['attempt'] == recovery['failed_attempt']
                     and row['manifest_hash'] == recovery['failed_manifest_sha256']]
            if len(prior) != 1:
                raise ValueError('Missing preserved authentication attempt')
            failed = prior[0]
            error = (json.loads(failed['outcome']) or {}).get('provider_error', {})
            prior_failure = {
                'call_id': failed['call_id'], 'attempt': failed['attempt'],
                'manifest_sha256': failed['manifest_hash'], 'state': failed['state'],
                'attempt_sha256': digest(failed), 'authorized_attempt_sha256': recovery['failed_attempt_sha256'],
                'http_status': error.get('status_code'), 'reserved_micro_usd': failed['reserved'],
                'reserved_usd': failed['reserved']/1_000_000, 'charged_micro_usd': failed['charged'],
                'known_charge_usd': failed['charged']/1_000_000 if failed['charged'] is not None else None,
                'preservation_verified': (digest(failed) == recovery['failed_attempt_sha256']
                    and failed['state'] == 'provider_failure' and error.get('status_code') == 401
                    and failed['charged'] is None
                    and failed['reserved'] == recovery['retained_reservation_micro_usd'])}
        except (ProviderFailure, ValueError, TypeError, KeyError, AttributeError):
            prior_failure = {'preservation_verified': False,
                             'error_kind': 'authentication_recovery_predecessor_unverified'}
    prior_continuation_failure = None
    if continuation_record:
        failed = next(row for row in all_rows
                      if row['call_id'] == continuation_record['failed_call_id']
                      and row['attempt'] == continuation_record['failed_attempt'])
        error = json.loads(failed['outcome']).get('provider_error', {})
        prior_continuation_failure = {
            'call_id': failed['call_id'], 'attempt': failed['attempt'],
            'manifest_sha256': failed['manifest_hash'], 'state': failed['state'],
            'attempt_sha256': digest(failed),
            'authorized_attempt_sha256': continuation_record['failed_attempt_sha256'],
            'http_status': error.get('status_code'), 'reserved_micro_usd': failed['reserved'],
            'reserved_usd': failed['reserved']/1_000_000,
            'charged_micro_usd': failed['charged'],
            'known_charge_usd': failed['charged']/1_000_000 if failed['charged'] is not None else None,
            'preservation_verified': (digest(failed) == continuation_record['failed_attempt_sha256']
                and failed['state'] == 'provider_failure' and error.get('status_code') == 400
                and failed['charged'] is None)}
    smoke_rows = [row for row in all_rows if row['call_id'] in {prefix+c['call_id'] for c in schedule}]
    known = sum(row['charged'] for row in all_rows if row['charged'] is not None)
    outstanding = sum(row['reserved'] for row in all_rows if row['charged'] is None)
    token_totals = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0,
                    'reasoning_tokens': 0, 'cached_tokens': 0, 'cache_write_tokens': 0}
    usage_records = 0
    usage_rows = ([initial] if inherited else []) + smoke_rows
    for row in usage_rows:
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
    if inherited:
        calls[0].update(inherited=True, source_call_id=initial['call_id'],
                        source_manifest_sha256=initial['manifest_hash'])
    attempts = [{key:row.get(key) for key in ('call_id','attempt','state','error_kind','started','finished')}
                | {'reserved_usd':row['reserved']/1_000_000,
                   'known_charge_usd':row['charged']/1_000_000 if row['charged'] is not None else None,
                   'outstanding_reservation_usd':row['reserved']/1_000_000 if row['charged'] is None else 0}
                for row in smoke_rows]
    complete = all(outcome.get('response_status') == 'completed' for outcome in outcomes)
    return {'schema_version':1, 'execution_scope':'protocol_smoke',
            'manifest_sha256':manifest['manifest_sha256'], 'task_id':manifest['smoke_task']['task_id'],
            'requested_settings':manifest['settings'], 'logical_calls':len(schedule),
            'inherited_completed_responses': 1 if inherited and initial_valid else 0,
            'responses_in_full_smoke': len(rows),
            'attempts':len(smoke_rows), 'completed_three_responses':complete,
            'protocol_passed':bool(complete and initial_valid and all(full_replay) and context_only and
                                   all(outcome.get('protocol_valid') is True for outcome in outcomes)
                                   and (prior_failure is None or prior_failure['preservation_verified'])
                                   and (prior_continuation_failure is None or prior_continuation_failure['preservation_verified'])
                                   and (lineage is None or lineage['verified'])),
            'initial_checkpoint_sha256':digest(checkpoint) if checkpoint else None,
            'initial_checkpoint_usable':initial_valid,
            'inherited_initial_checkpoint':lineage, 'replay_normalization':normalization,
            'full_initial_output_replayed':dict(zip(('updated_retained','updated_dropped'),full_replay)),
            'paired_requests_differ_only_in_reasoning_context':context_only,
            'same_initial_checkpoint_for_both_branches':all(full_replay), 'calls':calls,
            'attempt_records':attempts,
            'authentication_recovery_prior_failure':prior_failure,
            'continuation_recovery_prior_failure':prior_continuation_failure,
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
    scope_id = None
    if execution_scope == 'exploratory_pilot':
        from .exploratory import AUTHORIZATION
        scope_id = AUTHORIZATION['authorization_id']
        ledger.bind_scope(scope_id, manifest['manifest_sha256'],
                          cap_micro_usd=5_000_000, duration_seconds=1800)
    inherited_initial = None
    if manifest.get('continuation_recovery'):
        if (execution_scope != 'protocol_smoke'
                or schedule != continuation_schedule(manifest['smoke_task'])):
            raise ValueError('Continuation recovery requires exactly the two frozen branches')
        inherited_initial, _ = _inherited_initial(ledger, manifest)
    by_id = {task['task_id']:task for task in tasks}
    prefix = manifest['manifest_sha256']+'/'
    initial_ids = {c['task_id']:prefix+c['call_id'] for c in schedule if c['condition']=='initial'}
    ledger.recover_interrupted()
    stop_reason = None
    for call in schedule:
        call_id = prefix+call['call_id']
        previous = ledger.latest(call_id)
        if previous and previous['state'] in ('completed','provider_failure'):
            previous_outcome = json.loads(previous['outcome']) if previous['outcome'] else {}
            if (previous['state'] == 'provider_failure'
                    or previous_outcome.get('status') in ('protocol_failure', 'provider_failure')):
                stop_reason = _provider_stop_reason(previous_outcome, previous['error_kind'])
                break
            continue
        if previous and previous['attempt'] >= 2:
            stop_reason = 'transport_retry_exhausted'
            break
        branch = call['condition']
        checkpoint = None
        if branch not in ('initial','fresh'):
            initial_id = initial_ids.get(call['task_id'])
            initial = inherited_initial if inherited_initial is not None else (ledger.latest(initial_id) if initial_id else None)
            if not initial or not initial.get('response'):
                stop_reason = 'initial_checkpoint_missing'
                break
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
                kind = ('exploratory_pilot' if scope_id else
                        'smoke' if call['call_id'].startswith('smoke/') else 'pilot')
                attempt = ledger.reserve(call_id, manifest['manifest_sha256'], request,
                                         bounds['micro_usd'], kind,
                                         **({'scope_id':scope_id} if scope_id else {}))
            except BudgetRefused as exc:
                stop_reason = str(exc)
                break
            ledger.dispatched(call_id,attempt)
            try:
                if scope_id:
                    ledger.assert_scope_dispatch(scope_id, manifest['manifest_sha256'], call_id, attempt)
                if scoped_provider:
                    response = provider.create(request, execution_context={
                        'manifest_sha256':manifest['manifest_sha256'],
                        'task_id':call['task_id'], 'call_id':call_id,
                        'condition':call['condition'], 'sample':call['sample'],
                        'attempt':attempt})
                else:
                    response = provider.create(request)
            except BudgetRefused as exc:
                # A deadline can pass after reservation but before the SDK call.
                # Preserve that reservation and a terminal stop; never retry it.
                stop_reason = str(exc)
                failure = dict(call, status='budget_stopped', protocol_valid=False,
                               error_kind='exploratory_scope_limit', scope_limit_reason=stop_reason)
                ledger.provider_failure(call_id, attempt, 'exploratory_scope_limit', failure)
                break
            except ProviderFailure as exc:
                if exc.retryable:
                    ledger.uncertain(call_id,attempt,exc.kind)
                    if attempt < 2:
                        continue
                    stop_reason = 'transport_retry_exhausted'
                else:
                    failure = dict(call, status='protocol_failure' if exc.kind=='protocol_failure' else 'provider_failure',
                                   protocol_valid=False,error_kind=exc.kind,provider_error=exc.as_dict())
                    ledger.provider_failure(call_id,attempt,exc.kind,failure)
                    stop_reason = _provider_stop_reason(failure)
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
            if outcome['status'] == 'provider_failure':
                stop_reason = _provider_stop_reason(outcome)
            elif not outcome['protocol_valid']:
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
        if not result['protocol_report']['protocol_passed'] and not result['stop_reason']:
            result['stop_reason'] = 'protocol_smoke_incomplete'
    if execution_scope == 'exploratory_pilot':
        from .feasibility import describe_exploratory, ledger_accounting
        result['feasibility_report'] = describe_exploratory(
            manifest, outcomes, accounting=ledger_accounting(ledger, manifest), stop_reason=stop_reason)
        if not result['feasibility_report']['all_planned_calls_completed'] and not result['stop_reason']:
            result['stop_reason'] = 'exploratory_pilot_incomplete'
            result['feasibility_report']['stop_reason'] = result['stop_reason']
    return result
