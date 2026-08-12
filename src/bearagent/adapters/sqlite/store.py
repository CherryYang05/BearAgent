"""SQLite implementation of the durable EventStore port."""

import asyncio
import hashlib
import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Final, cast

from pydantic import JsonValue, ValidationError

from bearagent.domain._base import thaw_json_mapping
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import RunId
from bearagent.domain.run_events import parse_run_event_payload
from bearagent.domain.runs import ActivityState, BudgetLimits, BudgetUsage, RunState
from bearagent.ports.store import (
    DEFAULT_EVENT_QUERY_LIMIT,
    MAX_EVENT_SEQUENCE,
    EventStoreConflictError,
    EventStoreCorruptionError,
    EventStoreError,
    EventStoreMigrationError,
    EventStoreNotInitializedError,
    validate_event_query,
)
from bearagent.runtime.reducer import reduce_event

MAX_EVENT_PAYLOAD_BYTES: Final = 4 * 1024 * 1024
DEFAULT_BUSY_TIMEOUT_MS: Final = 5_000
MAX_BUSY_TIMEOUT_MS: Final = 60_000
_MIGRATION_NAME: Final = "0001_initial.sql"
_RUN_COLUMN_COUNT: Final = 19
_ACTIVITY_COLUMN_COUNT: Final = 12


