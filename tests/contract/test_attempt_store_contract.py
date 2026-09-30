import asyncio
from pathlib import Path

import pytest
from tests.attempt_fixtures import retried_read_events

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.adapters.sqlite.replay import SqliteEventReplaySource
from bearagent.adapters.testing import InMemoryEventStore
from bearagent.domain.attempts import AttemptStatus, RunStateV5
from bearagent.domain.runs import RunStatus
from bearagent.runtime.reducer import reduce_events
from bearagent.runtime.replay import state_hash


@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_two_attempts_have_one_result_and_two_budget_charges(kind: str, tmp_path: Path) -> None:
    async def exercise() -> None:
        database = tmp_path / "attempts.sqlite3"
        store = InMemoryEventStore() if kind == "memory" else SqliteEventStore(database)
        if isinstance(store, SqliteEventStore):
            await store.initialize()
        events = retried_read_events()
        for event in events:
            await store.append(event)
        state = await store.get_run(events[0].run_id)
        assert isinstance(state, RunStateV5)
        assert state.status is RunStatus.SUCCEEDED
        assert len(state.activities) == 1
        assert [a.status for a in state.attempts] == [AttemptStatus.FAILED, AttemptStatus.SUCCEEDED]
        assert state.budget_usage.tool_calls == 2
        assert state.budget_usage.model_iterations == 0
        assert len(state.recovery_decisions) == 1
        assert state == reduce_events(events)
        source = (
            store if isinstance(store, InMemoryEventStore) else SqliteEventReplaySource(database)
        )
        snapshot = await source.read_run_events(state.run_id)
        assert snapshot.projection == state
        assert state_hash(reduce_events(snapshot.events)) == state_hash(state)
        if kind == "sqlite":
            assert await SqliteEventStore(database).get_run(state.run_id) == state

    asyncio.run(exercise())
