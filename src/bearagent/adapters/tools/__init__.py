"""Built-in bounded workspace Tool adapters."""

import os
from pathlib import Path

from bearagent.adapters.tools.workspace_boundary import (
    WorkspaceBoundary,
    WorkspaceBoundaryError,
    normalize_output_path,
    normalize_workspace_path,
)
from bearagent.adapters.tools.workspace_list import WorkspaceListTool
from bearagent.adapters.tools.workspace_read import WorkspaceReadTool
from bearagent.adapters.tools.workspace_search import WorkspaceSearchTool
from bearagent.adapters.tools.workspace_write import WorkspaceWriteTool
from bearagent.domain.ids import IdGenerator
from bearagent.ports.tools import Tool

__all__ = [
    "WorkspaceBoundary",
    "WorkspaceBoundaryError",
    "WorkspaceListTool",
    "WorkspaceReadTool",
    "WorkspaceSearchTool",
    "WorkspaceWriteTool",
    "build_workspace_read_tools",
    "build_workspace_tools",
    "normalize_output_path",
    "normalize_workspace_path",
]


def build_workspace_read_tools(root: str | os.PathLike[str]) -> tuple[Tool, ...]:
    """Build all read-only Tools around one immutable workspace boundary."""
    boundary = WorkspaceBoundary(root)
    return (
        WorkspaceListTool(boundary),
        WorkspaceReadTool(boundary),
        WorkspaceSearchTool(boundary),
    )


def build_workspace_tools(
    root: str | os.PathLike[str],
    *,
    id_generator: IdGenerator | None = None,
    protected_paths: tuple[Path, ...] = (),
) -> tuple[Tool, ...]:
    """Build all P1 workspace Tools around one immutable boundary."""
    boundary = WorkspaceBoundary(root, protected_paths=protected_paths)
    return (
        WorkspaceListTool(boundary),
        WorkspaceReadTool(boundary),
        WorkspaceSearchTool(boundary),
        WorkspaceWriteTool(boundary, id_generator=id_generator),
    )
