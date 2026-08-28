"""Bounded line-oriented UTF-8 workspace read Tool."""

import asyncio
import time

from pydantic import BaseModel, ConfigDict, Field

from bearagent.adapters.tools.workspace_boundary import (
    WorkspaceBoundary,
    WorkspaceBoundaryError,
    normalize_workspace_path,
)
from bearagent.adapters.tools.workspace_common import (
    boundary_failure,
    json_model_data,
    success_result,
)
from bearagent.adapters.tools.workspace_limits import (
    DEFAULT_READ_LINES,
    MAX_READ_LINES,
    MAX_READ_TEXT_BYTES,
    MAX_TOOL_INPUT_BYTES,
    MAX_TOOL_OUTPUT_BYTES,
    READ_TIMEOUT_MS,
)
from bearagent.adapters.tools.workspace_text import read_utf8_file
from bearagent.domain.tools import (
    PreparedToolRequest,
    ToolRequest,
    ToolResult,
    ToolRetrySafety,
    ToolSideEffect,
    ToolSpec,
)


class _ReadArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    path: str
    start_line: int = Field(default=1, ge=1)
    max_lines: int = Field(default=DEFAULT_READ_LINES, ge=1, le=MAX_READ_LINES)


class _ReadOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    text: str
    start_line: int
    end_line: int | None
    next_start_line: int | None
    total_lines: int
    truncated: bool


class WorkspaceReadTool:
    """Read one complete-line page from an ordinary UTF-8 workspace file."""

    spec = ToolSpec(
        name="workspace.read",
        spec_version="1",
        description="Read one bounded page of complete lines from a UTF-8 workspace file.",
        input_schema=_ReadArguments.model_json_schema(),
        output_schema=_ReadOutput.model_json_schema(),
        side_effect=ToolSideEffect.READ_ONLY,
        timeout_ms=READ_TIMEOUT_MS,
        max_input_bytes=MAX_TOOL_INPUT_BYTES,
        max_output_bytes=MAX_TOOL_OUTPUT_BYTES,
        retry_safety=ToolRetrySafety.SAFE,
    )

    def __init__(self, boundary: WorkspaceBoundary) -> None:
        self._boundary = boundary

    def prepare(self, request: ToolRequest) -> PreparedToolRequest:
        """Validate arguments and canonicalize separators without filesystem I/O."""
        if request.name != self.spec.name:
            raise ValueError("request name does not match workspace.read")
        arguments = _ReadArguments.model_validate(dict(request.arguments))
        return PreparedToolRequest(
            tool_call_id=request.tool_call_id,
            name=request.name,
            arguments={
                "path": normalize_workspace_path(arguments.path),
                "start_line": arguments.start_line,
                "max_lines": arguments.max_lines,
            },
        )

    async def execute(self, request: PreparedToolRequest) -> ToolResult:
        """Read one page on a worker thread so filesystem I/O cannot block the loop."""
        return await asyncio.to_thread(self._execute_sync, request)

    def _execute_sync(self, request: PreparedToolRequest) -> ToolResult:
        arguments = _ReadArguments.model_validate(dict(request.arguments))
        deadline = time.monotonic() + self.spec.timeout_ms / 1_000
        try:
            text_file = read_utf8_file(
                self._boundary,
                arguments.path,
                deadline=deadline,
            )
        except WorkspaceBoundaryError as error:
            return boundary_failure(request.tool_call_id, error)

        start_index = arguments.start_line - 1
        selected_lines: list[str] = []
        selected_bytes = 0
        for line in text_file.lines[start_index : start_index + arguments.max_lines]:
            line_bytes = len(line.encode("utf-8"))
            if selected_bytes + line_bytes > MAX_READ_TEXT_BYTES:
                break
            selected_lines.append(line)
            selected_bytes += line_bytes

        end_index = start_index + len(selected_lines)
        has_more = end_index < len(text_file.lines)
        output = _ReadOutput(
            path=arguments.path,
            text="".join(selected_lines),
            start_line=arguments.start_line,
            end_line=(arguments.start_line + len(selected_lines) - 1) if selected_lines else None,
            next_start_line=end_index + 1 if has_more else None,
            total_lines=len(text_file.lines),
            truncated=has_more,
        )
        return success_result(request.tool_call_id, json_model_data(output))
