import asyncio
import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

from bearagent.adapters.tools import (
    WorkspaceBoundary,
    WorkspaceBoundaryError,
    WorkspaceWriteTool,
)
from bearagent.adapters.tools.workspace_boundary import StagedWorkspaceOutput
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import ToolCallId
from bearagent.domain.tools import ToolRequest, ToolStatus
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry


def _write_request(path: str, content: str = "new content") -> ToolRequest:
    return ToolRequest(
        tool_call_id=ToolCallId.new(),
        name="workspace.write",
        arguments={"path": path, "content": content},
    )


def test_default_policy_denies_before_creating_outputs(tmp_path: Path) -> None:
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))
    executor = ToolExecutor(ToolRegistry([tool]), FixedToolPolicy())

    result = asyncio.run(executor.execute(_write_request("outputs/intro.md")))

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code is ErrorCode.TOOL_PERMISSION_DENIED
    assert not (tmp_path / "outputs").exists()


@pytest.mark.parametrize(
    "path",
    ["README.md", "../outputs/secret.txt", "/outputs/secret.txt", r"C:\outputs\secret.txt"],
)
def test_executor_rejects_paths_outside_outputs_without_echoing_them(
    tmp_path: Path,
    path: str,
) -> None:
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))
    executor = ToolExecutor(ToolRegistry([tool]), FixedToolPolicy([tool.spec.name]))

    result = asyncio.run(executor.execute(_write_request(path)))

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code is ErrorCode.TOOL_INVALID_INPUT
    assert path not in result.model_dump_json()
    assert not (tmp_path / "outputs").exists()


def test_replace_failure_preserves_old_target_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    target = output_dir / "intro.md"
    target.write_text("old content", encoding="utf-8")
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))

    def fail_replace(_source: os.PathLike[str], _target: os.PathLike[str]) -> None:
        raise PermissionError("host path and secret should be hidden")

    monkeypatch.setattr(os, "replace", fail_replace)

    result = asyncio.run(tool.execute(tool.prepare(_write_request("outputs/intro.md"))))

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code is ErrorCode.WORKSPACE_ACCESS_FAILED
    assert target.read_text(encoding="utf-8") == "old content"
    assert list(output_dir.iterdir()) == [target]
    assert str(tmp_path) not in result.model_dump_json()
    assert "secret" not in result.model_dump_json()


def test_fsync_failure_preserves_old_target_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    target = output_dir / "intro.md"
    target.write_text("old content", encoding="utf-8")
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("sensitive host detail")

    monkeypatch.setattr(os, "fsync", fail_fsync)

    result = asyncio.run(tool.execute(tool.prepare(_write_request("outputs/intro.md"))))

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code is ErrorCode.WORKSPACE_ACCESS_FAILED
    assert target.read_text(encoding="utf-8") == "old content"
    assert list(output_dir.iterdir()) == [target]
    assert "sensitive" not in result.model_dump_json()


def test_output_directory_creation_failure_is_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))
    original_mkdir = Path.mkdir

    def fail_outputs_mkdir(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if path == tmp_path / "outputs":
            raise PermissionError("sensitive directory detail")
        original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", fail_outputs_mkdir)

    result = asyncio.run(tool.execute(tool.prepare(_write_request("outputs/intro.md"))))

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code is ErrorCode.WORKSPACE_ACCESS_FAILED
    assert not (tmp_path / "outputs").exists()
    assert "sensitive" not in result.model_dump_json()


def test_temporary_file_creation_failure_preserves_old_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    target = outputs / "intro.md"
    target.write_text("old", encoding="utf-8")
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))

    def fail_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
        raise PermissionError("sensitive temporary detail")

    monkeypatch.setattr(tempfile, "mkstemp", fail_mkstemp)

    result = asyncio.run(tool.execute(tool.prepare(_write_request("outputs/intro.md"))))

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code is ErrorCode.WORKSPACE_ACCESS_FAILED
    assert target.read_text(encoding="utf-8") == "old"
    assert list(outputs.iterdir()) == [target]
    assert "sensitive" not in result.model_dump_json()


