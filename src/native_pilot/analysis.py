"""Frozen task-level exploratory analysis; no post-treatment case selection."""
from __future__ import annotations

from collections import Counter
import math
import random
from typing import Any

from .grading import RETURNED_GRADES

CONDITIONS = ("initial", "updated_retained", "updated_dropped", "fresh",
              "unchanged_retained", "unchanged_dropped")
BOOTSTRAP_SEED = 20261024
BOOTSTRAP_REPEATS = 10000


def sign_flip_pvalue(differences: list[float]) -> float | None:
    """Exact inclusive upper-tail paired randomization p for two repeats.

    Each problem is flipped as a whole. Integer half-units avoid floating point
    comparisons, and a multiplicity-counting DP enumerates all 2**n sign choices.
    Under the null, within-problem retained/dropped labels must be exchangeable;
    this is an exploratory randomization assumption, not a causal mechanism test.
    """
    if not differences:
        return None
    weights = []
    for difference in differences:
        doubled = difference * 2
        if not math.isfinite(doubled) or abs(doubled - round(doubled)) > 1e-9 or abs(difference) > 1:
            raise ValueError("Differences must be two-repeat accuracy gaps in half units")
        weights.append(round(doubled))
    observed = sum(weights)
    distribution = Counter({0: 1})
    for weight in weights:
        next_distribution = Counter()
        for total, count in distribution.items():
            next_distribution[total + abs(weight)] += count
            next_distribution[total - abs(weight)] += count
        distribution = next_distribution
    return sum(count for total, count in distribution.items() if total >= observed) / (2 ** len(weights))


def bootstrap_interval(values: list[float], *, seed: int = BOOTSTRAP_SEED,
                       repeats: int = BOOTSTRAP_REPEATS) -> list[float] | None:
    """Fixed-seed percentile 95% bootstrap, resampling whole problems."""
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(repeats))
    return [means[math.floor(0.025 * (repeats - 1))], means[math.ceil(0.975 * (repeats - 1))]]


def _grade(outcome: dict | None) -> str | None:
    if not outcome:
        return None
    grade = outcome.get("grade", {})
    if isinstance(grade, str):
        return grade
    return grade.get("status", outcome.get("grade_status"))


def _available(outcome: dict | None) -> bool:
    if not outcome or outcome.get("protocol_valid") is not True:
        return False
    if outcome.get("status") not in RETURNED_GRADES | {"completed"}:
        return False
    return _grade(outcome) in RETURNED_GRADES


def _population(rows: list[dict], name: str) -> dict:
    complete_pairs = bool(rows) and all(row["difference"] is not None for row in rows)
    complete_fresh = bool(rows) and all(row["fresh_accuracy"] is not None for row in rows)
    values = [row["difference"] for row in rows] if complete_pairs else []
    return {"population": name, "n_problems": len(rows), "paired_outcomes_complete": complete_pairs,
            "dropped_accuracy": sum(row["dropped_accuracy"] for row in rows) / len(rows) if complete_pairs else None,
            "retained_accuracy": sum(row["retained_accuracy"] for row in rows) / len(rows) if complete_pairs else None,
            "dropped_minus_retained": sum(values) / len(values) if values else None,
            "fresh_accuracy": sum(row["fresh_accuracy"] for row in rows) / len(rows) if complete_fresh else None,
            "one_sided_p": sign_flip_pvalue(values), "bootstrap_95_percent_interval": bootstrap_interval(values),
            "per_problem": rows}


