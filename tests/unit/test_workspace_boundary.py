from pathlib import Path

import pytest

from bearagent.adapters.tools import WorkspaceBoundary, WorkspaceBoundaryError
from bearagent.domain.errors import ErrorCode


def test_boundary_lists_stable_portable_entries(tmp_path: Path) -> None:
    (tmp_path / "z.txt").write_text("z", encoding="utf-8")
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "nested.txt").write_text("nested", encoding="utf-8")
    boundary = WorkspaceBoundary(tmp_path)

    snapshot = boundary.list_directory(".")

    assert [(entry.path, entry.kind) for entry in snapshot.entries] == [
        ("a", "directory"),
        ("z.txt", "file"),
    ]
    assert snapshot.blocked_entries == 0


def test_boundary_opens_regular_file_and_rejects_wrong_types(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_bytes(b"BearAgent")
    boundary = WorkspaceBoundary(tmp_path)

    with boundary.open_binary("docs/readme.md") as handle:
        assert handle.read() == b"BearAgent"

    with pytest.raises(WorkspaceBoundaryError) as captured:
        boundary.resolve_file("docs")
    assert captured.value.code is ErrorCode.WORKSPACE_WRONG_TYPE


def test_boundary_returns_stable_not_found_error(tmp_path: Path) -> None:
    boundary = WorkspaceBoundary(tmp_path)

    with pytest.raises(WorkspaceBoundaryError) as captured:
        boundary.resolve_file("missing.txt")

    assert captured.value.code is ErrorCode.WORKSPACE_NOT_FOUND
    assert str(tmp_path) not in str(captured.value)


def test_boundary_requires_an_ordinary_directory_root(tmp_path: Path) -> None:
    file_root = tmp_path / "file.txt"
    file_root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a directory"):
        WorkspaceBoundary(file_root)
