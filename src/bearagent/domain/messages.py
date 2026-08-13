"""Provider-neutral conversation messages."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, field_serializer, field_validator, model_validator

from bearagent.domain._base import (
    DomainModel,
    freeze_json_mapping,
    thaw_json_mapping,
    validate_json_object,
)
from bearagent.domain.ids import ToolCallId

MAX_MESSAGE_PARTS = 128
MAX_TEXT_CHARS = 1_000_000
MAX_PROVIDER_CALL_ID_CHARS = 256
TOOL_NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"


class MessageRole(StrEnum):
    """Roles understood by the BearAgent runtime."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class TextPart(DomainModel):
    """A non-empty text segment."""

    kind: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class ToolCallPart(DomainModel):
    """A structured tool request emitted by a model adapter."""

    kind: Literal["tool_call"] = "tool_call"
    tool_call_id: ToolCallId
    provider_call_id: str | None = Field(
        default=None, min_length=1, max_length=MAX_PROVIDER_CALL_ID_CHARS
    )
    name: str = Field(pattern=TOOL_NAME_PATTERN)
    arguments: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("arguments", mode="before")
    @classmethod
    def require_json_arguments(cls, value: object) -> object:
        return validate_json_object(value)

    @field_validator("arguments")
    @classmethod
    def freeze_arguments(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return freeze_json_mapping(value)

    @field_serializer("arguments")
    def serialize_arguments(self, value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        return thaw_json_mapping(value)

    @field_validator("provider_call_id")
    @classmethod
    def reject_blank_provider_call_id(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("provider_call_id must not be blank")
        return value


class ToolResultPart(DomainModel):
    """A tool observation correlated to its request."""

    kind: Literal["tool_result"] = "tool_result"
    tool_call_id: ToolCallId
    content: str = Field(max_length=MAX_TEXT_CHARS)
    is_error: bool = False


MessagePart = Annotated[TextPart | ToolCallPart | ToolResultPart, Field(discriminator="kind")]


class Message(DomainModel):
    """One provider-neutral message with role-compatible content parts."""

    role: MessageRole
    parts: tuple[MessagePart, ...] = Field(min_length=1, max_length=MAX_MESSAGE_PARTS)

    @model_validator(mode="after")
    def validate_role_parts(self) -> Self:
        if self.role in {MessageRole.SYSTEM, MessageRole.USER}:
            if any(not isinstance(part, TextPart) for part in self.parts):
                raise ValueError(f"{self.role.value} messages may contain only text")
        elif self.role is MessageRole.ASSISTANT:
            if any(isinstance(part, ToolResultPart) for part in self.parts):
                raise ValueError("assistant messages may not contain tool results")
            tool_call_ids = [
                part.tool_call_id for part in self.parts if isinstance(part, ToolCallPart)
            ]
            if len(tool_call_ids) != len(set(tool_call_ids)):
                raise ValueError("assistant tool_call_id values must be unique")
        elif len(self.parts) != 1 or not isinstance(self.parts[0], ToolResultPart):
            raise ValueError("tool messages must contain exactly one tool result")
        return self
