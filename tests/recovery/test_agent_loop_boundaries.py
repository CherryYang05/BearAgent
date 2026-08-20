import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from tests.agent_loop_fixtures import (
    TickingClock,
    agent_config,
    agent_run_input,
    budget_limits,
    model_completed,
    read_tool_spec,
    tool_executor,
)

from bearagent.adapters.testing import (
    FakeTool,
    InMemoryEventStore,
    ScriptedFakeModelProvider,
)
from bearagent.adapters.tools import build_workspace_tools
from bearagent.application.agent_loop import AgentLoop
from bearagent.application.run_queries import RunQueryService
from bearagent.domain.agent import AgentConfig, RunInput
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import RunId, SessionId, ToolCallId
from bearagent.domain.model import (
    ModelEvent,
    ModelFinishReason,
    ModelRequest,
    ModelTextDelta,
    ModelToolCall,
)
from bearagent.domain.runs import RunState
from bearagent.ports.store import EventStoreError
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry


class FailingEventStore:
    def __init__(self, failed_event_type: str, failed_occurrence: int = 1) -> None:
        self._inner = InMemoryEventStore()
        self._failed_event_type = failed_event_type
        self._failed_occurrence = failed_occurrence
        self.attempted_types: list[str] = []
        self.committed_events: list[Event] = []

    async def append(self, event: Event) -> RunState:
        self.attempted_types.append(event.event_type)
        if (
            event.event_type == self._failed_event_type
            and self.attempted_types.count(event.event_type) == self._failed_occurrence
        ):
            raise EventStoreError(
                ErrorInfo(
                    category=ErrorCategory.PERSISTENCE,
                    code=ErrorCode.PERSISTENCE_ERROR,
                    message="Injected EventStore failure.",
                )
            )
        state = await self._inner.append(event)
        self.committed_events.append(event)
        return state

    async def list_events(
        self,
        run_id: RunId,
        *,
        after_sequence: int = 0,
        limit: int = 1_000,
    ) -> tuple[Event, ...]:
        return await self._inner.list_events(
            run_id,
            after_sequence=after_sequence,
            limit=limit,
        )

    async def get_run(self, run_id: RunId) -> RunState | None:
        return await self._inner.get_run(run_id)


def loop_for(
    provider: ScriptedFakeModelProvider,
    store: FailingEventStore,
    tool: FakeTool | None = None,
) -> AgentLoop:
    return AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=tool_executor(tool),
        clock=TickingClock(),
    )


def test_started_append_failure_prevents_provider_call() -> None:
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelTextDelta(text="not reached"),
                model_completed(ModelFinishReason.STOP),
            )
        ]
    )
    store = FailingEventStore("ModelCallStarted")

    with pytest.raises(EventStoreError):
        asyncio.run(loop_for(provider, store).run(agent_run_input()))

    assert provider.requests == []
    assert store.attempted_types[-1] == "ModelCallStarted"
    assert "RunFailed" not in store.attempted_types


def test_model_completed_append_failure_stops_without_retry_or_fake_terminal() -> None:
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelTextDelta(text="Provider charged once."),
                model_completed(ModelFinishReason.STOP),
            )
        ]
    )
    store = FailingEventStore("ModelCallCompleted")

    with pytest.raises(EventStoreError):
        asyncio.run(loop_for(provider, store).run(agent_run_input()))

    assert len(provider.requests) == 1
    assert store.attempted_types.count("ModelCallCompleted") == 1
    assert "RunSucceeded" not in store.attempted_types
    assert "RunFailed" not in store.attempted_types


def test_tool_completed_append_failure_does_not_repeat_external_action() -> None:
    call_id = ToolCallId.new()
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelToolCall(
                    tool_call_id=call_id,
                    provider_call_id="call-1",
                    name="workspace.read",
                    arguments={"path": "docs/index.md"},
                ),
                model_completed(ModelFinishReason.TOOL_CALLS),
            )
        ]
    )
    tool = FakeTool(read_tool_spec(), data={"content": "already read"})
    store = FailingEventStore("ToolCallCompleted")

    with pytest.raises(EventStoreError):
        asyncio.run(loop_for(provider, store, tool).run(agent_run_input()))

    assert len(tool.requests) == 1
    assert store.attempted_types.count("ToolCallCompleted") == 1
    assert "RunFailed" not in store.attempted_types


def test_cancellation_propagates_and_keeps_last_committed_activity_non_terminal() -> None:
    class BlockingProvider:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.requests: list[ModelRequest] = []

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            self.requests.append(request)
            self.started.set()
            await asyncio.sleep(60)
            yield ModelTextDelta(text="not reached")

    async def exercise() -> tuple[FailingEventStore, BlockingProvider]:
        provider = BlockingProvider()
        store = FailingEventStore("Never")
        loop = AgentLoop(
            model_provider=provider,
            event_store=store,
            tool_executor=tool_executor(),
            clock=TickingClock(),
        )
        task = asyncio.create_task(loop.run(agent_run_input()))
        await provider.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return store, provider

    store, provider = asyncio.run(exercise())

    assert len(provider.requests) == 1
    assert store.attempted_types[-1] == "ModelCallStarted"
    assert store.committed_events[-1].event_type == "ModelCallStarted"
    assert "ModelCallFailed" not in store.attempted_types
    assert "RunFailed" not in store.attempted_types
    inspection = asyncio.run(RunQueryService(store).inspect(store.committed_events[0].run_id))
    assert inspection.state.status.value == "running"
    assert inspection.state.activities[-1].status.value == "running"
    assert inspection.artifacts == ()


