from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel, ValidationError

from bearagent.domain.agent import (
    AgentConfig,
    ContextBuildReport,
    ModelPricing,
    RunInput,
    RunResult,
)
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import (
    ActivityId,
    CausationId,
    CorrelationId,
    EventId,
    ModelCallId,
    RunId,
    SessionId,
    ToolCallId,
)
from bearagent.domain.messages import Message, MessageRole, TextPart
from bearagent.domain.model import ModelFinishReason, ModelRequest
from bearagent.domain.run_events import (
    ModelCallCompletedPayloadV2,
    ModelCallRequestedPayloadV2,
    ModelCallStartedPayloadV2,
    RunCreatedPayloadV2,
    RunStartedPayloadV2,
    RunSucceededPayloadV2,
    parse_run_event_payload,
)
from bearagent.domain.runs import BudgetLimits, RunState, RunStatus
from bearagent.domain.tools import (
    PolicyDecision,
    PolicyOutcome,
    PolicyReason,
    PreparedToolRequest,
    ToolExecutionRecord,
    ToolRequest,
    ToolResult,
    ToolStatus,
)
from bearagent.runtime.pricing import estimate_model_cost_microusd
from bearagent.runtime.reducer import reduce_event

BASE_TIME = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)


def pricing() -> ModelPricing:
    return ModelPricing(
        version="test-pricing-2026-08-18",
        input_microusd_per_million_tokens=2_000_000,
        output_microusd_per_million_tokens=8_000_000,
    )


def agent_config() -> AgentConfig:
    return AgentConfig(
        agent_id="bearagent-research",
        agent_version="p1-v1",
        instructions="Read only the requested workspace and write results under outputs.",
        model="test-model-2026-08-18",
        prompt_version="runtime-p1-v1",
        context_version="context-p1-v1",
        max_output_tokens=1_024,
        model_timeout_ms=30_000,
        max_context_chars=524_288,
        max_tool_result_bytes=65_536,
        tool_names=(
            "workspace.list",
            "workspace.read",
            "workspace.search",
            "workspace.write",
        ),
        pricing=pricing(),
    )


def limits() -> BudgetLimits:
    return BudgetLimits(
        max_model_iterations=4,
        max_tokens=10_000,
        max_cost_microusd=1_000_000,
        max_wall_time_ms=60_000,
        max_tool_calls=4,
    )


def event(run_id: RunId, sequence: int, event_type: str, payload: BaseModel) -> Event:
    return Event(
        event_id=EventId.new(),
        run_id=run_id,
        sequence=sequence,
        event_type=event_type,
        schema_version=2,
        occurred_at=BASE_TIME + timedelta(milliseconds=sequence),
        causation_id=CausationId.new(),
        correlation_id=CorrelationId.new(),
        payload=payload.model_dump(mode="json"),
    )


def test_agent_config_is_bounded_frozen_and_has_no_secret_fields() -> None:
    source_names = ["workspace.read", "workspace.write"]
    config = AgentConfig.model_validate({**agent_config().model_dump(), "tool_names": source_names})
    source_names.append("workspace.shell")

    assert config.tool_names == ("workspace.read", "workspace.write")
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({**config.model_dump(), "api_key": "secret"})
    with pytest.raises(ValidationError):
        AgentConfig.model_validate(
            {**config.model_dump(), "tool_names": ("workspace.write", "workspace.read")}
        )
    with pytest.raises(ValidationError):
        AgentConfig.model_validate(
            {**config.model_dump(), "max_tool_result_bytes": config.max_context_chars + 1}
        )


def test_run_input_rejects_blank_or_oversized_objectives() -> None:
    with pytest.raises(ValidationError):
        RunInput(
            session_id=SessionId.new(),
            objective="   ",
            budget_limits=limits(),
            agent_config=agent_config(),
        )
    with pytest.raises(ValidationError):
        RunInput(
            session_id=SessionId.new(),
            objective="x" * 1_000_001,
            budget_limits=limits(),
            agent_config=agent_config(),
        )


def test_model_cost_estimate_rounds_input_and_output_separately() -> None:
    assert estimate_model_cost_microusd(1, 1, pricing()) == 10
    assert estimate_model_cost_microusd(500_000, 125_000, pricing()) == 2_000_000


def test_run_result_accepts_only_matching_terminal_shapes() -> None:
    run_id = RunId.new()
    failed = RunState(
        run_id=run_id,
        session_id=SessionId.new(),
        status=RunStatus.FAILED,
        budget_limits=limits(),
        created_at=BASE_TIME,
        started_at=BASE_TIME,
        completed_at=BASE_TIME,
        terminal_error=ErrorInfo(
            category=ErrorCategory.BUDGET,
            code=ErrorCode.BUDGET_EXHAUSTED,
            message="Run budget exhausted: model_iterations.",
        ),
        last_sequence=3,
    )

    assert RunResult(run_id=run_id, state=failed).final_text is None
    with pytest.raises(ValidationError):
        RunResult(run_id=run_id, state=failed, final_text="not a success")


