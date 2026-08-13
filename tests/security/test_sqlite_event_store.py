import asyncio
import sqlite3
from pathlib import Path

import pytest
from tests.store_fixtures import failed_run_event, make_event, payload_json, run_created_event

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.domain.ids import RunId
from bearagent.domain.run_events import RunStartedPayload
from bearagent.ports.store import MAX_EVENT_SEQUENCE, EventStoreCorruptionError, EventStoreError


def test_sql_like_payload_is_data_not_an_identifier(tmp_path: Path) -> None:
    async def exercise() -> None:
        database_path = tmp_path / "events.sqlite3"
        store = SqliteEventStore(database_path)
        await store.initialize()
        event = run_created_event(RunId.new())
        started = make_event(event.run_id, 2, "RunStarted", payload_json(RunStartedPayload()))
        injected = failed_run_event(event.run_id, 3, "'); DROP TABLE events; --")

        await store.append(event)
        await store.append(started)
        await store.append(injected)
        assert await store.list_events(event.run_id) == (event, started, injected)

    asyncio.run(exercise())


def test_malformed_event_json_fails_without_exposing_content_or_path(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        database_path = tmp_path / "private-name.sqlite3"
        store = SqliteEventStore(database_path)
        await store.initialize()
        event = run_created_event(RunId.new())
        await store.append(event)
        sensitive = "secret-event-content"
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "UPDATE events SET payload_json = ? WHERE event_id = ?",
                (sensitive, str(event.event_id)),
            )

        with pytest.raises(EventStoreCorruptionError) as captured:
            await store.list_events(event.run_id)
        visible = str(captured.value)
        assert sensitive not in visible
        assert str(database_path) not in visible
        assert "SELECT" not in visible

    asyncio.run(exercise())


def test_locked_database_returns_retryable_safe_error(tmp_path: Path) -> None:
    async def exercise() -> None:
        database_path = tmp_path / "locked.sqlite3"
        store = SqliteEventStore(database_path, busy_timeout_ms=10)
        await store.initialize()
        lock = sqlite3.connect(database_path, isolation_level=None)
        lock.execute("BEGIN IMMEDIATE")
        try:
            with pytest.raises(EventStoreError) as captured:
                await store.append(run_created_event(RunId.new()))
            assert captured.value.info.retryable is True
            assert str(database_path) not in str(captured.value)
        finally:
            lock.rollback()
            lock.close()

    asyncio.run(exercise())


def test_payload_and_sqlite_integer_limits_fail_before_writing(tmp_path: Path) -> None:
    async def exercise() -> None:
        database_path = tmp_path / "bounded.sqlite3"
        store = SqliteEventStore(database_path)
        await store.initialize()
        oversized = run_created_event(RunId.new())
        values = oversized.model_dump(mode="json")
        values["payload"]["padding"] = "x" * (4 * 1024 * 1024)
        oversized = oversized.model_validate(values)

        with pytest.raises(ValueError, match="payload exceeds"):
            await store.append(oversized)
        sequence_values = run_created_event(RunId.new()).model_dump(mode="json")
        sequence_values["sequence"] = MAX_EVENT_SEQUENCE + 1
        oversized_sequence = oversized.model_validate(sequence_values)
        with pytest.raises(ValueError, match="signed integer range"):
            await store.append(oversized_sequence)
        assert await store.get_run(oversized.run_id) is None

    asyncio.run(exercise())