class SqliteEventStore:
    """Persist Event facts and reducer-derived projections in one transaction."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        busy_timeout_ms: object = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        if (
            isinstance(busy_timeout_ms, bool)
            or not isinstance(busy_timeout_ms, int)
            or not 1 <= busy_timeout_ms <= MAX_BUSY_TIMEOUT_MS
        ):
            raise ValueError(
                f"busy_timeout_ms must be an integer between 1 and {MAX_BUSY_TIMEOUT_MS}"
            )
        self._database_path = Path(database_path)
        self._busy_timeout_ms = busy_timeout_ms

    async def initialize(self) -> None:
        """Create or validate the explicit schema migration ledger."""
        await asyncio.to_thread(self._initialize_sync)

    async def append(self, event: Event) -> RunState:
        """Append one Event and update its Run projection atomically."""
        if event.sequence > MAX_EVENT_SEQUENCE:
            raise ValueError("Event sequence exceeds SQLite's signed integer range")
        payload_json = _encode_json(thaw_json_mapping(event.payload))
        if len(payload_json.encode("utf-8")) > MAX_EVENT_PAYLOAD_BYTES:
            raise ValueError(f"Event payload exceeds {MAX_EVENT_PAYLOAD_BYTES} bytes")
        return await asyncio.to_thread(self._append_sync, event, payload_json)

    async def list_events(
        self,
        run_id: RunId,
        *,
        after_sequence: int = 0,
        limit: int = DEFAULT_EVENT_QUERY_LIMIT,
    ) -> tuple[Event, ...]:
        """Return a bounded, ordered page of validated Event facts."""
        validate_event_query(after_sequence, limit)
        return await asyncio.to_thread(self._list_events_sync, run_id, after_sequence, limit)

    async def get_run(self, run_id: RunId) -> RunState | None:
        """Return the validated Run projection without replaying its Event stream."""
        return await asyncio.to_thread(self._get_run_sync, run_id)

    def _initialize_sync(self) -> None:
        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            migration_sql = _read_migration()
        except OSError as cause:
            raise _migration_error(
                "Database schema resources could not be prepared.", cause=cause
            ) from cause
        checksum = hashlib.sha256(migration_sql.encode("utf-8")).hexdigest()
        try:
            connection = self._connect()
        except sqlite3.Error as cause:
            raise _migration_error("Database schema initialization failed.", cause=cause) from cause
        try:
            journal_mode = cast(
                tuple[object, ...], connection.execute("PRAGMA journal_mode=WAL").fetchone()
            )
            if str(journal_mode[0]).lower() != "wal":
                raise _migration_error("SQLite WAL mode could not be enabled.")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY NOT NULL CHECK (version >= 1),
                    name TEXT NOT NULL UNIQUE,
                    checksum TEXT NOT NULL CHECK (length(checksum) = 64),
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            rows = cast(
                list[tuple[object, ...]],
                connection.execute(
                    "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
                ).fetchall(),
            )
            if any(_db_int(row[0]) > 1 for row in rows):
                raise _migration_error("Database schema is newer than this BearAgent build.")
            version_one = next((row for row in rows if _db_int(row[0]) == 1), None)
            if version_one is None:
                for statement in _sql_statements(migration_sql):
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(version, name, checksum) VALUES (?, ?, ?)",
                    (1, _MIGRATION_NAME, checksum),
                )
            elif str(version_one[1]) != _MIGRATION_NAME or str(version_one[2]) != checksum:
                raise _migration_error("Applied database migration does not match this build.")
            _verify_required_tables(connection)
            connection.commit()
        except EventStoreMigrationError:
            connection.rollback()
            raise
        except sqlite3.Error as cause:
            connection.rollback()
            raise _migration_error("Database schema initialization failed.", cause=cause) from cause
        finally:
            connection.close()

    def _append_sync(self, event: Event, payload_json: str) -> RunState:
        connection = self._open_initialized()
        event_inserted = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            previous_state = _load_run_projection(connection, event.run_id)
            maximum_sequence = _maximum_sequence(connection, event.run_id)
            _validate_projection_sequence(previous_state, maximum_sequence)
            state = reduce_event(previous_state, event)
            connection.execute(
                """
                INSERT INTO events(
                    event_id, run_id, sequence, event_type, schema_version, occurred_at,
                    causation_id, correlation_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.event_id),
                    str(event.run_id),
                    event.sequence,
                    event.event_type,
                    event.schema_version,
                    event.occurred_at.isoformat(),
                    str(event.causation_id),
                    str(event.correlation_id),
                    payload_json,
                ),
            )
            event_inserted = True
            _write_run_projection(connection, state)
            connection.commit()
            return state
        except sqlite3.IntegrityError as cause:
            connection.rollback()
            if event_inserted:
                raise EventStoreError(
                    _persistence_info("EventStore projection update failed."), cause=cause
                ) from cause
            raise EventStoreConflictError(
                _persistence_info("Event identity conflicts with a committed fact."), cause=cause
            ) from cause
        except EventStoreError:
            connection.rollback()
            raise
        except sqlite3.Error as cause:
            connection.rollback()
            raise _sqlite_error(cause) from cause
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _list_events_sync(
        self, run_id: RunId, after_sequence: int, limit: int
    ) -> tuple[Event, ...]:
        connection = self._open_initialized()
        try:
            connection.execute("BEGIN")
            state = _load_run_projection(connection, run_id)
            maximum_sequence = _maximum_sequence(connection, run_id)
            _validate_projection_sequence(state, maximum_sequence)
            rows = cast(
                list[tuple[object, ...]],
                connection.execute(
                    """
                    SELECT event_id, run_id, sequence, event_type, schema_version, occurred_at,
                           causation_id, correlation_id, payload_json
                    FROM events
                    WHERE run_id = ? AND sequence > ?
                    ORDER BY sequence
                    LIMIT ?
                    """,
                    (str(run_id), after_sequence, limit),
                ).fetchall(),
            )
            events = tuple(_event_from_row(row) for row in rows)
            connection.commit()
            return events
        except EventStoreCorruptionError:
            connection.rollback()
            raise
        except sqlite3.Error as cause:
            connection.rollback()
            raise _sqlite_error(cause) from cause
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _get_run_sync(self, run_id: RunId) -> RunState | None:
        connection = self._open_initialized()
        try:
            connection.execute("BEGIN")
            state = _load_run_projection(connection, run_id)
            maximum_sequence = _maximum_sequence(connection, run_id)
            _validate_projection_sequence(state, maximum_sequence)
            connection.commit()
            return state
        except EventStoreCorruptionError:
            connection.rollback()
            raise
        except sqlite3.Error as cause:
            connection.rollback()
            raise _sqlite_error(cause) from cause
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            timeout=self._busy_timeout_ms / 1_000,
            isolation_level=None,
        )
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _open_initialized(self) -> sqlite3.Connection:
        if not self._database_path.is_file():
            raise EventStoreNotInitializedError(
                _persistence_info("EventStore has not been initialized.")
            )
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            _verify_schema(connection)
            return connection
        except EventStoreError:
            if connection is not None:
                connection.close()
            raise
        except sqlite3.Error as cause:
            if connection is not None:
                connection.close()
            raise EventStoreNotInitializedError(
                _persistence_info("EventStore schema is not initialized."), cause=cause
            ) from cause


