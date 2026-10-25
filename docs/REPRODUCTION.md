# Reproduction notes

The public files support inspecting the design, checking the aggregate results, and running the software tests. Exact replay of the original continuations also requires their saved native reasoning and local ledger, which are not included.

## Execution versions

| Run | Commit | Configuration |
| --- | --- | --- |
| High-effort screen | `8b74a544c1d75e2a55006d4cab44fa25d654b133` | [pilot-v6.json](../manifests/pilot-v6.json) |
| Low-effort follow-up | `a1f7432f72111ed84d50f2523bc885e27820aab7` | Locally frozen v7; hash recorded in [RESULTS.json](RESULTS.json) |

The low-effort manifest was built locally because it binds the exact four initial checkpoints. The public summary records its hash; the manifest and those checkpoints are not included.

Use the corresponding execution commit when inspecting an original frozen configuration. The loader checks source and documentation hashes, so a historical manifest will reject a newer checkout. The public write-up was added after both runs.

## Software tests

From a Python 3.12 environment with the project installed:

```bash
python -m unittest discover -s tests -v
```

The latest implementation check passed 328 tests, including a run with symlinked temporary paths to exercise the macOS path handling. These are software tests with synthetic API responses. They do not repeat the experiment or establish the correctness of the reported model answers.

## Source data and grading

Pinned source revisions and download hashes are recorded in [source_lock.json](../provenance/source_lock.json). The original preparation commands are:

```bash
native-pilot prepare
native-pilot prepare-upstream
```

Downloaded sources and coding-test payloads are kept in an ignored local cache. Reference construction and qualification require Docker and the pinned images documented in [GRADING.md](GRADING.md) and [HISTORICAL_SETUP.md](HISTORICAL_SETUP.md).

The repository includes selected source statements, corrections, reference implementations, proofs, and derived expected outputs. It does not redistribute the full upstream dataset or full downloaded coding-test inputs. See [THIRD_PARTY.md](../THIRD_PARTY.md) for attribution.

## Running new model calls

The scripts were built for a particular run history, including verified setup calls, a shared budget ledger, and saved initial checkpoints. They are not a one-command fresh replication from a new clone. The [high-effort](EXPLORATORY_V6.md) and [low-effort](LOW_EFFORT_FOLLOWUP.md) instructions document those original runs.

No new calls are needed to inspect this result. A separate experiment would need its own configuration and source qualification; the archived 200-response proposal was never executed.
