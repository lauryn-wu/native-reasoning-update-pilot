"""Bounded low-effort continuations of immutable high-effort initial solves.

Historical initial outcomes are read for reporting, never copied into new ledger
rows. All 24 assignments remain scheduled irrespective of initial correctness.
"""
from __future__ import annotations

import copy
import json

from .budget import BudgetRefused, LOW_EFFORT_CAP_MICRO_USD, LOW_EFFORT_DURATION_SECONDS, reservation
from .feasibility import _completed, _grade, _graded
from .runner import _provider_stop_reason, outcomes_from_ledger, require_campaign_lock
from .util import utcnow

SCOPE = 'low_effort_followup'
CONDITIONS = ('updated_retained', 'updated_dropped', 'fresh')


def _initial_outcomes(manifest):
    """Use manifest-bound historical grading, not a new grade or model call."""
    result = {}
    for task in manifest['tasks']:
        tid = task['task_id']
        item = manifest['inherited_initials'][tid]
        outcome = copy.deepcopy(item['outcome'])
        outcome.update(task_id=tid, condition='initial', sample=0, inherited=True)
        result[tid] = outcome
    return result


def _accounting(ledger, manifest):
    from .low_effort import AUTHORIZATION
    rows = ledger.rows()
    own = ledger.rows(manifest['manifest_sha256'])
    known = sum(row['charged'] for row in rows if row['charged'] is not None)
    outstanding = sum(row['reserved'] for row in rows if row['charged'] is None)
    scope = ledger.scope_status(AUTHORIZATION['authorization_id'])
    return {
        'scope': dict(scope, bound=True) if scope else {
            'scope_id': AUTHORIZATION['authorization_id'], 'bound': False,
            'manifest_hash': manifest['manifest_sha256'], 'status': 'not_started',
            'cap_micro_usd': LOW_EFFORT_CAP_MICRO_USD,
            'duration_seconds': LOW_EFFORT_DURATION_SECONDS,
            'attempts': 0, 'known_charges_usd': 0, 'outstanding_reservations_usd': 0,
            'accounted_usd': 0, 'elapsed_seconds': 0, 'dispatch_allowed': False},
        'shared_known_charges_usd': known / 1e6,
        'shared_outstanding_reservations_usd': outstanding / 1e6,
        'shared_accounted_usd': (known + outstanding) / 1e6,
        'attempts_this_manifest': len(own),
        'transport_retries_this_manifest': sum(row['attempt'] == 2 for row in own),
    }


