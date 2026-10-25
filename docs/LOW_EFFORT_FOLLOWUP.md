# One bounded low-effort follow-up

This exploratory follow-up holds the four saved **high-effort initial solutions** fixed and uses **low effort** for new revisions and fresh solves. It does not evaluate an entirely low-effort conversation. V6's high-effort results remain intact.

Task order is `aime2025:1042`, `aime2025:1057`, `livecodebench:299`, `livecodebench:276`. Each task receives retained, dropped and fresh calls, in that order, for samples 1 and 2: **24 new logical responses**. Both revision branches replay the identical original input and native output; `reasoning.context` is the only difference between them. The new request sets `reasoning.effort=low` directly. Model, output cap, prompts, graders, native state normalization and uncached requests remain unchanged.

The primary descriptive subset contains correct inherited initial solutions. The initially incorrect coding task remains assigned and is reported separately and in all-task results. No answer-based retries, replacement tasks or new initials are permitted. One transport retry is allowed per logical call, with uncertain charges retained.

The additional cap is **$2 charged plus reserved**, within the same shared **$40 ledger**. Historical reservations are preserved. The **30-minute dispatch window** starts at the first reservation, includes downtime and cannot restart on resume. An in-flight call may finish after the window. A worst-case reservation can stop dispatch before actual charges reach $2.

If all outcomes remain correct, stop this screen. A general accuracy drop across all three conditions does not establish harm from retention. Four tasks and two samples per branch cannot support a broad null conclusion or a reliable population interaction estimate. Any apparent retention-specific result requires independent cases before a main study.

## Prepare on the original Mac checkout

The existing raw v6 checkpoints and shared ledger are private and remain on the Mac. Consequently v7 is **frozen locally during preparation**, not distributed with invented checkpoint bindings. Preparation verifies the exact historical rows, checks reference dependencies and cached assets, and runs current unit tests and Docker software checks. It reuses the unchanged historical reference qualification; it does not rerun reference construction or call a model.

With Docker running and the existing environment available:

```bash
../../work/provider/venv/bin/python -m native_pilot.low_effort prepare \
  --asset-cache ../../work/source-cache
```

Preparation creates `manifests/pilot-v7.json` and `runs/qualification-low-v7.json`. Repeating preparation verifies and reuses the existing manifest. It refuses to overwrite it. Existing v1-v6 manifests and ledger attempts are not modified. Changing bound code or documentation after preparation requires inspection; do not delete evidence to bypass the check.

## Run and report

Use the Terminal session where `OPENAI_API_KEY` is already exported. The command does not require pasting the key again. On macOS, `caffeinate` keeps the machine awake while it runs:

```bash
caffeinate -i ../../work/provider/venv/bin/python -m native_pilot.low_effort run \
  --asset-cache ../../work/source-cache --allow-paid
```

The command prints a completion/accounting summary and writes `runs/low-<manifest hash>.json`. Resume with the same command; completed responses are not repeated and the budget/window remain persistent. Provider or protocol failures stop without automatic resampling. The full 200-response pilot remains blocked.

```bash
../../work/provider/venv/bin/python -m native_pilot.low_effort report
```

The public report includes response usage and grades but no prompts or encrypted native reasoning. Raw checkpoints stay in the original local ledger. No new live calls were made while implementing this follow-up; local preparation and execution are separate steps.
