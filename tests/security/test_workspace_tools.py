import asyncio
import threading
from pathlib import Path
from typing import IO, Any, cast

import pytest

from bearagent.adapters.tools import (
    WorkspaceBoundary,
    WorkspaceBoundaryError,
    WorkspaceReadTool,
)
from bearagent.adapters.tools.workspace_limits import MAX_TEXT_FILE_BYTES
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import ToolCallId
from bearagent.domain.tools import PreparedToolRequest, ToolRequest, ToolResult, ToolStatus
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry


def _read_request(path: str) -> ToolRequest:
    return ToolRequest(
        tool_call_id=ToolCallId.new(),
        name="workspace.read",
        arguments={"path": path},
    )


@pytest.mark.parametrize(
    "path",
    ["../secret.txt", "/etc/passwd", r"C:\secret.txt", r"\\server\share\secret"],
)
def test_executor_rejects_escaping_paths_without_echoing_them(tmp_path: Path, path: str) -> None:
    tool = WorkspaceReadTool(WorkspaceBoundary(tmp_path))
    executor = ToolExecutor(ToolRegistry([tool]), FixedToolPolicy([tool.spec.name]))

    result = asyncio.run(executor.execute(_read_request(path)))

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code is ErrorCode.TOOL_INVALID_INPUT
    assert path not in result.model_dump_json()


def test_boundary_never_follows_workspace_symlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside secret", encoding="utf-8")
    link = tmp_path / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")
    boundary = WorkspaceBoundary(tmp_path)

    with pytest.raises(WorkspaceBoundaryError) as captured:
        boundary.resolve_file("linked.txt")

    assert captured.value.code is ErrorCode.WORKSPACE_PATH_DENIED
    assert str(outside) not in str(captured.value)


def test_boundary_rejects_junction_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "junction"
    target.mkdir()
    boundary = WorkspaceBoundary(tmp_path)
    original_is_junction = Path.is_junction

    def classify_target_as_junction(path: Path) -> bool:
        return path == target or original_is_junction(path)

    monkeypatch.setattr(Path, "is_junction", classify_target_as_junction)

    with pytest.raises(WorkspaceBoundaryError) as captured:
        boundary.resolve_directory("junction")

    assert captured.value.code is ErrorCode.WORKSPACE_PATH_DENIED


def test_boundary_rejects_file_replaced_between_check_and_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target.txt"
    target.write_text("original", encoding="utf-8")
    boundary = WorkspaceBoundary(tmp_path)
    original_open = Path.open
    replaced = False

    def replacing_open(path: Path, *args: Any, **kwargs: Any) -> IO[Any]:
        nonlocal replaced
        if path == target and not replaced:
            replaced = True
            path.unlink()
            with original_open(path, "w", encoding="utf-8") as replacement:
                replacement.write("replacement secret")
        return cast(IO[Any], original_open(path, *args, **kwargs))

    monkeypatch.setattr(Path, "open", replacing_open)
    reached_read = False

    with (
        pytest.raises(WorkspaceBoundaryError) as captured,
        boundary.open_binary("target.txt") as handle,
    ):
        reached_read = True
        handle.read()

    assert captured.value.code is ErrorCode.WORKSPACE_PATH_DENIED
    assert reached_read is False


def test_read_rejects_file_over_trusted_limit(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_bytes(b"x" * (MAX_TEXT_FILE_BYTES + 1))
    tool = WorkspaceReadTool(WorkspaceBoundary(tmp_path))

    result = asyncio.run(tool.execute(tool.prepare(_read_request("large.txt"))))

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code is ErrorCode.WORKSPACE_LIMIT_EXCEEDED


def test_workspace_thread_cancellation_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "readme.md").write_text("BearAgent", encoding="utf-8")
    tool = WorkspaceReadTool(WorkspaceBoundary(tmp_path))
    # This private seam deliberately holds the worker thread to exercise cancellation.
    original_execute_sync = tool._execute_sync  # pyright: ignore[reportPrivateUsage]
    started = threading.Event()
    release = threading.Event()

    def delayed_execute(request: PreparedToolRequest) -> ToolResult:
        started.set()
        release.wait(timeout=2)
        return original_execute_sync(request)

    monkeypatch.setattr(tool, "_execute_sync", delayed_execute)
    executor = ToolExecutor(ToolRegistry([tool]), FixedToolPolicy([tool.spec.name]))

    async def exercise() -> None:
        task = asyncio.create_task(executor.execute(_read_request("readme.md")))
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()

    asyncio.run(exercise())
