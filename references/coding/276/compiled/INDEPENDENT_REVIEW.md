# Independent review of the compiled source276 reference

Reviewer: `grading_analysis`, a separate agent from the reference author. The
reviewed optimized source SHA-256 is
`3628ae7ebbeba3f413128bd78adb41de071d943ce445d59788e5de11faf07324`.
Status: **passed**. Static proof/code review and the independent compiled
cross-comparisons below are complete.
No paid model output contributed to this review.

## Recurrence and odd lengths

A pair removed from the current sequence cannot straddle an index that survives
to the end. Two removed pairs cannot cross: the first of two crossing pairs
would still have one endpoint of the other between its own endpoints. Conversely,
innermost-first deletion realizes every noncrossing perfect matching. The
optimized recurrence enumerates the left endpoint's possible partners at odd
distance, then adds independent inner and right-subinterval optima. Every
subproblem has smaller even length, so the evaluation order is valid.

For odd N, a survivor separates two even-sized sets of removed indices. Its
zero-based position must therefore be even. Summing the prefix and suffix
optima and minimizing across exactly those positions is exhaustive. The code
handles empty sides and N=0 or N=1 without uninitialized scores.

I independently authored `independent_reference.cpp`. It uses a plain N×N table
and the distinct split-or-enclose formulation: either the endpoints are paired,
leaving the inside interval, or the first matching component ends at an even
prefix and separates two submatchings. This does not reuse the optimized packed
storage or its partner-loop indexing. Its checked uint64 arithmetic is sufficient
for the retained finite suite; it explicitly rejects an input whose score bound
exceeds that type instead of silently narrowing it.

The second independent oracle, `independent_oracle_full.py`, does not use an
interval recurrence or a matching theorem. It represents the currently remaining
original indices by a bitmask, tries every adjacent pair in that current order,
and recursively computes both extrema. It imports neither reference. The
12,142 inputs include every positive ternary sequence of lengths 2–8, every binary
extreme-value sequence of lengths 2–9, signed ternary inputs, fixed-seed random
inputs, odd survivors, failed-greedy examples, signed64/unsigned64 boundaries,
and 80-digit signed integers. All expected answers were generated inside pinned
Python Docker in 0.754351 seconds. The earlier 2,305-case generation remains
preserved separately and took 0.440383 seconds.

## Packed storage

For a sequence of length N, row l contains `floor((N-l)/2)` even intervals and
column r contains `floor((r+1)/2)`. Both totals are `floor(N²/4)`. The code checks
the product and offset totals before allocating. A column's allowed left
endpoints all have parity opposite r, so the slot for l is `floor(l/2)`.

For interval length 2p and partner `j=l+1+2k`, the inside interval is in
`row(l+1)[k-1]` when k>0. The right interval is in
`column(r)[floor((l+2)/2)+k]` when k<p-1. The optimized code separately evaluates
k=0 and k=p-1, then every interior k once. Both arrays refer only to previously
computed intervals. Writing the chosen score into both row and column copies
preserves their equality. I found no missing partner, parity error, stale read,
or out-of-bounds index in these formulas.

## Integer correctness

Decimal parsing is exact and supports leading zeros, either sign, and normalized
negative zero. Each base 10^9 limb fits uint32. Addition uses a uint64 temporary
bounded by 2×10^9−1. Subtraction uses an int64 temporary bounded between −10^9 and
10^9−1 and checks the nonnegative-result precondition. Comparisons and output
formatting preserve normalized little-endian limbs.

The fast path requires every input to fit int64 and checks
`floor(N/2) <= UINT64_MAX/span` for nonzero span. Ordered unsigned subtraction
gives the exact distance even for INT64_MIN versus INT64_MAX. Every partial
candidate contains no more than floor(N/2) pair distances, so the checked global
bound covers every intermediate addition as well as the final answer.
UINT64_MAX itself is permitted: an actual first candidate initializes the
minimum, without an infinity sentinel. Values or score bounds outside that path
select arbitrary-precision limb arithmetic. Allocation failure produces a
nonzero exit, never an invented numerical answer.

## Qualification and scope

The compiled program is an offline gold-output constructor. Its reviewed proof
is general, but its resource verification concerns the entire retained finite
suite, including all 43 published inputs with largest N=4736. It remains a cubic
algorithm with quadratic storage; this review does not call it scalable at the
published corrected-task limit N=300000.

The integrated qualification path replays the compiled source against every
initial input under the separately bound offline compiler/resource policy.
Only source and invocation inputs enter that container; expected outputs stay
on the host. The same `compare_stdin` helper used for Python candidates compares
the replay outputs, whitespace-equivalent outputs and deliberate wrong outputs.
A shared-input disagreement with the corrected expectations proves the stale
reference fails the updated suite, even where separate independent fixtures use
different translations. The corrected Python reference still runs directly on
both complete suites using unchanged candidate limits.

The baseline check names are preserved, but their method is explicit:
`original_reference` is a successful certified compiled replay plus host output
comparison; it is not a claim that the slow original Python implementation passed
the candidate sandbox. Method labels and execution records are stored outside
the boolean check map. No lookup-table submission is fabricated, no grading case
is dropped, and the paid-execution hold remains independent.

## Execution evidence

- `independent_oracle_full_execution.json` records actual Docker generation of
  all 12,142 literal-oracle cases and binds the checker and result bytes.
- `independent_oracle_execution.json` preserves the earlier 2,305-case generation.
- The optimized compiled reference produced all 205 retained initial answers
  (43 published plus 162 independent) in 17.123974 seconds. The separately
  authored split-or-enclose C++ reference reproduced all 205 exact outputs in
  130.221445 seconds. Both processed the identical ordered input set.
- The optimized reference matched all 12,142 literal minimum answers in both
  automatic arithmetic mode (1.455998 seconds) and forced arbitrary-precision
  mode (0.990678 seconds). This includes UINT64_MAX scores, fallback score
  overflow, signed64 extremes, and 80-digit signed values.
- All compilation and execution occurred in the pinned isolated containers.
  The construction campaign, including the two Python oracle generations,
  consumed 160.689484 seconds against the uniform 1,800-second budget.
- `independent_review.json` binds the reviewed code, both independent checkers,
  their oracle/result bytes, and the immutable gold-output artifact. It copies
  the completed execution metadata from `construction_campaign.json` without
  binding that campaign's mutable aggregation bytes.

The immutable `gold_outputs.json` SHA-256 is
`7c2a8dfaa4d907a9b0b0096af99340e3689487013cd9869f47cc594a9c2f7170`.
Its ordered inputs digest is
`03a02db5fb03453376ca6d384ab8e5ceaefda782c4c15fb01b180b518a4dd6b0`;
its ordered outputs digest is
`d5bfb4f846e9b4704447a8dcb01245e55aa220badec6b93f09cfb87448a73a6a`.
These are verification results for source276's finite grading suite. They do
not themselves assert that the full pilot qualification or paid execution has
been approved.
