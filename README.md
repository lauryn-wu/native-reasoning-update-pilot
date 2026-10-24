# Native reasoning update pilot

Does retaining a model's native reasoning impair adaptation to a legitimate later
correction, beyond its previous visible answer? This is an exploratory screen,
not evidence for a mechanism or a claim of novelty. The source interrupts ongoing
reasoning; this pilot instead corrects a completed response in a new user turn.

**Paid execution is explicitly blocked. No paid model calls have been made.**

Candidate **276 is resolved** with a compiled version of the proved exact cubic
DP and immutable gold outputs. The unchanged deterministic order supplies
**12 math + 12 coding pairs**, plus separate smoke case `livecodebench:337`.
No reference-feasibility exclusion amendment is applied. All statements,
corrections, earlier attempts and published inputs are preserved.

The current [v2 manifest](manifests/pilot-v2.json) freezes all 24 pairs, separate
smoke case, eight controls, and the 200-response schedule. Its
[integrated qualification](provenance/integrated_qualification.json) binds passing
offline, Docker, and reference checks to this exact implementation and source audit.
The historical [v1 manifest](manifests/pilot-v1.json) is unchanged. Paid execution
remains blocked. See [validation](docs/VALIDATION.md) and
[offline reference construction](docs/REFERENCE_CONSTRUCTION.md).

The recorded run passes **146 unit tests**, **24 Docker software checks**,
and all eight reference checks for each of the **25 qualified pairs**.

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
docker pull gcc@sha256:5e927c284bf55a7dc796262e311a0703344f62f41f5621eb56843111b1d37e15
native-pilot prepare
native-pilot prepare-upstream
```

`paid` installs the SDK only; these commands require no API key and make no paid
calls. Source/test downloads use ignored `work/source-cache`. To reuse another
cache, pass `--cache PATH` to preparation/review and `--asset-cache PATH` before
`qualify-reviewed`. Reference qualification establishes grader readiness before experimental execution;
the explicit paid hold remains active after it passes.

`review` rebuilds the current audit from pinned sources, reference assets, exact
math grading checks, and independent review records. `qualify-reviewed --selected-only` runs the offline suite, Docker isolation
checks, and correct/equivalent/wrong/stale checks on the 24 selected pairs and
separate smoke case. Omit `--selected-only` to check every completed reference. Results are saved under ignored `runs/`.
The committed validation record states what was actually run.

## Freezing and execution gates

The committed v2 snapshot is already source-qualified. Inspect it, or repeat
qualification without changing its bound evidence:

```sh
native-pilot --manifest manifests/pilot-v2.json dry-run
native-pilot --manifest manifests/pilot-v2.json report
native-pilot --manifest manifests/pilot-v2.json archive
native-pilot --manifest manifests/pilot-v2.json qualify --docker --workers 4
```

Four workers run independent offline task checks; each retains the same complete
suites and per-container limits. The default is one worker. This option does not
change the experimental call schedule.

To deliberately rebuild the audit and freeze a revised snapshot, choose an unused
version. Rebuilding the audit changes a bound file and requires the new freeze:

```sh
native-pilot review
native-pilot qualify-reviewed --selected-only --docker --workers 4
native-pilot freeze --version pilot-v3 --out manifests/pilot-v3.json --audit provenance/qualification_audit.json --qualification runs/reviewed-candidate-qualification.json
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
