import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from bearagent.adapters.testing import (
    FakeTool,
    InMemoryEventStore,
    ScriptedFakeModelProvider,
)
from bearagent.application.agent_loop import AgentLoop
from bearagent.domain.agent import AgentConfig, ModelPricing, RunInput
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.ids import SessionId, ToolCallId
from bearagent.domain.messages import MessageRole, ToolResultPart
from bearagent.domain.model import (
    ModelCompleted,
    ModelFinishReason,
    ModelTextDelta,
    ModelToolCall,
    ModelUsage,
)
from bearagent.domain.run_events import parse_run_event_payload
from bearagent.domain.runs import MAX_TOKENS, BudgetLimits, RunStatus
from bearagent.domain.tools import ToolRetrySafety, ToolSideEffect, ToolSpec
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry

BASE_TIME = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)


class TickingClock:
    def __init__(self) -> None:
        self._ticks = 0

    def now(self) -> datetime:
        value = BASE_TIME + timedelta(milliseconds=self._ticks)
        self._ticks += 1
        return value


def tool_spec() -> ToolSpec:
    return ToolSpec(
        name="workspace.read",
        description="Read one workspace text file.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        output_schema={"type": "object"},
        side_effect=ToolSideEffect.READ_ONLY,
        timeout_ms=1_000,
        max_input_bytes=1_024,
        max_output_bytes=4_096,
        retry_safety=ToolRetrySafety.SAFE,
    )


def config() -> AgentConfig:
    return AgentConfig(
        agent_id="test-agent",
        agent_version="p1-v1",
        instructions="Use the workspace read Tool when needed.",
        model="test-model",
        prompt_version="prompt-p1-v1",
        context_version="context-p1-v1",
        max_output_tokens=512,
        model_timeout_ms=1_000,
        max_context_chars=100_000,
        max_tool_result_bytes=10_000,
        tool_names=("workspace.read",),
        pricing=ModelPricing(
            version="pricing-v1",
            input_microusd_per_million_tokens=2_000_000,
            output_microusd_per_million_tokens=8_000_000,
        ),
    )


def limits(**overrides: int) -> BudgetLimits:
    values = {
        "max_model_iterations": 5,
        "max_tokens": 10_000,
        "max_cost_microusd": 1_000_000,
        "max_wall_time_ms": 60_000,
        "max_tool_calls": 5,
    }
    values.update(overrides)
    return BudgetLimits(**values)


def run_input(**budget_overrides: int) -> RunInput:
    return RunInput(
        session_id=SessionId.new(),
        objective="Summarize docs/index.md.",
        budget_limits=limits(**budget_overrides),
        agent_config=config(),
    )


def executor(tool: FakeTool | None = None) -> ToolExecutor:
    registered = (
        FakeTool(tool_spec(), data={"content": "default test content"}) if tool is None else tool
    )
    return ToolExecutor(ToolRegistry([registered]), FixedToolPolicy(["workspace.read"]))


def completed(reason: ModelFinishReason, *, input_tokens: int = 10) -> ModelCompleted:
    return ModelCompleted(
        provider_request_id="response-1",
        model="test-model",
        finish_reason=reason,
        usage=ModelUsage(input_tokens=input_tokens, output_tokens=5),
    )


def test_agent_loop_persists_a_text_run_and_deterministic_cost() -> None:
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelTextDelta(text="BearAgent is local-first."),
                completed(ModelFinishReason.STOP),
            )
        ]
    )
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input()))
    events = asyncio.run(store.list_events(result.run_id))

    assert result.state.status is RunStatus.SUCCEEDED
    assert result.final_text == "BearAgent is local-first."
    assert result.state.budget_usage.cost_microusd == 60
    assert tuple(event.event_type for event in events) == (
        "RunCreated",
        "RunStarted",
        "ModelCallRequested",
        "ModelCallStarted",
        "ModelCallCompleted",
        "RunSucceeded",
    )
    assert all(event.schema_version == 2 for event in events)
    requested = parse_run_event_payload(events[2])
    assert requested.request == provider.requests[0]  # type: ignore[union-attr]


