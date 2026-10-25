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
import re
from pathlib import Path
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
ROOT = Path(__file__).resolve().parents[2]
SMOKE_MANIFEST_PATH = ROOT / "manifests/pilot-v5.json"
SHARED_LEDGER_PATH = ROOT / "runs/budget.sqlite"
SMOKE_AUTHORIZATION = {
    "allowed": True,
    "task_id": "livecodebench:337",
    "authorization_id": "user-2026-10-24-continuation-recovery-smoke-v5",
    "max_logical_calls": 2,
    "max_transport_retries_per_call": 1,
    "shared_budget_usd": 40,
    "manifest_version": "pilot-v5",
    "max_continuation_recoveries": 1,
    "initial_generation_allowed": False,
}
AUTHENTICATION_RECOVERY_PATH = "provenance/authentication_recovery_v4.json"
AUTHENTICATION_RECOVERY = {
    "failed_manifest_sha256": "2b93bc0d231cc435c2e2ebc792f36f75f7f7280f1828d4250fc05bd8c4a46e28",
    "failed_call_id": "2b93bc0d231cc435c2e2ebc792f36f75f7f7280f1828d4250fc05bd8c4a46e28/smoke/livecodebench:337/initial/0",
    "failed_attempt": 1,
    "failed_attempt_sha256": "837396fed306676e968c1da846b2059c1dd1ad97d2904db4cfafcbb1f5665c0a",
    "failed_authorization_id": "user-2026-10-24-three-call-smoke-v3",
    "retained_reservation_micro_usd": 354210,
    "required_http_status": 401,
    "max_recoveries": 1,
    "recovery_condition": "initial",
}
CONTINUATION_RECOVERY_PATH = "provenance/continuation_recovery_v5.json"
CONTINUATION_RECOVERY = {
    "prior_manifest_sha256": "4577e945a7df5ac5823b4dc02532c782daf69771ae1ea8a37bfdd591234a004f",
    "initial_call_id": "4577e945a7df5ac5823b4dc02532c782daf69771ae1ea8a37bfdd591234a004f/smoke/livecodebench:337/initial/0",
    "initial_attempt": 1,
    "initial_attempt_sha256": "76efa8d8d8708a4f518524bf26ace0ed9480aacf80156a01cdc1a849e5dbe016",
    "initial_response_sha256": "4ec551c960e1ee21c6bfb0902ae70a52ec74ba43c714da1b27dde1a3f23706e5",
    "initial_checkpoint_sha256": "39c6528a75d1016a7196f22165fec99476a871aeafd91a99ed8f38ea9171f961",
    "failed_call_id": "4577e945a7df5ac5823b4dc02532c782daf69771ae1ea8a37bfdd591234a004f/smoke/livecodebench:337/updated_retained/1",
    "failed_attempt": 1,
    "failed_attempt_sha256": "21990bfcc5c4cbcd5fe6b8332b2f6fde85a2a0635f0ac3bf62660d3953146224",
    "prior_authorization_id": "user-2026-10-24-auth-recovery-smoke-v4",
    "required_http_status": 400,
    "max_recoveries": 1,
}


class ProtocolError(ValueError):
    """An invalid request/checkpoint; never a scored model answer."""


class ProviderFailure(RuntimeError):
    """Safe exception metadata; deliberately excludes server bodies/credentials."""

    def __init__(self, kind: str, *, retryable: bool = False,
                 uncertain_charge: bool = True, status_code: int | None = None,
                 api_error: dict | None = None):
        self.kind = kind
        self.retryable = retryable
        self.uncertain_charge = uncertain_charge
        self.status_code = status_code
        self.api_error = copy.deepcopy(api_error)
        super().__init__(kind)

    def as_dict(self) -> dict:
        result = {"kind": self.kind, "retryable": self.retryable,
                "uncertain_charge": self.uncertain_charge,
                "status_code": self.status_code}
        if self.api_error is not None:
            result["api_error"] = copy.deepcopy(self.api_error)
        return result


