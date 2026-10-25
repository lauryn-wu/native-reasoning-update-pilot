# Historical setup instructions

This is the README from the implementation stage, before the final public write-up. Commands and status statements below refer to those earlier checkouts. For the completed results and current reproduction guidance, see [RESULTS.md](RESULTS.md) and [REPRODUCTION.md](REPRODUCTION.md).


Does retaining a model's native reasoning impair adaptation to a legitimate later
correction, beyond its previous visible answer? This is an exploratory screen,
not evidence for a mechanism or a claim of novelty. The source interrupts ongoing
reasoning; this pilot instead corrects a completed response in a new user turn.

**Current follow-up: low effort, with the original high-effort checkpoints held fixed.**
The [low-effort instructions](LOW_EFFORT_FOLLOWUP.md) prepare a local v7
manifest and run at most 24 new responses under a persistent additional **$2 cap**
and **30-minute dispatch window**, using the same shared ledger. Preparation
makes no model calls. The full study remains blocked. V7 has not been run here;
the existing private checkpoints and Docker checks must be verified on the Mac.

The [completed v6 report](EXPLORATORY_V6_RESULT.md) records 28 valid responses
and correct updated answers in all three conditions. The low-effort follow-up
is a descriptive screen, not an all-low-effort deployment evaluation.

**Historical v6 exploratory screen of four existing cases:**
`aime2025:1042`, `aime2025:1057`, `livecodebench:299`, and `livecodebench:276`.
The [prospective protocol](../provenance/exploratory_authorization_v6.json) fixes that
order and complete seven-call task blocks: one initial plus two samples each of
retained, dropped, and fresh branches. Prompts, graders, reference assets, and
model settings are unchanged. The full 200-response study remains blocked.

The persistent additional budget is **$5 charged plus reserved**, within the
existing shared **$40 cap**. A **30-minute soft dispatch deadline** starts at the
first reservation and does not reset on resume. Completed calls and checkpoints
are reused. Limits can stop a partial block, which remains explicitly reported.
See the [Terminal command and resume rules](EXPLORATORY_V6.md#terminal-command).

The v5 smoke passed live protocol verification. All five historical attempts,
including the original HTTP 401 and HTTP 400 failures, remain unchanged. Before
v6 execution, known charges are $0.041284 and outstanding reservations are
$0.880630. No v6 model call was made while preparing this screen.

The [v6 manifest](../manifests/pilot-v6.json) is separate from the archived full-study
and smoke manifests. Its [qualification](EXPLORATORY_V6_QUALIFICATION.json)
reuses unchanged reference evidence with fresh software checks. Its
[status report](EXPLORATORY_V6_STATUS.json) reports descriptive accuracy,
completed comparisons, elapsed time and spending. The full study's significance
gate is not applied; a null result cannot rule out the hypothesis.

Candidate 276 retains the compiled exact DP and immutable gold outputs. No
reference-feasibility exclusion amendment was needed. All original statements,
corrections, prior attempts and published test inputs remain preserved.

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
and function-call interfaces are supported. See [grading](GRADING.md),
[math derivations](../references/math/proofs.md), and
[coding references](CODING_REFERENCES.md).

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
passing it does not authorize the pilot.

`review` rebuilds the current audit from pinned sources, reference assets, exact
math grading checks, and independent review records. `qualify-reviewed --selected-only` runs the offline suite, Docker isolation
checks, and correct/equivalent/wrong/stale checks on the 24 selected pairs and
separate smoke case. Omit `--selected-only` to check every completed reference. Results are saved under ignored `runs/`.
The committed validation record states what was actually run.

## Freezing and execution gates

The committed v6 subset snapshot is source-qualified. Inspect it without dispatching:

```sh
native-pilot --manifest manifests/pilot-v6.json dry-run
native-pilot --manifest manifests/pilot-v6.json report
native-pilot --manifest manifests/pilot-v6.json archive
```

Four workers run independent offline task checks; each retains the same complete
suites and per-container limits. The default is one worker. This option does not
change the experimental call schedule.

To deliberately rebuild the audit and freeze a revised snapshot, choose an unused
version. Rebuilding the audit changes a bound file and requires the new freeze:

```sh
native-pilot review
native-pilot qualify-reviewed --selected-only --docker --workers 4
native-pilot freeze --version UNUSED_VERSION --out manifests/UNUSED_VERSION.json --audit provenance/qualification_audit.json --qualification runs/reviewed-candidate-qualification.json
```

A blocked audit cannot produce a 24-case schedule. Existing manifests cannot be
overwritten; changing frozen implementation or evidence requires a new version.
Historical v1/v2/v3/v4/v5 implementation-file hashes are expected to reject the updated
checkout; they are archival snapshots, preserved byte-for-byte.

The scoped `explore --allow-paid` command requires v6 manifest-bound qualification,
the verified historical v5 smoke, the canonical shared ledger and a locally
entered key. It permits only the 28 prospectively scheduled subset calls.
Completed calls are skipped on resume; the budget and deadline are persistent.
The provider rechecks scope, checkpoint, schedule, and limits before dispatch.

Use the [hidden-key Terminal command](EXPLORATORY_V6.md#terminal-command).
Provider errors retain safely sanitized diagnostics. Incomplete execution is
reported explicitly. `run --allow-paid` remains blocked. The ledger stays at
`runs/budget.sqlite`; never reset or replace it. Credentials, raw responses and
native reasoning remain private and excluded from Git.

## Archived full-study design and limits

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
See [protocol](PROTOCOL.md), [provider](PROVIDER.md), and
[source provenance](SOURCE_AUDIT.md).
