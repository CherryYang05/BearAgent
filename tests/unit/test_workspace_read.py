import asyncio
from collections.abc import Mapping
from pathlib import Path

from pydantic import JsonValue

from bearagent.adapters.tools import WorkspaceBoundary, WorkspaceReadTool
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import ToolCallId
from bearagent.domain.tools import ToolRequest, ToolStatus


def _request(arguments: Mapping[str, JsonValue]) -> ToolRequest:
    return ToolRequest(
        tool_call_id=ToolCallId.new(),
        name="workspace.read",
        arguments=arguments,
    )


def test_read_returns_complete_line_page_and_next_start(tmp_path: Path) -> None:
    (tmp_path / "guide.md").write_bytes("一\n二\n三\n".encode())
    tool = WorkspaceReadTool(WorkspaceBoundary(tmp_path))
    request = _request({"path": r".\guide.md", "start_line": 2, "max_lines": 1})

    result = asyncio.run(tool.execute(tool.prepare(request)))

    assert result.status is ToolStatus.SUCCEEDED
    assert result.data == {
        "path": "guide.md",
        "text": "二\n",
        "start_line": 2,
        "end_line": 2,
        "next_start_line": 3,
        "total_lines": 3,
        "truncated": True,
    }


def test_read_returns_safe_non_text_failure(tmp_path: Path) -> None:
    (tmp_path / "binary.dat").write_bytes(b"text\x00binary")
    tool = WorkspaceReadTool(WorkspaceBoundary(tmp_path))
    request = _request({"path": "binary.dat"})

    result = asyncio.run(tool.execute(tool.prepare(request)))

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code is ErrorCode.WORKSPACE_NOT_TEXT
    assert str(tmp_path) not in result.model_dump_json()


def test_read_past_end_returns_an_explicit_empty_page(tmp_path: Path) -> None:
    (tmp_path / "one.txt").write_text("one\n", encoding="utf-8")
    tool = WorkspaceReadTool(WorkspaceBoundary(tmp_path))
    request = _request({"path": "one.txt", "start_line": 10})

    result = asyncio.run(tool.execute(tool.prepare(request)))

    assert result.status is ToolStatus.SUCCEEDED
    assert result.data["text"] == ""
    assert result.data["end_line"] is None
    assert result.data["next_start_line"] is None
    assert result.data["truncated"] is False