def report(manifest, ledger, *, stop_reason=None):
    """Descriptive public metadata only; prompts and native output stay local."""
    from .low_effort import make_schedule, verify_initials
    verify_initials(ledger, manifest)
    schedule = make_schedule(manifest['tasks'])
    if manifest['schedule'] != schedule:
        raise ValueError('Low-effort schedule changed')
    outcomes = outcomes_from_ledger(ledger, manifest, schedule)
    indexed = {outcome['call_id']: outcome for outcome in outcomes}
    initials = _initial_outcomes(manifest)

    def summary(calls):
        values = [indexed[call['call_id']] for call in calls]
        graded = [value for value in values if _graded(value)]
        correct = sum(_grade(value) == 'correct' for value in graded)
        missing = sum(value.get('status') in ('unassigned', 'budget_stopped') for value in values)
        return {'planned_n': len(calls), 'graded_n': len(graded), 'correct_n': correct,
                'accuracy': correct / len(graded) if graded else None,
                'completed_response_n': sum(_completed(value) for value in values),
                'missing_n': missing,
                'unavailable_or_protocol_invalid_n': len(calls) - len(graded) - missing}

    task_rows, eligible_ids, pairs, complete_ids = [], [], [], []
    for task in manifest['tasks']:
        tid = task['task_id']
        calls = [call for call in schedule if call['task_id'] == tid]
        initial = initials[tid]
        eligible = _graded(initial) and _grade(initial) == 'correct'
        if eligible:
            eligible_ids.append(tid)
        complete = len(calls) == 6 and all(_completed(indexed[call['call_id']]) for call in calls)
        if complete:
            complete_ids.append(tid)
        for sample in (1, 2):
            calls_in_pair = [call for call in calls if call['sample'] == sample
                             and call['condition'] in CONDITIONS[:2]]
            pairs.append({'task_id': tid, 'sample': sample,
                          'completed': len(calls_in_pair) == 2 and all(
                              _completed(indexed[call['call_id']]) for call in calls_in_pair)})
        task_rows.append({'task_id': tid, 'domain': task.get('domain'),
                          'initial_grade': _grade(initial), 'initial_correct_eligible': eligible,
                          'initial_inherited': True, 'task_block_complete': complete,
                          'by_condition': {condition: summary([call for call in calls
                              if call['condition'] == condition]) for condition in CONDITIONS}})

    def population(ids):
        return {'task_ids': ids, 'n_tasks': len(ids),
                'completed_task_blocks': sum(tid in ids for tid in complete_ids),
                'planned_retained_dropped_sample_pairs': 2 * len(ids),
                'completed_retained_dropped_sample_pairs': sum(
                    pair['completed'] for pair in pairs if pair['task_id'] in ids),
                'by_condition': {condition: summary([call for call in schedule
                    if call['task_id'] in ids and call['condition'] == condition])
                    for condition in CONDITIONS}}

    public_calls = []
    for outcome in outcomes:
        public = {key: outcome.get(key) for key in (
            'call_id', 'task_id', 'condition', 'sample', 'attempt', 'status',
            'protocol_valid', 'response_status', 'returned_model', 'returned_reasoning',
            'returned_service_tier', 'error_kind', 'usage')}
        if isinstance(public['returned_reasoning'], dict):
            public['returned_reasoning'] = {key: public['returned_reasoning'].get(key)
                                           for key in ('effort', 'context', 'mode')}
        public['grade_status'] = _grade(outcome)
        error = outcome.get('provider_error')
        public['provider_error'] = ({key: error.get(key) for key in (
            'kind', 'retryable', 'uncertain_charge', 'status_code')} if isinstance(error, dict) else None)
        public_calls.append(public)
    completed = sum(_completed(outcome) for outcome in outcomes)
    inherited = []
    for tid, initial in initials.items():
        descriptor = manifest['inherited_initials'][tid]
        inherited.append({'task_id': tid, 'grade_status': _grade(initial),
                          'protocol_valid': initial.get('protocol_valid') is True,
                          'response_status': initial.get('response_status'),
                          'ledger_row_copied': False, 'new_initial_dispatched': False,
                          'lineage': {key: descriptor.get(key) for key in (
                              'source_call_id', 'source_attempt', 'source_manifest_sha256',
                              'checkpoint_sha256')}})
    return {'report_type': 'descriptive_low_effort_followup', 'execution_scope': SCOPE,
            'manifest_sha256': manifest['manifest_sha256'], 'reported_at': utcnow(),
            'requested_settings': manifest['settings'],
            'initial_effort': 'high', 'revision_and_fresh_effort': 'low',
            'stop_reason': stop_reason, 'planned_calls': len(schedule),
            'completed_protocol_valid_responses': completed,
            'all_planned_calls_completed': completed == len(schedule) == 24,
            'completed_task_blocks': len(complete_ids), 'planned_task_blocks': 4,
            'completed_task_ids': complete_ids,
            'completed_retained_dropped_sample_pairs': sum(pair['completed'] for pair in pairs),
            'planned_retained_dropped_sample_pairs': 8,
            'all_selected_tasks': population([task['task_id'] for task in manifest['tasks']]),
            'initial_correct_subset': population(eligible_ids), 'per_task': task_rows,
            'sample_pairs': pairs, 'calls': public_calls, 'inherited_initials': inherited,
            'accounting': _accounting(ledger, manifest),
            'interpretation': [
                'All 24 new calls are low effort; the four immutable initial solves were high effort.',
                'Historical initial correctness defines a separate subset; no assignments are suppressed.',
                'This exploratory comparison is conditional on these initial checkpoints, not an all-low-effort evaluation.',
                'Accuracy uses protocol-valid graded returns; missing and unavailable outcomes are reported separately.',
                'Repeated samples do not increase the number of independent task problems.',
                'Elapsed scope time includes downtime and permits in-flight completion after the dispatch deadline.',
                'No significance test, continuation gate, or general null-effect conclusion is applied.']}


