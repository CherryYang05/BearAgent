from collections.abc import Mapping
from typing import cast

import pytest
from pydantic import JsonValue, ValidationError

from bearagent.domain.ids import ToolCallId
from bearagent.domain.messages import (
    Message,
    MessageRole,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)


def test_text_and_tool_messages_round_trip_without_provider_types() -> None:
    tool_call_id = ToolCallId.new()
    assistant = Message(
        role=MessageRole.ASSISTANT,
        parts=(
            TextPart(text="I will inspect the file."),
            ToolCallPart(
                tool_call_id=tool_call_id,
                name="read_file",
                arguments={"path": "docs/index.md", "options": {"line_limit": 20}},
            ),
        ),
    )
    tool = Message(
        role=MessageRole.TOOL,
        parts=(ToolResultPart(tool_call_id=tool_call_id, content="BearAgent"),),
    )

    assert Message.model_validate_json(assistant.model_dump_json()) == assistant
    assert Message.model_validate_json(tool.model_dump_json()) == tool
    assert assistant.model_dump(mode="json")["parts"][1]["kind"] == "tool_call"

    arguments = cast(ToolCallPart, assistant.parts[1]).arguments
    with pytest.raises(TypeError):
        cast(dict[str, JsonValue], arguments)["path"] = "changed"
    nested = cast(Mapping[str, JsonValue], arguments["options"])
    with pytest.raises(TypeError):
        cast(dict[str, JsonValue], nested)["line_limit"] = 999


@pytest.mark.parametrize("role", [MessageRole.SYSTEM, MessageRole.USER])
def test_system_and_user_messages_reject_tool_parts(role: MessageRole) -> None:
    with pytest.raises(ValidationError, match="may contain only text"):
        Message(
            role=role,
            parts=(
                ToolCallPart(
                    tool_call_id=ToolCallId.new(),
                    name="read_file",
                    arguments={},
                ),
            ),
        )


def test_tool_message_requires_exactly_one_tool_result() -> None:
    with pytest.raises(ValidationError, match="exactly one tool result"):
        Message(role=MessageRole.TOOL, parts=(TextPart(text="not a result"),))


def test_assistant_rejects_duplicate_tool_call_ids() -> None:
    tool_call_id = ToolCallId.new()
    with pytest.raises(ValidationError, match="must be unique"):
        Message(
            role=MessageRole.ASSISTANT,
            parts=(
                ToolCallPart(tool_call_id=tool_call_id, name="read_file", arguments={}),
                ToolCallPart(tool_call_id=tool_call_id, name="search_files", arguments={}),
            ),
        )


def test_message_boundary_rejects_unknown_fields_and_non_json_arguments() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Message.model_validate(
            {
                "role": "user",
                "parts": [{"kind": "text", "text": "hello"}],
                "provider_response": {"id": "external"},
            }
        )

    with pytest.raises(ValidationError):
        ToolCallPart.model_validate(
            {
                "tool_call_id": str(ToolCallId.new()),
                "name": "read_file",
                "arguments": {"provider_object": object()},
            }
        )

    with pytest.raises(ValidationError, match="numbers must be finite"):
        ToolCallPart(
            tool_call_id=ToolCallId.new(),
            name="read_file",
            arguments={"offset": float("nan")},
        )


def test_text_rejects_blank_content() -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        TextPart(text="   ")
