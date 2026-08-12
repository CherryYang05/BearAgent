import asyncio
import sqlite3
from pathlib import Path

import pytest
from tests.store_fixtures import (
    make_event,
    payload_json,
    run_created_event,
    successful_run_events,
)

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.domain.ids import ActivityId, ModelCallId, RunId
from bearagent.domain.run_events import ModelCallRequestedPayload, RunStartedPayload
from bearagent.domain.runs import RunState
from bearagent.ports.store import (
    EventStoreCorruptionError,
    EventStoreError,
    EventStoreMigrationError,
    EventStoreNotInitializedError,
)
from bearagent.runtime.reducer import RunReducerError, reduce_events


def test_initialize_is_idempotent_and_enables_wal(tmp_path: Path) -> None:
    database_path = tmp_path / "events.sqlite3"
    store = SqliteEventStore(database_path)

    asyncio.run(store.initialize())
    asyncio.run(store.initialize())

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        version, name, checksum = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations"
        ).fetchone()
        assert version == 1
        assert name == "0001_initial.sql"
        assert len(checksum) == 64
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"events", "run_projections", "activity_projections"} <= tables


def test_reopen_preserves_events_and_projection(tmp_path: Path) -> None:
    async def exercise() -> None:
        database_path = tmp_path / "events.sqlite3"
        first_store = SqliteEventStore(database_path)
        await first_store.initialize()
        events = successful_run_events()
        for event in events:
            await first_store.append(event)

        reopened = SqliteEventStore(database_path)
        await reopened.initialize()
        assert await reopened.list_events(events[0].run_id) == events
        assert await reopened.get_run(events[0].run_id) == reduce_events(events)

    asyncio.run(exercise())


def test_query_requires_explicit_initialization(tmp_path: Path) -> None:
    async def exercise() -> None:
        store = SqliteEventStore(tmp_path / "missing.sqlite3")
        with pytest.raises(EventStoreNotInitializedError, match="not been initialized"):
            await store.list_events(RunId.new())

    asyncio.run(exercise())


@pytest.mark.parametrize("tamper", ("future", "checksum"))
def test_initialize_rejects_incompatible_migration(tmp_path: Path, tamper: str) -> None:
    database_path = tmp_path / "events.sqlite3"
    store = SqliteEventStore(database_path)
    asyncio.run(store.initialize())
    with sqlite3.connect(database_path) as connection:
        if tamper == "future":
            connection.execute(
                """
                INSERT INTO schema_migrations(version, name, checksum)
                VALUES (2, 'future.sql', ?)
                """,
                ("0" * 64,),
            )
        else:
            connection.execute(
                "UPDATE schema_migrations SET checksum = ? WHERE version = 1",
                ("0" * 64,),
            )

    with pytest.raises(EventStoreMigrationError):
        asyncio.run(store.initialize())


def test_projection_failure_rolls_back_inserted_event(tmp_path: Path) -> None:
    async def exercise() -> None:
        database_path = tmp_path / "events.sqlite3"
        store = SqliteEventStore(database_path)
        await store.initialize()
        run_id = RunId.new()
        created = run_created_event(run_id)
        started = make_event(run_id, 2, "RunStarted", payload_json(RunStartedPayload()))
        await store.append(created)
        state_before = await store.append(started)
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                CREATE TRIGGER reject_pending_activity
                BEFORE INSERT ON activity_projections
                WHEN NEW.status = 'pending'
                BEGIN
                    SELECT RAISE(ABORT, 'injected projection failure');
                END
                """
            )
        requested = make_event(
            run_id,
            3,
            "ModelCallRequested",
            payload_json(
                ModelCallRequestedPayload(
                    activity_id=ActivityId.new(), model_call_id=ModelCallId.new()
                )
            ),
        )

        with pytest.raises(EventStoreError, match="projection update failed"):
            await store.append(requested)
        assert await store.list_events(run_id) == (created, started)
        assert await store.get_run(run_id) == state_before

    asyncio.run(exercise())


def test_concurrent_same_sequence_commits_only_one_event(tmp_path: Path) -> None:
    async def exercise() -> None:
        store = SqliteEventStore(tmp_path / "events.sqlite3")
        await store.initialize()
        run_id = RunId.new()
        await store.append(run_created_event(run_id))
        await store.append(make_event(run_id, 2, "RunStarted", payload_json(RunStartedPayload())))
        events = tuple(
            make_event(
                run_id,
                3,
                "ModelCallRequested",
                payload_json(
                    ModelCallRequestedPayload(
                        activity_id=ActivityId.new(), model_call_id=ModelCallId.new()
                    )
                ),
            )
            for _ in range(2)
        )

        results = await asyncio.gather(
            *(store.append(event) for event in events), return_exceptions=True
        )
        assert sum(isinstance(result, RunState) for result in results) == 1
        assert sum(isinstance(result, RunReducerError) for result in results) == 1
        assert len(await store.list_events(run_id)) == 3
        assert (await store.get_run(run_id)).last_sequence == 3  # type: ignore[union-attr]

    asyncio.run(exercise())


def test_projection_sequence_corruption_fails_closed(tmp_path: Path) -> None:
    async def exercise() -> None:
        database_path = tmp_path / "events.sqlite3"
        store = SqliteEventStore(database_path)
        await store.initialize()
        event = run_created_event(RunId.new())
        await store.append(event)
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "UPDATE run_projections SET last_sequence = 2 WHERE run_id = ?",
                (str(event.run_id),),
            )

        with pytest.raises(EventStoreCorruptionError, match="sequences differ"):
            await store.get_run(event.run_id)

    asyncio.run(exercise())


def test_missing_required_table_and_event_gap_fail_closed(tmp_path: Path) -> None:
    async def exercise() -> None:
        database_path = tmp_path / "events.sqlite3"
        store = SqliteEventStore(database_path)
        await store.initialize()
        events = successful_run_events()
        for event in events:
            await store.append(event)
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "DELETE FROM events WHERE run_id = ? AND sequence = 4",
                (str(events[0].run_id),),
            )

        with pytest.raises(EventStoreCorruptionError, match="not contiguous"):
            await store.list_events(events[0].run_id)

        other_database = tmp_path / "incomplete.sqlite3"
        other_store = SqliteEventStore(other_database)
        await other_store.initialize()
        with sqlite3.connect(other_database) as connection:
            connection.execute("DROP TABLE activity_projections")
        with pytest.raises(EventStoreMigrationError, match="incomplete"):
            await other_store.initialize()

    asyncio.run(exercise())
