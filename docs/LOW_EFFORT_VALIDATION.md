# Low-effort follow-up implementation validation

> This records software checks before the live run. The completed experiment is
> reported in [RESULTS.md](RESULTS.md).

The current offline suite passed **328 tests, no skips**, including 69 tests for
low-effort request construction, checkpoint binding, authorization, qualification,
budgeting and execution. Tests used synthetic responses and temporary ledgers.
The pinned SymPy 1.14.0 and OpenAI SDK 3.37.0 were installed for this check.

An independent offline integration review also exercised preparation, frozen
manifest loading, real authorization, 24 injected SDK responses, and completed
resume. Historical ledger rows stayed identical and resume made no extra calls.
These were synthetic responses, not live model results.

After the first Mac preparation attempt stopped, a path comparison defect was
reproduced by running the complete suite with a symlinked temporary directory:
five qualification tests compared resolved paths with unresolved aliases. Both
paths can identify the same directory on macOS (`/var` and `/private/var`). The
test assertions now compare canonical paths. All 328 tests pass both with normal
temporary paths and with the symlinked setup. This does not change the experiment
or relax any qualification requirement. Preparation now saves its detailed unit
and Docker output to `runs/low-preparation-checks.json`, including on failure.

Historical v6 qualification was read and validated against its frozen manifest.
Its evidence covers 25 task pairs, including the separate smoke task. Existing
grading and reference dependencies were verified unchanged. Sixty declared source
and grading asset bindings were inspected; repository assets were verified by
hash. The external source cache remains on the user's Mac and is verified there
during preparation. No reference solutions were executed for this change.

Docker is unavailable in this implementation environment. No new Docker result
is claimed. Local preparation runs the full unit suite and Docker software checks
and verifies the runtime identity against the historical qualification before
binding and freezing v7. It requires the existing private v6 ledger and checkpoints.

The native initial checkpoints and ledger were not uploaded to this environment.
No v7 manifest with invented or placeholder checkpoint hashes was generated.
Preparation writes an immutable local manifest only after checking the real data.

No live model calls were made. Live low-effort continuation acceptance, response
grades, effective returned settings and actual spending remain untested.
