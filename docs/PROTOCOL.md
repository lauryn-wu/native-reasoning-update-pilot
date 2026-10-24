# Frozen protocol v1 — exploratory feasibility screen

Question: Does retaining a model's previous native reasoning impair adaptation to a legitimate subsequent correction, beyond the influence of its previous visible answer?

This is an exploratory screen. It cannot establish a mechanism, dependency-propagation failure, publication-level novelty, or a reliable general effect. Retained reasoning, stale conclusions, and dependency-aware invalidation are not claimed as new. See SOURCE_AUDIT.md for the paper and related work. Passing the gate authorizes scientific consideration of confirmation on NEW held-out cases; it is not publication evidence.

## Adaptation and feasibility

The source paper interrupts ongoing reasoning. This pilot instead completes an initial response and adds an ordinary correction in a new user turn. Its outcomes must never be presented as a replication of the paper's reported failure rate. “Late interruption” describes a generation-time setting, not an intrinsic task attribute.

The source's `revised_problem` is our initial problem; its `original_problem` is our updated target. The source's `original_answer` does not grade our initial problem. The pinned release has zero fully qualified pairs for this design. The v1 manifest is therefore a frozen **blocked protocol**, not a frozen 24-case runnable experiment. No pilot IDs, controls, prompts, answers, tests, or 200-call schedule have been fabricated. A ranked review inventory preserves all 401 released candidates and provenance. Any repaired source basis requires independently audited assets and a NEW manifest version before any payment, including smoke.

## Selection fixed before outputs

Target: 24 distinct original identities, 12 AIME 2024/2025 and 12 LiveCodeBench-derived coding problems. Require unambiguous complete prompts, authoritative original and updated graders, and demonstrated changed answers/behavior. Deduplicate normalized original problem text and source identities. No task may be chosen from our model's outputs, failures, or corrected initial retries.

The deterministic rule prioritizes published coding difficulty (hard, medium, easy). AIME has no released per-item difficulty and therefore ties at that stage; do not invent difficulty values. Among ties, prefer smaller token changes, then SHA256(seed:task_id). Seed is 20261024. Small edit size is only a review preference, not proof of consequential, unambiguous updates. Select the first 12 qualified tasks per domain; never fill missing places with unqualified tasks. Choose four unchanged controls per domain by SHA256(seed:control:task_id). The first qualified unselected original provides the separate smoke task. Store full prompts, graders, references, source revisions, task hashes, controls, and schedule when qualification becomes possible.

## Calls and intervention

Each problem gets one authentic initial solve. Both samples of every continuation independently replay the SAME initial checkpoint, whether or not its visible answer was correct. There is no resampling to obtain correct initials. Planned counts:

| Type | Calls |
| --- | ---: |
| Initial | 24 |
| Updated retained, two/problem | 48 |
| Updated dropped, two/problem | 48 |
| Fresh updated, two/problem | 48 |
| Unchanged retained, two/eight controls | 16 |
| Unchanged dropped, two/eight controls | 16 |
| Total planned | 200 |

Smoke consists of exactly three assigned calls on a separate problem: initial, updated retained, updated dropped. Transport attempts are additional, labeled by stable call ID and explicit attempt (1 or 2), and share the same $40 cap. A missing checkpoint may make dependent outcomes unavailable; it never permits constructing a fake checkpoint.

Model is `gpt-6.1-sol`, Standard tier (`service_tier: default`), high effort, standard reasoning mode, maximum output 32,768. No temperature/top-p or other sampling overrides. Responses API uses `store: false`, `truncation: disabled`, encrypted reasoning inclusion, and complete manually replayed output items, including assistant phases. Never use `previous_response_id`. Never alter earlier messages, force-close reasoning, prefill thoughts, or prevent fresh reasoning.

The retained/dropped request pair is identical except `reasoning.context`: `all_turns` versus `current_turn`. Both contain every available initial output item, visible answer, and the same correction. The correction is an ordinary user message. Fresh receives the complete updated problem with no prior answer/history. Unchanged uses an identical neutral repeat request in both retention conditions. Verify returned effective context, effort, mode, service tier, model, usage, and usable initial encrypted reasoning. Missing/mismatched manipulation is a protocol failure, never evidence for or against retention.

A seeded random topological schedule interleaves conditions: draw uniformly from ready assignments, releasing a task's continuations once its initial assignment has been scheduled. Schedule does not depend on correctness. Record intended schedule and actual ledger order, UTC timestamps, returned model, usage, stop status, and request configuration.

## Grading and qualification

Math uses exact rational/integer equivalence with strict final-answer extraction, without executing symbolic input. Coding uses authoritative stdin/stdout tests in digest-pinned Docker containers only. Unsupported calling conventions or missing tests block qualification; they are not quietly converted to weaker tests. No LLM judge. No generated or released reference solution executes on the host.

