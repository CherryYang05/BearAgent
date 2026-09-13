"""Read-only SQLite snapshots which do not depend on valid projection tables."""

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from bearagent._bounded_read import ReadControl, run_bounded_read
from bearagent.adapters.sqlite.store import (
    decode_event_row,
    load_run_projection,
    verify_store_schema,
)
from bearagent.domain.errors import ErrorCode
from bearagent.domain.events import Event
from bearagent.domain.ids import RunId
from bearagent.domain.replay import (
    DEFAULT_REPLAY_LIMITS,
    DEFAULT_SCAN_RUNS,
    MAX_REPLAY_BYTES,
    MAX_REPLAY_EVENTS,
    MAX_SCAN_RUNS,
    EventReplaySnapshot,
    EventRunPage,
    ProjectionAvailability,
    ReplayLimits,
)
from bearagent.domain.runs import RunState
from bearagent.ports.replay import EventReplayError, replay_error
from bearagent.ports.store import EventStoreCorruptionError, EventStoreError

_EVENT_COLUMNS = (
    "event_id",
    "run_id",
    "sequence",
    "event_type",
    "schema_version",
    "occurred_at",
    "causation_id",
    "correlation_id",
    "payload_json",
)
_RUN_COLUMNS = (
    "run_id",
    "session_id",
    "status",
    "max_model_iterations",
    "max_tokens",
    "max_cost_microusd",
    "max_wall_time_ms",
    "max_tool_calls",
    "model_iterations",
    "input_tokens",
    "output_tokens",
    "cost_microusd",
    "tool_calls",
    "created_at",
    "started_at",
    "completed_at",
    "terminal_error_json",
    "last_sequence",
)
_ACTIVITY_COLUMNS = (
    "activity_id",
    "run_id",
    "ordinal",
    "kind",
    "status",
    "requested_at",
    "started_at",
    "completed_at",
    "error_json",
    "model_call_id",
    "tool_call_id",
    "tool_name",
)