def sanitize_api_error(exc, status_code=None) -> dict:
    """Retain structural API diagnostics without copying free-form server text."""
    body = getattr(exc, "body", None)
    data = body.get("error", body) if isinstance(body, Mapping) else {}
    data = data if isinstance(data, Mapping) else {}
    types = {"invalid_request_error", "authentication_error", "permission_error",
             "rate_limit_error", "server_error", "api_error", "not_found_error"}
    codes = {"invalid_api_key", "invalid_value", "invalid_type", "invalid_parameter",
             "invalid_request_error", "unsupported_value", "unsupported_parameter",
             "unknown_parameter", "missing_required_parameter", "missing_required_field",
             "context_length_exceeded", "model_not_found", "rate_limit_exceeded",
             "insufficient_quota", "permission_denied", "invalid_json", "server_error"}
    def identifier(field, allowed):
        value = data.get(field, getattr(exc, field, None))
        return value if isinstance(value, str) and len(value) <= 64 and value in allowed else None
    error_type, code = identifier("type", types), identifier("code", codes)
    param = data.get("param", getattr(exc, "param", None))
    roots = "input|reasoning|model|max_output_tokens|store|include|service_tier|truncation|prompt_cache_options"
    fields = "status|type|role|phase|content|text|summary|encrypted_content|effort|context|mode|ttl"
    if (not isinstance(param, str) or len(param) > 128 or not re.fullmatch(
            rf"(?:{roots})(?:(?:\[[0-9]{{1,4}}\])|(?:\.(?:{fields}))){{0,8}}", param)):
        param = None
    message = data.get("message")
    # Inspect bounded text solely to select a fixed explanation. No substring,
    # quoted value, URL, header, key, prompt, or ciphertext is ever emitted.
    message = message[:8192].lower() if isinstance(message, str) else ""
    if status_code == 401 or code == "invalid_api_key" or error_type == "authentication_error":
        explanation = "Provider rejected authentication; credential details omitted."
    elif param and param.endswith(".status") and re.search(r"\b(null|none)\b", message) and any(
            word in message for word in ("invalid", "expected", "must", "not allowed", "unsupported")):
        explanation = "Provider rejected a null status value in an input item; other supplied values omitted."
    elif "unsupported" in message or code in {"unsupported_value", "unsupported_parameter"}:
        explanation = "Provider reported an unsupported parameter or value; supplied values omitted."
    elif "unknown parameter" in message or code == "unknown_parameter":
        explanation = "Provider reported an unknown parameter; supplied values omitted."
    elif "required" in message or code in {"missing_required_parameter", "missing_required_field"}:
        explanation = "Provider reported a missing required field; supplied values omitted."
    elif "invalid type" in message or "expected" in message or code == "invalid_type":
        explanation = "Provider reported a parameter type mismatch; supplied values omitted."
    elif "invalid" in message or code in {"invalid_value", "invalid_parameter", "invalid_json"}:
        explanation = "Provider rejected a parameter value or request format; supplied values omitted."
    else:
        explanation = "Provider request failed; unrecognized free-form details omitted."
    result = {"type":error_type, "code":code, "param":param, "explanation":explanation}
    if param and param.endswith('.status') and any(word in message for word in ('supported','expected','one of')):
        values = [value for value in ('in_progress','completed','incomplete')
                  if re.search(r'\b'+value+r'\b',message)]
        if values:
            result['recognized_status_values'] = values
    return result


def normalize_replay_output(output):
    """Copy output and omit only null status on reasoning items for API replay."""
    normalized = copy.deepcopy(output)
    for item in normalized:
        if isinstance(item, dict) and item.get("type") == "reasoning" and item.get("status") is None:
            item.pop("status", None)
    return normalized


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
        history = []
        if task.get('output_instructions'):
            history.append({'role':'developer','content':_text(task,'output_instructions')})
        history.append({"role": "user", "content": prompt})
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
        history.extend(normalize_replay_output(response["output"]))
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


def _read_execution_policy() -> dict:
    policy_path = Path(__file__).resolve().parents[2] / "provenance/execution_policy.json"
    try:
        policy = json.loads(policy_path.read_text())
    except (OSError, ValueError):
        raise ProviderFailure("execution_policy_missing", uncertain_charge=False) from None
    if not isinstance(policy, dict):
        raise ProviderFailure("execution_policy_missing", uncertain_charge=False)
    return policy


def _read_frozen_smoke_manifest() -> dict:
    """Verify current files and qualification, even for direct library clients."""
    from .manifest import load_manifest, paid_preflight
    try:
        manifest = load_manifest(SMOKE_MANIFEST_PATH)
        qualification = json.loads((ROOT / "runs" /
            ("qualification-" + manifest["manifest_sha256"] + ".json")).read_text())
        paid_preflight(manifest, qualification, smoke=True)
        return manifest
    except (OSError, ValueError, KeyError, TypeError):
        raise ProviderFailure("frozen_smoke_qualification_unverified", uncertain_charge=False) from None


