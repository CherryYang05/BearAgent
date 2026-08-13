from collections.abc import Mapping
from typing import cast

import pytest
from pydantic import JsonValue, ValidationError

from bearagent.domain.ids import ToolCallId
from bearagent.domain.messages import (
    MAX_TEXT_CHARS,
    Message,
    MessageRole,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from bearagent.domain.model import (
    MAX_MODEL_INPUT_CHARS,
    ModelCompleted,
    ModelFinishReason,
    ModelRequest,
    ModelTextDelta,
    ModelToolCall,
    ModelToolDefinition,
    ModelUsage,
    model_event_from_json,
)


def build_request(**changes: object) -> ModelRequest:
    data: dict[str, object] = {
        "model": "test-model",
        "messages": (Message(role=MessageRole.USER, parts=(TextPart(text="hello"),)),),
        "tools": (),
        "max_output_tokens": 100,
        "timeout_ms": 5_000,
        "prompt_version": "agent-v1",
    }
    data.update(changes)
    return ModelRequest.model_validate(data)


def test_request_and_events_round_trip_without_provider_types() -> None:
    tool = ModelToolDefinition(
        name="read_file",
        description="Read one workspace file.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )
    request = build_request(tools=(tool,))
    event = ModelToolCall(
        tool_call_id=ToolCallId.new(),
        provider_call_id="call_123",
        name="read_file",
        arguments={"path": "docs/index.md", "options": {"limit": 20}},
    )
    completed = ModelCompleted(
        provider_request_id="resp_123",
        model="test-model-2026-08-13",
        finish_reason=ModelFinishReason.TOOL_CALLS,
        usage=ModelUsage(input_tokens=10, output_tokens=4),
    )

    assert ModelRequest.model_validate_json(request.model_dump_json()) == request
    assert model_event_from_json(event.model_dump_json()) == event
    assert model_event_from_json(completed.model_dump_json()) == completed

    schema = tool.input_schema
    with pytest.raises(TypeError):
        cast(dict[str, JsonValue], schema)["type"] = "array"
    properties = cast(Mapping[str, JsonValue], schema["properties"])
    with pytest.raises(TypeError):
        cast(dict[str, JsonValue], properties)["other"] = {"type": "string"}
    with pytest.raises(TypeError):
        cast(dict[str, JsonValue], event.arguments)["path"] = "changed"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"model": ""}, "String should match pattern"),
        ({"messages": ()}, "at least 1 item"),
        ({"max_output_tokens": 0}, "greater than 0"),
        ({"timeout_ms": 0}, "greater than 0"),
        ({"prompt_version": "bad version"}, "String should match pattern"),
    ],
)
def test_request_rejects_invalid_bounds(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        build_request(**changes)


def test_request_rejects_duplicate_tools_and_oversized_input() -> None:
    tool = ModelToolDefinition(
        name="read_file",
        description="Read a file.",
        input_schema={"type": "object"},
    )
    with pytest.raises(ValidationError, match="names must be unique"):
        build_request(tools=(tool, tool))
    with pytest.raises(ValidationError, match="input character limit"):
        build_request(
            messages=tuple(
                Message(
                    role=MessageRole.USER,
                    parts=(TextPart(text="x" * MAX_TEXT_CHARS),),
                )
                for _ in range(MAX_MODEL_INPUT_CHARS // MAX_TEXT_CHARS + 1)
            )
        )


def test_tool_schema_and_output_reject_untrusted_values() -> None:
    with pytest.raises(ValidationError, match="root type must be object"):
        ModelToolDefinition(
            name="bad",
            description="Bad schema.",
            input_schema={"type": "array"},
        )
    with pytest.raises(ValidationError, match="root type must be object"):
        ModelToolDefinition(
            name="bad",
            description="Bad schema.",
            input_schema={},
        )
    with pytest.raises(ValidationError):
        ModelToolDefinition.model_validate(
            {"name": "bad", "description": "Bad schema.", "input_schema": {"value": object()}}
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ModelTextDelta.model_validate({"text": "hello", "provider_object": {}})


def test_request_requires_correlated_provider_call_identity() -> None:
    tool_call_id = ToolCallId.new()
    assistant = Message(
        role=MessageRole.ASSISTANT,
        parts=(
            ToolCallPart(
                tool_call_id=tool_call_id,
                provider_call_id="call_123",
                name="read_file",
                arguments={"path": "README.md"},
            ),
        ),
    )
    result = Message(
        role=MessageRole.TOOL,
        parts=(ToolResultPart(tool_call_id=tool_call_id, content="BearAgent"),),
    )
    assert build_request(messages=(assistant, result)).messages == (assistant, result)

    missing_provider_identity = Message(
        role=MessageRole.ASSISTANT,
        parts=(
            ToolCallPart(
                tool_call_id=ToolCallId.new(),
                name="read_file",
                arguments={"path": "README.md"},
            ),
        ),
    )
    with pytest.raises(ValidationError, match="requires a provider_call_id"):
        build_request(messages=(missing_provider_identity,))

    with pytest.raises(ValidationError, match="earlier Tool call"):
        build_request(messages=(result,))


def test_missing_usage_is_distinct_from_zero_usage() -> None:
    without_usage = ModelCompleted(
        provider_request_id="resp_1",
        model="test-model",
        finish_reason=ModelFinishReason.STOP,
    )
    zero_usage = without_usage.model_copy(
        update={"usage": ModelUsage(input_tokens=0, output_tokens=0)}
    )

    assert without_usage.usage is None
    assert zero_usage.usage == ModelUsage(input_tokens=0, output_tokens=0)
