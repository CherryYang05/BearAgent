"""Bounded UTF-8 decoding shared by workspace read and search Tools."""

import os
import time
from dataclasses import dataclass

from bearagent.adapters.tools.workspace_boundary import (
    WorkspaceBoundary,
    WorkspaceBoundaryError,
)
from bearagent.adapters.tools.workspace_limits import (
    MAX_TEXT_FILE_BYTES,
    MAX_TEXT_LINE_BYTES,
)
from bearagent.domain.errors import ErrorCode


@dataclass(frozen=True, slots=True)
class WorkspaceTextFile:
    lines: tuple[str, ...]
    size_bytes: int


def read_utf8_file(
    boundary: WorkspaceBoundary,
    relative_path: str,
    *,
    deadline: float,
    max_file_bytes: int = MAX_TEXT_FILE_BYTES,
) -> WorkspaceTextFile:
    """Read one stable ordinary UTF-8 file under hard byte and line limits."""
    lines: list[str] = []
    total_bytes = 0
    with boundary.open_binary(relative_path) as handle:
        before = os.fstat(handle.fileno())
        if before.st_size > max_file_bytes:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_LIMIT_EXCEEDED,
                "Workspace file exceeds the text file limit.",
            )
        for raw_line in handle:
            _check_deadline(deadline)
            total_bytes += len(raw_line)
            if total_bytes > max_file_bytes or len(raw_line) > MAX_TEXT_LINE_BYTES:
                raise WorkspaceBoundaryError(
                    ErrorCode.WORKSPACE_LIMIT_EXCEEDED,
                    "Workspace file exceeds a text reading limit.",
                )
            try:
                line = raw_line.decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                raise WorkspaceBoundaryError(
                    ErrorCode.WORKSPACE_NOT_TEXT,
                    "Workspace file is not valid UTF-8 text.",
                ) from error
            if "\x00" in line:
                raise WorkspaceBoundaryError(
                    ErrorCode.WORKSPACE_NOT_TEXT,
                    "Workspace file contains binary text markers.",
                )
            lines.append(line)
        after = os.fstat(handle.fileno())
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or total_bytes != after.st_size
        ):
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_PATH_DENIED,
                "Workspace file changed while it was being read.",
            )
    return WorkspaceTextFile(tuple(lines), total_bytes)


def _check_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise WorkspaceBoundaryError(
            ErrorCode.TOOL_TIMEOUT,
            "Workspace Tool reached its execution deadline.",
        )
