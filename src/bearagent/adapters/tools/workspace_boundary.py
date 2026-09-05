"""Portable lexical paths and fail-closed access to one workspace root."""

import os
import stat
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
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


@dataclass(frozen=True, slots=True)
class StagedWorkspaceOutput:
    """One complete temporary output that has not reached its target name."""

    relative_path: str
    parent_relative_path: str
    target_path: Path
    temporary_path: Path
    parent_stat: os.stat_result
    temporary_stat: os.stat_result


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


def normalize_output_path(raw_path: str) -> str:
    """Return one normalized file path strictly below outputs/."""
    normalized = normalize_workspace_path(raw_path)
    segments = normalized.split("/")
    if len(segments) < 2 or segments[0] != "outputs":
        raise ValueError("output path must name a file below outputs")
    return normalized


class WorkspaceBoundary:
    """Resolve and open ordinary files without following workspace links."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        protected_paths: tuple[Path, ...] = (),
    ) -> None:
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
        # These paths come from trusted composition, never from Tool arguments.
        self._protected_paths = tuple(path.resolve(strict=False) for path in protected_paths)

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

    def stage_output(
        self,
        relative_path: str,
        data: bytes,
        *,
        deadline: float,
    ) -> StagedWorkspaceOutput:
        """Write and fsync a same-directory temporary file without changing the target."""
        normalized = normalize_output_path(relative_path)
        self._require_accessible(self._root.joinpath(*normalized.split("/")))
        segments = normalized.split("/")
        parent_relative = "/".join(segments[:-1])
        parent = self._ensure_output_directory(parent_relative, deadline=deadline)
        target = parent.path / segments[-1]
        self._validate_output_target(target)
        _check_deadline(deadline)

        temporary_path: Path | None = None
        descriptor: int | None = None
        try:
            descriptor, raw_temporary_path = tempfile.mkstemp(
                prefix=".bearagent-",
                suffix=".tmp",
                dir=parent.path,
            )
            temporary_path = Path(raw_temporary_path)
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = None
                for offset in range(0, len(data), 64 * 1_024):
                    _check_deadline(deadline)
                    handle.write(data[offset : offset + 64 * 1_024])
                handle.flush()
                os.fsync(handle.fileno())

            temporary_stat = self._safe_lstat(temporary_path)
            current_parent_stat = self._safe_lstat(parent.path)
            if (
                _is_link_like(temporary_path, temporary_stat)
                or not stat.S_ISREG(temporary_stat.st_mode)
                or _is_link_like(parent.path, current_parent_stat)
                or not os.path.samestat(parent.stat_result, current_parent_stat)
            ):
                raise WorkspaceBoundaryError(
                    ErrorCode.WORKSPACE_PATH_DENIED,
                    "Workspace output path changed while content was staged.",
                )
            _check_deadline(deadline)
            return StagedWorkspaceOutput(
                relative_path=normalized,
                parent_relative_path=parent_relative,
                target_path=target,
                temporary_path=temporary_path,
                parent_stat=parent.stat_result,
                temporary_stat=temporary_stat,
            )
        except WorkspaceBoundaryError:
            _discard_temporary_path(temporary_path)
            raise
        except OSError as error:
            _discard_temporary_path(temporary_path)
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_ACCESS_FAILED,
                "Workspace output could not be staged.",
            ) from error
        finally:
            if descriptor is not None:
                with suppress(OSError):
                    os.close(descriptor)

    def commit_output(self, staged: StagedWorkspaceOutput, *, deadline: float) -> None:
        """Atomically replace one target with a complete staged output."""
        _check_deadline(deadline)
        parent = self.resolve_directory(staged.parent_relative_path)
        if not os.path.samestat(staged.parent_stat, parent.stat_result):
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_PATH_DENIED,
                "Workspace output directory changed before commit.",
            )
        temporary_stat = self._safe_lstat(staged.temporary_path)
        if (
            _is_link_like(staged.temporary_path, temporary_stat)
            or not stat.S_ISREG(temporary_stat.st_mode)
            or not _same_path_file_snapshot(staged.temporary_stat, temporary_stat)
        ):
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_PATH_DENIED,
                "Workspace temporary output changed before commit.",
            )
        self._validate_output_target(staged.target_path)
        _check_deadline(deadline)

        # No await occurs around this only target-changing operation. A timed-out
        # staging worker can therefore leave a temporary file, but cannot commit it.
        try:
            os.replace(staged.temporary_path, staged.target_path)
        except OSError as error:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_ACCESS_FAILED,
                "Workspace output could not be committed.",
            ) from error

    @staticmethod
    def discard_output(staged: StagedWorkspaceOutput) -> None:
        """Best-effort removal that refuses to unlink a replaced temporary object."""
        with suppress(OSError):
            current_stat = os.stat(staged.temporary_path, follow_symlinks=False)
            if _same_path_file_snapshot(staged.temporary_stat, current_stat):
                os.unlink(staged.temporary_path)

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
            # check/open race where the final path is replaced. File systems may
            # immediately reuse an inode, so dev/inode equality alone is not enough.
            if (
                _is_link_like(resolved.path, current_stat)
                or not _same_open_file_snapshot(resolved.stat_result, opened_stat)
                or not _same_path_file_snapshot(resolved.stat_result, current_stat)
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
                    if (
                        self._is_protected(entry_path)
                        or _is_link_like(entry_path, entry_stat)
                        or (stat.S_ISREG(entry_stat.st_mode) and entry_stat.st_nlink != 1)
                    ):
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
        self._require_accessible(self._root.joinpath(*normalized.split("/")))
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
        self._require_accessible(physical_path)
        if expected == "file" and current_stat.st_nlink != 1:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_PATH_DENIED,
                "Workspace file cannot have multiple hard links.",
            )
        return _ResolvedWorkspacePath(normalized, current, current_stat)

    def _ensure_output_directory(
        self,
        relative_path: str,
        *,
        deadline: float,
    ) -> _ResolvedWorkspacePath:
        normalized = normalize_workspace_path(relative_path)
        if normalized != "outputs" and not normalized.startswith("outputs/"):
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_PATH_DENIED,
                "Workspace output directory is outside outputs.",
            )
        self._assert_root_identity()
        current = self._root
        current_stat = self._root_stat
        for segment in normalized.split("/"):
            _check_deadline(deadline)
            current = current / segment
            self._require_accessible(current)
            try:
                current_stat = os.stat(current, follow_symlinks=False)
            except FileNotFoundError:
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
                except OSError as error:
                    raise WorkspaceBoundaryError(
                        ErrorCode.WORKSPACE_ACCESS_FAILED,
                        "Workspace output directory could not be created.",
                    ) from error
                current_stat = self._safe_lstat(current)
            except OSError as error:
                raise WorkspaceBoundaryError(
                    ErrorCode.WORKSPACE_ACCESS_FAILED,
                    "Workspace output directory could not be inspected.",
                ) from error
            if _is_link_like(current, current_stat):
                raise WorkspaceBoundaryError(
                    ErrorCode.WORKSPACE_PATH_DENIED,
                    "Workspace output path cannot pass through a link or reparse point.",
                )
            if not stat.S_ISDIR(current_stat.st_mode):
                raise WorkspaceBoundaryError(
                    ErrorCode.WORKSPACE_WRONG_TYPE,
                    "Workspace output path contains a non-directory parent.",
                )

        try:
            current.resolve(strict=True).relative_to(self._root)
        except (OSError, RuntimeError, ValueError) as error:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_PATH_DENIED,
                "Workspace output directory resolves outside the configured root.",
            ) from error
        return _ResolvedWorkspacePath(normalized, current, current_stat)

    def _validate_output_target(self, path: Path) -> None:
        self._require_accessible(path)
        try:
            target_stat = os.stat(path, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as error:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_ACCESS_FAILED,
                "Workspace output target could not be inspected.",
            ) from error
        if _is_link_like(path, target_stat):
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_PATH_DENIED,
                "Workspace output target cannot be a link or reparse point.",
            )
        if not stat.S_ISREG(target_stat.st_mode):
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_WRONG_TYPE,
                "Workspace output target is not a regular file.",
            )
        if target_stat.st_nlink != 1:
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_PATH_DENIED,
                "Workspace output target cannot have multiple hard links.",
            )

    def _is_protected(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self._root)
        except ValueError:
            return True
        if relative.parts:
            first = relative.parts[0].casefold()
            if first in {"data", ".git", ".env"} or first.startswith(".env."):
                return True
        return any(path.is_relative_to(protected) for protected in self._protected_paths)

    def _require_accessible(self, path: Path) -> None:
        if self._is_protected(path):
            raise WorkspaceBoundaryError(
                ErrorCode.WORKSPACE_PATH_DENIED,
                "Workspace path is reserved for local runtime data or configuration.",
            )

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


def _same_open_file_snapshot(
    expected: os.stat_result,
    observed: os.stat_result,
) -> bool:
    """Compare identity and metadata shared reliably by path stat and fstat."""
    return os.path.samestat(expected, observed) and (
        expected.st_mode,
        expected.st_size,
        expected.st_mtime_ns,
        expected.st_nlink,
    ) == (
        observed.st_mode,
        observed.st_size,
        observed.st_mtime_ns,
        observed.st_nlink,
    )


def _same_path_file_snapshot(
    expected: os.stat_result,
    observed: os.stat_result,
) -> bool:
    """Compare two path snapshots, including change time when both use stat."""
    return _same_open_file_snapshot(expected, observed) and (
        expected.st_ctime_ns == observed.st_ctime_ns
    )


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


def _check_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise WorkspaceBoundaryError(
            ErrorCode.TOOL_TIMEOUT,
            "Workspace Tool reached its execution deadline.",
        )


def _discard_temporary_path(path: Path | None) -> None:
    if path is None:
        return
    with suppress(OSError):
        os.unlink(path)
