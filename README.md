# Native reasoning update pilot

Does retaining a model's native reasoning impair adaptation to a legitimate later
correction, beyond its previous visible answer? This is an exploratory screen,
not evidence for a mechanism or a claim of novelty. The source interrupts ongoing
reasoning; this pilot instead corrects a completed response in a new user turn.

**Paid execution is explicitly blocked. No paid model calls have been made.**

The current ordered review supports **12 math + 9 coding pairs**. The coding
shortfall is **3**: `livecodebench:276` (Adjacent Delete), at one-based coding
review rank 45, remains pending. Its minimum-score initial variant has a proved
exact interval algorithm and 9,999 small checks, but no verified implementation
covering the large released tests within the sandbox bounds. It is not excluded
for difficulty, and later validated references do not replace it. No new 24-case
manifest, control assignment, smoke assignment, or 200-call schedule is frozen.

The historical [v1 manifest](manifests/pilot-v1.json) and baseline source audit
are preserved. They describe the earlier source-only inspection, before verified
reference construction was authorized. Current evidence is in
[qualification audit](provenance/qualification_audit.json),
[math review](provenance/math_review.json), [coding review](provenance/coding_review.json),
and [validation](docs/VALIDATION.md). The existing deterministic order and seed
are unchanged. Selection never reads experimental model outcomes.

## References and grading

Math references include checkable derivations, exhaustive integer calculations,
exact rational/radical answers, and a rigorous interval certificate for the
trigonometric pair. Derivations and exclusions have independent reviews.

Coding tests are acquired from pinned upstream LiveCodeBench files and matched
by platform, contest, and title. Original published inputs are retained. Initial
expected outputs use proved transformations or independently validated reference
implementations. One erroneous game-test label is explicitly adjudicated with a
published theorem and a literal-state minimax certificate; its original label
is preserved. No case is silently dropped. Full tests remain in the ignored
source cache; committed checksums, small independent fixtures, proofs, references,
and reconstruction code bind the assets.

All reference and submitted code executes only inside Docker: no network or
credentials, unprivileged user, read-only filesystem, bounded CPU/memory/processes/
runtime/output. Expected outputs and grader decisions stay outside. Both stdin
and function-call interfaces are supported. See [grading](docs/GRADING.md),
[math derivations](references/math/proofs.md), and
[coding references](docs/CODING_REFERENCES.md).

## Setup and current offline commands

Use Python 3.12 and Docker Desktop on macOS:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[data,paid]'
open -a Docker
docker pull python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
native-pilot prepare
native-pilot prepare-upstream
native-pilot review
native-pilot qualify-reviewed --docker
```

`paid` installs the SDK only; these commands require no API key and make no paid
calls. Source/test downloads use ignored `work/source-cache`. To reuse another
cache, pass `--cache PATH` to preparation/review and `--asset-cache PATH` before
`qualify-reviewed`. Candidate qualification is separate from completed sample
qualification; the result records that the ordered selection is still blocked.

`review` rebuilds the current audit from pinned sources, reference assets, exact
math grading checks, and independent review records. `qualify-reviewed` runs the
offline suite, Docker isolation checks, and correct/equivalent/wrong/stale checks
on all completed candidate references. Results are saved under ignored `runs/`.
The committed validation record states what was actually run.

## Freezing and execution gates

After the pending source/reference work is genuinely resolved, use a new version:

```sh
native-pilot review
native-pilot freeze --version pilot-v2 --out manifests/pilot-v2.json --audit provenance/qualification_audit.json
native-pilot --manifest manifests/pilot-v2.json qualify --docker
native-pilot --manifest manifests/pilot-v2.json dry-run
native-pilot --manifest manifests/pilot-v2.json report
native-pilot --manifest manifests/pilot-v2.json archive
```

A blocked audit cannot produce a 24-case schedule. Existing manifests cannot be
overwritten; changing frozen implementation or evidence requires a new version.
The historical v1 implementation-file hashes are expected to reject the updated
checkout; it is an archival snapshot, not the current runnable campaign.

The separately labeled three-call `smoke --allow-paid` and subsequent
`run --allow-paid` commands remain implemented, but **the explicit user hold
rejects both before a real provider client is constructed**, even if all source
checks pass. Removing that hold requires new user authorization and a new freeze.
No command or successful reference check automatically removes it.

## Design and limits

The planned campaign remains 24 initial responses, 144 updated/fresh responses,
and 32 unchanged controls, totaling 200, plus separately accounted smoke/retries.
Both samples independently continue the same initial checkpoint. Full native
reasoning and assistant phases are replayed; paired requests differ only in
`reasoning.context`. The $40 atomic ledger reserves worst-case costs before any
request and retains uncertain charges. It does not guarantee all 200 will fit.

The primary population uses initial correctness only. Analysis uses problem-level
paired differences and exact one-sided sign flips, with the predeclared 18-case,
75% fresh-accuracy, 10-point-gap, p≤0.10 exploratory gate. An incomplete campaign
is inconclusive. No research performance is inferred from reference checks.
See [protocol](docs/PROTOCOL.md), [provider](docs/PROVIDER.md), and
[source provenance](docs/SOURCE_AUDIT.md).
