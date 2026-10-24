# Native reasoning provider protocol

The adapter uses `gpt-6.1-sol` in the Responses API with high effort, a 32,768
output-token ceiling, standard reasoning mode, Standard service (`default`), and
`store: false`. It disables automatic input truncation and sends no temperature,
top-p, tool, or sampling overrides. A new user message applies the correction.

`build_request(task, branch, checkpoint=None, settings=None)` returns the complete
JSON request. `task` has `original_prompt`, `updated_prompt`, and optionally the
frozen `correction_prompt`. A checkpoint contains the exact original `request`
and full raw `response`. Continuations copy its entire output array after the
original input, preserving item order, opaque encrypted reasoning, assistant
phase, and all other returned fields. A continuation cannot become the next
sample's checkpoint. Fresh solves contain only the complete updated problem.

Within either updated or unchanged pairs, the sole JSON difference is
`reasoning.context`: retained uses `all_turns`, dropped uses `current_turn`.
Both requests submit the same opaque reasoning items. Dropping these items in
the client would be a different manipulation. Initial and fresh requests use
`current_turn`. Both unchanged conditions append the identical neutral request.
No request uses `previous_response_id`, a server conversation, a fabricated
assistant message, or reasoning prefill. See the official
[reasoning guide](https://developers.openai.com/api/docs/guides/reasoning).

Every response must report the requested effective context, high effort,
standard mode, the model or its dated snapshot, and Standard service tier.
Missing settings fail closed. Initial checkpoints must be complete, contain
opaque encrypted reasoning and a visible answer. Their correctness is graded
separately; an incorrect initial answer is never regenerated. Native reasoning
is opaque: presence and provider-reported settings verify the API protocol,
not the contents or causal mechanism of internal reasoning.

`validate_response(response, expected_context, require_checkpoint=False)` returns
`{"valid": bool, "errors": [...]}`. With `require_checkpoint=False`, a returned
truncation may still have a valid manipulation. Its unsuccessful operational
grade remains separate from protocol validity. `extract_visible_answer` excludes
commentary from grading while retaining it in the checkpoint. Full response
usage, status, incomplete details, model identifier, and output remain available
for the scheduler's private attempt record.

The optional SDK is pinned to `openai==3.37.0`. Its downloaded wheel and relevant
source files were inspected; their hashes and the official documentation hashes
are in `provenance/provider_docs.json`. Tests exercised actual SDK serialization
and parsing with `httpx2.MockTransport`: three local fixture responses, zero
network requests. Account access and actual service behavior remain unverified
until the separately authorized three-call paid smoke test. A failed smoke
cannot become a pilot outcome or silently change the frozen manifest.

The adapter requires `allow_paid=True`, uses the standard OpenAI endpoint, and
sets SDK `max_retries=0`. Only the scheduler may authorize one transport retry
with a separate attempt reservation. Timeouts/connections have uncertain
charges. Refusals, wrong answers, and truncations are never retried for a better
score. Exceptions contain only safe classifications and status codes, never
raw server messages, headers, credentials, or prompts.

# Pricing snapshot and cache policy

Official [model pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
and [pricing tables](https://developers.openai.com/api/docs/pricing), checked
2026-10-24, specify the following Standard rates per million tokens:

| Category | USD |
| --- | ---: |
| Ordinary input | 2.00 |
| Cached input | 0.10 |
| 30-minute cache write | 2.50 |
| 12-hour cache write | 5.00 |
| Output, including reasoning | 10.00 |

Above 272,000 input tokens the whole request uses twice the input/cache rates
and 1.5 times the output rate. Regional processing adds 10%. The adapter fixes
the standard endpoint and service, and the campaign budget gate must reserve
using the appropriate context tier. These are OpenAI-specific rates, not
another provider's cache multipliers.

All conditions set `prompt_cache_options` to `{"mode":"explicit","ttl":"30m"}`
and provide no breakpoints. The official
[caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
states that this produces no cache reads or writes. The adapter rejects
unexpected nonzero cache usage as a protocol deviation; the ledger still
accounts for the charge. The SDK currently types `ttl` as `30m` only, so no
12-hour option is sent.

For reconciliation, `input_tokens_details.cached_tokens` and
`input_tokens_details.cache_write_tokens` are distinct subsets of `input_tokens`.
Ordinary input equals input minus cached minus written. Charge each subset at
its own rate, plus `output_tokens` at the output rate. Reasoning tokens are
already part of output tokens and must not be charged twice. Missing usage
cannot release a worst-case reservation. The cap includes smoke, retry, and
uncertain attempt charges; completing 200 responses is not promised.

# Offline checks actually run

On Python 3.12, 17 provider tests passed, including paired request equivalence,
independent checkpoint branches, complete SDK replay, final-phase extraction,
invalid initial checkpoints, missing effective mode, safe failure handling,
and a required paid gate. The optional SDK test skips when the pinned SDK is
not installed. No paid protocol smoke or model call was made during implementation.
