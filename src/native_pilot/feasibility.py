"""Descriptive accounting for the separately authorized four-case exploration."""
from collections import Counter

from .grading import RETURNED_GRADES

CONDITIONS = ('initial', 'updated_retained', 'updated_dropped', 'fresh')


def _grade(outcome):
    grade = (outcome or {}).get('grade')
    return grade.get('status') if isinstance(grade, dict) else None


def _graded(outcome):
    return bool(outcome and outcome.get('protocol_valid') is True
                and outcome.get('status') in RETURNED_GRADES
                and _grade(outcome) in RETURNED_GRADES)


def _completed(outcome):
    return _graded(outcome) and outcome.get('response_status') == 'completed'


def describe_exploratory(manifest, outcomes, *, accounting=None, stop_reason=None):
    """Keep missing outcomes separate; report observed counts without inference.

    Accuracy uses protocol-valid graded returns, including returned invalid or
    truncated answers. Unassigned, unavailable, and protocol-invalid calls never
    enter its denominator. Every frozen assignment remains visible in counts.
    """
    indexed = {}
    duplicates = []
    for outcome in outcomes:
        if outcome['call_id'] in indexed:
            duplicates.append(outcome['call_id'])
        indexed[outcome['call_id']] = outcome
    schedule = manifest['schedule']
    expected_ids = {call['call_id'] for call in schedule}
    unexpected = sorted(set(indexed) - expected_ids)

    def summary(calls):
        values = [indexed.get(call['call_id']) for call in calls]
        graded = [outcome for outcome in values if _graded(outcome)]
        correct = sum(_grade(outcome) == 'correct' for outcome in graded)
        missing = sum(not outcome or outcome.get('status') in ('unassigned', 'budget_stopped') for outcome in values)
        return {'planned_n':len(calls), 'graded_n':len(graded), 'correct_n':correct,
                'accuracy':correct/len(graded) if graded else None,
                'completed_response_n':sum(_completed(outcome) for outcome in values),
                'missing_n':missing,
                'unavailable_or_protocol_invalid_n':len(calls)-len(graded)-missing,
                'returned_grade_counts':dict(Counter(_grade(outcome) for outcome in graded))}

    def population(task_ids):
        ids = set(task_ids)
        return {'task_ids':task_ids, 'n_tasks':len(task_ids),
                'completed_task_blocks':sum(task_id in ids for task_id in completed_blocks),
                'completed_retained_dropped_sample_pairs':sum(pair['completed'] for pair in sample_pairs if pair['task_id'] in ids),
                'planned_retained_dropped_sample_pairs':2*len(task_ids),
                'by_condition':{condition:summary([call for call in schedule
                    if call['task_id'] in ids and call['condition'] == condition])
                    for condition in CONDITIONS}}

    rows, eligible_ids, sample_pairs = [], [], []
    completed_blocks = []
    for task in manifest['tasks']:
        task_id = task['task_id']
        calls = [call for call in schedule if call['task_id'] == task_id]
        by_condition = {condition:summary([call for call in calls if call['condition'] == condition])
                        for condition in CONDITIONS}
        initial_calls = [call for call in calls if call['condition'] == 'initial']
        initial = indexed.get(initial_calls[0]['call_id']) if len(initial_calls) == 1 else None
        eligible = bool(_graded(initial) and _grade(initial) == 'correct')
        if eligible:
            eligible_ids.append(task_id)
        pairs = []
        for sample in (1, 2):
            pair = [call for call in calls if call['sample'] == sample
                    and call['condition'] in ('updated_retained', 'updated_dropped')]
            complete = len(pair) == 2 and all(_completed(indexed.get(call['call_id'])) for call in pair)
            item = {'task_id':task_id, 'sample':sample, 'completed':complete}
            pairs.append(item)
            sample_pairs.append(item)
        block_complete = len(calls) == 7 and all(_completed(indexed.get(call['call_id'])) for call in calls)
        if block_complete:
            completed_blocks.append(task_id)
        rows.append({'task_id':task_id, 'domain':task.get('domain'),
                     'initial_correct':(_grade(initial) == 'correct') if _graded(initial) else None,
                     'initial_grade':_grade(initial) if _graded(initial) else None,
                     'initial_correct_eligible':eligible, 'by_condition':by_condition,
                     'completed_retained_dropped_sample_pairs':sum(pair['completed'] for pair in pairs),
                     'planned_retained_dropped_sample_pairs':2, 'task_block_complete':block_complete})
    public_calls = []
    for call in schedule:
        outcome = indexed.get(call['call_id']) or {}
        error = outcome.get('provider_error')
        sanitized_error = None
        if isinstance(error, dict):
            sanitized_error = {key:error[key] for key in ('kind','retryable','uncertain_charge','status_code') if key in error}
            if isinstance(error.get('api_error'), dict):
                sanitized_error['api_error'] = {key:error['api_error'][key] for key in
                    ('type','code','param','explanation') if key in error['api_error']}
        public_calls.append(dict(call, status=outcome.get('status', 'unassigned'),
            response_status=outcome.get('response_status'), protocol_valid=outcome.get('protocol_valid') is True,
            attempt=outcome.get('attempt'), grade_status=_grade(outcome),
            error_kind=outcome.get('error_kind'), provider_error=sanitized_error))
    completed = sum(_completed(indexed.get(call['call_id'])) for call in schedule)
    protocol_invalid = [call['call_id'] for call in schedule
                        if (indexed.get(call['call_id']) or {}).get('status') not in (None, 'unassigned', 'budget_stopped')
                        and (indexed.get(call['call_id']) or {}).get('protocol_valid') is not True]
    from .util import utcnow
    return {'report_type':'descriptive_feasibility', 'execution_scope':'exploratory_pilot',
            'reported_at':utcnow(),
            'manifest_sha256':manifest['manifest_sha256'], 'stop_reason':stop_reason,
            'planned_calls':len(schedule), 'completed_protocol_valid_responses':completed,
            'all_planned_calls_completed':bool(schedule) and completed == len(schedule)
                                         and not duplicates and not unexpected,
            'completed_task_blocks':len(completed_blocks), 'planned_task_blocks':len(manifest['tasks']),
            'completed_task_ids':completed_blocks,
            'completed_retained_dropped_sample_pairs':sum(pair['completed'] for pair in sample_pairs),
            'planned_retained_dropped_sample_pairs':len(sample_pairs),
            'all_selected_tasks':population([task['task_id'] for task in manifest['tasks']]),
            'initial_correct_subset':population(eligible_ids), 'per_task':rows,
            'sample_pairs':sample_pairs, 'calls':public_calls,
            'protocol':{'invalid_call_ids':protocol_invalid, 'duplicate_outcome_call_ids':duplicates,
                        'unexpected_outcome_call_ids':unexpected},
            'accounting':accounting or {},
            'interpretation':[
                'Descriptive feasibility on four selected cases; no significance test, continuation gate, or null-effect conclusion.',
                'Accuracy is correct_n / graded_n. Missing and protocol-invalid calls are excluded from that denominator and reported separately.',
                'Returned invalid or truncated answers remain unsuccessful graded returns; a complete task block requires seven protocol-valid completed responses.',
                'The initial-correct subset is reported separately; all selected tasks remain in the primary descriptive counts.',
                'Elapsed seconds are measured at report time from the first successful scope reservation, including resume downtime; they are not summed request latency.',
                'Partial task blocks remain visible if the fixed budget, deadline, or an execution failure stops the schedule.']}


