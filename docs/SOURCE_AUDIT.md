# Source audit — 2026-10-24

> Historical baseline inspection. The later authorized reference-construction
> review is recorded in `provenance/qualification_audit.json`, `MATH_REFERENCES.md`,
> and `CODING_REFERENCES.md`. Its current ordered sample is blocked at coding276;
> the baseline zero-reference findings below are not the current reference count.

The pinned release does **not** support a qualified 12 AIME + 12 coding pilot under this protocol. Paid execution remains blocked. The release supplies 60 AIME pairs and 341 coding pairs, but none has the complete initial-grading evidence required here. No substitute problems, invented updates, inferred answers, or provisional assignments have been inserted into the frozen campaign.

## Revisions and actual inspection

`provenance/source_lock.json` records SHA-256, byte lengths and immutable URLs for 43 downloaded artifacts. All downloaded GitHub text also matched its Git blob SHA. The artifacts include the two actual Parquet files, dataset card, upstream loaders, augmentation scripts and prompts, source inference/prompt handling, mathematical and coding graders, licenses, and four versioned paper HTML files. Source files were read as text; upstream loaders/graders and generated solution code were not imported or executed on the host.

| Source | Pinned revision |
|---|---|
| [interrupt-lrm code](https://github.com/dynamic-lm/interrupt-lrm/tree/b87d61bd2e5e998f34878fb0ee5fb2f5550f98c6) | `b87d61bd2e5e998f34878fb0ee5fb2f5550f98c6` |
| [Update dataset](https://huggingface.co/datasets/dynamic-lm/update-interrupt-benchmark/tree/6ac4ea4baadeccafbb452c1649c90e24ffac4cfc) | `6ac4ea4baadeccafbb452c1649c90e24ffac4cfc` |
| [Upstream LiveCodeBench metadata](https://huggingface.co/datasets/livecodebench/code_generation_lite/tree/0fe84c3912ea0c4d4a78037083943e8f0c4dd505) | `0fe84c3912ea0c4d4a78037083943e8f0c4dd505`, loader's `release_v6` |

The source cache is deliberately untracked. `native-pilot prepare` redownloads only pinned bytes and rejects checksum mismatches; it does not call an augmentation model. `native-pilot audit` uses PyArrow to read Parquet without `trust_remote_code`. The runtime does not deserialize source pickles.

## The naming reversal matters

| Pilot concept | Released field |
|---|---|
| Initial problem, whose first answer determines eligibility | `revised_problem`, plus `revised_starter_code` for coding |
| Subsequent ordinary user correction | `update` |
| Restored mathematical task | `original_problem` |
| Restored mathematical reference | `original_answer` |

The released correction runs **from revised to original**. Reusing `original_answer` to grade the pilot's initial response would apply the wrong grader. Reversing the update would invent a different intervention. Coding additionally withholds constraints, examples and input/output descriptions until the update, so its `original_problem` field alone is not a certified complete fresh-updated prompt. These mappings are supported by the [dataset card](https://huggingface.co/datasets/dynamic-lm/update-interrupt-benchmark/blob/6ac4ea4baadeccafbb452c1649c90e24ffac4cfc/README.md) and the pinned construction scripts.

## Structural findings from all actual rows

| Check | Observed result |
|---|---|
| Math release | 1,060 rows: 500 GSM8K, 500 MATH500, 30 AIME2024, 30 AIME2025 |
| Eligible source families | 60 AIME rows; the easier math families are excluded |
| Coding release | 341 rows: 152 hard, 105 medium, 84 easy |
| Initial/source-revised AIME reference answers | Absent for all 60 |
| Initial/source-revised coding tests/references | Absent for all 341 |
| Coding public/private tests in update release | Absent; dataset card explicitly directs users to upstream LiveCodeBench |
| Per-item AIME difficulty metadata | Absent; no difficulty scores inferred from row order |
| Duplicate source originals after whitespace normalization | None among 401 candidates |
| Coding main statement and starter text both unchanged | 33 rows; listed in `audit.json` |
| Fully qualified pilot pairs | 0 math, 0 coding |

The original LiveCodeBench tests can in principle grade the restored task. Its pinned loader lists public/private tests and function metadata, but no reference implementation field and no grader for the artificial initial behavior. Acquiring those tests cannot by itself fix initial-correct eligibility. Upstream test payloads were not downloaded or claimed executed. Examples embedded in an update are not a replacement for the hidden tests. Unchanged main text likewise does not prove an unchanged task when withheld constraints may matter.

## Concrete semantic counterexamples

These are static mathematical deductions from actual source rows, not model outcomes. Row hashes are in `review_inventory.json`. They demonstrate why release-level human-review claims cannot replace qualification for this completed-response design.

* **AIME2024, id 1001:** the revised triangle has sides 6, 8, 10 with AC the hypotenuse. AC is a diameter of its circumcircle; the tangents at A and C are parallel and cannot meet at the stated point D. The initial geometry is impossible.
* **AIME2024, id 1026:** the revised statement asks for exactly 1,000 finite nonempty sets of positive integers whose minimum belongs to A. For any element a of a nonempty A, the sets `{a,n}` for all n greater than a already give infinitely many such sets. An empty A gives zero. The requested finite positive count is impossible.

The construction prompt asks for four mathematical specification edits, not a uniformly minimal single edit. Coding construction separates main specifications from constraints/examples and can alter both semantics and starter signatures. We have not certified all 401 updates as unambiguous or consequential. Missing graders alone already prevent qualification; examples above are additional evidence.

## Prospective selection rule

Seed: **20261024**. Rank only the AIME family and LiveCodeBench rows, never our model's outcomes. Coding uses the published hard > medium > easy order. AIME rows are tied on difficulty because the release has no per-item difficulty. Within each domain/difficulty tier, prefer fewer changed word/punctuation tokens between source revised/original statements, including starter code; use `SequenceMatcher(autojunk=False)` and sum maximum changed spans. Break ties with SHA-256 of `seed:task_id`. This is an edit-size preference, not evidence of difficulty or behavioral consequence.

`review_inventory.json` records this deterministic ordering for all 401 unqualified candidates using IDs and source/prompt hashes. It is **not a 24-task selection**. Qualification requires complete unambiguous prompts, both graders, independent reference validation and changed-answer/behavior evidence. Only then may the selector take 12 distinct originals per domain, choose four controls per domain by `SHA256(seed:control:task_id)`, and reserve the first disjoint qualified remaining original for smoke. Insufficient qualification raises `SourceBlocked`; no fallback fills the sample.

## Grader audit

Static inspection found that the source math path extracts numeric substrings for AIME2024, uses a greedy boxed-reference pattern, and uses broader symbolic equivalence elsewhere. The substring sanitizer can mistake an expression's final number for the whole answer, so it cannot serve as this pilot's exact grader unchanged. This implementation instead specifies a strict final-answer representation and exact rational comparison, with its own false-positive/false-negative qualification fixtures. Those fixture checks do not validate absent AIME initial references.

The source coding grader accepts Python fences, aligns test data by row ID, decodes some test payloads with `pickle.loads`, compiles/executes candidate code, and compares call results or linewise numeric output. Its reliability guard explicitly warns that it is not a security sandbox. This project does not execute that path on the host, deserialize its pickle payloads, or accept sample tests alone. Coding qualification must use the project's restricted Docker runner and explicit, immutable test assets. Where problem semantics require tolerant numeric comparison or order-insensitive acceptance, exact-output grading must not be asserted sufficient without per-task review.

## Paper adaptation and claim limits

[Are Large Reasoning Models Interruptible? v3](https://arxiv.org/html/2510.11713v3) primarily introduces updates at fractions of an ongoing reasoning trace, with model-specific continuation formatting. Its construction restores a published task after a revised initial problem. This pilot instead waits for a completed response, then sends an ordinary new user correction while replaying native reasoning. It is an adaptation, not replication of the reported interruption failure rate. “Late” describes the source's timing intervention; it is not a task difficulty label.

[Computation, Not Memory v1](https://arxiv.org/html/2610.25760v1) distinguishes generating reasoning at an action from retaining previous reasoning and studies fixed-history reasoning interventions. That distinction directly limits claims that retention effects or reasoning-content effects are novel.

[Dependency-Guided Rollback Repair v2](https://arxiv.org/html/2608.10502v2) studies faulty memories, downstream dependencies, selective invalidation and replay. [Memories That Outlive Their Reasons v2](https://arxiv.org/html/2610.25123v2) studies verdicts whose supporting premises cease to hold and dependency-tethered memory. This pilot measures an operational retention contrast; it does not identify dependency propagation or establish a new mechanism.

## Licensing and remaining work

The update repository and its dataset card declare Apache-2.0; the unmodified code license is included as `provenance/UPSTREAM_APACHE_LICENSE.txt`. Underlying competition problems retain their own provenance. The upstream LiveCodeBench card says only `cc` while its loader says `MIT License`; this discrepancy was recorded, not silently resolved. No underlying question corpus or test payload is redistributed here. Tracked inventory contains only identifiers, hashes and audit metadata.

Unblocking requires a new independently reviewed, versioned set of reference answers/tests for the **existing released revisions**, full coding prompt reconstruction and test matching, verified consequential changes, and a newly frozen manifest. Do not solve these gaps by generating replacement updates, treating benchmark-original answers as initial references, weakening graders, or picking tasks after seeing treatment outcomes. Source qualification and Docker qualification are separate gates.
