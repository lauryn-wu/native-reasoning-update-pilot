# Exact offline reference construction

Candidate `livecodebench:276` retains its released initial minimization, corrected
maximization, complete statements, correction, and all published inputs. Its
proved noncrossing-matching interval DP remains cubic. Compilation and packed
row/column storage make exact finite-suite construction feasible; no faster
asymptotic algorithm or N=300000 performance claim is required or made.

The separate construction policy was recorded before benchmarking in
`provenance/reference_construction_policy.json`: one CPU, 2 GiB memory, 64 PIDs,
600 seconds per invocation, and 1800 seconds total per construction campaign.
Compilation, failed attempts, scaling, gold generation and independent checking
count against this budget. Network and credentials are unavailable, the user is
unprivileged, root/source are read-only, capabilities are dropped, and temporary
executable storage is bounded. Code never runs on the host. The compiler image,
compiler version, flags, source, inputs, outputs and elapsed time are recorded.

Submitted-program limits are unchanged. Submissions still use the existing Python
stdin/function adapters and existing CPU, memory, time and output limits. The
compiled reference is an offline oracle, not a contestant submission. Finite gold
construction is not a promise that the cubic algorithm solves every theoretical
input size within those limits.

The initial suite retains all 43 upstream inputs followed by all 162 previously
retained independent inputs. `references/coding/276/compiled/gold_outputs.json`
contains exact gold values and an ordered SHA-256 binding for every input.
`certificate.json` binds the complete grading suite, source, compiler, construction
policy, successful executions and independent review. Gold files are created
exclusively; changing them requires new evidence and a new manifest. No published
input is removed, shortened or used to select candidates by experimental outcomes.

Qualification freshly replays the compiled reference on every initial input.
The host compares outputs using the same exact token comparator as candidate
stdin grading, accepts whitespace-equivalent outputs, rejects altered outputs,
and verifies a stale-answer mismatch on a shared input. The updated Python
reference is executed under unchanged candidate limits against both complete
suites. Expected values are not placed inside candidate containers. No lookup-table
program is used as a purported reference solution.

The independent reviewer checks recurrence, packed indices, survivor parity,
checked 64-bit bounds and the exact decimal-integer fallback. A separately
implemented split-or-enclose DP verifies all 205 gold values. A literal
current-adjacency oracle supplies 12142 small/signed/arithmetic-boundary cases;
both automatic and forced arbitrary-precision paths are checked against it.
The original Python DP, prior pending assessment and all earlier evidence remain
available in the repository and history.

Reference construction is feasible within the fixed budget. **No
reference-feasibility exclusion amendment is applied.** Candidate 276 remains
eligible in its unchanged deterministic position. Paid execution remains blocked,
including smoke and retries. A completed source-qualified freeze does not remove
that hold.
