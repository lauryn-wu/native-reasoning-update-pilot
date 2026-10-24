# Native reasoning update pilot

An exploratory implementation of the question: **Does retaining a model's previous native reasoning impair adaptation to a legitimate later correction, beyond its previous visible answer?**

**Status: implementation complete; paid research execution blocked by source qualification. No paid model calls have been made.** The released tasks cannot currently support the requested valid 12 AIME + 12 coding sample. This is an audited feasibility result, not a model-performance result.

The source presents a *revised* problem, then corrects it back to the benchmark's *original* problem. Its 60 AIME revisions have no initial-answer references. Its 341 coding rows omit executable tests and references; upstream original tests cannot grade the revised initial behavior. Some revisions are ill-posed, and 33 coding rows have unchanged problem/starter text. We did not invent answers, updates, tests, pilot IDs, or substitute easier problems. See [source audit](docs/SOURCE_AUDIT.md), [frozen protocol](docs/PROTOCOL.md), and [blocked manifest](manifests/pilot-v1.json).

The source paper interrupts ongoing thinking. This pilot uses a correction in a **new user turn after a completed response**, so it is an adaptation, not a replication of the reported failure rate. No novelty or causal mechanism is claimed.

## What is implemented

- Revision-pinned acquisition, checksums, source/schema/license audit, deterministic difficulty/edit-size ranking, deduplication, and fail-closed selection.
- Responses API adapter for `gpt-6.1-sol`: full manual replay, encrypted reasoning and phases preserved, `store:false`, identical high effort, and returned-context verification. Retained/dropped payloads differ only in `reasoning.context`.
- Immutable checkpoints, independent repeats, randomized topological schedule, stable IDs, and resumable execution.
- Exact math grading and Docker-only Python stdin/stdout grading. No generated code runs on the host. Missing source graders never pass software qualification.
- Atomic persistent $40 ledger shared by smoke, retries, and manifest versions; maximum-cost reservation, usage reconciliation, and uncertain-charge retention.
- Initial-correct eligibility, exact problem-level sign-flip inference, bootstrap uncertainty, secondary all-assigned analysis, descriptive controls, and the specified continuation gate.

The planned design is 200 responses: 24 initial, 144 updated/fresh, and 32 unchanged. There are no assigned research calls in the blocked v1 manifest. The 401-case inventory is unqualified review metadata, not a selected sample. Synthetic test fixtures are software-only and cannot enter selection.

## macOS setup (Python 3.12 and Docker Desktop)

```sh
git clone https://github.com/lauryn-wu/native-reasoning-update-pilot.git
cd native-reasoning-update-pilot
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[data,paid]'
open -a Docker
docker pull python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
```

The `paid` extra installs the SDK only; it makes no paid calls. No API key is needed for source preparation, audits, qualification, dry-run, reporting, or archives. SDK and PyArrow versions are pinned; audited SDK wheel and source checksums are recorded in provenance. Use `python -m native_pilot` if the `native-pilot` console command is unavailable.

## Commands

Run these from the repository root with the virtual environment active.

1. Prepare and audit the exact public source bytes:

   ```sh
   native-pilot prepare
   native-pilot audit
   ```

   The audit succeeds as an audit while reporting source qualification blocked. Downloads remain in ignored `work/source-cache`; no upstream source or reference code is executed.

2. Inspect the shipped frozen v1, or freeze a new version after independently reviewing source changes:

   ```sh
   native-pilot dry-run
   native-pilot freeze --version pilot-v2 --out manifests/pilot-v2.json
   ```

   With current sources v2 is also blocked. Existing manifests cannot be overwritten. Any later implementation, configuration, data, or qualification-test change requires a new version. Pass `--manifest manifests/pilot-v2.json` **before** the subcommand to use another version.

3. Offline and Docker qualification:

   ```sh
   native-pilot qualify
   native-pilot qualify --docker
   ```

   Full qualification checks the same manifest's pilot AND separate smoke references. With v1, `--docker` records software checks as passed but exits **2** because source/reference qualification is blocked. If Docker is unavailable it records that check as not run and blocks paid coding evaluation. There is no host fallback.

