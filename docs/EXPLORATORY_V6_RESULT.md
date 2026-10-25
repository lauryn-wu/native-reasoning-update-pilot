# V6 exploratory pilot results

The four-case screen completed all 28 planned responses. Every updated response was graded correct under retained reasoning, dropped reasoning, and fresh solving. No accuracy difference was observed in this screen.

## Run and provenance

- Execution commit: `8b74a544c1d75e2a55006d4cab44fa25d654b133`.
- Frozen manifest: [pilot-v6.json](../manifests/pilot-v6.json).
- Manifest SHA-256: `021676718d1d29683b2e1e69e3e5c5eefa8a41f9ed9c3a3d952404c8f14ffb7f`.
- Model: `gpt-6.1-sol`; high reasoning effort; 32,768 maximum output tokens.
- Report time: October 24, 2026, 9:41:55 p.m. America/Chicago (`2026-10-25T02:41:55.557430+00:00`).
- Machine-readable results: [EXPLORATORY_V6_RESULT.json](EXPLORATORY_V6_RESULT.json).

Imported from the user-provided Terminal report and checked for internal consistency and agreement with the frozen manifest's assignments. The underlying local ledger, raw API responses, and grading artifacts were not independently inspected. No model requests or regrading were performed during this import.

The uploaded source was `Pasted markdown(10).md`, SHA-256 `6025a11a9bf70b60a3632c54d14235022159ba0f1972b64a39f39ab8a9c477c3`. The committed JSON contains the report object only; the terminal command/header and its local username/path are omitted. JSON formatting was normalized without intentionally changing any fields or values. The source upload and raw run artifacts are not included.

## Outcomes

Each task has one initial response and two samples in each updated condition. Both continuation samples use the same initial checkpoint.

| Task | Initial correct | Retained correct | Dropped correct | Fresh correct |
| --- | ---: | ---: | ---: | ---: |
| aime2025:1042 | 1/1 | 2/2 | 2/2 | 2/2 |
| aime2025:1057 | 1/1 | 2/2 | 2/2 | 2/2 |
| livecodebench:299 | 1/1 | 2/2 | 2/2 | 2/2 |
| livecodebench:276 | 0/1 | 2/2 | 2/2 | 2/2 |
| **All selected tasks** | **3/4** | **8/8** | **8/8** | **8/8** |

The initial-correct subset contains three tasks: 1042, 1057, and 299. Retained, dropped, and fresh conditions each score **6/6** in that subset. There are eight complete retained/dropped sample pairs overall and six in the initial-correct subset. Repeated samples do not increase the number of distinct tasks.

All 28 responses are reported protocol-valid and completed, with no provider errors, no transport retries, no missing outcomes, and no duplicate or unexpected call IDs. The only incorrect grade is the initial solution to case 276. This report does not identify the reason for that incorrect grade.

## Time and accounting

| Quantity | Reported value |
| --- | ---: |
| New v6 known charges | $0.741338 |
| New v6 outstanding reservations | $0.000000 |
| V6 charged-plus-reserved cap | $5.000000 |
| Shared known charges across versions | $0.782622 |
| Historical outstanding reservations | $0.880630 |
| Shared accounted total | $1.663252 |
| Shared cap | $40.000000 |
| Elapsed time at report | 1,806.313 seconds, approximately 30 minutes 6 seconds |

The shared accounted total includes reservations and must not be described as actual spending. The historical reservations are from earlier smoke attempts, not this pilot. These are harness accounting figures from the submitted report, not independently reconciled provider invoices.

The scope's 30-minute dispatch window had elapsed at report time. All planned calls nevertheless completed, and `stop_reason` is null. This is consistent with the soft deadline allowing an in-flight response and grading to finish after the dispatch window; the report does not supply individual dispatch timestamps for independent verification.

## Interpretation and status

This is a descriptive feasibility result on four prospectively selected tasks, with only three initially correct tasks. It shows no observed accuracy penalty from retaining native reasoning in these completed-answer correction cases. It does not establish equivalence, exclude smaller or task-dependent effects, identify a mechanism, or contradict failures under a different interruption setup.

No significance test or full-study continuation gate is applied. The recommendation is to pause this version rather than expand it to the full 200-response study on the strength of these results. This recommendation does not change the frozen execution policy or authorize further calls.

The pre-run qualification and status snapshots remain unchanged. This result records the subsequent completed run; it does not alter prompts, graders, manifests, budgets, or historical ledger entries.
