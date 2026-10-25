# V3 authorization and qualification

On 2026-10-24 the user explicitly authorized only the existing three-call live
protocol smoke and its existing maximum of one transport retry per assigned
call, charged to the shared $40 campaign budget. The exact instruction and
scope are recorded in `provenance/smoke_authorization_v3.json`. The 200-response
pilot remains blocked. This is an execution authorization, not a design or
reference-feasibility amendment.

V2 and its completed integrated qualification remain immutable historical
artifacts. V3 retains every selected task, control, prompt, correction, test,
reference, schedule assignment, model setting, price, and analysis parameter.
The smoke task remains `livecodebench:337`. Both continuations independently
replay the single initial checkpoint. The only paired request difference is
`reasoning.context`; correctness never changes dispatch or the design.

Reference evidence may be reused only after verifying the previous manifest's
content hash, the exact frozen qualification bytes, the unchanged source audit,
all protected source/grading/sandbox/reference dependencies, all task assets,
and the full design identity. Current unit tests and Docker software checks
must pass against an unchanged implementation snapshot. The new record labels
reference results as reused and retains their original execution evidence. A
separate post-freeze record binds those checks to the new manifest hash.

The live provider verifies the canonical v3 manifest, manifest-bound
qualification, current scoped policy, and canonical shared ledger before any
request. Each request must match a reserved and dispatched smoke assignment,
including its attempt number and exact frozen request. The ledger binds this
authorization to one manifest hash; completed assignments cannot be replayed as
a new smoke run. Ordinary API failures, incorrect answers, refusals and
truncations receive no correctness retries. Unknown charges retain reservations.

The private ledger preserves full requests and responses, including opaque
native reasoning. The public smoke report contains only hashes, protocol-check
results, returned effective settings, errors, usage, costs, reservations and
answer grades. It does not publish native reasoning or credential material.
After smoke the runner stops; no pilot assignment is authorized.