def test_agent_loop_executes_tool_then_rebuilds_context_for_final_answer() -> None:
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
                completed(ModelFinishReason.TOOL_CALLS, input_tokens=2),
            ),
            (
                ModelTextDelta(text="The file describes BearAgent."),
                ModelCompleted(
                    provider_request_id="response-2",
                    model="test-model",
                    finish_reason=ModelFinishReason.STOP,
                    usage=ModelUsage(input_tokens=3, output_tokens=4),
                ),
            ),
        ]
    )
    tool = FakeTool(tool_spec(), data={"content": "BearAgent docs"})
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(tool),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input()))
    events = asyncio.run(store.list_events(result.run_id))

    assert result.state.status is RunStatus.SUCCEEDED
    assert len(provider.requests) == 2
    assert len(tool.requests) == 1
    assert tuple(event.event_type for event in events) == (
        "RunCreated",
        "RunStarted",
        "ModelCallRequested",
        "ModelCallStarted",
        "ModelCallCompleted",
        "ToolCallRequested",
        "ToolCallStarted",
        "ToolCallCompleted",
        "ModelCallRequested",
        "ModelCallStarted",
        "ModelCallCompleted",
        "RunSucceeded",
    )
    tool_message = provider.requests[1].messages[-1]
    assert tool_message.role is MessageRole.TOOL
    tool_result = tool_message.parts[0]
    assert isinstance(tool_result, ToolResultPart)
    assert "BearAgent docs" in tool_result.content


def test_agent_loop_executes_multiple_model_tool_calls_in_returned_order() -> None:
    first_id = ToolCallId.new()
    second_id = ToolCallId.new()
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelToolCall(
                    tool_call_id=first_id,
                    provider_call_id="call-1",
                    name="workspace.read",
                    arguments={"path": "docs/first.md"},
                ),
                ModelToolCall(
                    tool_call_id=second_id,
                    provider_call_id="call-2",
                    name="workspace.read",
                    arguments={"path": "docs/second.md"},
                ),
                completed(ModelFinishReason.TOOL_CALLS),
            ),
            (
                ModelTextDelta(text="Both files were read."),
                ModelCompleted(
                    provider_request_id="response-2",
                    model="test-model",
                    finish_reason=ModelFinishReason.STOP,
                    usage=ModelUsage(input_tokens=3, output_tokens=4),
                ),
            ),
        ]
    )
    tool = FakeTool(tool_spec(), data={"content": "content"})
    loop = AgentLoop(
        model_provider=provider,
        event_store=InMemoryEventStore(),
        tool_executor=executor(tool),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input()))

    assert result.state.status is RunStatus.SUCCEEDED
    assert tuple(request.tool_call_id for request in tool.requests) == (
        first_id,
        second_id,
    )
    assert tuple(message.role for message in provider.requests[1].messages[-3:]) == (
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
        MessageRole.TOOL,
    )


def test_agent_loop_returns_structured_tool_failure_to_the_model() -> None:
    call_id = ToolCallId.new()
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelToolCall(
                    tool_call_id=call_id,
                    provider_call_id="call-1",
                    name="workspace.read",
                    arguments={"path": "../secret.txt"},
                ),
                completed(ModelFinishReason.TOOL_CALLS),
            ),
            (
                ModelTextDelta(text="The denied path was not read."),
                ModelCompleted(
                    provider_request_id="response-2",
                    model="test-model",
                    finish_reason=ModelFinishReason.STOP,
                    usage=ModelUsage(input_tokens=3, output_tokens=4),
                ),
            ),
        ]
    )
    tool = FakeTool(
        tool_spec(),
        failure=ErrorInfo(
            category=ErrorCategory.TOOL,
            code=ErrorCode.WORKSPACE_PATH_DENIED,
            message="Workspace path is not allowed.",
        ),
    )
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(tool),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input()))
    events = asyncio.run(store.list_events(result.run_id))

    assert result.state.status is RunStatus.SUCCEEDED
    assert "ToolCallFailed" in tuple(event.event_type for event in events)
    result_part = provider.requests[1].messages[-1].parts[0]
    assert isinstance(result_part, ToolResultPart)
    assert result_part.is_error is True
    assert "workspace_path_denied" in result_part.content


