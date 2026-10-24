"""Stateless Responses API adapter; this module makes no calls on import.

Checkpoint dictionaries are immutable by convention and copied before replay.
Never convert response.output to only output_text: opaque reasoning and assistant
phase metadata are part of the intervention's shared history.
"""
from __future__ import annotations

import copy
import importlib.metadata
import json
import logging
import os
from typing import Any, Mapping

MODEL = "gpt-6.1-sol"
SDK_VERSION = "3.37.0"
DEFAULT_SETTINGS = {
    "model": MODEL,
    "reasoning_effort": "high",
    "max_output_tokens": 32768,
}
UNCHANGED_REQUEST = (
    "Please solve the same original problem again. Its statement and requirements "
    "are unchanged. Give your final answer in the originally requested format."
)
BRANCHES = {
    "initial", "fresh", "updated_retained", "updated_dropped",
    "unchanged_retained", "unchanged_dropped",
}


class ProtocolError(ValueError):
    """An invalid request/checkpoint; never a scored model answer."""


class ProviderFailure(RuntimeError):
    """Safe exception metadata; deliberately excludes server bodies/credentials."""

    def __init__(self, kind: str, *, retryable: bool = False,
                 uncertain_charge: bool = True, status_code: int | None = None):
        self.kind = kind
        self.retryable = retryable
        self.uncertain_charge = uncertain_charge
        self.status_code = status_code
        super().__init__(kind)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "retryable": self.retryable,
                "uncertain_charge": self.uncertain_charge,
                "status_code": self.status_code}


def _text(task: Mapping, key: str) -> str:
    value = task.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f"Missing nonempty task field: {key}")
    return value


def _settings(settings: Mapping | None) -> dict:
    result = copy.deepcopy(DEFAULT_SETTINGS)
    if settings is not None:
        if not isinstance(settings, Mapping):
            raise ProtocolError("Settings must be an object")
        if set(settings) - set(DEFAULT_SETTINGS):
            raise ProtocolError("Unknown model setting")
        result.update(settings)
    if result["model"] != MODEL or result["reasoning_effort"] != "high":
        raise ProtocolError("Frozen pilot requires gpt-6.1-sol at high effort")
    if result["max_output_tokens"] != 32768:
        raise ProtocolError("Frozen pilot requires 32768 maximum output tokens")
    return result


def build_request(task: Mapping, branch: str, checkpoint: Mapping | None = None,
                  settings: Mapping | None = None) -> dict:
    """Build one independent request; the only paired difference is context.

    A checkpoint is exactly {'request': initial_request, 'response': raw_response}.
    Sample number is deliberately absent: both repeats use this same checkpoint.
    """
    config = _settings(settings)
    if branch not in BRANCHES:
        raise ProtocolError("Unknown branch")
    context = "all_turns" if branch.endswith("_retained") else "current_turn"
    if branch in {"initial", "fresh"}:
        if checkpoint is not None:
            raise ProtocolError("Initial/fresh requests must not contain history")
        prompt = _text(task, "original_prompt" if branch == "initial" else "updated_prompt")
        history = [{"role": "user", "content": prompt}]
    else:
        if not isinstance(checkpoint, Mapping):
            raise ProtocolError("Continuation requires an initial checkpoint")
        initial_request = build_request(task, "initial", settings=config)
        if checkpoint.get("request") != initial_request:
            raise ProtocolError("Checkpoint is not this task's frozen initial request")
        response = checkpoint.get("response")
        result = validate_response(response, "current_turn", require_checkpoint=True)
        if not result["valid"]:
            raise ProtocolError("Unusable initial checkpoint: " + "; ".join(result["errors"]))
        history = copy.deepcopy(initial_request["input"])
        history.extend(copy.deepcopy(response["output"]))
        if branch.startswith("unchanged_"):
            followup = UNCHANGED_REQUEST
        else:
            followup = task.get("correction_prompt")
            if followup is None:
                followup = (
                    "Correction: the problem is now as follows. Please solve the "
                    "updated problem and give your final answer in its requested format.\n\n"
                    + _text(task, "updated_prompt")
                )
            if not isinstance(followup, str) or not followup.strip():
                raise ProtocolError("Correction must be a nonempty ordinary user message")
        history.append({"role": "user", "content": followup})
    return {
        "model": config["model"], "store": False, "input": history,
        "reasoning": {"effort": config["reasoning_effort"], "context": context,
                      "mode": "standard"},
        "max_output_tokens": config["max_output_tokens"],
        "service_tier": "default", "truncation": "disabled",
        "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
        "include": ["reasoning.encrypted_content"],
    }


