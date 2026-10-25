# Bounded four-case feasibility screen

This is a prospective exploratory subset of the already qualified task pairs:
`aime2025:1042`, `aime2025:1057`, `livecodebench:299`, and
`livecodebench:276`, in exactly that user-requested order. It is a feasibility
screen; the full 200-response study remains blocked. The task selection did not
use experimental outcomes. Each complete task record, including original,
updated and correction prompts, both graders, assets, and control flag, is copied
unchanged from v5. All four have `unchanged_control: false`.

Each task forms one contiguous seven-call block:

1. Initial response, sample 0.
2. Updated retained, sample 1.
3. Updated dropped, sample 1.
4. Fresh updated solve, sample 1.
5. Updated retained, sample 2.
6. Updated dropped, sample 2.
7. Fresh updated solve, sample 2.

The next task starts only after that block. The maximum is 28 logical calls.
Both retained/dropped samples independently replay the same original checkpoint;
none continues a previous continuation. Paired requests differ only in
`reasoning.context`. The v5 replay normalization remains unchanged: omit only a
null `status` on reasoning items in request copies, preserving raw checkpoints,
all native reasoning, order, encrypted contents, and assistant phase.

The existing v5 smoke has now passed live protocol verification. Its initial and
both continuations returned matching settings and preserved replay invariants.
The archived v5 report supplies the prerequisite evidence; its answer correctness
does not select tasks or authorize changes to this screen. No new smoke or initial
smoke answer is generated.

## Persistent limits and resuming

One stable authorization binds this screen to the frozen v6 manifest and existing
`runs/budget.sqlite`. The additional limit is **$5 charged plus reserved**, summed
across every attempt in this scope. Known charges replace their reservations;
unknown charges retain the entire reservation. A transport retry consumes a
separate reservation. Prior v3/v4/v5 charges and reservations stay in the same
ledger and count toward the shared **$40 cap**, but do not consume the new $5
allocation. No new manifest, authorization label, or resume resets these limits.

At preparation time, the existing shared ledger contains $0.041284 in known
charges and $0.880630 in outstanding reservations: $0.921914 accounted, leaving
$39.078086 unreserved. Preparing v6 makes no model calls and writes no campaign
ledger entries.

A persistent 30-minute wall-clock window starts on the first successful pilot
reservation. No new dispatch starts at or after that deadline, including retries.
Time while the process is stopped still counts; resuming does not restart the
window. An in-flight response and its grading may finish after the deadline.
The deadline is checked again immediately before provider dispatch. A backward
clock reading fails closed.

Complete task blocks receive scheduling priority, but neither budget nor deadline
is extended to finish a block. A stop can leave a partial block. Completed calls,
responses, charges, and initial checkpoints are preserved and skipped on resume.
The existing maximum of one transport retry per logical call is unchanged.
Provider or protocol errors stop further dispatch; correctness does not trigger
retry, regeneration, or selection. A response with failed protocol validation is
not silently scored as an ordinary wrong answer.

## Qualification and interpretation

The model and all settings remain unchanged: `gpt-6.1-sol`, high reasoning effort,
standard mode, default service tier, 32768 maximum output tokens, the same cache
configuration, and explicit retained/dropped context. The full historical
reference qualification is reused after verifying protected dependencies and
source/grading assets. Current software receives fresh unit, Docker, and
manifest-bound qualification checks.

Reports provide initial correctness, retained/dropped/fresh correct and graded
counts, planned and missing outcomes, complete retained/dropped sample pairs,
complete task blocks, and a separately labeled initial-correct subset. They also
show elapsed wall-clock time, the persistent deadline, known charges, outstanding
reservations, and both scope and shared budget totals. Partial coverage remains
explicit. No full-study significance gate, hypothesis test, or confirmatory
threshold is applied. A null difference in this small screen cannot rule out the
hypothesis.

## Terminal command

This prompts for the key using hidden input and keeps it in the child process
only. It uses the existing ledger and resumes the same bounded authorization.

```sh
cd "/path/to/native-reasoning-update-pilot" &&
../../work/provider/venv/bin/python -c '
import getpass, os, sys
from native_pilot.cli import main
if not sys.stdin.isatty():
    sys.exit("Run this in Terminal.")
key = getpass.getpass("OpenAI API key (hidden): ").strip()
if not key:
    sys.exit("No key entered; nothing sent.")
os.environ["OPENAI_API_KEY"] = key
raise SystemExit(main(["--manifest", "manifests/pilot-v6.json", "--asset-cache", "../../work/source-cache", "explore", "--allow-paid"]))
'
```

After a run, regenerate the descriptive report without a key or model request:

```sh
cd "/path/to/native-reasoning-update-pilot" &&
../../work/provider/venv/bin/python -m native_pilot.cli --manifest manifests/pilot-v6.json report
```