def test_write_rejects_link_like_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    blocked = outputs / "linked"
    blocked.mkdir()
    boundary = WorkspaceBoundary(tmp_path)
    tool = WorkspaceWriteTool(boundary)
    original_is_junction = Path.is_junction

    def classify_as_junction(path: Path) -> bool:
        return path == blocked or original_is_junction(path)

    monkeypatch.setattr(Path, "is_junction", classify_as_junction)

    result = asyncio.run(tool.execute(tool.prepare(_write_request("outputs/linked/intro.md"))))

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code is ErrorCode.WORKSPACE_PATH_DENIED
    assert not (blocked / "intro.md").exists()


def test_write_rejects_link_like_or_directory_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    target = outputs / "intro.md"
    target.write_text("old", encoding="utf-8")
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))
    original_is_junction = Path.is_junction

    def classify_target_as_junction(path: Path) -> bool:
        return path == target or original_is_junction(path)

    monkeypatch.setattr(Path, "is_junction", classify_target_as_junction)
    link_result = asyncio.run(tool.execute(tool.prepare(_write_request("outputs/intro.md"))))

    assert link_result.status is ToolStatus.FAILED
    assert link_result.error is not None
    assert link_result.error.code is ErrorCode.WORKSPACE_PATH_DENIED
    assert target.read_text(encoding="utf-8") == "old"

    monkeypatch.setattr(Path, "is_junction", original_is_junction)
    target.unlink()
    target.mkdir()
    directory_result = asyncio.run(tool.execute(tool.prepare(_write_request("outputs/intro.md"))))
    assert directory_result.status is ToolStatus.FAILED
    assert directory_result.error is not None
    assert directory_result.error.code is ErrorCode.WORKSPACE_WRONG_TYPE


def test_parent_replacement_before_commit_is_denied(tmp_path: Path) -> None:
    boundary = WorkspaceBoundary(tmp_path)
    staged = boundary.stage_output(
        "outputs/intro.md",
        b"complete",
        deadline=time.monotonic() + 5,
    )
    original_outputs = tmp_path / "outputs-original"
    (tmp_path / "outputs").rename(original_outputs)
    (tmp_path / "outputs").mkdir()

    with pytest.raises(WorkspaceBoundaryError) as captured:
        boundary.commit_output(staged, deadline=time.monotonic() + 5)

    assert captured.value.code is ErrorCode.WORKSPACE_PATH_DENIED
    assert not (tmp_path / "outputs" / "intro.md").exists()
    assert not (original_outputs / "intro.md").exists()


def test_cancellation_during_staging_never_commits_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))
    executor = ToolExecutor(ToolRegistry([tool]), FixedToolPolicy([tool.spec.name]))
    original_stage = tool._stage_sync  # pyright: ignore[reportPrivateUsage]
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def delayed_stage(path: str, content: bytes, deadline: float) -> StagedWorkspaceOutput:
        started.set()
        release.wait(timeout=2)
        try:
            return original_stage(path, content, deadline)
        finally:
            finished.set()

    monkeypatch.setattr(tool, "_stage_sync", delayed_stage)

    async def exercise() -> None:
        task = asyncio.create_task(executor.execute(_write_request("outputs/intro.md")))
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
            assert await asyncio.to_thread(finished.wait, 1)

    asyncio.run(exercise())
    assert not (tmp_path / "outputs" / "intro.md").exists()


def test_executor_timeout_during_staging_does_not_retry_or_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = WorkspaceWriteTool(WorkspaceBoundary(tmp_path))
    tool.spec = tool.spec.model_copy(update={"timeout_ms": 10})
    executor = ToolExecutor(ToolRegistry([tool]), FixedToolPolicy([tool.spec.name]))
    original_stage = tool._stage_sync  # pyright: ignore[reportPrivateUsage]
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    calls = 0

    def delayed_stage(path: str, content: bytes, deadline: float) -> StagedWorkspaceOutput:
        nonlocal calls
        calls += 1
        started.set()
        release.wait(timeout=2)
        try:
            return original_stage(path, content, deadline)
        finally:
            finished.set()

    monkeypatch.setattr(tool, "_stage_sync", delayed_stage)

    async def exercise() -> ToolStatus:
        task = asyncio.create_task(executor.execute(_write_request("outputs/intro.md")))
        assert await asyncio.to_thread(started.wait, 1)
        result = await task
        assert result.error is not None
        assert result.error.code is ErrorCode.TOOL_TIMEOUT
        release.set()
        assert await asyncio.to_thread(finished.wait, 1)
        return result.status

    assert asyncio.run(exercise()) is ToolStatus.FAILED
    assert calls == 1
    assert not (tmp_path / "outputs" / "intro.md").exists()