def extract_visible_answer(response: Mapping) -> str:
    """Read final assistant text only; commentary is kept for replay, not grading."""
    if not isinstance(response, Mapping):
        return ""
    output = response.get("output")
    if not isinstance(output, list):
        return ""
    messages = [item for item in output
                if isinstance(item, Mapping) and item.get("type") == "message"
                and item.get("role") == "assistant"
                and item.get("phase") in {None, "final_answer"}
                and isinstance(item.get("content"), list)]
    return "\n".join(block["text"] for item in messages
                     for block in item.get("content", [])
                     if isinstance(block, Mapping) and block.get("type") == "output_text"
                     and isinstance(block.get("text"), str))


def validate_response(response: Any, expected_context: str,
                      require_checkpoint: bool = False) -> dict:
    """Verify observed protocol, independently of semantic answer correctness.

    Returned incomplete answers can be protocol-valid and score as unsuccessful.
    An initial checkpoint additionally must be a completed response with usable
    opaque reasoning and a visible answer. No regeneration is permitted.
    """
    errors: list[str] = []
    if not isinstance(response, Mapping):
        return {"valid": False, "errors": ["Response is not an object"]}
    if expected_context not in {"current_turn", "all_turns"}:
        errors.append("Invalid expected context")
    reasoning = response.get("reasoning")
    if not isinstance(reasoning, Mapping):
        errors.append("Missing returned reasoning settings")
    else:
        if reasoning.get("context") != expected_context:
            errors.append("Effective reasoning context missing or mismatched")
        if reasoning.get("effort") != "high":
            errors.append("Effective reasoning effort missing or mismatched")
        if reasoning.get("mode") != "standard":
            errors.append("Effective reasoning mode missing or mismatched")
    model = response.get("model")
    if not isinstance(model, str) or not (model == MODEL or model.startswith(MODEL + "-")):
        errors.append("Returned model does not match frozen model family")
    if response.get("service_tier") != "default":
        errors.append("Effective service tier missing or nonstandard")
    if response.get("status") not in {"completed", "incomplete", "failed", "cancelled"}:
        errors.append("Missing or nonterminal response status")
    if not isinstance(response.get("id"), str) or not response["id"]:
        errors.append("Missing response identifier")
    output = response.get("output")
    if not isinstance(output, list) or any(not isinstance(i, Mapping) for i in output):
        errors.append("Malformed response output")
        output = []
    for item in output:
        if not isinstance(item.get("type"), str):
            errors.append("Output item has no type")
        if item.get("type") == "message":
            if item.get("phase") not in {None, "commentary", "final_answer"}:
                errors.append("Unknown assistant phase")
            if not isinstance(item.get("content"), list):
                errors.append("Malformed assistant message")
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        errors.append("Missing usage; charge is uncertain")
    else:
        def count(value: Any) -> bool:
            return type(value) is int and value >= 0
        tokens_ok = all(count(usage.get(k)) for k in ("input_tokens", "output_tokens", "total_tokens"))
        if not tokens_ok:
            errors.append("Malformed token usage")
        elif usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
            errors.append("Inconsistent total token usage")
        details = usage.get("input_tokens_details")
        if not isinstance(details, Mapping) or not all(count(details.get(k)) for k in ("cached_tokens", "cache_write_tokens")):
            errors.append("Missing or malformed cache usage")
        elif details["cached_tokens"] or details["cache_write_tokens"]:
            errors.append("Unexpected cache usage under explicit mode without breakpoints")
        out_details = usage.get("output_tokens_details")
        if not isinstance(out_details, Mapping) or not count(out_details.get("reasoning_tokens")):
            errors.append("Missing or malformed reasoning usage")
        elif tokens_ok and out_details["reasoning_tokens"] > usage["output_tokens"]:
            errors.append("Reasoning tokens exceed total output tokens")
    if require_checkpoint:
        if response.get("status") != "completed":
            errors.append("Initial response did not complete")
        if not any(item.get("type") == "reasoning"
                   and isinstance(item.get("encrypted_content"), str)
                   and item["encrypted_content"].strip() for item in output):
            errors.append("No usable encrypted native reasoning item")
        try:
            answer = extract_visible_answer(response)
        except (TypeError, KeyError):
            answer = ""
        if not answer.strip():
            errors.append("Initial checkpoint has no visible final answer")
    return {"valid": not errors, "errors": errors}