def _read_migration() -> str:
    return (
        resources.files("bearagent.adapters.sqlite")
        .joinpath("migrations", _MIGRATION_NAME)
        .read_text(encoding="utf-8")
    )


def _sql_statements(script: str) -> tuple[str, ...]:
    statements: list[str] = []
    current: list[str] = []
    for line in script.splitlines(keepends=True):
        current.append(line)
        candidate = "".join(current).strip()
        if candidate and sqlite3.complete_statement(candidate):
            statements.append(candidate)
            current.clear()
    if "".join(current).strip():
        raise _migration_error("Database migration contains incomplete SQL.")
    return tuple(statements)


def _verify_schema(connection: sqlite3.Connection) -> None:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if table is None:
        raise EventStoreNotInitializedError(
            _persistence_info("EventStore schema is not initialized.")
        )
    migration_sql = _read_migration()
    expected_checksum = hashlib.sha256(migration_sql.encode("utf-8")).hexdigest()
    rows = cast(
        list[tuple[object, ...]],
        connection.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        ).fetchall(),
    )
    if len(rows) != 1 or _db_int(rows[0][0]) != 1:
        raise EventStoreMigrationError(
            _persistence_info("Database schema version is not supported.")
        )
    if str(rows[0][1]) != _MIGRATION_NAME or str(rows[0][2]) != expected_checksum:
        raise EventStoreMigrationError(
            _persistence_info("Applied database migration does not match this build.")
        )
    _verify_required_tables(connection)
    journal_mode = cast(tuple[object, ...], connection.execute("PRAGMA journal_mode").fetchone())
    if str(journal_mode[0]).lower() != "wal":
        raise EventStoreCorruptionError(
            _persistence_info("Database durability settings are invalid.")
        )


