"""Bounded one-level directory listing Tool."""

import asyncio
import time
from typing import Literal

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
    DEFAULT_LIST_PAGE_ENTRIES,
    LIST_TIMEOUT_MS,
    MAX_DIRECTORY_ENTRIES,
    MAX_LIST_PAGE_ENTRIES,
    MAX_TOOL_INPUT_BYTES,
    MAX_TOOL_OUTPUT_BYTES,
)
from bearagent.domain.tools import (
    PreparedToolRequest,
    ToolRequest,
    ToolResult,
    ToolRetrySafety,
    ToolSideEffect,
    ToolSpec,
)


class _ListArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    path: str = "."
    offset: int = Field(default=0, ge=0, le=MAX_DIRECTORY_ENTRIES)
    limit: int = Field(default=DEFAULT_LIST_PAGE_ENTRIES, ge=1, le=MAX_LIST_PAGE_ENTRIES)


class _ListEntryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    kind: Literal["file", "directory", "blocked"]
    size_bytes: int | None


class _ListOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    entries: tuple[_ListEntryOutput, ...]
    next_offset: int | None
    truncated: bool
    blocked_entries: int


class WorkspaceListTool:
    """List direct children below one fixed workspace boundary."""

    spec = ToolSpec(
        name="workspace.list",
        description="List one page of direct entries in a workspace directory.",
        input_schema=_ListArguments.model_json_schema(),
        output_schema=_ListOutput.model_json_schema(),
        side_effect=ToolSideEffect.READ_ONLY,
        timeout_ms=LIST_TIMEOUT_MS,
        max_input_bytes=MAX_TOOL_INPUT_BYTES,
        max_output_bytes=MAX_TOOL_OUTPUT_BYTES,
        retry_safety=ToolRetrySafety.SAFE,
    )

    def __init__(self, boundary: WorkspaceBoundary) -> None:
        self._boundary = boundary

    def prepare(self, request: ToolRequest) -> PreparedToolRequest:
        """Validate arguments and canonicalize separators without filesystem I/O."""
        if request.name != self.spec.name:
            raise ValueError("request name does not match workspace.list")
        arguments = _ListArguments.model_validate(dict(request.arguments))
        normalized_path = normalize_workspace_path(arguments.path)
        return PreparedToolRequest(
            tool_call_id=request.tool_call_id,
            name=request.name,
            arguments={
                "path": normalized_path,
                "offset": arguments.offset,
                "limit": arguments.limit,
            },
        )

    async def execute(self, request: PreparedToolRequest) -> ToolResult:
        """List one page on a worker thread so filesystem I/O cannot block the loop."""
        return await asyncio.to_thread(self._execute_sync, request)

    def _execute_sync(self, request: PreparedToolRequest) -> ToolResult:
        arguments = _ListArguments.model_validate(dict(request.arguments))
        deadline = time.monotonic() + self.spec.timeout_ms / 1_000
        try:
            snapshot = self._boundary.list_directory(arguments.path, deadline=deadline)
        except WorkspaceBoundaryError as error:
            return boundary_failure(request.tool_call_id, error)

        end_offset = min(arguments.offset + arguments.limit, len(snapshot.entries))
        page = snapshot.entries[arguments.offset : end_offset]
        next_offset = end_offset if end_offset < len(snapshot.entries) else None
        output = _ListOutput(
            path=arguments.path,
            entries=tuple(
                _ListEntryOutput(
                    path=entry.path,
                    kind=entry.kind,
                    size_bytes=entry.size_bytes,
                )
                for entry in page
            ),
            next_offset=next_offset,
            truncated=next_offset is not None,
            blocked_entries=snapshot.blocked_entries
            + sum(entry.kind == "blocked" for entry in snapshot.entries),
        )
        return success_result(request.tool_call_id, json_model_data(output))
