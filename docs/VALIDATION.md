# Validation record — 2026-10-24 qualification update

No paid model call was made. Real provider behavior, the three-call smoke, and
the 200-response campaign remain untested and explicitly blocked. Reference
construction and software checks are not experimental outcomes.

The review covers **22 math candidates** (14 verified references, 8 exclusions)
and **64 coding candidates** (21 verified references, 42 exclusions, 1 pending).
The deterministic resolved prefix supports **12 math + 9 coding**, a **3-coding
shortfall**. Candidate 276 remains pending at one-based coding rank 45. Its exact
minimum solver is not adequate for the full released suite. No new 24-case
manifest or smoke/control assignment has been frozen.

## Checks actually performed

- Source acquisition and checksum audit: 43 pinned source artifacts; 1,401 released
  rows parsed; 401 AIME/LiveCodeBench candidates retained in the unchanged order.
- All 14 complete math references: exact derivations, independent review, and
  correct/equivalent/wrong/stale grading checks. Eight exclusions have specific
  contradictions or ambiguities and independent reviews.
- The trigonometric pair: outward-rounded integer interval certification gives
  1,244 initial and 385 updated intersections, with no unresolved intervals.
  Independent higher precision and asymmetric subdivision reproduce both counts.
- Coding: all 21 completed reference pairs have proof-based implementations,
  pinned upstream matching, full published-input validation, and independent
  exact tests. Test construction and every reference/oracle execution used
  Docker. Per-case evidence is bound from `provenance/coding_review.json`.
- An erroneous upstream label for candidate 258 is retained and explicitly
  corrected after the published theorem and a separate 7,714-state exact minimax
  agree. No test input is removed or silently relabeled.
- Candidate 276: 9,999 exact small checks validate the initial interval recurrence;
  its updated maximum reference passes all 43 published files. Full initial
  validation is **not complete**: the largest published input has 4,736 items,
  requiring 4,428,930,784 partner transitions for the known cubic algorithm.
- Docker function adapter: correct/tuple-equivalent results accepted; wrong,
  self-asserted-pass and boolean-as-number results rejected. Expected answers
  remain outside the container. The original targeted command and output are
  retained in `references/coding/function_adapter_validation_recovered.json`.
- Final small stdin adapter follow-up: three fresh Python subprocesses/work
  directories with `sys.exit(0)` pass; self-asserted-pass output fails. See
  `references/coding/stdin_adapter_validation.json`.
- The final offline suite passed **116 tests**. This includes bounded batch
  retention, exact algebraic grading, source/evidence integrity, unchanged
  review order, paid-execution holds, and infrastructure-deadline classification.
  The full log is `REFERENCE_UNIT_TESTS.txt`; the consolidated record is
  `REFERENCE_QUALIFICATION.json`.

## Reproducibility and observed failures

The first complete asset-reconstruction rerun failed during Docker execution.
The broader live stdin attempt also observed Docker latency and cleanup-command
failure; its actual failed outputs are retained separately. Cleanup now kills the
Docker client even if removal times out and reports infrastructure unavailability.
The container-side hard deadline remains bounded; there is no host fallback.
A separate small live retry passed. A reconstruction retry reached candidate 167
before a timeout. Reference-construction batches now also have an eight-case
bound, retaining every input and its order. The subsequent reconstruction
**passed for all 21 coding pairs**, reproducing both variants’ reviewed fixture
hashes in 135.581 seconds. Its result and previous failures are retained in
`references/coding/asset_rebuild_validation.json`.

The full final integrated 35-candidate grader qualification has **not been
completed**. This is separate from the completed proofs, reference executions,
asset reconstruction, and targeted adapter checks. Its status is recorded in
`REFERENCE_QUALIFICATION.json`. The ordered campaign qualification remains
blocked by candidate 276 regardless of that integration result.

The prior 76-test/17-Docker-check baseline remains in `OFFLINE_QUALIFICATION.json`
and `DOCKER_QUALIFICATION.json`. Those historical checks do not claim to validate
later adapters. Current runtime is Python 3.12.13 on macOS arm64, Docker 29.8.2,
with the image pinned in `sandbox/runner.py`. The host only parses data, compares
outputs, and runs the trusted harness; submitted/reference/oracle code runs only
inside Docker.

## Commands for this checkout

```sh
../../work/provider/venv/bin/python -m unittest discover -s tests -v
../../work/provider/venv/bin/python -m native_pilot prepare-upstream --cache ../../work/source-cache
../../work/provider/venv/bin/python -m native_pilot review --cache ../../work/source-cache
../../work/provider/venv/bin/python -m native_pilot --asset-cache ../../work/source-cache qualify-reviewed --docker
```

On a clean checkout use the virtual environment and default cache commands in
README. `qualify-reviewed` validates completed candidate references; it cannot
skip 276, freeze a complete sample, or authorize a paid call. A scalable exact
initial reference for 276, independent review, and full retained-suite validation
are required before selection can continue. The explicit user hold must remain
in force throughout this work.
