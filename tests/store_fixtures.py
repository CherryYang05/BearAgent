"""Shared valid EventStore contract fixtures."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, JsonValue

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
from bearagent.domain.run_events import (
    ModelCallCompletedPayload,
    ModelCallRequestedPayload,
    ModelCallStartedPayload,
    RunCreatedPayload,
    RunFailedPayload,
    RunStartedPayload,
    RunSucceededPayload,
    ToolCallCompletedPayload,
    ToolCallRequestedPayload,
    ToolCallStartedPayload,
)
from bearagent.domain.runs import BudgetLimits

START_TIME = datetime(2026, 8, 12, 8, 0, tzinfo=UTC)
DEFAULT_LIMITS = BudgetLimits(
    max_model_iterations=10,
    max_tokens=10_000,
    max_cost_microusd=1_000_000,
    max_wall_time_ms=60_000,
    max_tool_calls=10,
)


def make_event(
    run_id: RunId,
    sequence: int,
    event_type: str,
    payload: Mapping[str, JsonValue],
    *,
    event_id: EventId | None = None,
    schema_version: int = 1,
) -> Event:
    return Event(
        event_id=event_id or EventId.new(),
        run_id=run_id,
        sequence=sequence,
        event_type=event_type,
        schema_version=schema_version,
        occurred_at=START_TIME + timedelta(seconds=sequence),
        causation_id=CausationId.new(),
        correlation_id=CorrelationId.new(),
        payload=payload,
    )


def payload_json(payload: BaseModel) -> Mapping[str, JsonValue]:
    return payload.model_dump(mode="json")


def run_created_event(
    run_id: RunId,
    *,
    event_id: EventId | None = None,
    sequence: int = 1,
) -> Event:
    return make_event(
        run_id,
        sequence,
        "RunCreated",
        payload_json(RunCreatedPayload(session_id=SessionId.new(), budget_limits=DEFAULT_LIMITS)),
        event_id=event_id,
    )


def successful_run_events(run_id: RunId | None = None) -> tuple[Event, ...]:
    actual_run_id = run_id or RunId.new()
    model_activity_id = ActivityId.new()
    model_call_id = ModelCallId.new()
    tool_activity_id = ActivityId.new()
    tool_call_id = ToolCallId.new()
    payloads: tuple[tuple[str, object], ...] = (
        (
            "RunCreated",
            RunCreatedPayload(session_id=SessionId.new(), budget_limits=DEFAULT_LIMITS),
        ),
        ("RunStarted", RunStartedPayload()),
        (
            "ModelCallRequested",
            ModelCallRequestedPayload(activity_id=model_activity_id, model_call_id=model_call_id),
        ),
        (
            "ModelCallStarted",
            ModelCallStartedPayload(activity_id=model_activity_id, model_call_id=model_call_id),
        ),
        (
            "ModelCallCompleted",
            ModelCallCompletedPayload(
                activity_id=model_activity_id,
                model_call_id=model_call_id,
                input_tokens=20,
                output_tokens=10,
                cost_microusd=300,
            ),
        ),
        (
            "ToolCallRequested",
            ToolCallRequestedPayload(
                activity_id=tool_activity_id,
                tool_call_id=tool_call_id,
                tool_name="workspace.read",
            ),
        ),
        (
            "ToolCallStarted",
            ToolCallStartedPayload(activity_id=tool_activity_id, tool_call_id=tool_call_id),
        ),
        (
            "ToolCallCompleted",
            ToolCallCompletedPayload(activity_id=tool_activity_id, tool_call_id=tool_call_id),
        ),
        ("RunSucceeded", RunSucceededPayload()),
    )
    return tuple(
        make_event(actual_run_id, sequence, event_type, payload_json(payload))
        for sequence, (event_type, payload) in enumerate(payloads, start=1)
    )


def failed_run_event(run_id: RunId, sequence: int, message: str) -> Event:
    error = ErrorInfo(
        category=ErrorCategory.INTERNAL,
        code=ErrorCode.INTERNAL_ERROR,
        message=message,
    )
    return make_event(
        run_id,
        sequence,
        "RunFailed",
        payload_json(RunFailedPayload(error=error)),
    )