def test_agent_loop_fails_on_budget_before_calling_provider() -> None:
    provider = ScriptedFakeModelProvider([])
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input(max_model_iterations=0)))
    events = asyncio.run(store.list_events(result.run_id))

    assert result.state.status is RunStatus.FAILED
    assert result.state.terminal_error is not None
    assert result.state.terminal_error.code is ErrorCode.BUDGET_EXHAUSTED
    assert provider.requests == []
    assert tuple(event.event_type for event in events) == (
        "RunCreated",
        "RunStarted",
        "RunFailed",
    )


def test_agent_loop_rejects_unregistered_configured_tool_before_creating_run() -> None:
    provider = ScriptedFakeModelProvider([])
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(),
        clock=TickingClock(),
    )
    invalid_config = AgentConfig.model_validate(
        {**config().model_dump(), "tool_names": ("workspace.write",)}
    )
    invalid_input = RunInput(
        session_id=SessionId.new(),
        objective="Write a result.",
        budget_limits=limits(),
        agent_config=invalid_config,
    )

    with pytest.raises(ValueError, match="not registered"):
        asyncio.run(loop.run(invalid_input))

    assert provider.requests == []


def test_agent_loop_discards_partial_output_on_protocol_failure() -> None:
    provider = ScriptedFakeModelProvider([(ModelTextDelta(text="partial secret"),)])
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input()))
    events = asyncio.run(store.list_events(result.run_id))

    assert result.state.status is RunStatus.FAILED
    assert result.final_text is None
    assert result.state.terminal_error is not None
    assert result.state.terminal_error.code is ErrorCode.PROVIDER_PROTOCOL_ERROR
    assert tuple(event.event_type for event in events[-2:]) == (
        "ModelCallFailed",
        "RunFailed",
    )
    failure = parse_run_event_payload(events[-2])
    assert failure.discarded_output_chars == len("partial secret")  # type: ignore[union-attr]
    assert "partial secret" not in events[-2].model_dump_json()


def test_agent_loop_does_not_pretend_missing_provider_usage_is_zero() -> None:
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelTextDelta(text="unaccounted answer"),
                ModelCompleted(
                    provider_request_id="response-without-usage",
                    model="test-model",
                    finish_reason=ModelFinishReason.STOP,
                ),
            )
        ]
    )
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input()))
    events = asyncio.run(store.list_events(result.run_id))

    assert result.state.status is RunStatus.FAILED
    assert result.state.terminal_error is not None
    assert result.state.terminal_error.code is ErrorCode.PROVIDER_PROTOCOL_ERROR
    assert "ModelCallCompleted" not in tuple(event.event_type for event in events)


def test_agent_loop_rejects_oversized_tool_arguments_before_model_completion() -> None:
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelToolCall(
                    tool_call_id=ToolCallId.new(),
                    provider_call_id="oversized-call",
                    name="workspace.read",
                    arguments={"path": "x" * 1_000_001},
                ),
                completed(ModelFinishReason.TOOL_CALLS),
            )
        ]
    )
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input()))
    events = asyncio.run(store.list_events(result.run_id))

    assert result.state.status is RunStatus.FAILED
    assert result.state.terminal_error is not None
    assert result.state.terminal_error.code is ErrorCode.PROVIDER_PROTOCOL_ERROR
    assert "ModelCallCompleted" not in tuple(event.event_type for event in events)
    assert "ToolCallRequested" not in tuple(event.event_type for event in events)


def test_agent_loop_rejects_duplicate_provider_tool_call_identity() -> None:
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelToolCall(
                    tool_call_id=ToolCallId.new(),
                    provider_call_id="duplicate-call",
                    name="workspace.read",
                    arguments={"path": "docs/first.md"},
                ),
                ModelToolCall(
                    tool_call_id=ToolCallId.new(),
                    provider_call_id="duplicate-call",
                    name="workspace.read",
                    arguments={"path": "docs/second.md"},
                ),
                completed(ModelFinishReason.TOOL_CALLS),
            )
        ]
    )
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input()))
    events = asyncio.run(store.list_events(result.run_id))

    assert result.state.status is RunStatus.FAILED
    assert result.state.terminal_error is not None
    assert result.state.terminal_error.code is ErrorCode.PROVIDER_PROTOCOL_ERROR
    assert "ModelCallCompleted" not in tuple(event.event_type for event in events)


