import asyncio
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from tests.replay_fixtures import persist, tool_history, versioned_history
from tests.store_fixtures import successful_run_events

import bearagent.adapters.sqlite.replay as sqlite_replay
from bearagent.application.run_replay import RunReplayService
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import RunId
from bearagent.domain.replay import ProjectionComparison, ReplayLimits
from bearagent.domain.runs import RunState
from bearagent.ports.replay import EventReplayError
from bearagent.runtime.reducer import reduce_events


def database_dump(path: Path) -> tuple[str, ...]:
    with sqlite3.connect(path) as connection:
        return tuple(connection.iterdump())


@pytest.mark.parametrize(
    ("mutation", "comparison"),
    (
        ("DELETE FROM activity_projections; DELETE FROM run_projections", "missing"),
        ("DROP TABLE activity_projections; DROP TABLE run_projections", "missing"),
        ("DROP TABLE activity_projections", "missing"),
        ("UPDATE run_projections SET input_tokens = input_tokens + 1", "mismatch"),
        ("UPDATE run_projections SET status = 'broken'", "unreadable"),
        ("UPDATE activity_projections SET error_json = 'broken'", "unreadable"),
        ("ALTER TABLE run_projections RENAME COLUMN status TO broken", "unreadable"),
    ),
)
def test_reconstructs_without_trusting_or_repairing_projection(
    tmp_path: Path,
    mutation: str,
    comparison: str,
) -> None:
    path = tmp_path / "events.db"
    events = successful_run_events()
    asyncio.run(persist(path, events))
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.executescript(mutation)
    before = database_dump(path)
    service = RunReplayService(sqlite_replay.SqliteEventReplaySource(path))
    replay = asyncio.run(service.replay(events[0].run_id))
    assert replay.state == reduce_events(events)
    assert replay.summary.projection.value == comparison
    checked = asyncio.run(service.check())
    assert checked.exit_code == 1 and checked.items[0].summary == replay.summary
    assert database_dump(path) == before


def test_false_terminal_projection_cannot_hide_unfinished_event_run(tmp_path: Path) -> None:
    path = tmp_path / "events.db"
    events = successful_run_events()
    asyncio.run(persist(path, events))
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM events WHERE sequence = 9")
    page = asyncio.run(RunReplayService(sqlite_replay.SqliteEventReplaySource(path)).check())
    assert page.exit_code == 1 and page.scanned_count == 1
    summary = page.items[0].summary
    assert summary is not None and summary.status.value == "running"
    assert summary.projection is ProjectionComparison.MISMATCH


@pytest.mark.parametrize(
    "mutation",
    (
        "DELETE FROM events WHERE sequence = 2",
        "UPDATE events SET schema_version = 99 WHERE sequence = 2",
        "UPDATE events SET event_type = 'RunSucceeded' WHERE sequence = 2",
        "UPDATE events SET payload_json = '{broken' WHERE sequence = 2",
        "UPDATE events SET run_id = '00000000-0000-4000-8000-000000000099' WHERE sequence = 2",
    ),
)
def test_corrupt_history_has_safe_error_and_other_runs_are_still_checked(
    tmp_path: Path,
    mutation: str,
) -> None:
    path = tmp_path / "events.db"
    events = successful_run_events()
    asyncio.run(persist(path, events))
    healthy = versioned_history(4)
    asyncio.run(persist(path, healthy))
    with sqlite3.connect(path) as connection:
        # Apply only to the first Run even when the mutation changes its identity.
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(mutation + " AND run_id = ?", (str(events[0].run_id),))
    service = RunReplayService(sqlite_replay.SqliteEventReplaySource(path))
    with pytest.raises(EventReplayError) as error:
        asyncio.run(service.replay(events[0].run_id))
    assert error.value.info.code is ErrorCode.INVALID_EVENT
    page = asyncio.run(service.check())
    assert page.exit_code == 2
    assert any(item.run_id == events[0].run_id for item in page.items)
    assert all(item.run_id != healthy[0].run_id for item in page.items)


@pytest.mark.parametrize("version", (2, 3, 4))
def test_replay_rejects_mismatched_full_tool_request(tmp_path: Path, version: int) -> None:
    path = tmp_path / "events.db"
    events = tool_history(version)
    asyncio.run(persist(path, events))
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE events SET payload_json = replace(payload_json, 'PRIVATE-PATH', 'different') "
            "WHERE event_type = 'ToolCallCompleted'"
        )
    with pytest.raises(EventReplayError) as error:
        asyncio.run(
            RunReplayService(sqlite_replay.SqliteEventReplaySource(path)).replay(events[0].run_id)
        )
    assert error.value.info.code is ErrorCode.INVALID_EVENT


def test_concurrent_commit_never_mixes_events_and_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.db"
    events = successful_run_events()
    store = asyncio.run(persist(path, events[:7]))
    arrived, release = threading.Event(), threading.Event()
    original = sqlite_replay.load_run_projection

    def pause(connection: sqlite3.Connection, run_id: RunId) -> RunState | None:
        arrived.set()
        assert release.wait(5)
        return original(connection, run_id)

    monkeypatch.setattr(sqlite_replay, "load_run_projection", pause)

    async def scenario() -> None:
        service = RunReplayService(sqlite_replay.SqliteEventReplaySource(path))
        task = asyncio.create_task(service.replay(events[0].run_id))
        try:
            assert await asyncio.to_thread(arrived.wait, 5)
            for event in events[7:]:
                await store.append(event)
        finally:
            release.set()
        old = await task
        assert old.state == reduce_events(events[:7])
        assert old.summary.projection is ProjectionComparison.MATCHED
        assert (await service.replay(events[0].run_id)).state == reduce_events(events)

    asyncio.run(scenario())


