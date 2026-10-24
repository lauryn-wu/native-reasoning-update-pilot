# Math reference construction

All paid execution remains blocked. This work checks the actual released pairs;
it does not change task text, produce experimental answers, or select on model
performance. The released revised problem is the pilot initial task, and the
released original problem is the corrected task.

The first22 mathematical candidates in the existing deterministic review order
were examined. Fourteen have independently reviewed exact reference derivations
and Docker arithmetic certificates; eight have independently reviewed contradictory
or ambiguous specifications. The difficult earlier candidate `aime2024:1003` is
resolved by a complete certified intersection count, so no unresolved earlier
candidate has been replaced by a later easier candidate.

`provenance/math_review.json` records every rank, source row and prompt checksum,
status, reference, validation, and reason. `references/math/source_pairs.json`
preserves the exact source objects. `references/math/proofs.md` provides checkable
proofs for both versions of every derived reference, and direct counterexamples
or contradictions for every exclusion. `INDEPENDENT_REVIEW.md` and
`TRIG_INDEPENDENT_REVIEW.md` record the separate proof reviews and checks.
The exact initial radical `sqrt(241330)` and rational `1923/8` are retained without
rounding; grader support is a separate requirement, not a reason to exclude them.

`references/math/verify_exact.py` exhaustively counts finite residue domains,
checks digit replacements, uses exact rational arithmetic, and evaluates proved
modular recurrences. `verify_exclusions.py` checks an irreducible cubic and the
squared-diagonal identity behind one false-rationality exclusion. Both ran with
exit0 inside the pinned Python Docker image under no-network, read-only,
unprivileged, bounded-resource execution. The raw results and pinned image digest
are in their `*-run.json` files. None of the reference programs ran on the host.

`trig_certifier.py` exhausts both trigonometric residual domains using outward
integer intervals and exact analytic guards. It proves1244 intersections initially
and385 after correction. `trig_independent_check.py` raises the precision and
changes the partition; it proves the same counts with no unresolved intervals.
All root brackets and execution records are retained. A separate independent
arithmetic checker also verifies the other derivations through alternative exact
calculations, including Hensel lifting, cyclic determinants, and complete integer
pair enumeration.

The prefix contains twelve verified reference pairs by rank20 and two supplemental
pairs by rank22. Exact grader qualification is recorded separately before selection
is frozen. No smoke or pilot model call was made; paid execution remains blocked.
