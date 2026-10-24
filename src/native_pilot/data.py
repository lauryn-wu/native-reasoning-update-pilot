"""Pinned, non-executing source acquisition and fail-closed dataset qualification.

The source's ``revised_problem`` is the pilot's *initial* problem. Its update
returns to ``original_problem``. Never mistake ``original_answer`` for an
answer to the initial problem. The pinned release cannot qualify this design.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import urllib.request
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

SEED = 20261024
ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "provenance/source_lock.json"
SELECTION_RULE = {
    "version": 1,
    "seed": SEED,
    "population": "AIME 2024/2025 only, plus LiveCodeBench-derived coding rows",
    "ranking": [
        "Published coding difficulty: hard, medium, easy; AIME rows tied because no per-item difficulty is released",
        "Ascending changed-token count between source revised and original prompts, including starter code",
        "SHA256 of seed:task_id as stable tie-break; no model outputs are consulted",
    ],
    "qualification": "Both initial and updated graders, changed answer/behavior evidence, and unambiguous complete prompts must pass before selection",
    "deduplication": "Whitespace-normalized source original prompt SHA256 plus source identity; reject duplicate originals",
    "controls": "Four per domain using SHA256 of seed:control:task_id among selected tasks",
    "smoke": "First qualified unselected candidate in the same frozen ranking; separate original identity",
}


class SourceBlocked(ValueError):
    """The public release cannot satisfy the frozen design."""


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _load_lock(lock_path: Path | str = LOCK_PATH) -> dict:
    return json.loads(Path(lock_path).read_text())


def _safe_path(cache: Path, relative: str) -> Path:
    target = (cache / relative).resolve()
    if not target.is_relative_to(cache.resolve()):
        raise SourceBlocked("Source artifact path escapes cache")
    return target


def verify_sources(cache_dir: Path | str, lock_path: Path | str = LOCK_PATH) -> dict:
    cache = Path(cache_dir)
    failures = []
    checked = 0
    for item in _load_lock(lock_path)["artifacts"]:
        target = _safe_path(cache, item["path"])
        if not target.is_file():
            failures.append(f"Missing pinned artifact: {item['path']}")
        elif target.stat().st_size != item["bytes"] or _file_hash(target) != item["sha256"]:
            failures.append(f"Checksum mismatch: {item['path']}")
        else:
            checked += 1
    return {"verified": not failures, "checked_artifacts": checked, "blockers": failures}


def prepare_sources(cache_dir: Path | str, lock_path: Path | str = LOCK_PATH) -> dict:
    """Download exact pinned public bytes, never execute/import upstream code.

    Existing valid files are reused. Corrupt cached files cause a hard failure;
    acquisition never silently replaces evidence. No tokens or credentials used.
    """
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    for item in _load_lock(lock_path)["artifacts"]:
        target = _safe_path(cache, item["path"])
        if target.exists():
            if target.stat().st_size != item["bytes"] or _file_hash(target) != item["sha256"]:
                raise SourceBlocked(f"Checksum mismatch: {item['path']}; remove corrupt cache file explicitly")
            continue
        if not item["url"].startswith("https://"):
            raise SourceBlocked("Only HTTPS public-source acquisition is allowed")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".download-", dir=target.parent)
        try:
            request = urllib.request.Request(item["url"], headers={"User-Agent": "native-reasoning-update-pilot-source-audit/1"})
            with os.fdopen(fd, "wb") as stream, urllib.request.urlopen(request, timeout=60) as response:
                remaining = item["bytes"] + 1
                while remaining:
                    chunk = response.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    stream.write(chunk)
                    remaining -= len(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            path = Path(temporary)
            if path.stat().st_size != item["bytes"] or _file_hash(path) != item["sha256"]:
                raise SourceBlocked(f"Downloaded bytes differ from lock: {item['path']}")
            os.replace(path, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return verify_sources(cache, lock_path)


def _read_rows(cache_dir: Path | str) -> tuple[list[dict], list[dict]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SourceBlocked("Install the pinned data extra: python -m pip install '.[data]'") from exc
    cache = Path(cache_dir)
    return (pq.read_table(cache / "data_math.parquet").to_pylist(),
            pq.read_table(cache / "data_code.parquet").to_pylist())


def normalized_original_hash(row: dict) -> str:
    # Prompt identity is intentionally independent of revised wording or row ID.
    text = " ".join(row["original_problem"].split())
    return hashlib.sha256(text.encode()).hexdigest()


def changed_token_count(row: dict) -> int:
    original = row["original_problem"] + "\n" + row.get("original_starter_code", "")
    revised = row["revised_problem"] + "\n" + row.get("revised_starter_code", "")
    left = re.findall(r"\w+|[^\w\s]", original)
    right = re.findall(r"\w+|[^\w\s]", revised)
    return sum(max(b-a, d-c) for tag, a, b, c, d in SequenceMatcher(None, left, right, autojunk=False).get_opcodes() if tag != "equal")


def _candidate(row: dict, domain: str) -> dict:
    source = row.get("source", "livecodebench")
    task_id = f"{source}:{row['id']}"
    return {
        "task_id": task_id,
        "domain": domain,
        "source_id": row["id"],
        "source": source,
        "source_row_sha256": canonical_hash(row),
        "original_identity": normalized_original_hash(row),
        "source_original_prompt_sha256": hashlib.sha256(row["original_problem"].encode()).hexdigest(),
        "source_revised_prompt_sha256": hashlib.sha256(row["revised_problem"].encode()).hexdigest(),
        "correction_prompt_sha256": hashlib.sha256(row["update"].encode()).hexdigest(),
        "published_difficulty": row.get("difficulty"),
        "changed_tokens": changed_token_count(row),
        "qualified": False,
        "qualification_blockers": (["No released reference answer for pilot initial/source revised problem"] if domain == "math" else ["No released tests for pilot initial/source revised behavior", "Original LCB tests require separate upstream acquisition and matching"]),
    }


def rank_candidates(candidates: list[dict], seed: int = SEED) -> list[dict]:
    """Stable prospective review ordering; ranking does not imply qualification."""
    difficulty = {"hard": 0, "medium": 1, "easy": 2, None: 0}
    return sorted(candidates, key=lambda c: (
        c["domain"], difficulty[c.get("published_difficulty")], c["changed_tokens"],
        hashlib.sha256(f"{seed}:{c['task_id']}".encode()).hexdigest(),
    ))


def audit_sources(cache_dir: Path | str, lock_path: Path | str = LOCK_PATH) -> dict:
    """Recompute structural audit over actual release; zero qualified tasks.

    No schema-presence check can certify semantic correctness. The pinned
    release lacks required initial graders, so this adapter cannot unblock it.
    """
    verified = verify_sources(cache_dir, lock_path)
    if not verified["verified"]:
        return {"schema_version": 1, "status": "blocked", "paid_execution_allowed": False,
                "qualified_tasks": [], "candidates": [], "blockers": verified["blockers"]}
    math_rows, code_rows = _read_rows(cache_dir)
    aime = [row for row in math_rows if row["source"] in {"aime2024", "aime2025"}]
    candidates = rank_candidates([_candidate(r, "math") for r in aime] + [_candidate(r, "coding") for r in code_rows])
    duplicate_groups = defaultdict(list)
    for candidate in candidates:
        duplicate_groups[candidate["original_identity"]].append(candidate["task_id"])
    unchanged_code = [r["id"] for r in code_rows if r["original_problem"].strip() == r["revised_problem"].strip() and r["original_starter_code"].strip() == r["revised_starter_code"].strip()]
    blockers = [
        f"All {len(aime)} AIME initial/source revised problems lack released reference answers; original-correct eligibility and answer-change validation cannot be certified.",
        f"All {len(code_rows)} coding initial/source revised behaviors lack released executable graders; official LiveCodeBench tests cover the restored/source original task only.",
        "Coding updates also carry withheld constraints, input/output specifications and examples; source original_problem alone is not a certified complete fresh-updated prompt.",
        "Semantic qualification is incomplete: released revisions include impossible initial tasks (AIME ids 1001 and 1026); textual edits alone do not establish genuine answer/behavior changes.",
        "No 12+12 qualified sample, eight controls or disjoint qualified smoke case can be frozen from this pinned release; do not replace them with invented or easier tasks.",
    ]
    return {
        "schema_version": 1, "audit_date": "2026-10-24", "status": "blocked", "paid_execution_allowed": False,
        "source_lock_sha256": _file_hash(Path(lock_path)), "verified_artifacts": verified["checked_artifacts"],
        "planned_composition": {"math": 12, "coding": 12, "unchanged_controls": 8, "separate_smoke_tasks": 1},
        "release_counts": {"math_total": len(math_rows), "math_by_source": dict(sorted(Counter(r["source"] for r in math_rows).items())), "coding_total": len(code_rows), "coding_by_difficulty": dict(sorted(Counter(r["difficulty"] for r in code_rows).items()))},
        "release_schemas": {"math": list(math_rows[0]), "coding": list(code_rows[0])},
        "qualified_counts": {"math": 0, "coding": 0}, "qualified_tasks": [], "smoke_task": None,
        "duplicate_original_groups": [v for v in duplicate_groups.values() if len(v) > 1],
        "coding_unchanged_text_and_starter_ids": unchanged_code,
        "selection_rule": SELECTION_RULE, "candidates": candidates, "blockers": blockers,
        "checks_not_run": ["Initial-reference validation (references absent)", "Updated coding reference execution (tests/references not qualified)", "Per-task stale-code failure validation", "Complete semantic review of all 401 candidate pairs"],
    }


def select_tasks(audit: dict, seed: int = SEED) -> dict:
    """Select only a fully audited pool; never fall back to review candidates."""
    if audit.get("status") != "qualified" or audit.get("blockers"):
        raise SourceBlocked("Source qualification blocked: " + "; ".join(audit.get("blockers", ["not qualified"])))
    pool = rank_candidates(audit.get("qualified_tasks", []), seed)
    selected = []
    identities = set()
    for domain in ("math", "coding"):
        domain_rows = []
        for item in pool:
            if item["domain"] != domain:
                continue
            if not item.get("qualified") or not item.get("qualification_evidence_sha256"):
                raise SourceBlocked("Missing signed-off grader/semantic qualification evidence")
            if item["original_identity"] in identities:
                raise SourceBlocked("Duplicate original problem in qualified pool")
            identities.add(item["original_identity"])
            domain_rows.append(item)
        if len(domain_rows) < 12:
            raise SourceBlocked(f"Need 12 qualified {domain} originals, found {len(domain_rows)}")
        selected.extend(domain_rows[:12])
    chosen_ids = {row["task_id"] for row in selected}
    selected_originals = {row["original_identity"] for row in selected}
    smoke = next((r for r in pool if r["task_id"] not in chosen_ids and r["original_identity"] not in selected_originals), None)
    if smoke is None:
        raise SourceBlocked("No separate qualified smoke original available")
    controls = []
    for domain in ("math", "coding"):
        controls.extend(sorted((r["task_id"] for r in selected if r["domain"] == domain), key=lambda key: hashlib.sha256(f"{seed}:control:{key}".encode()).hexdigest())[:4])
    return {"tasks": [{**row, "unchanged_control": row["task_id"] in controls} for row in selected],
            "control_task_ids": controls, "smoke_task": smoke, "selection_rule": {**SELECTION_RULE, "seed": seed}}