def test_agent_loop_rejects_provider_tool_call_identity_reused_across_rounds() -> None:
    first_call_id = ToolCallId.new()
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelToolCall(
                    tool_call_id=first_call_id,
                    provider_call_id="reused-provider-call",
                    name="workspace.read",
                    arguments={"path": "docs/first.md"},
                ),
                completed(ModelFinishReason.TOOL_CALLS),
            ),
            (
                ModelToolCall(
                    tool_call_id=ToolCallId.new(),
                    provider_call_id="reused-provider-call",
                    name="workspace.read",
                    arguments={"path": "docs/second.md"},
                ),
                completed(ModelFinishReason.TOOL_CALLS),
            ),
        ]
    )
    tool = FakeTool(tool_spec(), data={"content": "first"})
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(tool),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input()))
    events = asyncio.run(store.list_events(result.run_id))
    event_types = tuple(event.event_type for event in events)

    assert result.state.status is RunStatus.FAILED
    assert result.state.terminal_error is not None
    assert result.state.terminal_error.code is ErrorCode.PROVIDER_PROTOCOL_ERROR
    assert event_types.count("ModelCallCompleted") == 1
    assert event_types.count("ToolCallRequested") == 1
    assert len(tool.requests) == 1


def test_agent_loop_fails_safely_when_model_request_event_exceeds_node_limit() -> None:
    large_schema_spec = ToolSpec.model_validate(
        {
            **tool_spec().model_dump(mode="json"),
            "input_schema": {"type": "object", "enum": ["x"] * 9_980},
        }
    )
    provider = ScriptedFakeModelProvider(
        [(ModelTextDelta(text="unused"), completed(ModelFinishReason.STOP))]
    )
    store = InMemoryEventStore()
    tool = FakeTool(large_schema_spec, data={"content": "unused"})
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(tool),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input()))
    events = asyncio.run(store.list_events(result.run_id))

    assert result.state.status is RunStatus.FAILED
    assert result.state.terminal_error is not None
    assert result.state.terminal_error.code is ErrorCode.INVALID_INPUT
    assert tuple(event.event_type for event in events) == (
        "RunCreated",
        "RunStarted",
        "RunFailed",
    )
    assert provider.requests == []


def test_agent_loop_fails_safely_when_model_request_event_exceeds_byte_limit() -> None:
    large_schema_spec = ToolSpec.model_validate(
        {
            **tool_spec().model_dump(mode="json"),
            "input_schema": {"type": "object", "description": "界" * 333_000},
        }
    )
    large_config = AgentConfig.model_validate(
        {
            **config().model_dump(mode="json"),
            "instructions": "规" * 65_536,
            "max_context_chars": 4_000_000,
        }
    )
    provider = ScriptedFakeModelProvider(
        [(ModelTextDelta(text="unused"), completed(ModelFinishReason.STOP))]
    )
    store = InMemoryEventStore()
    tool = FakeTool(large_schema_spec, data={"content": "unused"})
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(tool),
        clock=TickingClock(),
    )
    large_input = RunInput(
        session_id=SessionId.new(),
        objective="目" * 1_000_000,
        budget_limits=limits(),
        agent_config=large_config,
    )

    result = asyncio.run(loop.run(large_input))
    events = asyncio.run(store.list_events(result.run_id))

    assert result.state.status is RunStatus.FAILED
    assert result.state.terminal_error is not None
    assert result.state.terminal_error.code is ErrorCode.INVALID_INPUT
    assert tuple(event.event_type for event in events) == (
        "RunCreated",
        "RunStarted",
        "RunFailed",
    )
    assert provider.requests == []


def test_agent_loop_compacts_unpersistable_tool_execution_evidence() -> None:
    call_id = ToolCallId.new()
    large_spec = ToolSpec.model_validate(
        {
            **tool_spec().model_dump(mode="json"),
            "max_input_bytes": 300_000,
            "max_output_bytes": 4_000_000,
        }
    )
    large_argument = "a" * 150_000
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelToolCall(
                    tool_call_id=call_id,
                    provider_call_id="large-tool-evidence",
                    name="workspace.read",
                    arguments={"path": large_argument},
                ),
                completed(ModelFinishReason.TOOL_CALLS),
            )
        ]
    )
    tool = FakeTool(large_spec, data={"content": "r" * 3_999_900})
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(tool),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input()))
    events = asyncio.run(store.list_events(result.run_id))
    failed = parse_run_event_payload(
        next(event for event in events if event.event_type == "ToolCallFailed")
    )

    assert result.state.status is RunStatus.FAILED
    assert result.state.terminal_error is not None
    assert result.state.terminal_error.code is ErrorCode.TOOL_OUTPUT_TOO_LARGE
    assert failed.execution.persistence_truncated is True  # type: ignore[union-attr]
    assert failed.execution.reached_adapter is True  # type: ignore[union-attr]
    assert len(tool.requests) == 1


