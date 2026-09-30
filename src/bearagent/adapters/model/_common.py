"""Shared bounded translation helpers for production model adapters."""

import json
from collections.abc import Mapping
from typing import cast

import httpx
from pydantic import JsonValue, ValidationError

from bearagent.domain._base import thaw_json_mapping, validate_json_object
from bearagent.domain.attempts import ModelFailureEvidence, ModelSubmission
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo, SafeDetailValue
from bearagent.domain.ids import ToolCallId
from bearagent.domain.model import MAX_MODEL_OUTPUT_CHARS, ModelToolCall
from bearagent.ports.model import ModelProviderError


def translate_json_tool_call(
    *, provider_call_id: str, name: str, arguments_json: str
) -> ModelToolCall:
    try:
        if len(arguments_json) > MAX_MODEL_OUTPUT_CHARS:
            raise ValueError("function arguments exceed the character limit")
        validated = parse_json_object(arguments_json)
        return ModelToolCall(
            tool_call_id=ToolCallId.new(),
            provider_call_id=provider_call_id,
            name=name,
            arguments=validated,
        )
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as cause:
        raise protocol_error("Provider emitted an invalid function call.", cause=cause) from cause


def provider_error(
    code: ErrorCode,
    message: str,
    *,
    retryable: bool,
    details: Mapping[str, SafeDetailValue] | None = None,
    cause: BaseException | None = None,
) -> ModelProviderError:
    return ModelProviderError(
        ErrorInfo(
            category=ErrorCategory.PROVIDER,
            code=code,
            message=message,
            retryable=retryable,
            details={} if details is None else details,
        ),
        cause=cause,
        evidence=connection_failure_evidence(cause)
        if code in {ErrorCode.PROVIDER_TIMEOUT, ErrorCode.PROVIDER_UNAVAILABLE}
        else None,
    )


def protocol_error(message: str, *, cause: BaseException | None = None) -> ModelProviderError:
    return provider_error(
        ErrorCode.PROVIDER_PROTOCOL_ERROR,
        message,
        retryable=False,
        cause=cause,
    )


def safe_detail_text(value: object) -> str | None:
    if isinstance(value, str) and 0 < len(value) <= 512:
        return value
    return None


def parse_json_object(value: str) -> dict[str, JsonValue]:
    parsed = json.loads(value)
    return cast(dict[str, JsonValue], validate_json_object(parsed))


def canonical_json_text(value: str) -> str:
    try:
        return canonical_json_mapping(parse_json_object(value))
    except (json.JSONDecodeError, ValueError, TypeError) as cause:
        raise protocol_error(
            "Provider completion carried invalid function arguments.", cause=cause
        ) from cause


def canonical_json_mapping(value: Mapping[str, JsonValue]) -> str:
    return json.dumps(
        thaw_json_mapping(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def connection_failure_evidence(cause: BaseException | None) -> ModelFailureEvidence:
    """Only a concrete HTTP transport connect failure proves no model request was sent."""
    for _ in range(8):
        if cause is None:
            break
        if getattr(cause, "response", None) is not None:
            # A received HTTP response takes precedence over earlier connection
            # failures in SDK/transport wrappers.
            break
        if isinstance(cause, httpx.ConnectError | httpx.ConnectTimeout):
            return ModelFailureEvidence(submission=ModelSubmission.NOT_SUBMITTED, usage_known=True)
        if isinstance(cause, httpx.HTTPError):
            # Read/write/protocol failures can follow submission. Do not search
            # their older causes for a connection failure and erase that fact.
            break
        # Explicit SDK exception chaining is trusted adapter evidence; messages are never parsed.
        cause = cause.__cause__
    return ModelFailureEvidence()
