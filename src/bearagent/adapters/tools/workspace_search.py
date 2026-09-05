"""Deterministic bounded literal search across workspace text files."""

import asyncio
import heapq
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from bearagent.adapters.tools.workspace_boundary import (
    WorkspaceBoundary,
    WorkspaceBoundaryError,
    WorkspaceEntry,
    normalize_workspace_path,
)
from bearagent.adapters.tools.workspace_common import (
    boundary_failure,
    json_model_data,
    success_result,
)
from bearagent.adapters.tools.workspace_limits import (
    DEFAULT_SEARCH_RESULTS,
    MAX_SEARCH_DEPTH,
    MAX_SEARCH_FILES,
    MAX_SEARCH_PREVIEW_CHARS,
    MAX_SEARCH_QUERY_CHARS,
    MAX_SEARCH_RESULTS,
    MAX_SEARCH_TOTAL_BYTES,
    MAX_TEXT_FILE_BYTES,
    MAX_TOOL_INPUT_BYTES,
    MAX_TOOL_OUTPUT_BYTES,
    SEARCH_TIMEOUT_MS,
)
from bearagent.adapters.tools.workspace_text import read_utf8_file
from bearagent.domain.errors import ErrorCode
from bearagent.domain.tools import (
    PreparedToolRequest,
    ToolRequest,
    ToolResult,
    ToolRetrySafety,
    ToolSideEffect,
    ToolSpec,
)

type SearchLimitReason = Literal[
    "max_results",
    "max_files",
    "max_total_bytes",
    "max_depth",
    "file_limit",
]


class _SearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    path: str = "."
    query: str = Field(min_length=1, max_length=MAX_SEARCH_QUERY_CHARS)
    case_sensitive: bool = True
    max_results: int = Field(default=DEFAULT_SEARCH_RESULTS, ge=1, le=MAX_SEARCH_RESULTS)

    @field_validator("query")
    @classmethod
    def reject_blank_or_multiline_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("search query must not be blank")
        if any(character in value for character in ("\x00", "\r", "\n")):
            raise ValueError("search query must fit on one text line")
        return value


class _SearchMatchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    line_number: int
    line: str
    line_truncated: bool


class _SearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    query: str
    case_sensitive: bool
    matches: tuple[_SearchMatchOutput, ...]
    truncated: bool
    limit_reason: SearchLimitReason | None
    scanned_files: int
    scanned_bytes: int
    skipped_files: int
    blocked_entries: int