4. Dry-run assignments, request differences, and budget assumptions:

   ```sh
   native-pilot dry-run
   ```

   Blocked v1 honestly reports zero qualified tasks and zero assignments, alongside the intended 200-response design. Mock tests separately verify the 200-assignment shape and paired request equality.

5. **Paid three-call protocol smoke — blocked until all qualification passes:**

   ```sh
   # Supply OPENAI_API_KEY securely in the environment; never commit it.
   native-pilot smoke --allow-paid
   ```

   Exactly three planned calls on one disjoint, qualified source problem; retries are extra. Current v1 rejects this before constructing a real API client. Smoke spends from the SAME $40 ledger. It is not a pilot outcome. Changes after smoke require a new manifest version and repeat qualification/smoke.

6. **Paid run/resume — explicit flag required and blocked for current v1:**

   ```sh
   native-pilot run --allow-paid
   ```

   The same command resumes completed calls without dispatching or charging them again. Do not delete `runs/budget.sqlite`, clone the campaign into a second spending ledger, or reset it between versions. Only transport failures get at most one separately reserved retry; incorrect answers, refusals, and truncations never get score-improving retries.

7. Produce the analysis and review archive:

   ```sh
   native-pilot report
   native-pilot archive
   ```

   Reports and archives are in ignored `runs/`. Review archives exclude the ledger, raw model text, encrypted reasoning, credentials, and downloaded source corpora. The blocked report is inconclusive; no model accuracy is inferred from absent runs.

## Validation actually completed

See [validation record](docs/VALIDATION.md) for actual commands, counts, environment, and limits. Source preparation verified 43 artifacts and parsed all 1,401 released rows; 401 belong to the requested task families. The offline suite includes mocked serialization through the actual pinned OpenAI SDK, statistical known examples, request equivalence, same-checkpoint repeats, budget refusals, recovery, failure classification, and immutable-manifest checks. Docker software checks ran successfully on Docker 29.8.2 with the pinned Python image. No benchmark reference solutions or paid model calls were run.

## Remaining blocker

Obtain published or independently audited authoritative initial AND updated answers/tests and complete unambiguous prompts for at least 12 AIME and 12 coding originals, plus a disjoint smoke case. Update the source adapter and audit with evidence of changed behavior; do not merely toggle the audit's status. The source report lists precise omissions and malformed examples. That work requires new evidence; no CLI command can reconstruct missing references reliably. Then freeze a new manifest, requalify, and run the paid smoke explicitly. Actual account-level model access and manipulation remain untested until that authorized smoke.

## Budget and interpretation

Official pricing verified 2026-10-24: Standard $2 input / $0.10 cached input / $2.50 30m write / $5 12h write / $10 output per million tokens. Cache mode is explicitly frozen without breakpoints; reservation assumes no savings and covers the highest write rate. Full pricing/provenance is in [pricing.json](provenance/pricing.json). Maximum output alone for 200 calls costs **$65.536**; $40 is a cap, not a promise of completion. Budget exhaustion produces an incomplete, inconclusive campaign.

A positive preliminary gate requires >=18 initially correct problems, >=75% fresh accuracy on that same population, >=10-point dropped-minus-retained gap, exploratory one-sided p<=0.10, and complete valid outcomes. Problems are the analysis units; repeats remain together. Passing only motivates confirmation on NEW held-out problems. Old-answer matches do not establish reasoning causation; eight unchanged controls cannot establish absence of a general retention effect.

## Layout

`src/native_pilot/` contains data, design/manifest, provider, budget, runner, grading/sandbox, analysis, and CLI modules. `tests/` contains software fixtures. `provenance/` records public-source revisions, licenses, checksums, pricing and review metadata. `manifests/` contains frozen protocol artifacts. `docs/` records the protocol, source/provider/grader audits, and actual qualification.
