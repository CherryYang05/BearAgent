import asyncio

import pytest

from bearagent.adapters.testing import (
    EventSequenceError,
    FakeModelProvider,
    FakeTool,
    InMemoryEventStore,
)
from bearagent.domain.events import Event
from bearagent.domain.model import ModelEvent, ModelEventKind, ModelRequest
from bearagent.domain.tools import ToolRequest, ToolResult, ToolStatus


def test_fake_model_returns_configured_events_and_records_request() -> None:
    async def exercise() -> tuple[ModelEvent, ...]:
        provider = FakeModelProvider(
            [
                ModelEvent(ModelEventKind.TEXT_DELTA, "hello"),
                ModelEvent(ModelEventKind.COMPLETED),
            ]
        )
        request = ModelRequest(messages=("hi",))
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
        first = Event("event-1", "run-1", 1, "RunCreated")
        second = Event("event-2", "run-1", 2, "RunStarted")
        await store.append(first)
        await store.append(second)
        return await store.list_events("run-1")

    events = asyncio.run(exercise())
    assert [event.sequence for event in events] == [1, 2]


def test_in_memory_store_rejects_sequence_gaps() -> None:
    async def exercise() -> None:
        store = InMemoryEventStore()
        await store.append(Event("event-1", "run-1", 2, "RunStarted"))

    with pytest.raises(EventSequenceError, match="expected sequence 1"):
        asyncio.run(exercise())


def test_in_memory_store_rejects_duplicate_event_ids_across_runs() -> None:
    async def exercise() -> None:
        store = InMemoryEventStore()
        await store.append(Event("event-1", "run-1", 1, "RunCreated"))
        await store.append(Event("event-1", "run-2", 1, "RunCreated"))

    with pytest.raises(EventSequenceError, match="duplicate event_id"):
        asyncio.run(exercise())
