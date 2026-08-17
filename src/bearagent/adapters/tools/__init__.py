"""Built-in bounded workspace Tool adapters."""

import os

from bearagent.adapters.tools.workspace_boundary import (
    WorkspaceBoundary,
    WorkspaceBoundaryError,
    normalize_workspace_path,
)
from bearagent.adapters.tools.workspace_list import WorkspaceListTool
from bearagent.adapters.tools.workspace_read import WorkspaceReadTool
from bearagent.adapters.tools.workspace_search import WorkspaceSearchTool
from bearagent.ports.tools import Tool

__all__ = [
    "WorkspaceBoundary",
    "WorkspaceBoundaryError",
    "WorkspaceListTool",
    "WorkspaceReadTool",
    "WorkspaceSearchTool",
    "build_workspace_read_tools",
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
