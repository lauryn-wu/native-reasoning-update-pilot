"""Frozen assignments: no selection or scheduling uses model outcomes."""
from collections import Counter
import random
import hashlib

SEED = 20261024
BRANCHES = ("updated_retained", "updated_dropped", "fresh")
CONTROL_BRANCHES = ("unchanged_retained", "unchanged_dropped")


def make_schedule(tasks, seed=SEED):
    """Random topological order, selecting uniformly among currently ready calls."""
    rng = random.Random(seed)
    ready = [{"call_id": f"{t['task_id']}/initial/0", "task_id": t["task_id"],
              "condition": "initial", "sample": 0} for t in sorted(tasks, key=lambda t: t['task_id'])]
    by_id = {t["task_id"]: t for t in tasks}
    if len(by_id) != len(tasks):
        raise ValueError("Duplicate task IDs")
    schedule = []
    while ready:
        row = ready.pop(rng.randrange(len(ready)))
        schedule.append(row)
        if row["condition"] == "initial":
            tid = row["task_id"]
            branches = BRANCHES + (CONTROL_BRANCHES if by_id[tid].get("unchanged_control") else ())
            ready.extend({"call_id": f"{tid}/{branch}/{sample}", "task_id": tid,
                          "condition": branch, "sample": sample}
                         for branch in branches for sample in (1, 2))
    return schedule


def original_identity(task):
    return task.get('original_identity') or task.get('original_id') or hashlib.sha256(
        ' '.join(task['original_prompt'].split()).encode()).hexdigest()


def validate_design(tasks, schedule):
    if len(tasks) != 24 or Counter(t["domain"] for t in tasks) != {"math": 12, "coding": 12}:
        raise ValueError("Need exactly 12 math and 12 coding distinct originals")
    if Counter(t["domain"] for t in tasks if t.get("unchanged_control")) != {"math": 4, "coding": 4}:
        raise ValueError("Need eight controls balanced 4+4")
    originals = [original_identity(t) for t in tasks]
    if len(set(originals)) != 24:
        raise ValueError("Duplicate original problems")
    expected = {r["call_id"]: r for r in make_schedule(tasks)}
    if len(schedule) != 200 or {r["call_id"]: r for r in schedule} != expected:
        raise ValueError("Incorrect assignments or repeats")
    seen = set()
    for row in schedule:
        if row["condition"] != "initial" and row["task_id"] not in seen:
            raise ValueError("Continuation precedes its initial checkpoint")
        seen.add(row["task_id"])
