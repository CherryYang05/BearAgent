"""Atomic bounded UTF-8 workspace output Tool."""

import asyncio
import hashlib
import time

from pydantic import BaseModel, ConfigDict

from bearagent.adapters.tools.workspace_boundary import (
    StagedWorkspaceOutput,
    WorkspaceBoundary,
    WorkspaceBoundaryError,
    normalize_output_path,
)
from bearagent.adapters.tools.workspace_common import (
    boundary_failure,
    json_model_data,
    success_result,
)
from bearagent.adapters.tools.workspace_limits import (
    MAX_TEXT_LINE_BYTES,
    MAX_WRITE_CONTENT_BYTES,
    MAX_WRITE_TOOL_INPUT_BYTES,
    MAX_WRITE_TOOL_OUTPUT_BYTES,
    WRITE_TIMEOUT_MS,
)
from bearagent.domain.artifacts import Artifact, ArtifactEncoding, ArtifactKind
from bearagent.domain.ids import ArtifactId, IdGenerator, Uuid4IdGenerator
from bearagent.domain.tools import (
    PreparedToolRequest,
    ToolRequest,
    ToolResult,
    ToolRetrySafety,
    ToolSideEffect,
    ToolSpec,
)


class _WriteArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    path: str
    content: str


class _WriteOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact: Artifact


class WorkspaceWriteTool:
    """Atomically create or replace one bounded UTF-8 file below outputs/."""

    spec = ToolSpec(
        name="workspace.write",
        description="Atomically write one bounded UTF-8 text file below outputs/.",
        input_schema=_WriteArguments.model_json_schema(),
        output_schema=_WriteOutput.model_json_schema(),
        side_effect=ToolSideEffect.WORKSPACE_WRITE,
        timeout_ms=WRITE_TIMEOUT_MS,
        max_input_bytes=MAX_WRITE_TOOL_INPUT_BYTES,
        max_output_bytes=MAX_WRITE_TOOL_OUTPUT_BYTES,
        retry_safety=ToolRetrySafety.NOT_SAFE,
    )

    def __init__(
        self,
        boundary: WorkspaceBoundary,
        *,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._boundary = boundary
        self._id_generator = Uuid4IdGenerator() if id_generator is None else id_generator

    def prepare(self, request: ToolRequest) -> PreparedToolRequest:
        """Validate output scope and text limits without filesystem I/O."""
        if request.name != self.spec.name:
            raise ValueError("request name does not match workspace.write")
        arguments = _WriteArguments.model_validate(dict(request.arguments))
        normalized_path = normalize_output_path(arguments.path)
        _content_bytes(arguments.content)
        return PreparedToolRequest(
            tool_call_id=request.tool_call_id,
            name=request.name,
            arguments={"path": normalized_path, "content": arguments.content},
        )

    async def execute(self, request: PreparedToolRequest) -> ToolResult:
        """Stage in a worker thread, then commit once without an intervening await."""
        arguments = _WriteArguments.model_validate(dict(request.arguments))
        content_bytes = _content_bytes(arguments.content)
        artifact = Artifact(
            artifact_id=self._id_generator.new(ArtifactId),
            path=arguments.path,
            kind=ArtifactKind.TEXT,
            encoding=ArtifactEncoding.UTF8,
            size_bytes=len(content_bytes),
            sha256=hashlib.sha256(content_bytes).hexdigest(),
        )
        result = success_result(
            request.tool_call_id,
            json_model_data(_WriteOutput(artifact=artifact)),
        )
        deadline = time.monotonic() + self.spec.timeout_ms / 1_000
        try:
            staged = await asyncio.to_thread(
                self._stage_sync,
                arguments.path,
                content_bytes,
                deadline,
            )
        except WorkspaceBoundaryError as error:
            return boundary_failure(request.tool_call_id, error)

        try:
            self._boundary.commit_output(staged, deadline=deadline)
        except WorkspaceBoundaryError as error:
            self._boundary.discard_output(staged)
            return boundary_failure(request.tool_call_id, error)
        return result

    def _stage_sync(
        self,
        relative_path: str,
        content: bytes,
        deadline: float,
    ) -> StagedWorkspaceOutput:
        return self._boundary.stage_output(relative_path, content, deadline=deadline)


def _content_bytes(content: str) -> bytes:
    if "\x00" in content:
        raise ValueError("workspace output contains a binary text marker")
    try:
        encoded = content.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValueError("workspace output must be valid UTF-8 text") from error
    if len(encoded) > MAX_WRITE_CONTENT_BYTES:
        raise ValueError("workspace output exceeds the content byte limit")

    lines = encoded.split(b"\n")
    for index, line in enumerate(lines):
        line_bytes = len(line) + (1 if index < len(lines) - 1 else 0)
        if line_bytes > MAX_TEXT_LINE_BYTES:
            raise ValueError("workspace output exceeds the line byte limit")
    return encoded