def test_agent_loop_rejects_model_completion_that_cannot_fit_an_event() -> None:
    provider = ScriptedFakeModelProvider(
        [
            (
                *(
                    ModelToolCall(
                        tool_call_id=ToolCallId.new(),
                        provider_call_id=f"large-completion-{index}",
                        name="workspace.read",
                        arguments={"path": "p" * 850_000},
                    )
                    for index in range(5)
                ),
                completed(ModelFinishReason.TOOL_CALLS),
            )
        ]
    )
    store = InMemoryEventStore()
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=executor(),
        clock=TickingClock(),
    )

    result = asyncio.run(loop.run(run_input()))
    events = asyncio.run(store.list_events(result.run_id))
    event_types = tuple(event.event_type for event in events)

    assert result.state.status is RunStatus.FAILED
    assert result.state.terminal_error is not None
    assert result.state.terminal_error.code is ErrorCode.PROVIDER_PROTOCOL_ERROR
    assert "ModelCallCompleted" not in event_types
    assert "ToolCallRequested" not in event_types
    assert event_types[-2:] == ("ModelCallFailed", "RunFailed")


def test_agent_loop_records_maximum_valid_single_call_cost() -> None:
    high_pricing = ModelPricing(
        version="maximum-pricing-v1",
        input_microusd_per_million_tokens=1_000_000_000_000,
        output_microusd_per_million_tokens=1_000_000_000_000,
    )
    high_config = AgentConfig.model_validate(
        {**config().model_dump(), "pricing": high_pricing.model_dump()}
    )
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelTextDelta(text="Expensive but accounted."),
                ModelCompleted(
                    provider_request_id="maximum-cost-response",
                    model="test-model",
                    finish_reason=ModelFinishReason.STOP,
                    usage=ModelUsage(input_tokens=MAX_TOKENS, output_tokens=0),
                ),
            )
        ]
    )
    loop = AgentLoop(
        model_provider=provider,
        event_store=InMemoryEventStore(),
        tool_executor=executor(),
        clock=TickingClock(),
    )
    high_input = RunInput(
        session_id=SessionId.new(),
        objective="Return one final answer.",
        budget_limits=limits(max_tokens=MAX_TOKENS),
        agent_config=high_config,
    )

    result = asyncio.run(loop.run(high_input))

    assert result.state.status is RunStatus.SUCCEEDED
    assert result.state.budget_usage.cost_microusd == 10_000_000_000_000_000


def test_agent_loop_records_one_call_token_overshoot_before_stopping() -> None:
    call_id = ToolCallId.new()
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelToolCall(
                    tool_call_id=call_id,
                    provider_call_id="high-usage-tool-call",
                    name="workspace.read",
                    arguments={"path": "docs/index.md"},
                ),
                ModelCompleted(
                    provider_request_id="high-usage-response-1",
                    model="test-model",
                    finish_reason=ModelFinishReason.TOOL_CALLS,
                    usage=ModelUsage(input_tokens=6_000_000_000, output_tokens=0),
                ),
            ),
            (
                ModelTextDelta(text="Usage was recorded."),
                ModelCompleted(
                    provider_request_id="high-usage-response-2",
                    model="test-model",
                    finish_reason=ModelFinishReason.STOP,
                    usage=ModelUsage(input_tokens=6_000_000_000, output_tokens=0),
                ),
            ),
        ]
    )
    loop = AgentLoop(
        model_provider=provider,
        event_store=InMemoryEventStore(),
        tool_executor=executor(),
        clock=TickingClock(),
    )

    result = asyncio.run(
        loop.run(
            run_input(
                max_tokens=MAX_TOKENS,
                max_cost_microusd=1_000_000_000_000,
            )
        )
    )

    assert result.state.status is RunStatus.SUCCEEDED
    assert result.state.budget_usage.input_tokens == 12_000_000_000