def _read_authentication_recovery_record(manifest) -> dict:
    """Read immutable public lineage; its hash is frozen twice in the manifest."""
    from .util import file_digest
    descriptor = manifest.get("authentication_recovery")
    path = ROOT / AUTHENTICATION_RECOVERY_PATH
    try:
        if (not isinstance(descriptor, Mapping) or set(descriptor) != {"path", "sha256"} or
                descriptor["path"] != AUTHENTICATION_RECOVERY_PATH or
                descriptor["sha256"] != file_digest(path) or
                manifest.get("provenance_hashes", {}).get(AUTHENTICATION_RECOVERY_PATH) != descriptor["sha256"]):
            raise ValueError("Recovery descriptor mismatch")
        record = json.loads(path.read_text())
        if not isinstance(record, dict) or record.get("recovery") != AUTHENTICATION_RECOVERY:
            raise ValueError("Recovery authorization mismatch")
        return record["recovery"]
    except (OSError, ValueError, TypeError, KeyError):
        raise ProviderFailure("authentication_recovery_record_unverified", uncertain_charge=False) from None


def _verify_authentication_recovery(manifest, ledger) -> str:
    """Verify the preserved 401 without rewriting it or treating it as transport."""
    from .util import canonical, digest
    recovery = _read_authentication_recovery_record(manifest)
    if recovery != AUTHENTICATION_RECOVERY:
        raise ProviderFailure("authentication_recovery_record_unverified", uncertain_charge=False)
    prior = ledger.rows(recovery["failed_manifest_sha256"])
    if len(prior) != 1:
        raise ProviderFailure("authentication_recovery_predecessor_changed", uncertain_charge=False)
    failed = prior[0]
    if (failed["call_id"] != recovery["failed_call_id"] or
            failed["attempt"] != recovery["failed_attempt"] or
            digest(failed) != recovery["failed_attempt_sha256"] or
            failed["state"] != "provider_failure" or failed["kind"] != "smoke" or
            failed["error_kind"] != "provider_failure" or failed["response"] is not None or
            failed["charged"] is not None or failed["reserved"] != recovery["retained_reservation_micro_usd"]):
        raise ProviderFailure("authentication_recovery_predecessor_changed", uncertain_charge=False)
    try:
        outcome = json.loads(failed["outcome"])
        if (outcome.get("status") != "provider_failure" or outcome.get("condition") != "initial" or
                outcome.get("provider_error") != {"kind":"provider_failure", "retryable":False,
                    "uncertain_charge":False, "status_code":recovery["required_http_status"]}):
            raise ValueError("Not the authorized authentication failure")
    except (TypeError, ValueError, AttributeError):
        raise ProviderFailure("authentication_recovery_predecessor_changed", uncertain_charge=False) from None
    expected = build_request(manifest["smoke_task"], "initial", settings=manifest["settings"])
    if failed["request"] != canonical(expected).decode():
        raise ProviderFailure("authentication_recovery_request_changed", uncertain_charge=False)
    required_claims = ("execution_authorization/" + recovery["failed_authorization_id"],
                       "provider_dispatch/" + recovery["failed_call_id"] + "/" + str(recovery["failed_attempt"]))
    for key in required_claims:
        claim = ledger.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if not claim or claim[0] != recovery["failed_manifest_sha256"]:
            raise ProviderFailure("authentication_recovery_prior_authorization_changed", uncertain_charge=False)
    # Key by the failed assignment, not the new authorization ID: a new label or
    # manifest cannot reset the one permitted authentication recovery.
    return "authentication_recovery/" + recovery["failed_call_id"] + "/" + str(recovery["failed_attempt"])


def _read_continuation_recovery_record(manifest) -> dict:
    from .util import file_digest
    descriptor = manifest.get("continuation_recovery")
    path = ROOT / CONTINUATION_RECOVERY_PATH
    try:
        if (not isinstance(descriptor, Mapping) or set(descriptor) != {"path", "sha256"} or
                descriptor["path"] != CONTINUATION_RECOVERY_PATH or
                descriptor["sha256"] != file_digest(path) or
                manifest.get("provenance_hashes", {}).get(CONTINUATION_RECOVERY_PATH) != descriptor["sha256"]):
            raise ValueError("Continuation recovery descriptor mismatch")
        record = json.loads(path.read_text())
        if not isinstance(record, dict) or record.get("recovery") != CONTINUATION_RECOVERY:
            raise ValueError("Continuation recovery authorization mismatch")
        return record["recovery"]
    except (OSError, ValueError, TypeError, KeyError):
        raise ProviderFailure("continuation_recovery_record_unverified", uncertain_charge=False) from None