def _verify_required_tables(connection: sqlite3.Connection) -> None:
    required = {"events", "run_projections", "activity_projections"}
    rows = cast(
        list[tuple[object, ...]],
        connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name IN ('events', 'run_projections', 'activity_projections')
            """
        ).fetchall(),
    )
    present = {str(row[0]) for row in rows}
    if present != required:
        raise EventStoreMigrationError(_persistence_info("Database schema is incomplete."))


def _maximum_sequence(connection: sqlite3.Connection, run_id: RunId) -> int | None:
    row = cast(
        tuple[object, ...],
        connection.execute(
            "SELECT MIN(sequence), MAX(sequence), COUNT(*) FROM events WHERE run_id = ?",
            (str(run_id),),
        ).fetchone(),
    )
    if row[0] is None:
        return None
    minimum = _db_int(row[0])
    maximum = _db_int(row[1])
    count = _db_int(row[2])
    if minimum != 1 or maximum != count:
        raise EventStoreCorruptionError(
            _persistence_info("Persisted Event sequence is not contiguous.")
        )
    return maximum


def _validate_projection_sequence(state: RunState | None, maximum_sequence: int | None) -> None:
    if (state is None) != (maximum_sequence is None):
        raise EventStoreCorruptionError(
            _persistence_info("Event and Run projection are inconsistent.")
        )
    if state is not None and state.last_sequence != maximum_sequence:
        raise EventStoreCorruptionError(
            _persistence_info("Event and Run projection sequences differ.")
        )


def _event_from_row(row: tuple[object, ...]) -> Event:
    try:
        payload = _decode_json_object(str(row[8]))
        event = Event.model_validate(
            {
                "event_id": str(row[0]),
                "run_id": str(row[1]),
                "sequence": _db_int(row[2]),
                "event_type": str(row[3]),
                "schema_version": _db_int(row[4]),
                "occurred_at": str(row[5]),
                "causation_id": str(row[6]),
                "correlation_id": str(row[7]),
                "payload": payload,
            }
        )
        parse_run_event_payload(event)
        return event
    except (KeyError, TypeError, ValueError, ValidationError) as cause:
        raise EventStoreCorruptionError(
            _persistence_info("Persisted Event data is invalid."), cause=cause
        ) from cause


def _load_run_projection(connection: sqlite3.Connection, run_id: RunId) -> RunState | None:
    run_row = cast(
        tuple[object, ...] | None,
        connection.execute(
            """
            SELECT run_id, session_id, status,
                   max_model_iterations, max_tokens, max_cost_microusd,
                   max_wall_time_ms, max_tool_calls,
                   model_iterations, input_tokens, output_tokens, cost_microusd, tool_calls,
                   created_at, started_at, completed_at, terminal_error_json, last_sequence,
                   (SELECT COUNT(*) FROM activity_projections WHERE run_id = run_projections.run_id)
            FROM run_projections WHERE run_id = ?
            """,
            (str(run_id),),
        ).fetchone(),
    )
    if run_row is None:
        return None
    activity_rows = cast(
        list[tuple[object, ...]],
        connection.execute(
            """
            SELECT activity_id, kind, status, requested_at, started_at, completed_at,
                   error_json, model_call_id, tool_call_id, tool_name, ordinal, run_id
            FROM activity_projections WHERE run_id = ? ORDER BY ordinal
            """,
            (str(run_id),),
        ).fetchall(),
    )
    try:
        if len(run_row) != _RUN_COLUMN_COUNT or len(activity_rows) != _db_int(run_row[18]):
            raise ValueError("projection row shape mismatch")
        activities = tuple(_activity_from_row(row, run_id) for row in activity_rows)
        return RunState.model_validate(
            {
                "run_id": str(run_row[0]),
                "session_id": str(run_row[1]),
                "status": str(run_row[2]),
                "budget_limits": BudgetLimits(
                    max_model_iterations=_db_int(run_row[3]),
                    max_tokens=_db_int(run_row[4]),
                    max_cost_microusd=_db_int(run_row[5]),
                    max_wall_time_ms=_db_int(run_row[6]),
                    max_tool_calls=_db_int(run_row[7]),
                ),
                "budget_usage": BudgetUsage(
                    model_iterations=_db_int(run_row[8]),
                    input_tokens=_db_int(run_row[9]),
                    output_tokens=_db_int(run_row[10]),
                    cost_microusd=_db_int(run_row[11]),
                    tool_calls=_db_int(run_row[12]),
                ),
                "activities": activities,
                "created_at": str(run_row[13]),
                "started_at": _optional_text(run_row[14]),
                "completed_at": _optional_text(run_row[15]),
                "terminal_error": _decode_optional_json_object(run_row[16]),
                "last_sequence": _db_int(run_row[17]),
            }
        )
    except (TypeError, ValueError, ValidationError) as cause:
        raise EventStoreCorruptionError(
            _persistence_info("Persisted Run projection is invalid."), cause=cause
        ) from cause


def _activity_from_row(row: tuple[object, ...], run_id: RunId) -> ActivityState:
    if len(row) != _ACTIVITY_COLUMN_COUNT or str(row[11]) != str(run_id):
        raise ValueError("Activity projection row is inconsistent")
    return ActivityState.model_validate(
        {
            "activity_id": str(row[0]),
            "kind": str(row[1]),
            "status": str(row[2]),
            "requested_at": str(row[3]),
            "started_at": _optional_text(row[4]),
            "completed_at": _optional_text(row[5]),
            "error": _decode_optional_json_object(row[6]),
            "model_call_id": _optional_text(row[7]),
            "tool_call_id": _optional_text(row[8]),
            "tool_name": _optional_text(row[9]),
        }
    )


def _write_run_projection(connection: sqlite3.Connection, state: RunState) -> None:
    limits = state.budget_limits
    usage = state.budget_usage
    connection.execute(
        """
        INSERT INTO run_projections(
            run_id, session_id, status,
            max_model_iterations, max_tokens, max_cost_microusd, max_wall_time_ms, max_tool_calls,
            model_iterations, input_tokens, output_tokens, cost_microusd, tool_calls,
            created_at, started_at, completed_at, terminal_error_json, last_sequence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            session_id=excluded.session_id, status=excluded.status,
            max_model_iterations=excluded.max_model_iterations, max_tokens=excluded.max_tokens,
            max_cost_microusd=excluded.max_cost_microusd,
            max_wall_time_ms=excluded.max_wall_time_ms, max_tool_calls=excluded.max_tool_calls,
            model_iterations=excluded.model_iterations, input_tokens=excluded.input_tokens,
            output_tokens=excluded.output_tokens, cost_microusd=excluded.cost_microusd,
            tool_calls=excluded.tool_calls, created_at=excluded.created_at,
            started_at=excluded.started_at, completed_at=excluded.completed_at,
            terminal_error_json=excluded.terminal_error_json,
            last_sequence=excluded.last_sequence
        """,
        (
            str(state.run_id),
            str(state.session_id),
            state.status.value,
            limits.max_model_iterations,
            limits.max_tokens,
            limits.max_cost_microusd,
            limits.max_wall_time_ms,
            limits.max_tool_calls,
            usage.model_iterations,
            usage.input_tokens,
            usage.output_tokens,
            usage.cost_microusd,
            usage.tool_calls,
            state.created_at.isoformat(),
            _optional_datetime(state.started_at),
            _optional_datetime(state.completed_at),
            _optional_model_json(state.terminal_error),
            state.last_sequence,
        ),
    )
    connection.execute("DELETE FROM activity_projections WHERE run_id = ?", (str(state.run_id),))
    for ordinal, activity in enumerate(state.activities):
        connection.execute(
            """
            INSERT INTO activity_projections(
                activity_id, run_id, ordinal, kind, status,
                requested_at, started_at, completed_at, error_json,
                model_call_id, tool_call_id, tool_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(activity.activity_id),
                str(state.run_id),
                ordinal,
                activity.kind.value,
                activity.status.value,
                activity.requested_at.isoformat(),
                _optional_datetime(activity.started_at),
                _optional_datetime(activity.completed_at),
                _optional_model_json(activity.error),
                None if activity.model_call_id is None else str(activity.model_call_id),
                None if activity.tool_call_id is None else str(activity.tool_call_id),
                activity.tool_name,
            ),
        )


def _encode_json(value: Mapping[str, JsonValue]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_json_object(value: str) -> dict[str, object]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("JSON value is not an object")
    return cast(dict[str, object], decoded)


def _decode_optional_json_object(value: object) -> dict[str, object] | None:
    return None if value is None else _decode_json_object(str(value))


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_datetime(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _optional_model_json(value: ErrorInfo | None) -> str | None:
    if value is None:
        return None
    data = cast(dict[str, object], value.model_dump(mode="json"))
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _db_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("persisted value is not an integer")
    return value


def _persistence_info(message: str, *, retryable: bool = False) -> ErrorInfo:
    return ErrorInfo(
        category=ErrorCategory.PERSISTENCE,
        code=ErrorCode.PERSISTENCE_ERROR,
        message=message,
        retryable=retryable,
    )


def _migration_error(
    message: str, *, cause: BaseException | None = None
) -> EventStoreMigrationError:
    return EventStoreMigrationError(_persistence_info(message), cause=cause)


def _sqlite_error(cause: sqlite3.Error) -> EventStoreError:
    retryable = isinstance(cause, sqlite3.OperationalError) and (
        "locked" in str(cause).lower() or "busy" in str(cause).lower()
    )
    message = (
        "EventStore is temporarily unavailable." if retryable else "EventStore operation failed."
    )
    return EventStoreError(_persistence_info(message, retryable=retryable), cause=cause)
