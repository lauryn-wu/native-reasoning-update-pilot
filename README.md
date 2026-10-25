# Does keeping earlier reasoning make corrections harder?

When a model has already solved a problem, does keeping its reasoning make it harder to respond to a correction? I tested this on four math and coding problems with `gpt-6.1-sol`, comparing retained reasoning, dropped reasoning, and a fresh solve of the updated problem.

**All 48 updated answers were graded correct.** Lowering the effort setting for the follow-up calls produced the same result. I stopped the pilot because these cases gave no accuracy difference to investigate.

## Results

Each cell contains two responses per problem.

| Follow-up effort | Retained reasoning | Dropped reasoning | Fresh solve |
| --- | ---: | ---: | ---: |
| High | 8/8 | 8/8 | 8/8 |
| Low | 8/8 | 8/8 | 8/8 |

The four initial answers were generated once, at high effort; three were correct. Restricting the comparison to those three problems gives 6/6 in every cell. The low-effort run reused the same initial answers and native reasoning, so it tests **high-effort initial reasoning followed by low-effort revisions**.

There were 52 experimental responses in total: four initial answers and 48 updated answers. The two screens cost approximately $1.07 in recorded API charges, excluding setup calls.

[Per-problem results and run details](docs/RESULTS.md) · [Results JSON](docs/RESULTS.json)

## What changed between conditions?

The model first answered an initial version of a problem. After that answer was complete, it received a correction.

| Condition | Context for the updated answer |
| --- | --- |
| Retained | Previous conversation and answer, with earlier native reasoning available through `reasoning.context=all_turns` |
| Dropped | The same conversation and answer, with `reasoning.context=current_turn` |
| Fresh | The complete updated problem, without the previous conversation |

The retained and dropped requests contained the same messages and native output items. Only the API's reasoning-context setting differed. Each continuation was a separate request from the original response.

Math answers were checked for exact equivalence. Coding answers were evaluated against tests in Docker. No model judge was used.

## What this tells us

These four cases were at ceiling in both runs. They do not show that retaining reasoning is harmless in general, or explain how the model used its earlier reasoning. There is one model, four selected problems, and two samples per condition. The low-effort follow-up was added after seeing the high-effort results.

The tasks come from [Are Large Reasoning Models Interruptible?](https://arxiv.org/html/2510.11713v3). That study introduces changes during reasoning. Here, the correction arrived **after a completed answer**, so this is a different setting and does not reproduce its interruption experiment.

## Code and data

This repository contains the experiment code, graders, reference solutions, frozen configurations, and aggregate results. Raw API responses, encrypted reasoning, and the local run ledger are not included. The results were imported from local run reports; the release does not include an independent regrade of those raw responses.

To run the unit tests with Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[data,paid]'
python -m unittest discover -s tests -v
```

These tests make no paid model calls. See [reproduction notes](docs/REPRODUCTION.md) for the execution commits, source downloads, and limits on replaying the original runs.

[Grading](docs/GRADING.md) · [Source attribution](THIRD_PARTY.md) · [Development records](docs/DEVELOPMENT.md)
