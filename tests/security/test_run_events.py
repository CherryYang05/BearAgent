from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import JsonValue

from bearagent.domain.errors import ErrorCode
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
from bearagent.runtime.reducer import RunReducerError, reduce_event

BASE_TIME = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)


def make_event(
    run_id: RunId,
    sequence: int,
    event_type: str,
    payload: Mapping[str, JsonValue],
    *,
    schema_version: int = 1,
) -> Event:
    return Event(
        event_id=EventId.new(),
        run_id=run_id,
        sequence=sequence,
        event_type=event_type,
        schema_version=schema_version,
        occurred_at=BASE_TIME + timedelta(milliseconds=sequence),
        causation_id=CausationId.new(),
        correlation_id=CorrelationId.new(),
        payload=payload,
    )


def valid_limits() -> dict[str, JsonValue]:
    return {
        "max_model_iterations": 2,
        "max_tokens": 100,
        "max_cost_microusd": 100,
        "max_wall_time_ms": 1_000,
        "max_tool_calls": 2,
    }


def started_state(run_id: RunId):
    created = reduce_event(
        None,
        make_event(
            run_id,
            1,
            "RunCreated",
            {
                "session_id": str(SessionId.new()),
                "budget_limits": valid_limits(),
            },
        ),
    )
    return reduce_event(created, make_event(run_id, 2, "RunStarted", {}))


def test_run_created_rejects_untrusted_budget_override_without_leaking_value() -> None:
    run_id = RunId.new()
    secret_marker = "must-not-appear"
    event = make_event(
        run_id,
        1,
        "RunCreated",
        {
            "session_id": str(SessionId.new()),
            "budget_limits": valid_limits(),
            "authorization_override": secret_marker,
        },
    )

    with pytest.raises(RunReducerError) as caught:
        reduce_event(None, event)

    assert caught.value.info.code is ErrorCode.INVALID_EVENT
    assert str(caught.value) == "Run Event payload is invalid."
    assert secret_marker not in str(caught.value)


def test_model_event_cannot_raise_budget_limits() -> None:
    run_id = RunId.new()
    state = started_state(run_id)
    event = make_event(
        run_id,
        3,
        "ModelCallRequested",
        {
            "activity_id": str(ActivityId.new()),
            "model_call_id": str(ModelCallId.new()),
            "budget_limits": {
                "max_model_iterations": 99_999,
                "max_tokens": 9_999_999,
            },
        },
    )

    with pytest.raises(RunReducerError, match="payload is invalid") as caught:
        reduce_event(state, event)

    assert caught.value.info.code is ErrorCode.INVALID_EVENT
    assert state.budget_limits.max_model_iterations == 2


def test_unknown_event_type_and_schema_version_fail_closed() -> None:
    run_id = RunId.new()
    state = started_state(run_id)

    unknown_type = make_event(run_id, 3, "ModelGrantedMoreBudget", {})
    with pytest.raises(RunReducerError, match="Unsupported") as caught_type:
        reduce_event(state, unknown_type)
    assert caught_type.value.info.code is ErrorCode.INVALID_EVENT

    unknown_version = make_event(
        run_id,
        3,
        "ModelCallRequested",
        {
            "activity_id": str(ActivityId.new()),
            "model_call_id": str(ModelCallId.new()),
        },
        schema_version=3,
    )
    with pytest.raises(RunReducerError, match="Unsupported") as caught_version:
        reduce_event(state, unknown_version)
    assert caught_version.value.info.code is ErrorCode.INVALID_EVENT


def test_tool_name_is_validated_before_state_changes() -> None:
    run_id = RunId.new()
    state = started_state(run_id)
    before = state.model_dump_json()
    event = make_event(
        run_id,
        3,
        "ToolCallRequested",
        {
            "activity_id": str(ActivityId.new()),
            "tool_call_id": str(ToolCallId.new()),
            "tool_name": "../../host-shell",
        },
    )

    with pytest.raises(RunReducerError, match="payload is invalid"):
        reduce_event(state, event)

    assert state.model_dump_json() == before
