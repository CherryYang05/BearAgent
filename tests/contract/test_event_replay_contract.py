import asyncio
from pathlib import Path

import pytest
from tests.replay_fixtures import tool_history, versioned_history
from tests.store_fixtures import successful_run_events

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.adapters.sqlite.replay import SqliteEventReplaySource
from bearagent.adapters.testing.store import InMemoryEventStore
from bearagent.application.run_replay import RunReplayService
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import RunId
from bearagent.domain.replay import ProjectionComparison, ReplayLimits
from bearagent.ports.replay import EventReplayError, EventReplaySource
from bearagent.ports.store import EventStore
from bearagent.runtime.reducer import reduce_events
from bearagent.runtime.replay import state_hash


@pytest.fixture(params=("memory", "sqlite"))
def pair(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[EventStore, EventReplaySource]:
    if request.param == "memory":
        memory = InMemoryEventStore()
        return memory, memory
    path = tmp_path / "events.db"
    store = SqliteEventStore(path)
    asyncio.run(store.initialize())
    return store, SqliteEventReplaySource(path)


@pytest.mark.parametrize("version", (1, 2, 3, 4))
def test_replay_same_versioned_state_and_hash(
    pair: tuple[EventStore, EventReplaySource],
    version: int,
) -> None:
    async def scenario() -> None:
        store, source = pair
        histories = [versioned_history(version)]
        if version > 1:
            histories.append(tool_history(version))
        for events in histories:
            for event in events:
                await store.append(event)
            expected = reduce_events(events)
            replay = await RunReplayService(source).replay(events[0].run_id)
            assert replay.state == expected == await store.get_run(events[0].run_id)
            assert replay.summary.state_hash == state_hash(expected)
            assert replay.summary.projection is ProjectionComparison.MATCHED
            assert (replay.run_fingerprint is not None) == (version == 4)

    asyncio.run(scenario())


def test_pages_advance_over_healthy_runs_and_include_unfinished(
    pair: tuple[EventStore, EventReplaySource],
) -> None:
    async def scenario() -> None:
        store, source = pair
        ids = tuple(RunId.parse(f"00000000-0000-4000-8000-{i:012d}") for i in (1, 2, 3))
        for i in (2, 0, 1):
            events = versioned_history(1, ids[i])
            for event in events if i < 2 else events[:1]:
                await store.append(event)
        service = RunReplayService(source)
        first = await service.check(limit=2)
        assert first.items == () and first.exit_code == 0
        assert first.scanned_count == 2 and first.has_more
        assert first.next_after_run_id == ids[1]
        second = await service.check(after_run_id=first.next_after_run_id, limit=2)
        assert second.scanned_count == 1 and not second.has_more and second.exit_code == 1
        assert second.items[0].run_id == ids[2]
        empty = await service.check(after_run_id=second.next_after_run_id, limit=2)
        assert empty.scanned_count == 0 and not empty.has_more and empty.exit_code == 0
        assert empty.next_after_run_id == ids[2]

    asyncio.run(scenario())


def test_missing_and_exact_resource_boundaries(pair: tuple[EventStore, EventReplaySource]) -> None:
    async def scenario() -> None:
        store, source = pair
        events = successful_run_events()
        with pytest.raises(EventReplayError) as missing:
            await source.read_run_events(events[0].run_id)
        assert missing.value.info.code is ErrorCode.RUN_NOT_FOUND
        for event in events:
            await store.append(event)
        size = sum(len(event.model_dump_json().encode()) for event in events)
        exact = RunReplayService(
            source, limits=ReplayLimits(max_events=len(events), max_bytes=size)
        )
        assert (await exact.replay(events[0].run_id)).state.last_sequence == len(events)
        for limits in (ReplayLimits(max_events=len(events) - 1), ReplayLimits(max_bytes=size - 1)):
            with pytest.raises(EventReplayError) as limited:
                await RunReplayService(source, limits=limits).replay(events[0].run_id)
            assert limited.value.info.code is ErrorCode.QUERY_LIMIT_EXCEEDED
        for invalid in (0, 1001, True):
            with pytest.raises(EventReplayError) as bad:
                await source.list_event_run_ids(limit=invalid)
            assert bad.value.info.code is ErrorCode.INVALID_INPUT

    asyncio.run(scenario())


def test_state_hash_has_a_stable_format_v1_golden() -> None:
    run_id = RunId.parse("00000000-0000-4000-8000-000000000002")
    state = reduce_events(versioned_history(1, run_id))
    assert state_hash(state) == "72186256dbd2c5ff36565a18b0fde1b4364832d12bdd8042fcae895a93b44e51"
    assert state_hash(state.model_validate_json(state.model_dump_json())) == state_hash(state)
