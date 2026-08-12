import asyncio
from datetime import UTC, datetime

import pytest

from bearagent.adapters.testing import (
    EventSequenceError,
    FakeModelProvider,
    FakeTool,
    InMemoryEventStore,
)
from bearagent.domain.events import Event
from bearagent.domain.ids import CausationId, CorrelationId, EventId, RunId, SessionId
from bearagent.domain.messages import Message, MessageRole, TextPart
from bearagent.domain.model import ModelEvent, ModelEventKind, ModelRequest
from bearagent.domain.runs import BudgetLimits
from bearagent.domain.tools import ToolRequest, ToolResult, ToolStatus
from bearagent.runtime.reducer import RunReducerError


def test_fake_model_returns_configured_events_and_records_request() -> None:
    async def exercise() -> tuple[ModelEvent, ...]:
        provider = FakeModelProvider(
            [
                ModelEvent(ModelEventKind.TEXT_DELTA, "hello"),
                ModelEvent(ModelEventKind.COMPLETED),
            ]
        )
        request = ModelRequest(
            messages=(Message(role=MessageRole.USER, parts=(TextPart(text="hi"),)),)
        )
        events = tuple([event async for event in provider.stream(request)])
        assert provider.requests == [request]
        return events

    events = asyncio.run(exercise())
    assert events[0].text == "hello"
    assert events[-1].kind is ModelEventKind.COMPLETED


def test_fake_tool_returns_configured_result_and_records_request() -> None:
    async def exercise() -> ToolResult:
        expected = ToolResult(ToolStatus.SUCCEEDED, content="done")
        tool = FakeTool("example", expected)
        request = ToolRequest("example", {"value": 1})
        result = await tool.execute(request)
        assert tool.requests == [request]
        return result

    assert asyncio.run(exercise()).content == "done"


def test_in_memory_store_enforces_contiguous_run_sequences() -> None:
    async def exercise() -> tuple[Event, ...]:
        store = InMemoryEventStore()
        run_id = RunId.new()
        first = build_event(run_id=run_id, sequence=1, event_type="RunCreated")
        second = build_event(run_id=run_id, sequence=2, event_type="RunStarted")
        await store.append(first)
        await store.append(second)
        return await store.list_events(run_id)

    events = asyncio.run(exercise())
    assert [event.sequence for event in events] == [1, 2]


def test_in_memory_store_rejects_sequence_gaps() -> None:
    async def exercise() -> None:
        store = InMemoryEventStore()
        await store.append(build_event(run_id=RunId.new(), sequence=2, event_type="RunStarted"))

    with pytest.raises(RunReducerError, match="First Run Event must have sequence 1"):
        asyncio.run(exercise())


def test_in_memory_store_rejects_duplicate_event_ids_across_runs() -> None:
    async def exercise() -> None:
        store = InMemoryEventStore()
        event_id = EventId.new()
        await store.append(build_event(event_id=event_id, run_id=RunId.new()))
        await store.append(build_event(event_id=event_id, run_id=RunId.new()))

    with pytest.raises(EventSequenceError, match="Event identity already exists"):
        asyncio.run(exercise())


def build_event(
    *,
    run_id: RunId,
    event_id: EventId | None = None,
    sequence: int = 1,
    event_type: str = "RunCreated",
) -> Event:
    payload: dict[str, object] = {}
    if event_type == "RunCreated":
        payload = {
            "session_id": str(SessionId.new()),
            "budget_limits": BudgetLimits(
                max_model_iterations=10,
                max_tokens=10_000,
                max_cost_microusd=1_000_000,
                max_wall_time_ms=60_000,
                max_tool_calls=10,
            ).model_dump(mode="json"),
        }
    return Event.model_validate(
        {
            "event_id": event_id or EventId.new(),
            "run_id": run_id,
            "sequence": sequence,
            "event_type": event_type,
            "occurred_at": datetime(2026, 8, 10, tzinfo=UTC),
            "causation_id": CausationId.new(),
            "correlation_id": CorrelationId.new(),
            "payload": payload,
        }
    )
