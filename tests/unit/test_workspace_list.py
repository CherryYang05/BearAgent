import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from bearagent.adapters.tools import WorkspaceBoundary, WorkspaceListTool
from bearagent.domain.ids import ToolCallId
from bearagent.domain.tools import ToolRequest, ToolStatus


def _request(arguments: Mapping[str, JsonValue]) -> ToolRequest:
    return ToolRequest(
        tool_call_id=ToolCallId.new(),
        name="workspace.list",
        arguments=arguments,
    )


def test_list_prepare_canonicalizes_windows_and_unix_input(tmp_path: Path) -> None:
    tool = WorkspaceListTool(WorkspaceBoundary(tmp_path))

    prepared = tool.prepare(_request({"path": r"docs\api", "limit": 10}))

    assert prepared.arguments == {"path": "docs/api", "offset": 0, "limit": 10}


def test_list_returns_stable_pages(tmp_path: Path) -> None:
    for name in ("c.txt", "a.txt", "b.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    tool = WorkspaceListTool(WorkspaceBoundary(tmp_path))
    request = _request({"path": ".", "offset": 1, "limit": 1})

    result = asyncio.run(tool.execute(tool.prepare(request)))

    assert result.status is ToolStatus.SUCCEEDED
    entries = cast(tuple[Mapping[str, JsonValue], ...], result.data["entries"])
    assert [entry["path"] for entry in entries] == ["b.txt"]
    assert result.data["next_offset"] == 2
    assert result.data["truncated"] is True
