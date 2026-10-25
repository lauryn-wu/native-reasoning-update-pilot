# V4 authentication recovery

The v3 initial assignment for `livecodebench:337` received HTTP 401 and produced
no response or checkpoint. Its attempt remains `provider_failure`, with its
original $0.354210 reservation, NULL reconciled charge, timestamps and request.
No transport failure is inferred. The original authorization, dispatch claim,
manifest and evidence remain unchanged. The initial no-key result in the older
v3 report predates this later Terminal attempt; the v4 recovery record documents
the newly observed state without rewriting that historical report.

The user explicitly authorized one authentication recovery, linked in
`provenance/authentication_recovery_v4.json` to the exact v3 manifest, call,
attempt and complete row hash. V4 allows a replacement initial response followed
by retained and dropped continuations from that same new checkpoint. Every task,
prompt, model setting, control, schedule, grader and analysis parameter remains
identical to v3. The 200-response pilot remains blocked.

Before real dispatch, the provider verifies the original row and reservation,
its HTTP 401 classification, absence of a response and any v3 continuation,
and both original authorization/dispatch claims. A durable recovery claim keyed
by the failed call and attempt binds the single recovery to one v4 manifest.
The v4 attempt receives its own reservation in the existing shared $40 ledger.
A subsequent authentication failure is terminal; it does not authorize another
recovery. The existing one-transport-retry rule remains separate and unchanged.
Completed v4 assignments are skipped on resume. No ledger reset or release of
the old reservation is performed.

Provider failures now always set a clear stop reason, including the safe HTTP
status when available. Resuming a failed call reports that failure without
redispatch. Missing checkpoints and exhausted transport retries also stop
explicitly. The smoke command returns success only when all three responses are
complete and protocol validation passes. Correctness does not determine success
or trigger another answer. The public summary separates known charges and
outstanding reservations.

Qualification reuses the unchanged source/reference evidence after checking its
historical hashes, all protected dependencies and all grading assets. Fresh
unit and Docker checks cover this implementation; the post-freeze wrapper binds
them to v4. Actual recovery is left to the user in Terminal, where a hidden
prompt reads the key again. The key is not written to a file or shell history.

The authentication classification follows the official
[OpenAI error-code documentation](https://developers.openai.com/api/docs/guides/error-codes).
A successful model lookup is user-reported evidence of the separately entered
key; it is not evidence that a Responses smoke call succeeded.

## Resume in this checkout

This command always asks for the key again, with hidden input. It uses a child
process environment only, preserves the existing ledger, and runs no pilot.

```sh
cd "/Users/laurynwu/Documents/Codex/2026-10-24/files-pasted-by-the-user-implement/outputs/native-reasoning-update-pilot" &&
../../work/provider/venv/bin/python -c '
import getpass, os, sys
from native_pilot.cli import main
if not sys.stdin.isatty():
    sys.exit("Run this in Terminal.")
key = getpass.getpass("OpenAI API key (hidden): ").strip()
if not key:
    sys.exit("No key entered; nothing sent.")
os.environ["OPENAI_API_KEY"] = key
raise SystemExit(main(["--manifest", "manifests/pilot-v4.json", "--asset-cache", "../../work/source-cache", "smoke", "--allow-paid"]))
'
```
