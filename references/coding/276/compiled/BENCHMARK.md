# Construction benchmark policy and record

The construction limits were fixed before timing runs:

- One CPU and2GiB RAM.
- At most600 seconds per invocation (therefore also per case), and1800 seconds
  total for measurement and gold generation, including independent checks.
- Pinned compiler image
  `gcc@sha256:5e927c284bf55a7dc796262e311a0703344f62f41f5621eb56843111b1d37e15`.
- GCC14.3.0 on arm64, C++17 with optimization; exact command is recorded with
  each run. No host compilation or generated-code execution.
- No concurrent heavy reference jobs during the initial scaling measurement.

The first submitted source is `reference.cpp`, SHA256
`3628ae7ebbeba3f413128bd78adb41de071d943ce445d59788e5de11faf07324`.
Source changes after a run require a new checksum and repetition of affected
checks. These offline construction limits do not change the candidate grading
timeout, memory limit, test corpus, or input domain.

Asymptotic complexity is unchanged: cubic time and quadratic storage. Successful
generation for the complete retained finite suite would establish its exact
initial expected outputs, not demonstrate practical performance at N=300000.
That maximum-size claim is neither required nor made by this constructor.

## Measured construction and verification campaign

The unchanged source above compiled successfully with
`-std=c++17 -O3 -DNDEBUG -Wall -Wextra`. The root runner recorded these successful
invocations in `construction_campaign.json`:

| Invocation | Inputs | Host wall time, including compilation and cleanup |
| --- | ---: | ---: |
| Initial compiled smoke |4|1.170083 seconds|
| Fixed scaling batch |6|8.532571 seconds|
| Complete retained initial corpus |205|17.123974 seconds|
| Independent split-or-enclose implementation, complete corpus |205|130.221445 seconds|
| Literal-deletion oracle cases, automatic arithmetic |12,142|1.455998 seconds|
| Same literal-deletion cases, forced exact limb arithmetic |12,142|0.990678 seconds|

The complete corpus contains all43 released inputs and all162 retained independent
initial fixtures. No input was dropped or reduced. Each invocation returned
exactly one answer per input with exit0; source, input-list, output-list, compiler,
and policy checksums are recorded. All162 outputs for the existing independent
fixtures exactly match their previously recorded expected values. The full-corpus input-list SHA256 is
`03a02db5fb03453376ca6d384ab8e5ceaefda782c4c15fb01b180b518a4dd6b0`;
its output-list SHA256 is
`d5bfb4f846e9b4704447a8dcb01245e55aa220badec6b93f09cfb87448a73a6a`.
The first three invocations used26.826628 seconds. The complete campaign, including
all six compiled invocations and both independent Python-oracle executions,
used **160.689484 seconds of the1800-second limit**. Both successful and failed
attempts would be charged; all recorded attempts in this campaign succeeded.

The deterministic scaling batch reports the following per-case measurements.
These times exclude compilation, and every case used the checked uint64 path.

| N | Exact partner evaluations | Case seconds |
| ---: | ---: | ---: |
|256|707,264|0.000429542|
|512|5,625,216|0.003134292|
|1024|44,870,400|0.024725666|
|2048|358,438,400|0.194702292|
|4096|2,865,409,024|1.88222621|
|4736|4,428,930,784|5.48273167|

The largest scaling case completed far below the600-second invocation limit.
The table reports observed results only; it is not an extrapolated guarantee for
larger inputs. The independent square-table implementation uses a different
split-or-enclose recurrence and matches every one of the205 full-corpus outputs.
The12,142 literal current-adjacency cases match in both automatic and forced
exact arithmetic modes, including signed and80-digit inputs and machine-word
boundaries. The literal oracle uses no interval recurrence. Together with the
162 previously retained exact fixtures, these checks cover the earlier9,999
small-case validation and additional arithmetic cases.

`construction_campaign.json` records status `reference_construction_verified`
and `within_uniform_budget: true`. No feasibility exclusion, resource-limit
amendment, removed test, or paid model call was needed. The separate independent
review is in `INDEPENDENT_REVIEW.md`; immutable gold outputs and their source/input
bindings are in `gold_outputs.json`.