def _read_continuation_prior_manifest(manifest) -> dict:
    """Load the hash-bound v4 manifest solely as preserved historical evidence."""
    from .manifest import load_manifest
    from .util import file_digest
    recovery = _read_continuation_recovery_record(manifest)
    try:
        record = json.loads((ROOT / CONTINUATION_RECOVERY_PATH).read_text())
        descriptor = record["prior_manifest"]
        path = ROOT / "manifests/pilot-v4.json"
        if (descriptor.get("path") != "manifests/pilot-v4.json" or
                descriptor.get("sha256") != file_digest(path)):
            raise ValueError("Historical manifest file mismatch")
        prior = load_manifest(path, verify_files=False)
        if (prior.get("manifest_sha256") != recovery["prior_manifest_sha256"] or
                descriptor.get("manifest_sha256") != prior["manifest_sha256"] or
                prior.get("version") != "pilot-v4" or
                prior.get("protocol_smoke_authorization", {}).get("authorization_id") != recovery["prior_authorization_id"] or
                prior["smoke_task"] != manifest["smoke_task"] or prior["settings"] != manifest["settings"]):
            raise ValueError("Historical checkpoint design mismatch")
        return prior
    except (OSError, ValueError, TypeError, KeyError):
        raise ProviderFailure("continuation_recovery_prior_manifest_unverified", uncertain_charge=False) from None


def _verify_continuation_recovery(manifest, ledger) -> str:
    """Read-only verification of the unchanged v3 and v4 history and raw checkpoint."""
    from .util import canonical, digest
    historical_manifest = _read_continuation_prior_manifest(manifest)
    authentication_binding = _verify_authentication_recovery(historical_manifest, ledger)
    recovery = _read_continuation_recovery_record(manifest)
    if recovery != CONTINUATION_RECOVERY:
        raise ProviderFailure("continuation_recovery_record_unverified", uncertain_charge=False)
    prior = ledger.rows(recovery["prior_manifest_sha256"])
    by_call = {row["call_id"]:row for row in prior}
    if len(prior) != 2 or set(by_call) != {recovery["initial_call_id"], recovery["failed_call_id"]}:
        raise ProviderFailure("continuation_recovery_predecessor_changed", uncertain_charge=False)
    initial, failed = by_call[recovery["initial_call_id"]], by_call[recovery["failed_call_id"]]
    if (initial["attempt"] != recovery["initial_attempt"] or
            digest(initial) != recovery["initial_attempt_sha256"] or initial["state"] != "completed" or
            initial["kind"] != "smoke" or not initial["response"] or type(initial["charged"]) is not int or
            failed["attempt"] != recovery["failed_attempt"] or digest(failed) != recovery["failed_attempt_sha256"] or
            failed["state"] != "provider_failure" or failed["kind"] != "smoke" or
            failed["error_kind"] != "protocol_failure" or failed["response"] is not None or failed["charged"] is not None):
        raise ProviderFailure("continuation_recovery_predecessor_changed", uncertain_charge=False)
    try:
        checkpoint = {"request":json.loads(initial["request"]), "response":json.loads(initial["response"])}
        failure = json.loads(failed["outcome"])
        if (digest(checkpoint["response"]) != recovery["initial_response_sha256"] or
                digest(checkpoint) != recovery["initial_checkpoint_sha256"] or
                not validate_response(checkpoint["response"], "current_turn", require_checkpoint=True)["valid"] or
                failure.get("status") != "protocol_failure" or
                failure.get("provider_error") != {"kind":"protocol_failure", "retryable":False,
                    "uncertain_charge":False, "status_code":recovery["required_http_status"]}):
            raise ValueError("Invalid inherited checkpoint or prior protocol failure")
    except (TypeError, ValueError, AttributeError):
        raise ProviderFailure("continuation_recovery_predecessor_changed", uncertain_charge=False) from None
    if checkpoint["request"] != build_request(manifest["smoke_task"], "initial", settings=manifest["settings"]):
        raise ProviderFailure("continuation_recovery_request_changed", uncertain_charge=False)
    historical = build_request(manifest["smoke_task"], "updated_retained", checkpoint, manifest["settings"])
    historical["input"] = (copy.deepcopy(checkpoint["request"]["input"]) +
                           copy.deepcopy(checkpoint["response"]["output"]) + historical["input"][-1:])
    if failed["request"] != canonical(historical).decode():
        raise ProviderFailure("continuation_recovery_request_changed", uncertain_charge=False)
    required_claims = (authentication_binding,
        "execution_authorization/" + recovery["prior_authorization_id"],
        "provider_dispatch/" + recovery["initial_call_id"] + "/" + str(recovery["initial_attempt"]),
        "provider_dispatch/" + recovery["failed_call_id"] + "/" + str(recovery["failed_attempt"]))
    for key in required_claims:
        claim = ledger.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if not claim or claim[0] != recovery["prior_manifest_sha256"]:
            raise ProviderFailure("continuation_recovery_prior_authorization_changed", uncertain_charge=False)
    return "continuation_recovery/" + recovery["failed_call_id"] + "/" + str(recovery["failed_attempt"])