def _validate_dispatch_request(request: Mapping) -> None:
    required = {"model", "store", "input", "reasoning", "max_output_tokens",
                "service_tier", "truncation", "prompt_cache_options", "include"}
    if set(request) != required:
        raise ProtocolError("Unexpected request keys; manual history only")
    expected = build_request({"original_prompt": "validation"}, "initial")
    for field in required - {"input", "reasoning"}:
        if request[field] != expected[field]:
            raise ProtocolError("Request differs from frozen provider configuration")
    reasoning = copy.deepcopy(request["reasoning"])
    if not isinstance(reasoning, dict) or reasoning.pop("context", None) not in {"all_turns", "current_turn"}:
        raise ProtocolError("Invalid explicit reasoning context")
    if reasoning != {"effort": "high", "mode": "standard"}:
        raise ProtocolError("Invalid reasoning settings")
    if not isinstance(request["input"], list) or not request["input"]:
        raise ProtocolError("Manual input history must be nonempty")
    def has_breakpoint(value: Any) -> bool:
        if isinstance(value, dict):
            return "prompt_cache_breakpoint" in value or any(has_breakpoint(v) for v in value.values())
        return isinstance(value, list) and any(has_breakpoint(v) for v in value)
    if has_breakpoint(request["input"]):
        raise ProtocolError("Frozen protocol disables cache breakpoints")


class OpenAIProvider:
    """Optional SDK backend with an explicit paid gate and no implicit retries."""

    def __init__(self, *, allow_paid: bool = False, client: Any = None):
        if allow_paid is not True:
            raise ProviderFailure("paid_execution_not_authorized", uncertain_charge=False)
        if client is not None:  # Injection for offline tests; no SDK/network required.
            self.client = client
            return
        try:
            version = importlib.metadata.version("openai")
        except importlib.metadata.PackageNotFoundError:
            raise ProviderFailure("pinned_sdk_not_installed", uncertain_charge=False) from None
        if version != SDK_VERSION:
            raise ProviderFailure("sdk_version_mismatch", uncertain_charge=False)
        if not os.environ.get("OPENAI_API_KEY"):
            raise ProviderFailure("api_key_unavailable", uncertain_charge=False)
        from openai import OpenAI, DefaultHttpxClient
        # Do this after SDK import, which can configure OPENAI_LOG. Ancestor
        # disabled flags alone do not suppress a child's propagated records.
        roots = ("openai", "httpx", "httpcore", "httpx2", "httpcore2")
        names = set(roots) | {name for name in logging.Logger.manager.loggerDict
                             if any(name.startswith(root + ".") for root in roots)}
        for name in names:
            logger = logging.getLogger(name)
            logger.disabled = True
            logger.setLevel(logging.CRITICAL + 1)
        self.client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url="https://api.openai.com/v1", max_retries=0,
            timeout=600.0, http_client=DefaultHttpxClient(trust_env=False),
        )

    def create(self, request: Mapping) -> dict:
        _validate_dispatch_request(request)
        try:
            response = self.client.responses.create(**copy.deepcopy(dict(request)))
            data = response if isinstance(response, dict) else response.model_dump(mode="json")
            # A JSON copy prevents SDK/private objects leaking into persisted state.
            return json.loads(json.dumps(data, ensure_ascii=False))
        except Exception as exc:
            name = type(exc).__name__
            if name in {"APITimeoutError", "APIConnectionError", "TimeoutError", "ConnectionError"}:
                raise ProviderFailure("transport_failure", retryable=True,
                                      uncertain_charge=True) from None
            status = getattr(exc, "status_code", None)
            status = status if type(status) is int else None
            if status in {400, 422}:
                raise ProviderFailure("protocol_failure", status_code=status,
                                      uncertain_charge=False) from None
            # No retry of provider rejections, semantic failures, or truncations.
            raise ProviderFailure("provider_failure", status_code=status,
                                  uncertain_charge=status is None or status >= 500) from None