def empty_accounting(manifest):
    """A pre-start report describes limits without creating a ledger or clock."""
    from .exploratory import AUTHORIZATION
    return {'scope':{'scope_id':AUTHORIZATION['authorization_id'],
                     'manifest_hash':manifest['manifest_sha256'], 'bound':False,
                     'status':'not_started', 'cap_micro_usd':5_000_000, 'duration_seconds':1800,
                     'started_at':None, 'deadline_at':None,
                     'started_at_epoch_seconds':None, 'deadline_epoch_seconds':None,
                     'elapsed_seconds':0, 'remaining_seconds':1800, 'dispatch_allowed':False,
                     'attempts':0, 'known_charges_micro_usd':0, 'known_charges_usd':0,
                     'outstanding_reservations_micro_usd':0, 'outstanding_reservations_usd':0,
                     'accounted_micro_usd':0, 'accounted_usd':0,
                     'remaining_unreserved_micro_usd':5_000_000, 'remaining_unreserved_usd':5},
            'shared_known_charges_usd':0,'shared_outstanding_reservations_usd':0,
            'shared_accounted_usd':0,'attempts_this_manifest':0,'transport_retries_this_manifest':0}


def ledger_accounting(ledger, manifest):
    """Read accounting and elapsed wall time; never start or reset a scope clock."""
    from .exploratory import AUTHORIZATION
    all_rows = ledger.rows()
    scoped_rows = ledger.rows(manifest['manifest_sha256'])
    known = sum(row['charged'] for row in all_rows if row['charged'] is not None)
    outstanding = sum(row['reserved'] for row in all_rows if row['charged'] is None)
    status = ledger.scope_status(AUTHORIZATION['authorization_id'])
    return {'scope':dict(status,bound=True) if status else empty_accounting(manifest)['scope'],
            'shared_known_charges_usd':known/1_000_000,
            'shared_outstanding_reservations_usd':outstanding/1_000_000,
            'shared_accounted_usd':(known+outstanding)/1_000_000,
            'attempts_this_manifest':len(scoped_rows),
            'transport_retries_this_manifest':sum(row['attempt'] == 2 for row in scoped_rows)}
