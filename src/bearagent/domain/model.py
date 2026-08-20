"""Provider-neutral model request and streaming event contracts."""

import json
from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Literal, Self, cast

from pydantic import Field, JsonValue, field_serializer, field_validator, model_validator

from bearagent.domain._base import (
    MAX_EMBEDDED_JSON_NODES,
    DomainModel,
    freeze_json_mapping,
    thaw_json_mapping,
    validate_json_object,
)
from bearagent.domain.ids import ToolCallId
from bearagent.domain.messages import (
    TOOL_NAME_PATTERN,
    Message,
    TextPart,
    ToolCallPart,
)
from bearagent.domain.runs import MAX_TOKENS

MODEL_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$"
PROMPT_VERSION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
MAX_MODEL_MESSAGES = 512
MAX_MODEL_TOOLS = 128
MAX_TOOL_DESCRIPTION_CHARS = 4_096
MAX_MODEL_INPUT_CHARS = 4_000_000
MAX_MODEL_OUTPUT_CHARS = 4_000_000
MAX_MODEL_TIMEOUT_MS = 600_000
MAX_PROVIDER_IDENTIFIER_CHARS = 256


class ModelEventKind(StrEnum):
    """Stable event kinds emitted by every model adapter."""

    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    COMPLETED = "completed"


class ModelFinishReason(StrEnum):
    """Provider-neutral reasons a successful model response stopped."""

    STOP = "stop"
    TOOL_CALLS = "tool_calls"


class ModelToolDefinition(DomainModel):
    """A bounded function definition that grants no runtime authority."""

    name: str = Field(pattern=TOOL_NAME_PATTERN)
    description: str = Field(min_length=1, max_length=MAX_TOOL_DESCRIPTION_CHARS)
    input_schema: Mapping[str, JsonValue]

    @field_validator("description")
    @classmethod
    def reject_blank_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value

    @field_validator("input_schema", mode="before")
    @classmethod
    def require_json_schema_object(cls, value: object) -> object:
        return validate_json_object(value)

    @field_validator("input_schema")
    @classmethod
    def freeze_input_schema(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        schema_type = value.get("type")
        if schema_type != "object":
            raise ValueError("Tool input schema root type must be object")
        return freeze_json_mapping(value)

    @field_serializer("input_schema")
    def serialize_input_schema(self, value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        return thaw_json_mapping(value)


class ModelRequest(DomainModel):
    """A finite, Provider-neutral request for one model Activity."""

    model: str = Field(pattern=MODEL_NAME_PATTERN)
    messages: tuple[Message, ...] = Field(min_length=1, max_length=MAX_MODEL_MESSAGES)
    tools: tuple[ModelToolDefinition, ...] = Field(default=(), max_length=MAX_MODEL_TOOLS)
    max_output_tokens: int = Field(gt=0, le=MAX_TOKENS, strict=True)
    timeout_ms: int = Field(gt=0, le=MAX_MODEL_TIMEOUT_MS, strict=True)
    prompt_version: str = Field(pattern=PROMPT_VERSION_PATTERN)

    @model_validator(mode="after")
    def validate_history_and_size(self) -> Self:
        if len({tool.name for tool in self.tools}) != len(self.tools):
            raise ValueError("Tool definition names must be unique")

        known_calls: dict[ToolCallId, ToolCallPart] = {}
        answered_calls: set[ToolCallId] = set()
        provider_call_ids: set[str] = set()
        input_chars = 0

        for message in self.messages:
            for part in message.parts:
                if isinstance(part, TextPart):
                    input_chars += len(part.text)
                elif isinstance(part, ToolCallPart):
                    if part.tool_call_id in known_calls:
                        raise ValueError("Model history tool_call_id values must be unique")
                    known_calls[part.tool_call_id] = part
                    input_chars += len(
                        json.dumps(
                            thaw_json_mapping(part.arguments),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
                    if part.provider_call_id is None:
                        raise ValueError("Model history Tool call requires a provider_call_id")
                    if part.provider_call_id in provider_call_ids:
                        raise ValueError("provider_call_id values must be unique")
                    provider_call_ids.add(part.provider_call_id)
                else:
                    input_chars += len(part.content)
                    if part.tool_call_id not in known_calls:
                        raise ValueError("Tool result must reference an earlier Tool call")
                    if part.tool_call_id in answered_calls:
                        raise ValueError("Tool call may have only one result")
                    answered_calls.add(part.tool_call_id)

        for tool in self.tools:
            input_chars += len(
                json.dumps(
                    thaw_json_mapping(tool.input_schema),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            ) + len(tool.description)
        if input_chars > MAX_MODEL_INPUT_CHARS:
            raise ValueError("Model request exceeds the input character limit")
        return self


class ModelUsage(DomainModel):
    """Actual token usage reported by a Provider."""

    input_tokens: int = Field(ge=0, le=MAX_TOKENS, strict=True)
    output_tokens: int = Field(ge=0, le=MAX_TOKENS, strict=True)


class ModelTextDelta(DomainModel):
    """One non-empty fragment of assistant text."""

    kind: Literal[ModelEventKind.TEXT_DELTA] = ModelEventKind.TEXT_DELTA
    text: str = Field(min_length=1, max_length=MAX_MODEL_OUTPUT_CHARS)


class ModelToolCall(DomainModel):
    """One complete, validated function call proposed by a model."""

    kind: Literal[ModelEventKind.TOOL_CALL] = ModelEventKind.TOOL_CALL
    tool_call_id: ToolCallId
    provider_call_id: str = Field(min_length=1, max_length=MAX_PROVIDER_IDENTIFIER_CHARS)
    name: str = Field(pattern=TOOL_NAME_PATTERN)
    arguments: Mapping[str, JsonValue]

    @field_validator("provider_call_id")
    @classmethod
    def reject_blank_provider_call_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("provider_call_id must not be blank")
        return value

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


class ModelCompleted(DomainModel):
    """The unique terminal event for a successful model stream."""

    kind: Literal[ModelEventKind.COMPLETED] = ModelEventKind.COMPLETED
    provider_request_id: str = Field(min_length=1, max_length=MAX_PROVIDER_IDENTIFIER_CHARS)
    model: str = Field(pattern=MODEL_NAME_PATTERN)
    finish_reason: ModelFinishReason
    usage: ModelUsage | None = None

    @field_validator("provider_request_id")
    @classmethod
    def reject_blank_provider_request_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("provider_request_id must not be blank")
        return value


ModelEvent = Annotated[
    ModelTextDelta | ModelToolCall | ModelCompleted,
    Field(discriminator="kind"),
]


def model_event_from_json(data: str) -> ModelEvent:
    """Validate a serialized model event without exposing Provider types."""
    from pydantic import TypeAdapter

    return cast(ModelEvent, TypeAdapter(ModelEvent).validate_json(data))
