import asyncio
from datetime import UTC, datetime

import pytest
from tests.tool_fixtures import build_tool_request, build_tool_spec

from bearagent.adapters.testing import (
    EventSequenceError,
    FakeModelProvider,
    FakeTool,
    InMemoryEventStore,
)
from bearagent.domain.events import Event
from bearagent.domain.ids import CausationId, CorrelationId, EventId, RunId, SessionId
from bearagent.domain.messages import Message, MessageRole, TextPart
from bearagent.domain.model import (
    ModelCompleted,
    ModelEvent,
    ModelFinishReason,
    ModelRequest,
    ModelTextDelta,
)
from bearagent.domain.runs import BudgetLimits
from bearagent.domain.tools import ToolStatus
from bearagent.runtime.reducer import RunReducerError


def test_fake_model_returns_configured_events_and_records_request() -> None:
    async def exercise() -> tuple[ModelEvent, ...]:
        provider = FakeModelProvider(
            [
                ModelTextDelta(text="hello"),
                ModelCompleted(
                    provider_request_id="fake-response",
                    model="fake-model",
                    finish_reason=ModelFinishReason.STOP,
                ),
            ]
        )
        request = ModelRequest(
            model="fake-model",
            messages=(Message(role=MessageRole.USER, parts=(TextPart(text="hi"),)),),
            max_output_tokens=100,
            timeout_ms=5_000,
            prompt_version="test-v1",
        )
        events = tuple([event async for event in provider.stream(request)])
        assert provider.requests == [request]
        return events

    events = asyncio.run(exercise())
    assert isinstance(events[0], ModelTextDelta)
    assert events[0].text == "hello"
    assert isinstance(events[-1], ModelCompleted)


def test_fake_tool_returns_configured_result_and_records_request() -> None:
    async def exercise() -> str:
        tool = FakeTool(build_tool_spec(name="example"), data={"content": "done"})
        request = build_tool_request(name="example", arguments={"value": 1})
        prepared = tool.prepare(request)
        result = await tool.execute(prepared)
        assert tool.prepare_requests == [request]
        assert tool.requests == [prepared]
        assert result.status is ToolStatus.SUCCEEDED
        return str(result.data["content"])

    assert asyncio.run(exercise()) == "done"


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