class SqliteEventReplaySource:
    """Never initializes schemas or repairs data; each operation owns a readonly connection."""

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path).absolute()

    async def read_run_events(
        self, run_id: RunId, *, limits: ReplayLimits = DEFAULT_REPLAY_LIMITS
    ) -> EventReplaySnapshot:
        return await run_bounded_read(
            lambda control: self._transaction(
                control, lambda connection: self._snapshot(connection, run_id, limits, control)
            ),
            timeout_ms=limits.timeout_ms,
        )

    async def list_event_run_ids(
        self,
        *,
        after_run_id: RunId | None = None,
        limit: int = DEFAULT_SCAN_RUNS,
        limits: ReplayLimits = DEFAULT_REPLAY_LIMITS,
    ) -> EventRunPage:
        if type(limit) is not int or not 1 <= limit <= MAX_SCAN_RUNS:
            raise replay_error(ErrorCode.INVALID_INPUT)
        return await run_bounded_read(
            lambda control: self._transaction(
                control, lambda connection: self._page(connection, after_run_id, limit, control)
            ),
            timeout_ms=limits.timeout_ms,
        )

    def _transaction[T](self, control: ReadControl, read: Callable[[sqlite3.Connection], T]) -> T:
        control.check()
        connection: sqlite3.Connection | None = None
        try:
            if self._path.is_symlink() or self._path.is_junction() or not self._path.is_file():
                raise replay_error(ErrorCode.PERSISTENCE_ERROR)
            connection = sqlite3.connect(
                self._path.as_uri() + "?mode=ro", uri=True, timeout=0.05, isolation_level=None
            )
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_REPLAY_BYTES)
            connection.set_progress_handler(lambda: int(control.stopped), 1_000)
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("BEGIN")
            verify_store_schema(connection, require_projections=False)
            control.check()
            result = read(connection)
            control.check()
            return result
        except EventReplayError:
            raise
        except (EventStoreError, sqlite3.Error, OSError) as error:
            control.check()
            raise replay_error(ErrorCode.PERSISTENCE_ERROR) from error
        except (ValidationError, ValueError, TypeError) as error:
            raise replay_error(ErrorCode.INVALID_EVENT) from error
        finally:
            if connection is not None:
                connection.close()

    def _snapshot(
        self,
        connection: sqlite3.Connection,
        run_id: RunId,
        limits: ReplayLimits,
        control: ReadControl,
    ) -> EventReplaySnapshot:
        try:
            count, raw_bytes = _table_size(connection, "events", _EVENT_COLUMNS, run_id)
        except sqlite3.DataError as error:
            if error.sqlite_errorcode == sqlite3.SQLITE_TOOBIG:
                raise replay_error(ErrorCode.QUERY_LIMIT_EXCEEDED) from error
            raise
        control.check()
        if count == 0:
            raise replay_error(ErrorCode.RUN_NOT_FOUND)
        if count > limits.max_events or raw_bytes > limits.max_bytes:
            raise replay_error(ErrorCode.QUERY_LIMIT_EXCEEDED)
        events: list[Event] = []
        encoded_bytes = 0
        cursor = connection.execute(
            f"SELECT {', '.join(_EVENT_COLUMNS)} FROM events WHERE run_id = ? ORDER BY sequence",
            (str(run_id),),
        )
        for row in cursor:
            control.check()
            try:
                event = decode_event_row(cast(tuple[object, ...], row))
            except EventStoreCorruptionError as error:
                raise replay_error(ErrorCode.INVALID_EVENT) from error
            encoded_bytes += len(event.model_dump_json().encode("utf-8"))
            if encoded_bytes > limits.max_bytes or len(events) >= limits.max_events:
                raise replay_error(ErrorCode.QUERY_LIMIT_EXCEEDED)
            events.append(event)
        projection, availability = _projection(connection, run_id, control)
        return EventReplaySnapshot(
            run_id=run_id,
            events=tuple(events),
            projection=projection,
            projection_availability=availability,
        )

    def _page(
        self, connection: sqlite3.Connection, after: RunId | None, limit: int, control: ReadControl
    ) -> EventRunPage:
        rows = connection.execute(
            "SELECT DISTINCT run_id FROM events WHERE run_id > ? ORDER BY run_id LIMIT ?",
            (str(after) if after is not None else "", limit + 1),
        )
        ids: list[RunId] = []
        for row in rows:
            control.check()
            raw = str(row[0])
            parsed = RunId.parse(raw)
            if str(parsed) != raw:
                raise replay_error(ErrorCode.INVALID_EVENT)
            ids.append(parsed)
        has_more = len(ids) > limit
        selected = tuple(ids[:limit])
        return EventRunPage(
            after_run_id=after,
            limit=limit,
            run_ids=selected,
            next_after_run_id=selected[-1] if selected else after,
            has_more=has_more,
        )


def _table_size(
    connection: sqlite3.Connection, table: str, columns: tuple[str, ...], run_id: RunId
) -> tuple[int, int]:
    # All identifiers are private constants; only the UUID is supplied by callers.
    lengths = " + ".join(f"COALESCE(length(CAST({column} AS BLOB)), 0)" for column in columns)
    row = connection.execute(
        f"SELECT COUNT(*), COALESCE(SUM({lengths}), 0) FROM {table} WHERE run_id = ?",
        (str(run_id),),
    ).fetchone()
    return int(row[0]), int(row[1])


def _projection(
    connection: sqlite3.Connection, run_id: RunId, control: ReadControl
) -> tuple[RunState | None, ProjectionAvailability]:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('run_projections', 'activity_projections')"
        )
    }
    if len(tables) != 2:
        return None, ProjectionAvailability.MISSING
    try:
        run_count, run_bytes = _table_size(connection, "run_projections", _RUN_COLUMNS, run_id)
        count, size = _table_size(connection, "activity_projections", _ACTIVITY_COLUMNS, run_id)
        control.check()
        if count > MAX_REPLAY_EVENTS or run_count > 1 or run_bytes + size > MAX_REPLAY_BYTES:
            return None, ProjectionAvailability.UNREADABLE
        if not run_count:
            return None, ProjectionAvailability.MISSING
        return load_run_projection(connection, run_id), ProjectionAvailability.AVAILABLE
    except (EventStoreCorruptionError, sqlite3.Error, ValueError, TypeError):
        control.check()
        return None, ProjectionAvailability.UNREADABLE
