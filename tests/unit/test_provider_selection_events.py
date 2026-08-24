import asyncio

import pytest
from pydantic import ValidationError
from tests.agent_loop_fixtures import (
    TickingClock,
    agent_run_input,
    model_completed,
    read_tool_spec,
    tool_executor,
)

from bearagent.adapters.testing import FakeTool, InMemoryEventStore, ScriptedFakeModelProvider
from bearagent.application.agent_loop import AgentLoop
from bearagent.application.run_queries import RunQueryService
from bearagent.domain.agent import RunResult
from bearagent.domain.events import Event
from bearagent.domain.ids import ToolCallId
from bearagent.domain.model import (
    ModelFinishReason,
    ModelTextDelta,
    ModelToolCall,
)
from bearagent.domain.providers import ModelProtocol, ProviderSelection
from bearagent.domain.queries import RunInspection
from bearagent.domain.run_events import (
    RUN_EVENT_SCHEMA_VERSION_V3,
    RunCreatedPayloadV3,
    parse_run_event_payload,
)
from bearagent.interfaces.cli.renderers import render_inspection


def provider_selection() -> ProviderSelection:
    return ProviderSelection(
        provider_id="primary",
        config_version="2026-08-22",
        protocol=ModelProtocol.OPENAI_RESPONSES,
    )


def test_provider_selection_is_strict_and_contains_no_connection_fields() -> None:
    selection = provider_selection()

    assert selection.model_dump(mode="json") == {
        "provider_id": "primary",
        "config_version": "2026-08-22",
        "protocol": "openai_responses",
    }
    with pytest.raises(ValidationError):
        ProviderSelection.model_validate(
            {
                **selection.model_dump(mode="json"),
                "base_url": "https://private.example.com",
            }
        )


def test_v3_run_reuses_agent_loop_reducer_context_and_query_paths() -> None:
    tool_call_id = ToolCallId.new()
    provider = ScriptedFakeModelProvider(
        (
            (
                ModelToolCall(
                    tool_call_id=tool_call_id,
                    provider_call_id="provider-tool-1",
                    name="workspace.read",
                    arguments={"path": "docs/index.md"},
                ),
                model_completed(ModelFinishReason.TOOL_CALLS),
            ),
            (
                ModelTextDelta(text="Done."),
                model_completed(ModelFinishReason.STOP, request_id="provider-response-2"),
            ),
        )
    )
    tool = FakeTool(read_tool_spec(), data={"content": "bounded content"})
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=tool_executor(tool),
        clock=TickingClock(),
        provider_selection=provider_selection(),
    )

    async def exercise() -> tuple[RunResult, tuple[Event, ...], RunInspection]:
        result = await loop.run(agent_run_input())
        events = await store.list_events(result.run_id)
        inspection = await RunQueryService(store).inspect(result.run_id)
        return result, events, inspection

    result, events, inspection = asyncio.run(exercise())

    assert result.state.status.value == "succeeded"
    assert len(provider.requests) == 2
    assert len(tool.requests) == 1
    assert events
    assert all(event.schema_version == RUN_EVENT_SCHEMA_VERSION_V3 for event in events)
    parsed = tuple(parse_run_event_payload(event) for event in events)
    assert isinstance(parsed[0], RunCreatedPayloadV3)
    assert parsed[0].provider_selection == provider_selection()
    assert inspection.provider_selection == provider_selection()

    rendered = render_inspection(inspection)
    assert "Provider ID: primary" in rendered
    assert "Provider protocol: openai_responses" in rendered
    assert "base_url" not in rendered
    assert "API_KEY" not in rendered
