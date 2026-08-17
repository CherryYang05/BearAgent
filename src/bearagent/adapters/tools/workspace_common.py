"""Small result helpers shared by the workspace Tool adapters."""

from collections.abc import Mapping
from typing import cast

from pydantic import BaseModel, JsonValue

from bearagent.adapters.tools.workspace_boundary import WorkspaceBoundaryError
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo, SafeDetailValue
from bearagent.domain.ids import ToolCallId
from bearagent.domain.tools import ToolResult, ToolStatus


def json_model_data(model: BaseModel) -> Mapping[str, JsonValue]:
    """Return one validated private adapter model as ToolResult JSON data."""
    return cast(dict[str, JsonValue], model.model_dump(mode="json"))


def success_result(tool_call_id: ToolCallId, data: Mapping[str, JsonValue]) -> ToolResult:
    return ToolResult(tool_call_id=tool_call_id, status=ToolStatus.SUCCEEDED, data=data)


def failure_result(
    tool_call_id: ToolCallId,
    code: ErrorCode,
    message: str,
    *,
    details: Mapping[str, SafeDetailValue] | None = None,
) -> ToolResult:
    return ToolResult(
        tool_call_id=tool_call_id,
        status=ToolStatus.FAILED,
        error=ErrorInfo(
            category=ErrorCategory.TOOL,
            code=code,
            message=message,
            retryable=False,
            details={} if details is None else details,
        ),
    )


def boundary_failure(tool_call_id: ToolCallId, error: WorkspaceBoundaryError) -> ToolResult:
    return failure_result(tool_call_id, error.code, str(error))
