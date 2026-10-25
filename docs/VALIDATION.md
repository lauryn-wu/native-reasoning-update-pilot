# Validation record — compiled reference qualification

This records the completed v2 qualification: no paid model call was made during
that work, and its policy held smoke, pilot and retries. V3 later receives only
the explicit smoke authorization documented in `SMOKE_V3.md`; the pilot remains
blocked. `SMOKE_V3_QUALIFICATION.json` records current checks and evidence reuse,
and `SMOKE_V3_RESULT.json`, when present, records actual smoke status.

The source review covers 22 math candidates and 64 coding candidates. Fourteen
math and 22 coding pairs have verified references; eight math and 42 coding
candidates have documented exclusions. Candidate 276 is resolved by compiled
exact finite-suite reference construction, without excluding it or changing its
statement, correction, ordering, published inputs, or submitted-program limits.
The unchanged selection supplies 12 math + 12 coding pairs and separate smoke
case `livecodebench:337`. Exact IDs are in the audit and frozen manifest.

## Candidate 276 evidence

- The exact cubic recurrence, noncrossing-matching argument and old Python
  implementation are preserved. The compiled source is independently reviewed
  for indexing, odd survivors, checked 64-bit arithmetic and arbitrary-precision
  fallback. No asymptotically faster algorithm or full-domain runtime claim is made.
- Scaling is measured inside pinned GCC Docker at N=256,512,1024,2048,4096,4736.
  The six-case scaling batch takes 8.533 seconds. All 43 published inputs plus
  all 162 retained independent inputs produce exact initial gold in 17.124 seconds.
- A separately authored square-table split-or-enclose DP reproduces all 205 gold
  outputs in 130.221 seconds. All 162 previously stored initial answers agree.
- Both automatic arithmetic and forced arbitrary precision match 12,142 literal
  current-adjacency oracle cases, including exhaustive ternary sequences through
  length eight, signed inputs, odd survivors and large-integer boundaries.
- The construction campaign uses 160.690 seconds of its 1800-second budget,
  including compilation, scaling, generation, oracle execution and independent
  verification. Each invocation has a 600-second bound, one CPU and 2 GiB memory.
  Submitted-program limits are unchanged. No reference-feasibility exclusion
  amendment is applied.
- Immutable gold binds every ordered input, output, full test suite, source,
  compiler image/flags, budget policy and independent review. All executable
  reference/oracle work occurs inside Docker; expected answers stay on the host.

Detailed evidence is in `references/coding/276/compiled/`, especially
`construction_campaign.json`, `gold_outputs.json`, `certificate.json`,
`INDEPENDENT_REVIEW.md`, and `BENCHMARK.md`.

## Integrated grading and freeze

`provenance/integrated_qualification.json` is the immutable v2 integrated
run record. It records the actual offline test count and log, Docker isolation
checks, and complete correct/equivalent/wrong/stale checks for the 24 selected
pairs and separate smoke case. Candidate 276's initial reference is freshly
replayed under construction resources; its returned outputs use the same exact
stdin comparator as submissions. Its updated Python reference executes under
unchanged candidate limits against both full suites. It is never replaced by a
lookup-table submission or credited as a fast Python solution.

Freezing requires every expected check to be true and binds the exact audit,
implementation and required task IDs. Missing, stale, incomplete or failing
qualification cannot produce a source-qualified manifest. The paid hold remains
false in policy and manifest, regardless of passing qualification. A research
report without paid outcomes remains inconclusive.

The provider enforces the explicit hold before accepting any client and again
before every dispatch. Offline SDK tests patch only the private policy reader
and use mocked transport. Regression checks cover injected clients and a hold
reinstated after client construction. The interrupted integration attempt that
prompted this fix is preserved in `INTEGRATED_QUALIFICATION_ATTEMPTS.json` and
`INTEGRATED_QUALIFICATION_INTERRUPTED.txt`; it is not a passing qualification. A second serial attempt was superseded by
bounded parallel offline qualification; its log is separately preserved.
Parallelism runs at most four independent task checks at once, retains every
input and check, and preserves per-container limits and deterministic aggregation.
It does not change task selection or the frozen experimental call schedule.

The historical source-only and pre-compiled checks remain in
`OFFLINE_QUALIFICATION.json`, `DOCKER_QUALIFICATION.json`,
`REFERENCE_QUALIFICATION_PRE_COMPILED.json`, and
`HISTORICAL_VALIDATION_PRE_COMPILED.md`. Earlier Docker reconstruction failures
and successful retries remain recorded. They are not relabeled as candidate
model failures or erased by the later successful construction.

## Reproduction in this checkout

```sh
../../work/provider/venv/bin/python -m unittest discover -s tests -v
../../work/provider/venv/bin/python -m native_pilot prepare-upstream --cache ../../work/source-cache
../../work/provider/venv/bin/python -m native_pilot review --cache ../../work/source-cache
../../work/provider/venv/bin/python -m native_pilot --asset-cache ../../work/source-cache qualify-reviewed --selected-only --docker --workers 4
```

The setup commands in README use a normal project virtual environment and default
cache. The frozen manifest binds its integrated qualification record; modifying
any bound code, evidence or provenance requires a new version and requalification.
No command here makes a paid call or removes the hold.