def _require_paid_execution_policy(*, execution_scope=None, manifest=None,
                                   ledger=None, campaign_guard=None,
                                   request=None, execution_context=None) -> None:
    """Authorize only two remaining forks from the pinned v4 initial checkpoint.

    A stable authorization is durably bound to one verified manifest and the
    repository-wide ledger. Each dispatched attempt gets a unique claim before
    contacting the SDK, including when a client was injected by a caller.
    """
    policy = _read_execution_policy()
    if (execution_scope != "protocol_smoke" or
            policy.get("paid_execution_allowed") is not False or
            policy.get("protocol_smoke") != SMOKE_AUTHORIZATION):
        raise ProviderFailure("paid_execution_policy_hold", uncertain_charge=False)
    frozen = _read_frozen_smoke_manifest()
    if (not isinstance(manifest, Mapping) or manifest != frozen or
            frozen.get("version") != SMOKE_AUTHORIZATION["manifest_version"] or
            frozen.get("protocol_smoke_authorization") != SMOKE_AUTHORIZATION or
            frozen.get("paid_execution_allowed") is not False or
            frozen.get("status") != "frozen" or frozen.get("blockers") or
            frozen.get("hard_budget_usd") != 40 or
            frozen.get("smoke_task", {}).get("task_id") != SMOKE_AUTHORIZATION["task_id"]):
        raise ProviderFailure("smoke_manifest_not_authorized", uncertain_charge=False)
    from .budget import CAP_MICRO_USD, Ledger, reservation
    from .runner import continuation_schedule, require_campaign_lock
    from .util import canonical
    if not isinstance(ledger, Ledger) or ledger.path.resolve() != SHARED_LEDGER_PATH.resolve():
        raise ProviderFailure("shared_budget_ledger_required", uncertain_charge=False)
    try:
        require_campaign_lock(campaign_guard, ledger)
    except RuntimeError:
        raise ProviderFailure("active_campaign_lock_required", uncertain_charge=False) from None
    databases = ledger.db.execute("PRAGMA database_list").fetchall()
    if not any(row[1] == "main" and Path(row[2]).resolve() == SHARED_LEDGER_PATH.resolve()
               for row in databases):
        raise ProviderFailure("shared_budget_ledger_required", uncertain_charge=False)
    manifest_hash = frozen["manifest_sha256"]
    binding = "execution_authorization/" + SMOKE_AUTHORIZATION["authorization_id"]
    recovery_binding = _verify_continuation_recovery(frozen, ledger)
    with ledger.transaction():
        for key in (binding, recovery_binding):
            ledger.db.execute("INSERT OR IGNORE INTO meta VALUES (?,?)", (key, manifest_hash))
            if ledger.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()[0] != manifest_hash:
                raise ProviderFailure("smoke_authorization_already_bound", uncertain_charge=False)
    if request is None:
        return
    required = {"manifest_sha256", "task_id", "call_id", "condition", "sample", "attempt"}
    if not isinstance(execution_context, Mapping) or set(execution_context) != required:
        raise ProviderFailure("scoped_dispatch_metadata_required", uncertain_charge=False)
    context = execution_context
    schedule = continuation_schedule(frozen["smoke_task"])
    allowed = {manifest_hash + "/" + call["call_id"]: call for call in schedule}
    call = allowed.get(context["call_id"])
    if (call is None or context["manifest_sha256"] != manifest_hash or
            any(context[key] != call[key] for key in ("task_id", "condition", "sample")) or
            type(context["attempt"]) is not int or context["attempt"] not in (1, 2)):
        raise ProviderFailure("smoke_call_not_authorized", uncertain_charge=False)
    recovery = _read_continuation_recovery_record(frozen)
    initial = ledger.latest(recovery["initial_call_id"])
    checkpoint = {"request": json.loads(initial["request"]),
                  "response": json.loads(initial["response"])}
    expected = build_request(frozen["smoke_task"], call["condition"], checkpoint, frozen["settings"])
    if request != expected:
        raise ProviderFailure("smoke_request_not_frozen", uncertain_charge=False)
    row = ledger.latest(context["call_id"])
    if (not row or row["state"] != "dispatched" or row["attempt"] != context["attempt"] or
            row["manifest_hash"] != manifest_hash or row["kind"] != "smoke" or
            row["request"] != canonical(request).decode() or
            row["reserved"] < reservation(request, checkpoint)["micro_usd"] or
            ledger.total() > CAP_MICRO_USD):
        raise ProviderFailure("smoke_dispatch_reservation_required", uncertain_charge=False)
    prior_rows = ledger.rows(manifest_hash)
    if any(prior["call_id"] not in allowed for prior in prior_rows):
        raise ProviderFailure("smoke_ledger_contains_unauthorized_calls", uncertain_charge=False)
    if context["attempt"] == 2 and not any(
            prior["call_id"] == context["call_id"] and prior["attempt"] == 1 and
            prior["state"] == "transport_uncertain" for prior in prior_rows):
        raise ProviderFailure("smoke_transport_retry_not_authorized", uncertain_charge=False)
    for prior in prior_rows:
        status = json.loads(prior["outcome"]).get("status") if prior["outcome"] else None
        if status == "protocol_failure":
            raise ProviderFailure("smoke_stopped_after_protocol_failure", uncertain_charge=False)
        if prior["state"] == "provider_failure" or status == "provider_failure":
            raise ProviderFailure("smoke_stopped_after_provider_failure", uncertain_charge=False)
    claim = "provider_dispatch/" + context["call_id"] + "/" + str(context["attempt"])
    with ledger.transaction():
        if ledger.db.execute("SELECT value FROM meta WHERE key=?", (claim,)).fetchone():
            raise ProviderFailure("smoke_attempt_already_dispatched", uncertain_charge=False)
        ledger.db.execute("INSERT INTO meta VALUES (?,?)", (claim, manifest_hash))


