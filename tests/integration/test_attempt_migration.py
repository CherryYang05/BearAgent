import asyncio
import hashlib
import sqlite3
from importlib.resources import files
from pathlib import Path

import pytest
from tests.attempt_fixtures import retried_read_events
from tests.store_fixtures import successful_run_events

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.adapters.sqlite import store as store_module
from bearagent.adapters.sqlite.replay import SqliteEventReplaySource
from bearagent.ports.store import EventStoreError, EventStoreMigrationError
from bearagent.runtime.reducer import reduce_events
from bearagent.runtime.replay import state_hash


def make_legacy_database(path: Path) -> None:
    sql = (
        files("bearagent.adapters.sqlite.migrations")
        .joinpath("0001_initial.sql")
        .read_text(encoding="utf-8")
    )
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(sql)
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT, checksum TEXT)"
        )
        connection.execute(
            "INSERT INTO schema_migrations VALUES (1, '0001_initial.sql', ?)",
            (hashlib.sha256(sql.encode()).hexdigest(),),
        )


def test_second_migration_failure_rolls_back_all_new_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "legacy.sqlite3"
    make_legacy_database(database)
    original = (
        files("bearagent.adapters.sqlite.migrations")
        .joinpath("0002_attempt_projections.sql")
        .read_text(encoding="utf-8")
    )
    monkeypatch.setattr(
        store_module, "_read_attempt_migration", lambda: original + "\nINVALID SQL;\n"
    )
    with pytest.raises(EventStoreMigrationError):
        asyncio.run(SqliteEventStore(database).initialize())
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [(1,)]
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='run_attempt_projections'"
            ).fetchall()
            == []
        )
    monkeypatch.setattr(store_module, "_read_attempt_migration", lambda: original)
    asyncio.run(SqliteEventStore(database).initialize())
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,)]


def test_attempt_projection_failure_does_not_commit_event(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = tmp_path / "rollback.sqlite3"
        store = SqliteEventStore(database)
        await store.initialize()
        events = retried_read_events()
        for event in events[:4]:
            await store.append(event)
        before = await store.get_run(events[0].run_id)
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TRIGGER fail_attempt BEFORE UPDATE ON run_attempt_projections "
                "BEGIN SELECT RAISE(ABORT, 'injected'); END;"
            )
        with pytest.raises(EventStoreError):
            await store.append(events[4])
        assert await store.get_run(events[0].run_id) == before
        assert await store.list_events(events[0].run_id) == events[:4]

    asyncio.run(exercise())


def test_missing_attempt_projection_still_replays_events(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = tmp_path / "missing.sqlite3"
        store = SqliteEventStore(database)
        await store.initialize()
        events = retried_read_events()
        for event in events:
            await store.append(event)
        with sqlite3.connect(database) as connection:
            connection.execute("DROP TABLE run_attempt_projections")
        snapshot = await SqliteEventReplaySource(database).read_run_events(events[0].run_id)
        assert snapshot.projection is None
        assert reduce_events(snapshot.events) == reduce_events(events)

    asyncio.run(exercise())


def test_legacy_run_state_and_hash_survive_upgrade(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = tmp_path / "upgrade.sqlite3"
        store = SqliteEventStore(database)
        await store.initialize()
        events = successful_run_events()
        for event in events:
            await store.append(event)
        original = reduce_events(events)
        with sqlite3.connect(database) as connection:
            # Reconstruct the exact pre-0002 tables; old Events are untouched.
            connection.execute("DROP TABLE run_attempt_projections")
            connection.execute("DELETE FROM schema_migrations WHERE version=2")
            before = connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        snapshot = await SqliteEventReplaySource(database).read_run_events(events[0].run_id)
        assert state_hash(reduce_events(snapshot.events)) == state_hash(original)
        assert await store.get_run(events[0].run_id) == original
        assert await store.list_events(events[0].run_id) == events
        await store.initialize()
        assert await store.get_run(events[0].run_id) == original
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT * FROM events ORDER BY sequence").fetchall() == before
            assert connection.execute(
                "SELECT COUNT(*) FROM run_attempt_projections"
            ).fetchone() == (0,)

    asyncio.run(exercise())
