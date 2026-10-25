# Results

I tested whether keeping a model's previous reasoning makes it harder to incorporate a correction. The comparison used four selected problems: two from AIME 2025 and two coding problems derived from LiveCodeBench.

The model first answered an initial version of each problem at high effort. Once its answer was complete, I compared two continuations of that response: one with earlier native reasoning available and one with it excluded by the API context setting. A fresh solve received the updated problem without the earlier conversation. Each condition had two samples.

The high-effort screen returned correct answers in every updated condition. I then repeated the follow-ups at low effort, keeping the original checkpoints fixed. Those answers were also all correct.

## Per-problem outcomes

Each entry below is correct / graded. “Initial” is the single high-effort answer reused across both runs.

| Problem | Initial | High retained | High dropped | High fresh | Low retained | Low dropped | Low fresh |
| --- | --- | --- | --- | --- | --- | --- | --- |
| aime2025:1042 | Correct | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| aime2025:1057 | Correct | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| livecodebench:299 | Correct | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| livecodebench:276 | Incorrect | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| All four | 3/4 | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 |
| Initially correct subset | 3/3 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |

Both runs completed their assigned calls without transport retries. There were four initial responses and 48 updated responses, for 52 experimental responses in total. Repeated samples and the second effort setting do not increase the number of distinct problems.

## Details that matter for interpreting the result

The model was `gpt-6.1-sol`, with a maximum of 32,768 output tokens. The retained and dropped requests replayed identical messages and native output items. They differed only in `reasoning.context`: `all_turns` versus `current_turn`. Each continuation started from the same saved initial response, rather than from another continuation.

Math grading used exact answer equivalence. Coding grading used tests in Docker. The original and updated versions had separate references, and qualification checked that a stale solution would fail the updated task. This matters because a correction that left the answer unchanged would not test updating.

The initial-correct subset was reported separately. Case 276 stayed in the assigned schedule despite its incorrect initial answer. No initial answer was regenerated to make a task eligible.

The four cases were selected before their experimental outputs. The low-effort follow-up was chosen after seeing the high-effort ceiling result. It therefore tests low-effort revisions of high-effort initial reasoning; it is not a randomized comparison of entirely high- versus entirely low-effort conversations.

The source is [Are Large Reasoning Models Interruptible?](https://arxiv.org/html/2510.11713v3). Its update experiment interrupts ongoing reasoning. This pilot waits until the initial answer is finished. The different timing is a substantial change in the task, so these results should not be read as a failed replication of that paper.

## Decision

I stopped after the low-effort follow-up. The selected cases did not produce the accuracy separation needed to study a retention-related failure. The planned 200-response study was not run.

This result is limited to one model and four problems. It does not rule out effects on harder corrections, longer interactions, or interruptions during reasoning. It also does not establish whether the model relied on the earlier reasoning internally.

## Run records

| Run | New responses | Recorded charges | Elapsed time |
| --- | ---: | ---: | ---: |
| High effort | 28, including four initials | $0.741338 | 1,806.31 seconds |
| Low effort | 24, reusing those initials | $0.331888 | 538.35 seconds |

Recorded charges total $1.073226 for the two screens. Setup calls and historical unresolved reservations are excluded. These are harness accounting figures, not an independently reconciled provider invoice.

The [results JSON](RESULTS.json) records the configuration hashes and aggregate counts. The complete imported [high-effort report](EXPLORATORY_V6_RESULT.json) is also included. The low-effort summary was transcribed from the local run's Terminal summary and per-task correctness output.

The raw API responses, initial checkpoints, local ledger, and v7 manifest remain outside this repository. The public write-up checks consistency of the supplied reports; it does not independently regrade the raw model answers. [Reproduction notes](REPRODUCTION.md) describe what can be checked from the public files.