class OpenAIProvider:
    """Optional SDK backend with an explicit paid gate and no implicit retries."""

    def __init__(self, *, allow_paid: bool = False, client: Any = None,
                 execution_scope=None, manifest=None, ledger=None, campaign_guard=None):
        if allow_paid is not True:
            raise ProviderFailure("paid_execution_not_authorized", uncertain_charge=False)
        # A user hold applies to every client, including injected SDK clients.
        self.execution_scope = execution_scope
        self.manifest = copy.deepcopy(manifest)
        self.ledger = ledger
        self.campaign_guard = campaign_guard
        _require_paid_execution_policy(execution_scope=execution_scope,
            manifest=self.manifest, ledger=ledger, campaign_guard=campaign_guard)
        if client is not None:
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

    def authorize_schedule(self, manifest, ledger, schedule, tasks, *, execution_scope,
                           campaign_guard=None):
        """Reject new initial/fresh calls or changed forks before reserving a call."""
        from .runner import continuation_schedule
        if (execution_scope != "protocol_smoke" or execution_scope != self.execution_scope or
                manifest != self.manifest or ledger is not self.ledger or
                campaign_guard is not self.campaign_guard or
                schedule != continuation_schedule(manifest["smoke_task"]) or
                [task.get("task_id") for task in tasks] != [SMOKE_AUTHORIZATION["task_id"]]):
            raise ProviderFailure("smoke_schedule_not_authorized", uncertain_charge=False)
        _require_paid_execution_policy(execution_scope=self.execution_scope,
            manifest=self.manifest, ledger=self.ledger, campaign_guard=self.campaign_guard)

    def create(self, request: Mapping, *, execution_context=None) -> dict:
        # Re-read before each dispatch so retaining an instance cannot bypass a
        # hold that was reinstated after construction.
        _validate_dispatch_request(request)
        _require_paid_execution_policy(execution_scope=self.execution_scope,
            manifest=self.manifest, ledger=self.ledger, campaign_guard=self.campaign_guard, request=request,
            execution_context=execution_context)
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
                                      uncertain_charge=False, api_error=sanitize_api_error(exc, status)) from None
            # No retry of provider rejections, semantic failures, or truncations.
            raise ProviderFailure("provider_failure", status_code=status,
                                  uncertain_charge=status is None or status >= 500,
                                  api_error=sanitize_api_error(exc, status)) from None
