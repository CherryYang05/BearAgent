import asyncio

from tests.agent_loop_fixtures import (
    TickingClock,
    agent_run_input,
    model_completed,
    read_tool_spec,
    run_fingerprint,
    tool_executor,
)

from bearagent.adapters.testing import (
    FakeModelProvider,
    FakeTool,
    InMemoryEventStore,
    ScriptedFakeModelProvider,
)
from bearagent.application.agent_loop import AgentLoop
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import ToolCallId
from bearagent.domain.messages import ToolResultPart
from bearagent.domain.model import ModelFinishReason, ModelTextDelta, ModelToolCall
from bearagent.domain.run_events import parse_run_event_payload
from bearagent.domain.runs import RunStatus
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry


def test_raw_provider_exception_is_not_persisted_or_returned() -> None:
    secret = "authorization-bearer-super-secret"
    provider = FakeModelProvider((), failure=RuntimeError(secret))
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=tool_executor(),
        clock=TickingClock(),
        run_fingerprint=run_fingerprint(),
    )

    result = asyncio.run(loop.run(agent_run_input()))
    events = asyncio.run(store.list_events(result.run_id))

    assert result.state.status is RunStatus.FAILED
    assert result.state.terminal_error is not None
    assert result.state.terminal_error.code is ErrorCode.PROVIDER_ERROR
    assert secret not in result.model_dump_json()
    assert all(secret not in event.model_dump_json() for event in events)


def test_model_cannot_expand_exposed_tools_or_bypass_executor_policy() -> None:
    call_id = ToolCallId.new()
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelToolCall(
                    tool_call_id=call_id,
                    provider_call_id="call-dangerous",
                    name="workspace.shell",
                    arguments={"command": "read secret"},
                ),
                model_completed(ModelFinishReason.TOOL_CALLS),
            ),
            (
                ModelTextDelta(text="The unavailable action was not executed."),
                model_completed(ModelFinishReason.STOP, request_id="response-2"),
            ),
        ]
    )
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=ToolExecutor(
            ToolRegistry([FakeTool(read_tool_spec(), data={"content": "not reached"})]),
            FixedToolPolicy(),
        ),
        clock=TickingClock(),
        run_fingerprint=run_fingerprint(allowed_tool_names=()),
    )

    result = asyncio.run(loop.run(agent_run_input()))
    events = asyncio.run(store.list_events(result.run_id))

    assert result.state.status is RunStatus.SUCCEEDED
    assert tuple(tool.name for tool in provider.requests[0].tools) == ("workspace.read",)
    assert "workspace.shell" not in tuple(tool.name for tool in provider.requests[0].tools)
    assert "ToolCallFailed" in tuple(event.event_type for event in events)
    failure = next(event for event in events if event.event_type == "ToolCallFailed")
    payload = parse_run_event_payload(failure)
    assert payload.error.code is ErrorCode.TOOL_NOT_FOUND  # type: ignore[union-attr]
    result_part = provider.requests[1].messages[-1].parts[0]
    assert isinstance(result_part, ToolResultPart)
    assert result_part.is_error is True
