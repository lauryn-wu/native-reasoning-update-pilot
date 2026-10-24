# Validation performed — 2026-10-24

No paid model calls were made. Real OpenAI model availability and effective manipulation have **not** been tested. The three-call paid smoke and the 200-response pilot have **not** run. Source/reference qualification is blocked; the implementation does not present software checks as benchmark qualification.

| Check actually run | Result |
| --- | --- |
| Python runtime | Python 3.12.13 on macOS arm64 |
| Editable installation with data/paid extras | Succeeded in a project-local temporary virtual environment |
| Unit/integration suite | **76 tests passed**, no skips, `python -m unittest discover -s tests -v` |
| Actual `openai==3.37.0` SDK serialization through offline `httpx2.MockTransport` | Passed; three mocked Responses HTTP exchanges; no external request |
| Source acquisition/cache verification | **43 artifacts verified**, pinned bytes and SHA256; GitHub blobs also matched Git object hashes |
| Actual Parquet audit with `pyarrow==23.0.1` | **1,401 rows parsed**: 1,060 math, 341 coding; 401 target-family candidates |
| Source qualification | **Blocked**, zero qualified pairs; initial revised graders missing |
| Docker software isolation/grade qualification | **17 checks passed**, Docker 29.8.2, arm64 Linux image |
| Benchmark reference execution | **Not run**: required assets absent/unqualified |
| API spend | **$0**, no paid calls |

The actual environment was a temporary virtual environment under the project's `work/provider/venv`. Commands were run from the implementation repository. The source cache was in the parent project's `work/source-cache`; use the README defaults for a clean checkout.

```sh
python -m pip install -e '.[data,paid]'
python -m unittest discover -s tests -v
python -m native_pilot.cli prepare --cache ../../work/source-cache
python -m native_pilot.cli audit --cache ../../work/source-cache
```

Docker qualification was executed through `native_pilot.sandbox.qualify_docker()` and its actual result is saved in [DOCKER_QUALIFICATION.json](DOCKER_QUALIFICATION.json). The final sandbox command includes a container-side PID1 timeout, tested after that change. The pinned image is `python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704`; resolved local image ID `sha256:7efd45553a98be3d940b73600550669831c0be34f30c521159e7030a91fcdee6`.

The Docker checks accept correct/equivalent programs; reject wrong/stale programs; cross-grade the two software references; verify unprivileged UID, read-only root/submission, denied network, no forwarded credentials, only the program mounted, bounded runtime/output, and CPU/memory/process ceilings. Every submitted/reference fixture executed inside Docker; none executed on the host.

Tests cover exactly two continuation repeats, shared immutable initial checkpoint, full reasoning/phase replay, retained/dropped equality except context, frozen settings, missing manipulation rejection, authentic wrong initial preservation, one transport retry, crash recovery, no duplicate resumed calls/charges, shared cap across versions, budget refusal before dispatch, malformed/missing usage reservation retention, provider availability classification, exact math false positives/negatives, source deduplication and strict qualification, task-level sign-flip known examples, initial-only eligibility, incomplete decisions, and manifest mutation/paid-flag barriers.

Remaining qualification requires new source evidence, as detailed in SOURCE_AUDIT.md. Software mocks do not establish real provider behavior; only a later explicit paid smoke on a qualified disjoint case can do so. All future changes require a new manifest version before paid execution.
