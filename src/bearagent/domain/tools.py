"""Bounded Tool contracts shared by the runtime, ports, and adapters."""

import json
from collections.abc import Mapping
from enum import StrEnum
from typing import Self

from pydantic import Field, JsonValue, field_serializer, field_validator, model_validator

from bearagent.domain._base import (
    MAX_EMBEDDED_JSON_NODES,
    DomainModel,
    freeze_json_mapping,
    thaw_json_mapping,
    validate_json_object,
)
from bearagent.domain.errors import ErrorCode, ErrorInfo
from bearagent.domain.fingerprints import CONTRACT_VERSION_PATTERN
from bearagent.domain.ids import ToolCallId
from bearagent.domain.messages import TOOL_NAME_PATTERN

MAX_TOOL_DESCRIPTION_CHARS = 4_096
MAX_TOOL_SCHEMA_BYTES = 1_000_000
MAX_TOOL_ARGUMENT_BYTES = 1_000_000
MAX_TOOL_TIMEOUT_MS = 600_000
MAX_TOOL_INPUT_BYTES = 1_000_000
MAX_TOOL_OUTPUT_BYTES = 4_000_000


class ToolStatus(StrEnum):
    """Terminal outcome of one Tool call."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ToolSideEffect(StrEnum):
    """Trusted description of what a registered Tool can change."""

    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    EXTERNAL_WRITE = "external_write"
    CODE_EXECUTION = "code_execution"


class ToolRetrySafety(StrEnum):
    """Coarse Tool contract hint; never permission to retry an Activity by itself."""

    NOT_SAFE = "not_safe"
    SAFE = "safe"


class PolicyOutcome(StrEnum):
    """P1 Policy outcomes."""

    ALLOW = "allow"
    DENY = "deny"


class PolicyReason(StrEnum):
    """Stable reasons for the P1 fixed Policy decision."""

    ALLOWED = "allowed"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    SIDE_EFFECT_DENIED = "side_effect_denied"


class PolicyDecision(DomainModel):
    """A safe Policy result that contains no request argument copy."""

    outcome: PolicyOutcome
    reason: PolicyReason

    @model_validator(mode="after")
    def require_matching_outcome_and_reason(self) -> Self:
        if self.outcome is PolicyOutcome.ALLOW and self.reason is not PolicyReason.ALLOWED:
            raise ValueError("allow decision requires the allowed reason")
        if self.outcome is PolicyOutcome.DENY and self.reason is PolicyReason.ALLOWED:
            raise ValueError("deny decision requires a denial reason")
        return self


class ToolSpec(DomainModel):
    """Trusted registration data and resource limits for one Tool."""

    name: str = Field(pattern=TOOL_NAME_PATTERN)
    spec_version: str = Field(pattern=CONTRACT_VERSION_PATTERN)
    description: str = Field(min_length=1, max_length=MAX_TOOL_DESCRIPTION_CHARS)
    input_schema: Mapping[str, JsonValue]
    output_schema: Mapping[str, JsonValue]
    side_effect: ToolSideEffect
    timeout_ms: int = Field(gt=0, le=MAX_TOOL_TIMEOUT_MS, strict=True)
    max_input_bytes: int = Field(gt=0, le=MAX_TOOL_INPUT_BYTES, strict=True)
    max_output_bytes: int = Field(gt=0, le=MAX_TOOL_OUTPUT_BYTES, strict=True)
    retry_safety: ToolRetrySafety

    @field_validator("description")
    @classmethod
    def reject_blank_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value

    @field_validator("input_schema", "output_schema", mode="before")
    @classmethod
    def require_json_schema_object(cls, value: object) -> object:
        return validate_json_object(value)

    @field_validator("input_schema", "output_schema")
    @classmethod
    def freeze_object_schema(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        if value.get("type") != "object":
            raise ValueError("Tool schema root type must be object")
        return freeze_json_mapping(value)

    @field_serializer("input_schema", "output_schema")
    def serialize_schema(self, value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        return thaw_json_mapping(value)

    @model_validator(mode="after")
    def require_bounded_schemas(self) -> Self:
        for field_name, schema in (
            ("input_schema", self.input_schema),
            ("output_schema", self.output_schema),
        ):
            if _json_bytes(schema) > MAX_TOOL_SCHEMA_BYTES:
                raise ValueError(f"{field_name} exceeds the Tool schema byte limit")
        return self


class ToolRequest(DomainModel):
    """Untrusted model request for one named Tool."""

    tool_call_id: ToolCallId
    name: str = Field(pattern=TOOL_NAME_PATTERN)
    arguments: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("arguments", mode="before")
    @classmethod
    def require_json_arguments(cls, value: object) -> object:
        return validate_json_object(value, max_nodes=MAX_EMBEDDED_JSON_NODES)

    @field_validator("arguments")
    @classmethod
    def freeze_arguments(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return freeze_json_mapping(value)

    @field_serializer("arguments")
    def serialize_arguments(self, value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        return thaw_json_mapping(value)

    @model_validator(mode="after")
    def require_bounded_arguments(self) -> Self:
        if _json_bytes(self.arguments) > MAX_TOOL_ARGUMENT_BYTES:
            raise ValueError("Tool arguments exceed the byte limit")
        return self


class PreparedToolRequest(ToolRequest):
    """Tool request after pure, Tool-specific validation and normalization."""


class ToolResult(DomainModel):
    """Bounded structured result correlated with one Tool request."""

    tool_call_id: ToolCallId
    status: ToolStatus
    data: Mapping[str, JsonValue] = Field(default_factory=dict)
    error: ErrorInfo | None = None

    @field_validator("data", mode="before")
    @classmethod
    def require_json_data(cls, value: object) -> object:
        return validate_json_object(value)

    @field_validator("data")
    @classmethod
    def freeze_data(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return freeze_json_mapping(value)

    @field_serializer("data")
    def serialize_data(self, value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        return thaw_json_mapping(value)

    @model_validator(mode="after")
    def require_one_terminal_shape(self) -> Self:
        if self.status is ToolStatus.SUCCEEDED and self.error is not None:
            raise ValueError("successful Tool result cannot contain an error")
        if self.status is ToolStatus.FAILED:
            if self.error is None:
                raise ValueError("failed Tool result requires an error")
            if self.data:
                raise ValueError("failed Tool result cannot contain data")
        return self


class ToolExecutionRecord(DomainModel):
    """Provider-neutral evidence produced by the single Tool execution path."""

    request: ToolRequest
    prepared_request: PreparedToolRequest | None = None
    policy_decision: PolicyDecision | None = None
    reached_adapter: bool
    result: ToolResult
    persistence_truncated: bool = False

    @model_validator(mode="after")
    def require_consistent_execution(self) -> Self:
        if self.result.tool_call_id != self.request.tool_call_id:
            raise ValueError("Tool result identity must match its request")
        if self.prepared_request is not None and (
            self.prepared_request.tool_call_id != self.request.tool_call_id
            or self.prepared_request.name != self.request.name
        ):
            raise ValueError("prepared Tool request identity must match its request")
        if self.persistence_truncated:
            if self.prepared_request is not None or self.policy_decision is not None:
                raise ValueError("truncated persistence evidence cannot contain preparation data")
            if (
                self.result.status is not ToolStatus.FAILED
                or self.result.error is None
                or self.result.error.code is not ErrorCode.TOOL_OUTPUT_TOO_LARGE
            ):
                raise ValueError("truncated persistence evidence requires a bounded failure")
            return self
        if self.reached_adapter:
            if self.prepared_request is None:
                raise ValueError("adapter execution requires a prepared request")
            if (
                self.policy_decision is None
                or self.policy_decision.outcome is not PolicyOutcome.ALLOW
            ):
                raise ValueError("adapter execution requires an allow decision")
        if (
            self.policy_decision is not None
            and self.policy_decision.outcome is PolicyOutcome.DENY
            and self.reached_adapter
        ):
            raise ValueError("a denied Tool request cannot reach its adapter")
        if self.result.status is ToolStatus.SUCCEEDED and not self.reached_adapter:
            raise ValueError("a successful Tool result must come from its adapter")
        return self


def _json_bytes(value: Mapping[str, JsonValue]) -> int:
    serialized = json.dumps(
        thaw_json_mapping(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return len(serialized.encode("utf-8"))
