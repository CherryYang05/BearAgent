import asyncio
import hashlib
from collections.abc import Mapping
from pathlib import Path

import pytest

from bearagent.adapters.tools import WorkspaceBoundary, WorkspaceWriteTool
from bearagent.adapters.tools.workspace_limits import (
    MAX_TEXT_LINE_BYTES,
    MAX_WRITE_CONTENT_BYTES,
)
from bearagent.domain.ids import ToolCallId
from bearagent.domain.tools import (
    ToolRequest,
    ToolRetrySafety,
    ToolSideEffect,
    ToolStatus,
)


def _write_request(path: str, content: str) -> ToolRequest:
    return ToolRequest(
        tool_call_id=ToolCallId.new(),
        name="workspace.write",
        arguments={"path": path, "content": content},
    )


def test_write_prepare_normalizes_output_path_without_io(tmp_path: Path) -> None:
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))
    request = _write_request(r"outputs\reports\.\intro.md", "BearAgent\n")

    prepared = tool.prepare(request)

    assert prepared.arguments == {
        "path": "outputs/reports/intro.md",
        "content": "BearAgent\n",
    }
    assert not (tmp_path / "outputs").exists()
    assert tool.spec.side_effect is ToolSideEffect.WORKSPACE_WRITE
    assert tool.spec.retry_safety is ToolRetrySafety.NOT_SAFE


@pytest.mark.parametrize(
    ("path", "content"),
    [
        ("README.md", "outside"),
        ("outputs", "directory"),
        ("outputs/../secret.txt", "escape"),
        ("outputs/nul.txt", "bad\x00content"),
        ("outputs/large.txt", "x" * (MAX_WRITE_CONTENT_BYTES + 1)),
        ("outputs/long-line.txt", "x" * (MAX_TEXT_LINE_BYTES + 1)),
    ],
    ids=["outside", "outputs-dir", "parent", "nul", "content-limit", "line-limit"],
)
def test_write_prepare_rejects_invalid_scope_or_content(
    tmp_path: Path,
    path: str,
    content: str,
) -> None:
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))

    with pytest.raises(ValueError):
        tool.prepare(_write_request(path, content))

    assert not (tmp_path / "outputs").exists()


def test_write_creates_nested_output_and_returns_artifact(tmp_path: Path) -> None:
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))
    content = "# BearAgent\n完整结果。\n"
    request = _write_request("outputs/reports/intro.md", content)

    result = asyncio.run(tool.execute(tool.prepare(request)))

    expected_bytes = content.encode("utf-8")
    assert result.status is ToolStatus.SUCCEEDED
    assert (tmp_path / "outputs" / "reports" / "intro.md").read_bytes() == expected_bytes
    artifact = result.data["artifact"]
    assert isinstance(artifact, Mapping)
    assert artifact["path"] == "outputs/reports/intro.md"
    assert artifact["kind"] == "text"
    assert artifact["encoding"] == "utf-8"
    assert artifact["size_bytes"] == len(expected_bytes)
    assert artifact["sha256"] == hashlib.sha256(expected_bytes).hexdigest()
    assert list((tmp_path / "outputs" / "reports").iterdir()) == [
        tmp_path / "outputs" / "reports" / "intro.md"
    ]


@pytest.mark.parametrize(
    "content",
    [
        "",
        "第一行\r\n第二行\n",
        ("x" * (MAX_TEXT_LINE_BYTES - 1) + "\n") * (MAX_WRITE_CONTENT_BYTES // MAX_TEXT_LINE_BYTES),
    ],
    ids=["empty", "utf8-original-newlines", "exact-content-and-line-limits"],
)
def test_write_preserves_content_at_supported_boundaries(
    tmp_path: Path,
    content: str,
) -> None:
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))

    result = asyncio.run(
        tool.execute(tool.prepare(_write_request("outputs/boundary.txt", content)))
    )

    expected = content.encode("utf-8")
    assert result.status is ToolStatus.SUCCEEDED
    assert (tmp_path / "outputs" / "boundary.txt").read_bytes() == expected
    artifact = result.data["artifact"]
    assert isinstance(artifact, Mapping)
    assert artifact["size_bytes"] == len(expected)
    assert artifact["sha256"] == hashlib.sha256(expected).hexdigest()


def test_write_prepare_rejects_unknown_fields(tmp_path: Path) -> None:
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))
    request = ToolRequest(
        tool_call_id=ToolCallId.new(),
        name="workspace.write",
        arguments={
            "path": "outputs/intro.md",
            "content": "safe",
            "grant": "write-anywhere",
        },
    )

    with pytest.raises(ValueError):
        tool.prepare(request)

    assert not (tmp_path / "outputs").exists()


def test_write_atomically_replaces_existing_output(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    target = output_dir / "intro.md"
    target.write_text("old", encoding="utf-8")
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))

    result = asyncio.run(tool.execute(tool.prepare(_write_request("outputs/intro.md", "new"))))

    assert result.status is ToolStatus.SUCCEEDED
    assert target.read_text(encoding="utf-8") == "new"