class WorkspaceSearchTool:
    """Search ordinary UTF-8 files in stable portable path order."""

    spec = ToolSpec(
        name="workspace.search",
        spec_version="2",
        description="Search for a literal string in bounded UTF-8 workspace files.",
        input_schema=_SearchArguments.model_json_schema(),
        output_schema=_SearchOutput.model_json_schema(),
        side_effect=ToolSideEffect.READ_ONLY,
        timeout_ms=SEARCH_TIMEOUT_MS,
        max_input_bytes=MAX_TOOL_INPUT_BYTES,
        max_output_bytes=MAX_TOOL_OUTPUT_BYTES,
        retry_safety=ToolRetrySafety.SAFE,
    )

    def __init__(self, boundary: WorkspaceBoundary) -> None:
        self._boundary = boundary

    def prepare(self, request: ToolRequest) -> PreparedToolRequest:
        """Validate arguments and canonicalize separators without filesystem I/O."""
        if request.name != self.spec.name:
            raise ValueError("request name does not match workspace.search")
        arguments = _SearchArguments.model_validate(dict(request.arguments))
        return PreparedToolRequest(
            tool_call_id=request.tool_call_id,
            name=request.name,
            arguments={
                "path": normalize_workspace_path(arguments.path),
                "query": arguments.query,
                "case_sensitive": arguments.case_sensitive,
                "max_results": arguments.max_results,
            },
        )

    async def execute(self, request: PreparedToolRequest) -> ToolResult:
        """Run deterministic recursive search away from the runtime event loop."""
        return await asyncio.to_thread(self._execute_sync, request)

    def _execute_sync(self, request: PreparedToolRequest) -> ToolResult:
        arguments = _SearchArguments.model_validate(dict(request.arguments))
        deadline = time.monotonic() + self.spec.timeout_ms / 1_000
        try:
            output = self._search(arguments, deadline=deadline)
        except WorkspaceBoundaryError as error:
            return boundary_failure(request.tool_call_id, error)
        return success_result(request.tool_call_id, json_model_data(output))

    def _search(self, arguments: _SearchArguments, *, deadline: float) -> _SearchOutput:
        root_snapshot = self._boundary.list_directory(arguments.path, deadline=deadline)
        pending: list[tuple[str, WorkspaceEntry]] = [
            (entry.path, entry) for entry in root_snapshot.entries
        ]
        heapq.heapify(pending)
        base_depth = 0 if arguments.path == "." else len(arguments.path.split("/"))
        needle = arguments.query if arguments.case_sensitive else arguments.query.casefold()
        matches: list[_SearchMatchOutput] = []
        scanned_files = 0
        scanned_bytes = 0
        skipped_files = 0
        blocked_entries = root_snapshot.blocked_entries
        truncated = False
        limit_reason: SearchLimitReason | None = None

        # A heap preserves global path order while directories are discovered lazily.
        # Convenience walkers assume the tree is stable and can re-enter replaced links.
        while pending:
            if time.monotonic() >= deadline:
                raise WorkspaceBoundaryError(
                    ErrorCode.TOOL_TIMEOUT,
                    "Workspace Tool reached its execution deadline.",
                )
            _, entry = heapq.heappop(pending)
            if entry.kind == "blocked":
                blocked_entries += 1
                continue
            if entry.kind == "directory":
                depth = len(entry.path.split("/")) - base_depth
                if depth >= MAX_SEARCH_DEPTH:
                    truncated = True
                    limit_reason = limit_reason or "max_depth"
                    continue
                snapshot = self._boundary.list_directory(entry.path, deadline=deadline)
                blocked_entries += snapshot.blocked_entries
                for child in snapshot.entries:
                    heapq.heappush(pending, (child.path, child))
                continue

            if scanned_files >= MAX_SEARCH_FILES:
                truncated = True
                limit_reason = limit_reason or "max_files"
                break
            file_size = self._boundary.file_size(entry.path)
            if scanned_bytes + file_size > MAX_SEARCH_TOTAL_BYTES:
                truncated = True
                limit_reason = limit_reason or "max_total_bytes"
                break
            scanned_files += 1
            if file_size > MAX_TEXT_FILE_BYTES:
                skipped_files += 1
                truncated = True
                limit_reason = limit_reason or "file_limit"
                continue
            try:
                text_file = read_utf8_file(
                    self._boundary,
                    entry.path,
                    deadline=deadline,
                    max_file_bytes=min(
                        MAX_TEXT_FILE_BYTES,
                        MAX_SEARCH_TOTAL_BYTES - scanned_bytes,
                    ),
                )
            except WorkspaceBoundaryError as error:
                if error.code is ErrorCode.WORKSPACE_NOT_TEXT:
                    scanned_bytes += file_size
                    skipped_files += 1
                    continue
                if error.code is ErrorCode.WORKSPACE_LIMIT_EXCEEDED:
                    if MAX_SEARCH_TOTAL_BYTES - scanned_bytes < MAX_TEXT_FILE_BYTES:
                        truncated = True
                        limit_reason = limit_reason or "max_total_bytes"
                        break
                    scanned_bytes += file_size
                    skipped_files += 1
                    truncated = True
                    limit_reason = limit_reason or "file_limit"
                    continue
                raise

            scanned_bytes += text_file.size_bytes

            for line_number, line in enumerate(text_file.lines, start=1):
                haystack = line if arguments.case_sensitive else line.casefold()
                if needle not in haystack:
                    continue
                visible_line = line.rstrip("\r\n")
                line_truncated = len(visible_line) > MAX_SEARCH_PREVIEW_CHARS
                matches.append(
                    _SearchMatchOutput(
                        path=entry.path,
                        line_number=line_number,
                        line=visible_line[:MAX_SEARCH_PREVIEW_CHARS],
                        line_truncated=line_truncated,
                    )
                )
                if len(matches) >= arguments.max_results:
                    truncated = True
                    limit_reason = limit_reason or "max_results"
                    return _SearchOutput(
                        path=arguments.path,
                        query=arguments.query,
                        case_sensitive=arguments.case_sensitive,
                        matches=tuple(matches),
                        truncated=truncated,
                        limit_reason=limit_reason,
                        scanned_files=scanned_files,
                        scanned_bytes=scanned_bytes,
                        skipped_files=skipped_files,
                        blocked_entries=blocked_entries,
                    )

        return _SearchOutput(
            path=arguments.path,
            query=arguments.query,
            case_sensitive=arguments.case_sensitive,
            matches=tuple(matches),
            truncated=truncated,
            limit_reason=limit_reason,
            scanned_files=scanned_files,
            scanned_bytes=scanned_bytes,
            skipped_files=skipped_files,
            blocked_entries=blocked_entries,
        )
