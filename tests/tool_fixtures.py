from collections.abc import Mapping

from pydantic import JsonValue

from bearagent.domain.ids import ToolCallId
from bearagent.domain.tools import (
    ToolRequest,
    ToolRetrySafety,
    ToolSideEffect,
    ToolSpec,
)


def build_tool_spec(
    *,
    name: str = "workspace.read",
    side_effect: ToolSideEffect = ToolSideEffect.READ_ONLY,
    timeout_ms: int = 1_000,
    max_input_bytes: int = 1_024,
    max_output_bytes: int = 1_024,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description="Read one test resource.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
            "additionalProperties": False,
        },
        side_effect=side_effect,
        timeout_ms=timeout_ms,
        max_input_bytes=max_input_bytes,
        max_output_bytes=max_output_bytes,
        retry_safety=ToolRetrySafety.SAFE,
    )


def build_tool_request(
    *,
    name: str = "workspace.read",
    arguments: Mapping[str, JsonValue] | None = None,
) -> ToolRequest:
    return ToolRequest(
        tool_call_id=ToolCallId.new(),
        name=name,
        arguments={"path": "docs/index.md"} if arguments is None else arguments,
    )
