"""Portable lexical paths and fail-closed access to one workspace root."""

import os
import stat
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

from bearagent.adapters.tools.workspace_limits import (
    MAX_DIRECTORY_ENTRIES,
    MAX_WORKSPACE_PATH_BYTES,
    MAX_WORKSPACE_SEGMENT_BYTES,
    MAX_WORKSPACE_SEGMENTS,
)
from bearagent.domain.errors import ErrorCode

type WorkspaceEntryKind = Literal["file", "directory", "blocked"]

_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


@dataclass(frozen=True, slots=True)
class WorkspaceEntry:
    """One portable directory entry without host path metadata."""

    path: str
    kind: WorkspaceEntryKind
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class WorkspaceDirectorySnapshot:
    """Stable direct children and the number of unrepresentable entries."""

    entries: tuple[WorkspaceEntry, ...]
    blocked_entries: int


@dataclass(frozen=True, slots=True)
class _ResolvedWorkspacePath:
    relative_path: str
    path: Path
    stat_result: os.stat_result


class WorkspaceBoundaryError(Exception):
    """Safe adapter error that never includes a host path or raw exception."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


def normalize_workspace_path(raw_path: str) -> str:
    """Return one portable relative path without touching the filesystem."""
    if not raw_path:
        raise ValueError("workspace path must not be empty")
    if len(raw_path.encode("utf-8")) > MAX_WORKSPACE_PATH_BYTES:
        raise ValueError("workspace path exceeds the byte limit")
    if raw_path[0] in {"/", "\\"}:
        raise ValueError("workspace path must be relative")
    if any(ord(character) < 32 or ord(character) == 127 for character in raw_path):
        raise ValueError("workspace path contains a control character")
    if ":" in raw_path:
        raise ValueError("workspace path cannot contain a drive or stream separator")

    # Both host styles are accepted at the untrusted edge. Policy and execution
    # only see '/', so the same resource cannot acquire two authorization forms.
    portable = raw_path.replace("\\", "/")
    segments: list[str] = []
    for segment in portable.split("/"):
        if segment in {"", "."}:
            continue
        if segment == "..":
            raise ValueError("workspace path cannot contain a parent segment")
        if segment.endswith((" ", ".")):
            raise ValueError("workspace path segments cannot end in a space or dot")
        if len(segment.encode("utf-8")) > MAX_WORKSPACE_SEGMENT_BYTES:
            raise ValueError("workspace path segment exceeds the byte limit")
        device_stem = segment.split(".", maxsplit=1)[0].upper()
        if device_stem in _WINDOWS_RESERVED_NAMES:
            raise ValueError("workspace path contains a reserved device name")
        segments.append(segment)

    if len(segments) > MAX_WORKSPACE_SEGMENTS:
        raise ValueError("workspace path has too many segments")
    normalized = "/".join(segments) if segments else "."
    if len(normalized.encode("utf-8")) > MAX_WORKSPACE_PATH_BYTES:
        raise ValueError("workspace path exceeds the byte limit")
    return normalized


class WorkspaceBoundary:
    """Resolve and open ordinary files without following workspace links."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        root_path = Path(root)
        try:
            root_stat = os.stat(root_path, follow_symlinks=False)
        except OSError as error:
            raise ValueError("workspace root must be an accessible directory") from error
        if _is_link_like(root_path, root_stat):
            raise ValueError("workspace root cannot be a link or reparse point")
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ValueError("workspace root must be a directory")
        try:
            resolved_root = root_path.resolve(strict=True)
            resolved_stat = os.stat(resolved_root, follow_symlinks=False)
        except OSError as error:
            raise ValueError("workspace root must be an accessible directory") from error
        if not os.path.samestat(root_stat, resolved_stat):
            raise ValueError("workspace root changed during initialization")
        self._root = resolved_root
        self._root_stat = resolved_stat

    @property
    def root(self) -> Path:
        """Return the trusted canonical root for bootstrap diagnostics only."""
        return self._root

    def resolve_file(self, relative_path: str) -> _ResolvedWorkspacePath:
        """Resolve one ordinary file below the fixed root."""
        return self._resolve_existing(relative_path, expected="file")

    def resolve_directory(self, relative_path: str) -> _ResolvedWorkspacePath:
        """Resolve one ordinary directory below the fixed root."""
        return self._resolve_existing(relative_path, expected="directory")

    def file_size(self, relative_path: str) -> int:
        """Return the current verified regular-file size."""
        return self.resolve_file(relative_path).stat_result.st_size

    @contextmanager
    def open_binary(self, relative_path: str) -> Generator[BinaryIO, None, None]:
        """Open a verified regular file and compare its pre-open identity."""
        resolved = self.resolve_file(relative_path)
        try:
            handle = resolved.path.open("rb")
        except FileNotFoundError as error:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_NOT_FOUND,
                "Workspace file does not exist.",
            ) from error
        except OSError as error:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_ACCESS_FAILED,
                "Workspace file could not be opened.",
            ) from error
        try:
            opened_stat = os.fstat(handle.fileno())
            current_stat = self._safe_lstat(resolved.path)
            # No content is read until both checks agree. This closes the common
            # check/open race where the final path is replaced with a link.
            if (
                _is_link_like(resolved.path, current_stat)
                or not os.path.samestat(resolved.stat_result, opened_stat)
                or not os.path.samestat(resolved.stat_result, current_stat)
            ):
                raise WorkspaceBoundaryError(
                    ErrorCode.WORKSPACE_PATH_DENIED,
                    "Workspace file changed during boundary validation.",
                )
            yield handle
        except WorkspaceBoundaryError:
            raise
        except OSError as error:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_ACCESS_FAILED,
                "Workspace file could not be read.",
            ) from error
        finally:
            handle.close()

    def list_directory(
        self,
        relative_path: str,
        *,
        max_entries: int = MAX_DIRECTORY_ENTRIES,
        deadline: float | None = None,
    ) -> WorkspaceDirectorySnapshot:
        """Snapshot direct children without following link-like entries."""
        resolved = self.resolve_directory(relative_path)
        entries: list[WorkspaceEntry] = []
        blocked_entries = 0
        try:
            with os.scandir(resolved.path) as iterator:
                for index, directory_entry in enumerate(iterator, start=1):
                    if deadline is not None and time.monotonic() >= deadline:
                        raise WorkspaceBoundaryError(
                            ErrorCode.TOOL_TIMEOUT,
                            "Workspace Tool reached its execution deadline.",
                        )
                    if index > max_entries:
                        raise WorkspaceBoundaryError(
                            ErrorCode.WORKSPACE_LIMIT_EXCEEDED,
                            "Workspace directory exceeds the entry limit.",
                        )
                    entry_path = Path(directory_entry.path)
                    entry_stat = self._safe_lstat(entry_path)
                    portable_path = _portable_child_path(relative_path, directory_entry.name)
                    if portable_path is None:
                        blocked_entries += 1
                        continue
                    if _is_link_like(entry_path, entry_stat):
                        entries.append(WorkspaceEntry(portable_path, "blocked", None))
                    elif stat.S_ISDIR(entry_stat.st_mode):
                        entries.append(WorkspaceEntry(portable_path, "directory", None))
                    elif stat.S_ISREG(entry_stat.st_mode):
                        entries.append(WorkspaceEntry(portable_path, "file", entry_stat.st_size))
                    else:
                        entries.append(WorkspaceEntry(portable_path, "blocked", None))
        except WorkspaceBoundaryError:
            raise
        except OSError as error:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_ACCESS_FAILED,
                "Workspace directory could not be listed.",
            ) from error

        current_stat = self._safe_lstat(resolved.path)
        if _is_link_like(resolved.path, current_stat) or not os.path.samestat(
            resolved.stat_result, current_stat
        ):
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_PATH_DENIED,
                "Workspace directory changed during boundary validation.",
            )
        return WorkspaceDirectorySnapshot(
            entries=tuple(sorted(entries, key=lambda entry: entry.path)),
            blocked_entries=blocked_entries,
        )

    def _resolve_existing(
        self,
        relative_path: str,
        *,
        expected: Literal["file", "directory"],
    ) -> _ResolvedWorkspacePath:
        normalized = normalize_workspace_path(relative_path)
        self._assert_root_identity()
        segments = () if normalized == "." else tuple(normalized.split("/"))
        current = self._root
        current_stat = self._root_stat
        for index, segment in enumerate(segments):
            current = current / segment
            current_stat = self._safe_lstat(current)
            if _is_link_like(current, current_stat):
                raise WorkspaceBoundaryError(
                    ErrorCode.WORKSPACE_PATH_DENIED,
                    "Workspace path cannot pass through a link or reparse point.",
                )
            if index < len(segments) - 1 and not stat.S_ISDIR(current_stat.st_mode):
                raise WorkspaceBoundaryError(
                    ErrorCode.WORKSPACE_WRONG_TYPE,
                    "Workspace path contains a non-directory parent.",
                )

        if expected == "file" and not stat.S_ISREG(current_stat.st_mode):
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_WRONG_TYPE,
                "Workspace path is not a regular file.",
            )
        if expected == "directory" and not stat.S_ISDIR(current_stat.st_mode):
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_WRONG_TYPE,
                "Workspace path is not a directory.",
            )
        try:
            physical_path = current.resolve(strict=True)
            physical_path.relative_to(self._root)
        except (OSError, RuntimeError, ValueError) as error:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_PATH_DENIED,
                "Workspace path resolves outside the configured root.",
            ) from error
        return _ResolvedWorkspacePath(normalized, current, current_stat)

    def _assert_root_identity(self) -> None:
        root_stat = self._safe_lstat(self._root)
        if _is_link_like(self._root, root_stat) or not os.path.samestat(self._root_stat, root_stat):
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_PATH_DENIED,
                "Workspace root changed after configuration.",
            )

    @staticmethod
    def _safe_lstat(path: Path) -> os.stat_result:
        try:
            return os.stat(path, follow_symlinks=False)
        except FileNotFoundError as error:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_NOT_FOUND,
                "Workspace path does not exist.",
            ) from error
        except OSError as error:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_ACCESS_FAILED,
                "Workspace path could not be inspected.",
            ) from error


def _portable_child_path(parent: str, name: str) -> str | None:
    raw_path = name if parent == "." else f"{parent}/{name}"
    try:
        return normalize_workspace_path(raw_path)
    except ValueError:
        return None


def _is_link_like(path: Path, path_stat: os.stat_result) -> bool:
    if stat.S_ISLNK(path_stat.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(path_stat, "st_file_attributes", 0)
    if reparse_flag and file_attributes & reparse_flag:
        return True
    try:
        return path.is_junction()
    except OSError:
        return True
