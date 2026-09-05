import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from tests.store_fixtures import make_event, payload_json, run_created_event, successful_run_events

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.adapters.testing import InMemoryEventStore
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.ids import ActivityId, EventId, RunId, ToolCallId
from bearagent.domain.run_events import (
    RunStartedPayload,
    ToolCallFailedPayloadV2,
    ToolCallRequestedPayloadV2,
    ToolCallStartedPayload,
)
from bearagent.domain.runs import RunState, RunStatus
from bearagent.domain.tools import ToolExecutionRecord, ToolRequest, ToolResult, ToolStatus
from bearagent.ports.store import EventStore, EventStoreConflictError
from bearagent.runtime.reducer import RunReducerError, reduce_events

StoreFactory = Callable[[], Awaitable[EventStore]]


@pytest.fixture(params=("memory", "sqlite"))
def store_factory(request: pytest.FixtureRequest, tmp_path: Path) -> StoreFactory:
    kind = str(request.param)

    async def create() -> EventStore:
        if kind == "memory":
            return InMemoryEventStore()
        store = SqliteEventStore(tmp_path / "contract.sqlite3")
        await store.initialize()
        return store

    return create


def test_store_appends_queries_and_projects_valid_run(store_factory: StoreFactory) -> None:
    async def exercise() -> None:
        store = await store_factory()
        events = successful_run_events()
        state: RunState | None = None
        for event in events:
            state = await store.append(event)

        assert state is not None
        assert state == reduce_events(events)
        assert state.status is RunStatus.SUCCEEDED
        assert await store.get_run(events[0].run_id) == state
        assert await store.get_run(RunId.new()) is None
        assert await store.list_events(events[0].run_id, limit=2) == events[:2]
        assert await store.list_events(events[0].run_id, after_sequence=2, limit=3) == events[2:5]

    asyncio.run(exercise())


def test_store_rejects_invalid_sequence_without_partial_state(
    store_factory: StoreFactory,
) -> None:
    async def exercise() -> None:
        store = await store_factory()
        run_id = RunId.new()
        with pytest.raises(RunReducerError, match="First Run Event must have sequence 1"):
            await store.append(run_created_event(run_id, sequence=2))
        assert await store.list_events(run_id) == ()
        assert await store.get_run(run_id) is None

    asyncio.run(exercise())


def test_store_rejects_duplicate_event_identity_globally(
    store_factory: StoreFactory,
) -> None:
    async def exercise() -> None:
        store = await store_factory()
        event_id = EventId.new()
        first = run_created_event(RunId.new(), event_id=event_id)
        duplicate = run_created_event(RunId.new(), event_id=event_id)
        await store.append(first)

        with pytest.raises(EventStoreConflictError, match="Event identity"):
            await store.append(duplicate)
        assert await store.list_events(duplicate.run_id) == ()

    asyncio.run(exercise())


@pytest.mark.parametrize("schema_version", (2, 3, 4))
def test_store_rejects_versioned_terminal_evidence_for_a_different_request(
    store_factory: StoreFactory,
    schema_version: int,
) -> None:
    async def exercise() -> None:
        store = await store_factory()
        run_id = RunId.new()
        activity_id = ActivityId.new()
        tool_call_id = ToolCallId.new()
        requested = ToolRequest(
            tool_call_id=tool_call_id,
            name="workspace.read",
            arguments={"path": "docs/requested.md"},
        )
        initial = (
            run_created_event(run_id),
            make_event(run_id, 2, "RunStarted", payload_json(RunStartedPayload())),
            make_event(
                run_id,
                3,
                "ToolCallRequested",
                payload_json(
                    ToolCallRequestedPayloadV2(
                        activity_id=activity_id,
                        tool_call_id=tool_call_id,
                        tool_name=requested.name,
                        request=requested,
                    )
                ),
                schema_version=schema_version,
            ),
            make_event(
                run_id,
                4,
                "ToolCallStarted",
                payload_json(
                    ToolCallStartedPayload(
                        activity_id=activity_id,
                        tool_call_id=tool_call_id,
                    )
                ),
                schema_version=schema_version,
            ),
        )
        for event in initial:
            await store.append(event)
        error = ErrorInfo(
            category=ErrorCategory.TOOL,
            code=ErrorCode.TOOL_ERROR,
            message="Tool failed.",
        )
        different = ToolRequest(
            tool_call_id=tool_call_id,
            name="workspace.write",
            arguments={"path": "outputs/report.md", "content": "different"},
        )
        terminal = make_event(
            run_id,
            5,
            "ToolCallFailed",
            payload_json(
                ToolCallFailedPayloadV2(
                    activity_id=activity_id,
                    tool_call_id=tool_call_id,
                    error=error,
                    execution=ToolExecutionRecord(
                        request=different,
                        reached_adapter=False,
                        result=ToolResult(
                            tool_call_id=tool_call_id,
                            status=ToolStatus.FAILED,
                            error=error,
                        ),
                    ),
                )
            ),
            schema_version=schema_version,
        )

        with pytest.raises(RunReducerError, match="does not match"):
            await store.append(terminal)

        assert await store.list_events(run_id) == initial

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("after_sequence", "limit"),
    ((-1, 1), (0, 0), (0, 10_001), (True, 1), (0, True)),
)
def test_store_rejects_unbounded_query_parameters(
    store_factory: StoreFactory,
    after_sequence: int,
    limit: int,
) -> None:
    async def exercise() -> None:
        store = await store_factory()
        with pytest.raises(ValueError):
            await store.list_events(RunId.new(), after_sequence=after_sequence, limit=limit)

    asyncio.run(exercise())
