import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from bearagent.adapters.tools import WorkspaceBoundary, WorkspaceSearchTool
from bearagent.domain.ids import ToolCallId
from bearagent.domain.tools import ToolRequest, ToolStatus


def _request(arguments: Mapping[str, JsonValue]) -> ToolRequest:
    return ToolRequest(
        tool_call_id=ToolCallId.new(),
        name="workspace.search",
        arguments=arguments,
    )


def test_search_returns_literal_matches_in_portable_path_order(tmp_path: Path) -> None:
    (tmp_path / "z.txt").write_text("BearAgent z\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.txt").write_text("BearAgent a\nnone\n", encoding="utf-8")
    tool = WorkspaceSearchTool(WorkspaceBoundary(tmp_path))
    request = _request({"path": ".", "query": "BearAgent"})

    result = asyncio.run(tool.execute(tool.prepare(request)))

    assert result.status is ToolStatus.SUCCEEDED
    matches = cast(tuple[Mapping[str, JsonValue], ...], result.data["matches"])
    assert [(match["path"], match["line_number"]) for match in matches] == [
        ("docs/a.txt", 1),
        ("z.txt", 1),
    ]


def test_search_can_match_case_insensitively_and_skips_non_text(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("BEARagent\n", encoding="utf-8")
    (tmp_path / "binary.dat").write_bytes(b"BearAgent\x00")
    tool = WorkspaceSearchTool(WorkspaceBoundary(tmp_path))
    request = _request({"path": ".", "query": "bearagent", "case_sensitive": False})

    result = asyncio.run(tool.execute(tool.prepare(request)))

    assert result.status is ToolStatus.SUCCEEDED
    assert result.data["skipped_files"] == 1
    matches = cast(tuple[Mapping[str, JsonValue], ...], result.data["matches"])
    assert [match["path"] for match in matches] == ["readme.md"]


def test_search_marks_result_limit_without_hiding_partial_status(tmp_path: Path) -> None:
    (tmp_path / "many.txt").write_text("hit\nhit\nhit\n", encoding="utf-8")
    tool = WorkspaceSearchTool(WorkspaceBoundary(tmp_path))
    request = _request({"query": "hit", "max_results": 2})

    result = asyncio.run(tool.execute(tool.prepare(request)))

    assert result.status is ToolStatus.SUCCEEDED
    assert len(cast(tuple[object, ...], result.data["matches"])) == 2
    assert result.data["truncated"] is True
    assert result.data["limit_reason"] == "max_results"
