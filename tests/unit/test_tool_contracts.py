from typing import cast

import pytest
from pydantic import JsonValue, ValidationError
from tests.tool_fixtures import build_tool_request, build_tool_spec

from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.tools import (
    PolicyDecision,
    PolicyOutcome,
    PolicyReason,
    PreparedToolRequest,
    ToolResult,
    ToolSpec,
    ToolStatus,
)


def test_tool_spec_and_request_are_recursively_immutable() -> None:
    spec = build_tool_spec()
    request = build_tool_request(arguments={"path": "docs/index.md", "options": {"lines": [1, 2]}})

    with pytest.raises(TypeError):
        cast(dict[str, JsonValue], spec.input_schema)["new"] = {"type": "string"}
    options = cast(dict[str, JsonValue], request.arguments["options"])
    with pytest.raises(TypeError):
        options["new"] = True
    assert isinstance(options["lines"], tuple)


def test_tool_contracts_round_trip_as_json() -> None:
    request = build_tool_request()
    prepared = PreparedToolRequest.model_validate(request.model_dump(mode="json"))
    result = ToolResult(
        tool_call_id=request.tool_call_id,
        status=ToolStatus.SUCCEEDED,
        data={"content": "BearAgent"},
    )

    assert PreparedToolRequest.model_validate_json(prepared.model_dump_json()) == prepared
    assert ToolResult.model_validate_json(result.model_dump_json()) == result


def test_tool_spec_rejects_invalid_schema_and_resource_limits() -> None:
    values = build_tool_spec().model_dump(mode="json")
    values["input_schema"] = {"type": "array"}
    with pytest.raises(ValidationError, match="root type must be object"):
        ToolSpec.model_validate(values)

    values = build_tool_spec().model_dump(mode="json")
    values["timeout_ms"] = 0
    with pytest.raises(ValidationError, match="greater than 0"):
        ToolSpec.model_validate(values)

    values = build_tool_spec().model_dump(mode="json")
    values["max_input_bytes"] = 1_000_001
    with pytest.raises(ValidationError, match="less than or equal to 1000000"):
        ToolSpec.model_validate(values)

    values = build_tool_spec().model_dump(mode="json")
    values["max_output_bytes"] = 4_000_001
    with pytest.raises(ValidationError, match="less than or equal to 4000000"):
        ToolSpec.model_validate(values)


def test_tool_request_rejects_non_json_and_oversized_nesting() -> None:
    with pytest.raises(ValidationError, match="unsupported value"):
        build_tool_request(arguments={"raw": object()})  # type: ignore[dict-item]

    nested: dict[str, object] = {}
    cursor = nested
    for _ in range(34):
        child: dict[str, object] = {}
        cursor["child"] = child
        cursor = child
    with pytest.raises(ValidationError, match="nesting limit"):
        build_tool_request(arguments=cast(dict[str, JsonValue], nested))

    with pytest.raises(ValidationError, match="arguments exceed the byte limit"):
        build_tool_request(arguments={"value": "x" * 1_000_001})


def test_tool_result_requires_exactly_one_terminal_shape() -> None:
    tool_call_id = build_tool_request().tool_call_id
    error = ErrorInfo(
        category=ErrorCategory.TOOL,
        code=ErrorCode.TOOL_ERROR,
        message="Tool failed.",
    )

    with pytest.raises(ValidationError, match="successful Tool result cannot contain an error"):
        ToolResult(
            tool_call_id=tool_call_id,
            status=ToolStatus.SUCCEEDED,
            error=error,
        )
    with pytest.raises(ValidationError, match="failed Tool result requires an error"):
        ToolResult(tool_call_id=tool_call_id, status=ToolStatus.FAILED)
    with pytest.raises(ValidationError, match="failed Tool result cannot contain data"):
        ToolResult(
            tool_call_id=tool_call_id,
            status=ToolStatus.FAILED,
            data={"partial": True},
            error=error,
        )


def test_policy_decision_rejects_mismatched_reason() -> None:
    assert (
        PolicyDecision(
            outcome=PolicyOutcome.ALLOW,
            reason=PolicyReason.ALLOWED,
        ).outcome
        is PolicyOutcome.ALLOW
    )

    with pytest.raises(ValidationError, match="allow decision requires"):
        PolicyDecision(
            outcome=PolicyOutcome.ALLOW,
            reason=PolicyReason.TOOL_NOT_ALLOWED,
        )