def test_tool_execution_record_requires_one_consistent_identity() -> None:
    call_id = ToolCallId.new()
    request = ToolRequest(
        tool_call_id=call_id,
        name="workspace.read",
        arguments={"path": "docs/overview.md"},
    )
    prepared = PreparedToolRequest(
        tool_call_id=call_id,
        name="workspace.read",
        arguments={"path": "docs/overview.md", "offset": 0},
    )
    allowed = PolicyDecision(outcome=PolicyOutcome.ALLOW, reason=PolicyReason.ALLOWED)
    result = ToolResult(
        tool_call_id=call_id,
        status=ToolStatus.SUCCEEDED,
        data={"content": "BearAgent"},
    )

    record = ToolExecutionRecord(
        request=request,
        prepared_request=prepared,
        policy_decision=allowed,
        reached_adapter=True,
        result=result,
    )
    assert record.prepared_request == prepared

    with pytest.raises(ValidationError):
        ToolExecutionRecord(
            request=request,
            prepared_request=prepared,
            policy_decision=allowed,
            reached_adapter=True,
            result=ToolResult(
                tool_call_id=ToolCallId.new(),
                status=ToolStatus.SUCCEEDED,
                data={},
            ),
        )


def test_v2_events_replay_without_changing_v1_projection_rules() -> None:
    run_id = RunId.new()
    activity_id = ActivityId.new()
    model_call_id = ModelCallId.new()
    request = ModelRequest(
        model=agent_config().model,
        messages=(Message(role=MessageRole.USER, parts=(TextPart(text="Summarize docs."),)),),
        max_output_tokens=agent_config().max_output_tokens,
        timeout_ms=agent_config().model_timeout_ms,
        prompt_version=agent_config().prompt_version,
    )
    report = ContextBuildReport(
        context_version=agent_config().context_version,
        input_chars=15,
    )
    events = (
        event(
            run_id,
            1,
            "RunCreated",
            RunCreatedPayloadV2(
                session_id=SessionId.new(),
                budget_limits=limits(),
                objective="Summarize docs.",
                agent_config=agent_config(),
            ),
        ),
        event(run_id, 2, "RunStarted", RunStartedPayloadV2()),
        event(
            run_id,
            3,
            "ModelCallRequested",
            ModelCallRequestedPayloadV2(
                activity_id=activity_id,
                model_call_id=model_call_id,
                request=request,
                context_report=report,
            ),
        ),
        event(
            run_id,
            4,
            "ModelCallStarted",
            ModelCallStartedPayloadV2(
                activity_id=activity_id,
                model_call_id=model_call_id,
            ),
        ),
        event(
            run_id,
            5,
            "ModelCallCompleted",
            ModelCallCompletedPayloadV2(
                activity_id=activity_id,
                model_call_id=model_call_id,
                input_tokens=10,
                output_tokens=5,
                cost_microusd=60,
                message=Message(
                    role=MessageRole.ASSISTANT,
                    parts=(TextPart(text="Done."),),
                ),
                provider_request_id="provider-request-1",
                provider_model=agent_config().model,
                finish_reason=ModelFinishReason.STOP,
            ),
        ),
        event(run_id, 6, "RunSucceeded", RunSucceededPayloadV2()),
    )

    state = None
    for item in events:
        parsed = parse_run_event_payload(item)
        assert parsed is not None
        state = reduce_event(state, item)

    assert state is not None
    assert state.status is RunStatus.SUCCEEDED
    assert state.budget_usage.input_tokens == 10
    assert state.budget_usage.output_tokens == 5
    assert state.budget_usage.cost_microusd == 60


def test_v2_model_completion_rejects_finish_reason_message_mismatch() -> None:
    with pytest.raises(ValidationError):
        ModelCallCompletedPayloadV2(
            activity_id=ActivityId.new(),
            model_call_id=ModelCallId.new(),
            input_tokens=0,
            output_tokens=0,
            cost_microusd=0,
            message=Message(
                role=MessageRole.ASSISTANT,
                parts=(TextPart(text="No tool calls."),),
            ),
            provider_request_id="provider-request-1",
            provider_model="test-model",
            finish_reason=ModelFinishReason.TOOL_CALLS,
        )


def test_v2_run_failed_payload_uses_only_safe_error_info() -> None:
    error = ErrorInfo(
        category=ErrorCategory.INTERNAL,
        code=ErrorCode.INTERNAL_ERROR,
        message="Run failed safely.",
    )
    assert "secret" not in error.model_dump_json()