Sandbox: no network, no credentials, unprivileged UID/GID 65534, read-only root, bounded CPU, RAM, PIDs, wall time and captured output, no Docker socket, read-only submission mount. Tests and reference expected outputs stay on the host and are never mounted into the container. Host code compares returned output. No host fallback. Qualification includes correct, wrong, equivalent, stale, timeout, output flooding, and isolation fixtures; these fixtures test software and are never candidate pilot tasks.

Before payment, qualify both variants and their references, demonstrate update behavior change (including cross-grading stale solutions), check duplicate originals, audit graders, and validate provider/replay with mocks. Software Docker qualification does not establish dataset validity. Required gates are separate and bound to the exact manifest hash.

Statuses are correct, incorrect, old_answer_match, truncated_no_answer, invalid_output, provider_failure, protocol_failure, budget_stopped, or unassigned. Returned truncations and invalid answers count as zero operational accuracy. Provider/protocol failures and unassigned calls are availability failures and cannot silently become semantic errors. Old-answer matching alone does not identify a reasoning mechanism.

## Analysis and decision

Primary population: problems whose one initial response passes that problem's INITIAL/ORIGINAL grader. Eligibility precedes the retention intervention and never depends on retained, dropped, or fresh outcomes. Require at least 18 eligible problems. Also report all 24 assigned problems as secondary; never select only complete or favorable cases within an analysis population.

For each eligible problem, average its two dropped accuracies and its two retained accuracies, then subtract retained from dropped. The primary effect is the mean of these task-level differences. Problems, not samples, are independent units.

Exact one-sided sign-flip inference keeps each problem's repeats together. Multiply half-step differences by two; use a dynamic-programming integer convolution over independent plus/minus signs and count signed sums at least the observed sum, including ties. Zero differences do not affect the distribution. This tests an exchangeable/symmetric paired-effect null: retention labels must be exchangeable within problems under the null, and problem units must be independent. Randomized execution order alone does not establish that assumption. Report the exact p-value, task effects, raw rates, and a descriptive 95% percentile bootstrap resampling whole problems (10,000 replicates, seed 20261024). This small selected set does not support broad population claims.

All of these must hold for the preliminary continuation gate: at least 18 eligible; fresh updated accuracy >=75% across both samples on those SAME eligible problems; mean dropped-minus-retained >=10 percentage points; one-sided p<=0.10; source-qualified frozen design, valid manipulation, and complete required outcomes. Otherwise report inconclusive for insufficient eligibility or incomplete/invalid campaigns, or gate not met for a complete valid campaign. Do not inspect sequentially and change thresholds. The former “four discordances versus one” rule is not implemented.

Report unchanged dropped-minus-retained and update-minus-unchanged within the same control problems descriptively, for all eight and the initially-correct subset. Eight controls cannot establish absence of a general retention effect.

## Budget and recovery

One persistent SQLite ledger in `runs/budget.sqlite` spans smoke, retries, campaigns, and manifest versions. Hard cap: $40. Never delete/reset it to obtain more budget. Atomic immediate transactions, FULL durability, and a process file lock prevent concurrent overspending. Dispatch first reserves worst-case cost. Uncertain interrupted/transport attempts retain their full reservation; at most one transport retry is allowed and separately reserved. Refusals, incorrect answers, truncations, and ordinary API rejections receive no scoring retries. Resume skips completed calls. The ledger preserves requests/responses privately and provides authoritative checkpoints.

Pricing checked 2026-10-24 in official docs: per million tokens Standard input $2, cached input $0.10, 30m writes $2.50, 12h writes $5, output $10. No unrelated-provider cache factors. Explicit 30m cache mode with no breakpoints disables caching; unexpected cache usage invalidates the protocol. For reservation, use the worst supported input write rate ($5), plus maximum output. Conservative input bound is UTF-8 request bytes plus all prior output tokens plus 4096 framing tokens and 64 per input item; this includes ciphertext bytes and hidden-reasoning token allowance. Reject bounds exceeding 272,000 to avoid the long-context price tier. Actual output usage already includes reasoning, which must not be double charged. Unreported usage retains the maximum reservation; exceeding a reservation halts future dispatch.

The 200-call maximum output alone costs $65.536; the smoke maximum output alone adds $0.98304. Therefore $40 does not guarantee completion. Budget stopping yields an incomplete/inconclusive campaign. No silent cap increase or per-version budget reset.

## Freezing and private artifacts

Manifest content, data, schedule, source/provenance files, model settings, pricing, protocol, and implementation receive SHA256 hashes. Loading checks all hashes and the implementation file set. Any change after smoke requires a new immutable manifest version and requalification/smoke within the SAME cap. Frozen files are never overwritten by the CLI.

Ignore credentials, environments, downloaded datasets/models, raw paid traces, encrypted reasoning, result archives, and the ledger. Review archives use an explicit allowlist and exclude raw response/checkpoint data. The repository contains software, provenance, small metadata inventories, and a blocked manifest, not unlicensed bulk benchmark data.