def test_uncommitted_event_is_invisible(tmp_path: Path) -> None:
    path = tmp_path / "events.db"
    events = successful_run_events()
    asyncio.run(persist(path, events))
    with sqlite3.connect(path) as writer:
        writer.execute("DELETE FROM events WHERE sequence=9")
        replay = asyncio.run(
            RunReplayService(sqlite_replay.SqliteEventReplaySource(path)).replay(events[0].run_id)
        )
        assert replay.state.last_sequence == 9
        assert replay.summary.projection is ProjectionComparison.MATCHED
        writer.rollback()


def test_sqlite_deadline_interrupts_query_and_closes_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.db"
    events = versioned_history(1)
    asyncio.run(persist(path, events))

    def slow_sql(connection: sqlite3.Connection, *, require_projections: bool) -> None:
        del require_projections
        connection.execute(
            "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n "
            "WHERE x < 1000000000) SELECT sum(x) FROM n"
        ).fetchone()

    monkeypatch.setattr(sqlite_replay, "verify_store_schema", slow_sql)
    start = time.monotonic()
    with pytest.raises(EventReplayError) as error:
        asyncio.run(
            sqlite_replay.SqliteEventReplaySource(path).read_run_events(
                events[0].run_id, limits=ReplayLimits(timeout_ms=30)
            )
        )
    assert error.value.info.code is ErrorCode.QUERY_TIMEOUT
    assert time.monotonic() - start < 3
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0


def test_cancellation_waits_for_worker_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.db"
    events = versioned_history(1)
    asyncio.run(persist(path, events))
    arrived, release = threading.Event(), threading.Event()
    original = sqlite_replay.verify_store_schema

    def pause(connection: sqlite3.Connection, *, require_projections: bool) -> None:
        original(connection, require_projections=require_projections)
        arrived.set()
        assert release.wait(5)

    monkeypatch.setattr(sqlite_replay, "verify_store_schema", pause)

    async def scenario() -> None:
        task = asyncio.create_task(
            sqlite_replay.SqliteEventReplaySource(path).read_run_events(events[0].run_id)
        )
        try:
            assert await asyncio.to_thread(arrived.wait, 5)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            task.cancel()  # repeated cancellation must not orphan the worker
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0


@pytest.mark.parametrize("mutation", ("DROP TABLE events", "DELETE FROM schema_migrations"))
def test_missing_fact_storage_fails_without_initialization(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "events.db"
    events = versioned_history(1)
    asyncio.run(persist(path, events))
    with sqlite3.connect(path) as connection:
        connection.execute(mutation)
    before = database_dump(path)
    with pytest.raises(EventReplayError) as error:
        asyncio.run(RunReplayService(sqlite_replay.SqliteEventReplaySource(path)).check())
    assert error.value.info.code is ErrorCode.PERSISTENCE_ERROR
    assert database_dump(path) == before


def test_locked_database_returns_with_bounded_wait(tmp_path: Path) -> None:
    path = tmp_path / "events.db"
    asyncio.run(persist(path, versioned_history(1)))
    with sqlite3.connect(path, isolation_level=None) as lock:
        lock.execute("PRAGMA journal_mode=DELETE")
        lock.execute("BEGIN EXCLUSIVE")
        start = time.monotonic()
        try:
            with pytest.raises(EventReplayError) as error:
                asyncio.run(RunReplayService(sqlite_replay.SqliteEventReplaySource(path)).check())
            assert error.value.info.code is ErrorCode.PERSISTENCE_ERROR
            assert time.monotonic() - start < 3
        finally:
            lock.execute("ROLLBACK")


@pytest.mark.parametrize("dimension", ("events", "bytes"))
def test_oversized_history_is_rejected_before_payload_decoding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dimension: str,
) -> None:
    path = tmp_path / "events.db"
    events = versioned_history(1)
    asyncio.run(persist(path, events))
    with sqlite3.connect(path) as connection:
        if dimension == "events":
            connection.executemany(
                "INSERT INTO events SELECT ?, run_id, ?, event_type, schema_version, "
                "occurred_at, causation_id, correlation_id, payload_json FROM events "
                "WHERE sequence=1",
                ((f"00000000-0000-4000-8000-{i:012d}", i) for i in range(4, 10002)),
            )
        else:
            connection.execute(
                "UPDATE events SET payload_json = zeroblob(17000000) WHERE sequence=1"
            )

    def forbidden(row: tuple[object, ...]) -> None:
        raise AssertionError("oversized history must not be decoded")

    monkeypatch.setattr(sqlite_replay, "decode_event_row", forbidden)
    with pytest.raises(EventReplayError) as error:
        asyncio.run(sqlite_replay.SqliteEventReplaySource(path).read_run_events(events[0].run_id))
    assert error.value.info.code is ErrorCode.QUERY_LIMIT_EXCEEDED