def execute(manifest, ledger, provider, *, tasks=None, grader=None, campaign_guard=None):
    """Execute/resume exactly the frozen low-effort schedule, under one lock."""
    from .provider import OpenAIProvider
    real = isinstance(provider, OpenAIProvider)
    if real:
        require_campaign_lock(campaign_guard, ledger)
        if not campaign_guard.execution_mutex.acquire(blocking=False):
            raise RuntimeError('Another execution is using this campaign lock')
    try:
        return _execute(manifest, ledger, provider, tasks=tasks, grader=grader,
                        campaign_guard=campaign_guard)
    finally:
        if real:
            campaign_guard.execution_mutex.release()


def _execute(manifest, ledger, provider, *, tasks=None, grader=None, campaign_guard=None):
    from .low_effort import AUTHORIZATION, make_schedule, verify_initials
    from .provider import (OpenAIProvider, ProviderFailure, build_low_request,
                           extract_visible_answer, validate_low_response)
    if grader is None:
        from .grading import grade_response
        grader = grade_response
    schedule = make_schedule(manifest['tasks'])
    if manifest['schedule'] != schedule or len(schedule) != 24:
        raise ValueError('Only the exact 24-call low-effort schedule may execute')
    tasks = manifest['tasks'] if tasks is None else tasks
    if [task['task_id'] for task in tasks] != [task['task_id'] for task in manifest['tasks']]:
        raise ValueError('Low-effort grading tasks changed')
    checkpoints = verify_initials(ledger, manifest)
    scoped_provider = isinstance(provider, OpenAIProvider)
    if scoped_provider:
        require_campaign_lock(campaign_guard, ledger)
        provider.authorize_schedule(manifest, ledger, schedule, tasks,
                                    execution_scope=SCOPE, campaign_guard=campaign_guard)
    scope_id = AUTHORIZATION['authorization_id']
    ledger.bind_scope(scope_id, manifest['manifest_sha256'],
                      cap_micro_usd=LOW_EFFORT_CAP_MICRO_USD,
                      duration_seconds=LOW_EFFORT_DURATION_SECONDS)
    # Never recover or mutate an earlier campaign's historical attempts.
    ledger.recover_interrupted(manifest['manifest_sha256'])
    by_id = {task['task_id']: task for task in tasks}
    prefix = manifest['manifest_sha256'] + '/'
    stop_reason = None
    for call in schedule:
        call_id = prefix + call['call_id']
        previous = ledger.latest(call_id)
        if previous and previous['state'] in ('completed', 'provider_failure'):
            outcome = json.loads(previous['outcome']) if previous['outcome'] else {}
            if (previous['state'] == 'provider_failure' or not outcome.get('protocol_valid')
                    or outcome.get('status') in ('protocol_failure', 'provider_failure')):
                stop_reason = _provider_stop_reason(outcome, previous['error_kind'])
                break
            continue
        if previous and previous['attempt'] >= 2:
            stop_reason = 'transport_retry_exhausted'
            break
        checkpoint = None if call['condition'] == 'fresh' else checkpoints[call['task_id']]
        request = build_low_request(by_id[call['task_id']], call['condition'], checkpoint)
        while True:
            try:
                bounds = reservation(request, checkpoint)
                attempt = ledger.reserve(call_id, manifest['manifest_sha256'], request,
                                         bounds['micro_usd'], SCOPE, scope_id=scope_id)
            except BudgetRefused as exc:
                stop_reason = str(exc)
                break
            ledger.dispatched(call_id, attempt)
            try:
                ledger.assert_scope_dispatch(scope_id, manifest['manifest_sha256'], call_id, attempt)
                if scoped_provider:
                    response = provider.create(request, execution_context={
                        'manifest_sha256': manifest['manifest_sha256'], 'task_id': call['task_id'],
                        'call_id': call_id, 'condition': call['condition'],
                        'sample': call['sample'], 'attempt': attempt})
                else:
                    response = provider.create(request)
            except BudgetRefused as exc:
                stop_reason = str(exc)
                failure = dict(call, status='budget_stopped', protocol_valid=False,
                               error_kind='low_effort_scope_limit', scope_limit_reason=stop_reason)
                ledger.provider_failure(call_id, attempt, 'low_effort_scope_limit', failure)
                break
            except ProviderFailure as exc:
                if exc.retryable:
                    ledger.uncertain(call_id, attempt, exc.kind)
                    if attempt < 2:
                        continue
                    stop_reason = 'transport_retry_exhausted'
                else:
                    failure = dict(call, status='protocol_failure' if exc.kind == 'protocol_failure'
                                   else 'provider_failure', protocol_valid=False,
                                   error_kind=exc.kind, provider_error=exc.as_dict())
                    ledger.provider_failure(call_id, attempt, exc.kind, failure)
                    stop_reason = _provider_stop_reason(failure)
                break
            except Exception:
                ledger.uncertain(call_id, attempt, 'unclassified_transport_failure')
                stop_reason = 'Unclassified provider failure; inspect redacted attempt metadata'
                break
            validity = validate_low_response(response, request['reasoning']['context'])
            outcome = dict(call, protocol_valid=validity['valid'], returned_model=response.get('model'),
                           response_status=response.get('status'), returned_reasoning=response.get('reasoning'),
                           returned_service_tier=response.get('service_tier'),
                           stop_reason=response.get('incomplete_details'), usage=response.get('usage'),
                           input_tokens_bound=bounds['input_tokens_bound'], timestamp=utcnow())
            if response.get('status') in ('failed', 'cancelled'):
                outcome.update(status='provider_failure', error_kind='terminal_' + response['status'],
                               protocol_errors=validity['errors'])
            elif not validity['valid']:
                outcome.update(status='protocol_failure', protocol_errors=validity['errors'])
            else:
                try:
                    grade = grader(by_id[call['task_id']], 'updated', extract_visible_answer(response),
                                   response_status=response.get('status', 'invalid'))
                    outcome.update(status=grade['status'], grade=grade)
                except Exception:
                    outcome.update(status='protocol_failure', protocol_valid=False,
                                   protocol_errors=['Grading infrastructure failed; outcome unavailable'])
            ledger.finish(call_id, attempt, response, outcome)
            # Accounting may itself invalidate an otherwise valid response.
            outcome = json.loads(ledger.latest(call_id)['outcome'])
            if outcome['status'] == 'provider_failure':
                stop_reason = _provider_stop_reason(outcome)
            elif not outcome['protocol_valid']:
                stop_reason = outcome['status']
            break
        if stop_reason:
            break
    descriptive = report(manifest, ledger, stop_reason=stop_reason)
    if not descriptive['all_planned_calls_completed'] and not stop_reason:
        stop_reason = 'low_effort_followup_incomplete'
        descriptive['stop_reason'] = stop_reason
    return {'outcomes': outcomes_from_ledger(ledger, manifest, schedule),
            'stop_reason': stop_reason, 'execution_scope': SCOPE,
            'accounted_usd': ledger.total() / 1e6,
            'attempts': len(ledger.rows(manifest['manifest_sha256'])),
            'feasibility_report': descriptive}