def analyze(manifest: dict[str, Any], outcomes: list[dict] | dict[str, dict]) -> dict[str, Any]:
    tasks = manifest.get("tasks", [])
    schedule = manifest.get("schedule", [])
    duplicate_outcomes = []
    if isinstance(outcomes, list):
        indexed = {}
        for outcome in outcomes:
            if outcome["call_id"] in indexed:
                duplicate_outcomes.append(outcome["call_id"])
            indexed[outcome["call_id"]] = outcome
    else:
        indexed = outcomes
    assignments: dict[tuple[str, str], list[dict]] = {}
    availability = Counter()
    classifications = Counter()
    missing_ids, protocol_invalid_ids = [], []
    for call in schedule:
        assignments.setdefault((call["task_id"], call["condition"]), []).append(call)
        outcome = indexed.get(call["call_id"])
        if not outcome:
            availability["unassigned_or_missing"] += 1
            missing_ids.append(call["call_id"])
        elif not _available(outcome):
            availability[outcome.get("status", "unclassified_failure")] += 1
            if outcome.get("protocol_valid") is not True:
                protocol_invalid_ids.append(call["call_id"])
        else:
            availability["returned_protocol_valid"] += 1
            classifications[_grade(outcome)] += 1

    def accuracy(task_id: str, condition: str) -> float | None:
        calls = assignments.get((task_id, condition), [])
        required = 1 if condition == "initial" else 2
        if len(calls) != required or any(not _available(indexed.get(call["call_id"])) for call in calls):
            return None
        return sum(_grade(indexed[call["call_id"]]) == "correct" for call in calls) / required

    rows, eligible_ids, control_rows = [], [], []
    for task in tasks:
        task_id = task["task_id"]
        initial = accuracy(task_id, "initial")
        eligible = initial == 1.0
        if eligible:
            eligible_ids.append(task_id)
        retained, dropped = accuracy(task_id, "updated_retained"), accuracy(task_id, "updated_dropped")
        row = {"task_id": task_id, "domain": task.get("domain"), "eligible": eligible,
               "initial_accuracy": initial, "retained_accuracy": retained, "dropped_accuracy": dropped,
               "fresh_accuracy": accuracy(task_id, "fresh"),
               "difference": dropped - retained if dropped is not None and retained is not None else None}
        rows.append(row)
        if task.get("unchanged_control"):
            unchanged_r, unchanged_d = accuracy(task_id, "unchanged_retained"), accuracy(task_id, "unchanged_dropped")
            unchanged_gap = unchanged_d - unchanged_r if unchanged_d is not None and unchanged_r is not None else None
            control_rows.append({"task_id": task_id, "eligible": eligible,
                                 "unchanged_dropped_minus_retained": unchanged_gap,
                                 "updated_dropped_minus_retained": row["difference"],
                                 "update_minus_unchanged": row["difference"] - unchanged_gap
                                 if row["difference"] is not None and unchanged_gap is not None else None})

    primary = _population([row for row in rows if row["eligible"]], "single_initial_correct")
    secondary = _population(rows, "all_assigned_problems")
    domains = Counter(task.get("domain") for task in tasks)
    controls = Counter(task.get("domain") for task in tasks if task.get("unchanged_control"))
    schedule_ids = [call["call_id"] for call in schedule]
    task_ids = [task["task_id"] for task in tasks]
    shape_valid = (len(tasks) == 24 and domains == {"math": 12, "coding": 12}
                   and controls == {"math": 4, "coding": 4} and len(schedule) == 200
                   and len(set(schedule_ids)) == len(schedule_ids) and len(set(task_ids)) == len(task_ids))
    for task in tasks:
        for condition in CONDITIONS:
            calls = assignments.get((task["task_id"], condition), [])
            expected = 1 if condition == "initial" else (2 if condition.startswith("unchanged") and task.get("unchanged_control") else 0 if condition.startswith("unchanged") else 2)
            if len(calls) != expected or len({call.get("sample") for call in calls}) != len(calls):
                shape_valid = False
    if any(call["condition"] not in CONDITIONS or call["task_id"] not in task_ids for call in schedule):
        shape_valid = False
    unexpected_ids = sorted(set(indexed) - set(schedule_ids))
    complete = (bool(schedule) and all(_available(indexed.get(call["call_id"])) for call in schedule)
                and not duplicate_outcomes and not unexpected_ids)
    source_ready = not manifest.get("blockers") and manifest.get("source_qualified", False) is True
    criteria = {
        "frozen_design_valid": shape_valid,
        "source_qualified": source_ready,
        "at_least_18_initial_correct": len(eligible_ids) >= 18,
        "fresh_accuracy_at_least_75_percent": primary["fresh_accuracy"] is not None and primary["fresh_accuracy"] >= 0.75,
        "gap_at_least_10_percentage_points": primary["dropped_minus_retained"] is not None and primary["dropped_minus_retained"] >= 0.10,
        "one_sided_p_at_most_point10": primary["one_sided_p"] is not None and primary["one_sided_p"] <= 0.10,
        "complete_required_valid_outcomes": complete,
    }

    def control_summary(selected: list[dict]) -> dict:
        ready = bool(selected) and all(row["update_minus_unchanged"] is not None for row in selected)
        return {"n_problems": len(selected), "complete": ready,
                "unchanged_dropped_minus_retained": sum(row["unchanged_dropped_minus_retained"] for row in selected) / len(selected) if ready else None,
                "update_minus_unchanged": sum(row["update_minus_unchanged"] for row in selected) / len(selected) if ready else None,
                "per_problem": selected}

    positive = all(criteria.values())
    inconclusive = not (shape_valid and source_ready and complete and len(eligible_ids) >= 18)
    return {"decision": "continue_on_new_held_out_cases" if positive else "inconclusive" if inconclusive else "continuation_gate_not_met",
            "continuation_gate_passed": positive, "criteria": criteria,
            "primary": primary, "secondary": secondary,
            "unchanged_controls": {"all_preselected": control_summary(control_rows),
                                   "initial_correct": control_summary([row for row in control_rows if row["eligible"]]),
                                   "interpretation": "Descriptive only; eight controls cannot establish absence of a general retention effect."},
            "availability": dict(availability), "returned_classifications": dict(classifications),
            "required_responses": len(schedule), "missing_call_ids": missing_ids,
            "protocol_invalid_call_ids": protocol_invalid_ids, "duplicate_outcome_call_ids": duplicate_outcomes,
            "unexpected_outcome_call_ids": unexpected_ids,
            "uncertainty": {"method": "problem-level percentile bootstrap", "seed": BOOTSTRAP_SEED,
                            "replicates": BOOTSTRAP_REPEATS, "interval": 0.95},
            "assumptions": ["Independent problem units; both repeats remain together.",
                            "Retained/dropped labels are exchangeable within a problem under the sign-flip null.",
                            "No post-treatment filtering; incomplete populations receive no paired effect estimate.",
                            "Returned truncations and invalid answers are unsuccessful operational responses, not semantic stale-reasoning errors.",
                            "Old-answer matching is not proof of a retained-reasoning mechanism.",
                            "This exploratory gate is not publication evidence; any confirmation requires new held-out cases."]}