@pytest.mark.parametrize(
    ("failed_type", "occurrence", "provider_calls", "tool_calls"),
    [
        ("RunCreated", 1, 0, 0),
        ("RunStarted", 1, 0, 0),
        ("ModelCallRequested", 1, 0, 0),
        ("ModelCallStarted", 1, 0, 0),
        ("ModelCallCompleted", 1, 1, 0),
        ("ToolCallRequested", 1, 1, 0),
        ("ToolCallStarted", 1, 1, 0),
        ("ToolCallCompleted", 1, 1, 1),
        ("ModelCallRequested", 2, 1, 1),
        ("ModelCallStarted", 2, 1, 1),
        ("ModelCallCompleted", 2, 2, 1),
        ("RunSucceeded", 1, 2, 1),
    ],
)
def test_every_success_path_append_boundary_stops_scheduling(
    failed_type: str,
    occurrence: int,
    provider_calls: int,
    tool_calls: int,
) -> None:
    call_id = ToolCallId.new()
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelToolCall(
                    tool_call_id=call_id,
                    provider_call_id="boundary-call",
                    name="workspace.read",
                    arguments={"path": "docs/index.md"},
                ),
                model_completed(ModelFinishReason.TOOL_CALLS),
            ),
            (
                ModelTextDelta(text="Done."),
                model_completed(ModelFinishReason.STOP, request_id="boundary-response-2"),
            ),
        ]
    )
    tool = FakeTool(read_tool_spec(), data={"content": "read once"})
    store = FailingEventStore(failed_type, occurrence)

    with pytest.raises(EventStoreError):
        asyncio.run(loop_for(provider, store, tool).run(agent_run_input()))

    assert len(provider.requests) == provider_calls
    assert len(tool.requests) == tool_calls
    assert store.attempted_types.count(failed_type) == occurrence


@pytest.mark.parametrize("failed_type", ["ModelCallFailed", "ToolCallFailed", "RunFailed"])
def test_every_failure_terminal_append_boundary_stops_scheduling(failed_type: str) -> None:
    store = FailingEventStore(failed_type)
    if failed_type == "ModelCallFailed":
        provider = ScriptedFakeModelProvider([(ModelTextDelta(text="partial"),)])
        run_value = agent_run_input()
    elif failed_type == "ToolCallFailed":
        provider = ScriptedFakeModelProvider(
            [
                (
                    ModelToolCall(
                        tool_call_id=ToolCallId.new(),
                        provider_call_id="missing-tool-call",
                        name="workspace.shell",
                        arguments={"command": "no"},
                    ),
                    model_completed(ModelFinishReason.TOOL_CALLS),
                )
            ]
        )
        run_value = agent_run_input()
    else:
        provider = ScriptedFakeModelProvider([])
        run_value = agent_run_input(max_model_iterations=0)

    with pytest.raises(EventStoreError):
        asyncio.run(loop_for(provider, store).run(run_value))

    assert store.attempted_types[-1] == failed_type
    assert store.attempted_types.count(failed_type) == 1


def test_real_workspace_write_is_not_retried_when_terminal_append_fails(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = build_workspace_tools(workspace)
    registry = ToolRegistry(tools)
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelToolCall(
                    tool_call_id=ToolCallId.new(),
                    provider_call_id="write-boundary-call",
                    name="workspace.write",
                    arguments={
                        "path": "outputs/result.md",
                        "content": "complete output\n",
                    },
                ),
                model_completed(ModelFinishReason.TOOL_CALLS),
            )
        ]
    )
    store = FailingEventStore("ToolCallCompleted")
    config = AgentConfig.model_validate(
        {
            **agent_config().model_dump(),
            "tool_names": tuple(spec.name for spec in registry.specs),
        }
    )
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=ToolExecutor(
            registry,
            FixedToolPolicy(spec.name for spec in registry.specs),
        ),
        clock=TickingClock(),
    )

    with pytest.raises(EventStoreError):
        asyncio.run(
            loop.run(
                RunInput(
                    session_id=SessionId.new(),
                    objective="Write outputs/result.md.",
                    budget_limits=budget_limits(),
                    agent_config=config,
                )
            )
        )

    assert (workspace / "outputs" / "result.md").read_text(encoding="utf-8") == "complete output\n"
    assert store.attempted_types.count("ToolCallCompleted") == 1
    assert "RunFailed" not in store.attempted_types
    inspection = asyncio.run(RunQueryService(store).inspect(store.committed_events[0].run_id))
    assert inspection.state.status.value == "running"
    assert inspection.artifacts == ()
