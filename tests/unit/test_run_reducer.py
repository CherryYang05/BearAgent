from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from bearagent.domain._base import DomainModel
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
    ModelCallFailedPayload,
    ModelCallRequestedPayload,
    ModelCallStartedPayload,
    RunCreatedPayload,
    RunFailedPayload,
    RunStartedPayload,
    RunSucceededPayload,
    ToolCallCompletedPayload,
    ToolCallFailedPayload,
    ToolCallFailedPayloadV2,
    ToolCallRequestedPayload,
    ToolCallRequestedPayloadV2,
    ToolCallStartedPayload,
)
from bearagent.domain.runs import ActivityStatus, BudgetLimits, RunState, RunStatus
from bearagent.domain.tools import ToolExecutionRecord, ToolRequest, ToolResult, ToolStatus
from bearagent.runtime.reducer import RunReducerError, reduce_event, reduce_events

BASE_TIME = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)


def budget_limits(**overrides: int) -> BudgetLimits:
    values = {
        "max_model_iterations": 4,
        "max_tokens": 1_000,
        "max_cost_microusd": 10_000,
        "max_wall_time_ms": 60_000,
        "max_tool_calls": 4,
    }
    values.update(overrides)
    return BudgetLimits.model_validate(values)


def make_event(
    run_id: RunId,
    sequence: int,
    event_type: str,
    payload: DomainModel,
    *,
    occurred_at: datetime | None = None,
    schema_version: int = 1,
) -> Event:
    return Event(
        event_id=EventId.new(),
        run_id=run_id,
        sequence=sequence,
        event_type=event_type,
        schema_version=schema_version,
        occurred_at=occurred_at or BASE_TIME + timedelta(milliseconds=sequence * 10),
        causation_id=CausationId.new(),
        correlation_id=CorrelationId.new(),
        payload=payload.model_dump(mode="json"),
    )


def started_run_events(
    limits: BudgetLimits | None = None,
) -> tuple[RunId, SessionId, list[Event]]:
    run_id = RunId.new()
    session_id = SessionId.new()
    events = [
        make_event(
            run_id,
            1,
            "RunCreated",
            RunCreatedPayload(
                session_id=session_id,
                budget_limits=limits or budget_limits(),
            ),
        ),
        make_event(run_id, 2, "RunStarted", RunStartedPayload()),
    ]
    return run_id, session_id, events


def provider_error() -> ErrorInfo:
    return ErrorInfo(
        category=ErrorCategory.PROVIDER,
        code=ErrorCode.PROVIDER_ERROR,
        message="Provider call failed.",
        retryable=True,
    )


def tool_error() -> ErrorInfo:
    return ErrorInfo(
        category=ErrorCategory.TOOL,
        code=ErrorCode.TOOL_ERROR,
        message="Tool call failed.",
    )


def test_v2_tool_terminal_requires_the_exact_requested_tool_request() -> None:
    run_id, _, events = started_run_events()
    state = reduce_events(events)
    activity_id = ActivityId.new()
    tool_call_id = ToolCallId.new()
    requested = ToolRequest(
        tool_call_id=tool_call_id,
        name="workspace.read",
        arguments={"path": "docs/requested.md"},
    )
    requested_event = make_event(
        run_id,
        3,
        "ToolCallRequested",
        ToolCallRequestedPayloadV2(
            activity_id=activity_id,
            tool_call_id=tool_call_id,
            tool_name=requested.name,
            request=requested,
        ),
        schema_version=2,
    )
    state = reduce_event(state, requested_event)
    started_event = make_event(
        run_id,
        4,
        "ToolCallStarted",
        ToolCallStartedPayload(activity_id=activity_id, tool_call_id=tool_call_id),
        schema_version=2,
    )
    state = reduce_event(state, started_event)
    error = tool_error()
    different_request = ToolRequest(
        tool_call_id=tool_call_id,
        name="workspace.write",
        arguments={"path": "outputs/report.md", "content": "different"},
    )
    terminal = make_event(
        run_id,
        5,
        "ToolCallFailed",
        ToolCallFailedPayloadV2(
            activity_id=activity_id,
            tool_call_id=tool_call_id,
            error=error,
            execution=ToolExecutionRecord(
                request=different_request,
                reached_adapter=False,
                result=ToolResult(
                    tool_call_id=tool_call_id,
                    status=ToolStatus.FAILED,
                    error=error,
                ),
            ),
        ),
        schema_version=2,
    )

    with pytest.raises(RunReducerError, match="does not match"):
        reduce_events([*events, requested_event, started_event, terminal])

    assert state.activities[-1].status is ActivityStatus.RUNNING


def test_run_lifecycle_is_immutable_and_json_round_trips() -> None:
    run_id, session_id, events = started_run_events()
    events.append(make_event(run_id, 3, "RunSucceeded", RunSucceededPayload()))

    state = reduce_events(events)
    restored = RunState.model_validate_json(state.model_dump_json())

    assert state.run_id == run_id
    assert state.session_id == session_id
    assert state.status is RunStatus.SUCCEEDED
    assert state.last_sequence == 3
    assert state.completed_at == events[-1].occurred_at
    assert restored == state
    with pytest.raises(ValidationError, match="Instance is frozen"):
        state.last_sequence = 99


def test_run_failure_keeps_only_safe_terminal_error() -> None:
    run_id, _, events = started_run_events()
    error = provider_error()
    events.append(make_event(run_id, 3, "RunFailed", RunFailedPayload(error=error)))

    state = reduce_events(events)

    assert state.status is RunStatus.FAILED
    assert state.terminal_error == error
    assert state.model_dump(mode="json")["terminal_error"]["message"] == "Provider call failed."


def test_model_and_tool_activities_are_serial_and_account_usage() -> None:
    run_id, _, events = started_run_events()
    model_activity_id = ActivityId.new()
    model_call_id = ModelCallId.new()
    tool_activity_id = ActivityId.new()
    tool_call_id = ToolCallId.new()
    events.extend(
        [
            make_event(
                run_id,
                3,
                "ModelCallRequested",
                ModelCallRequestedPayload(
                    activity_id=model_activity_id,
                    model_call_id=model_call_id,
                ),
            ),
            make_event(
                run_id,
                4,
                "ModelCallStarted",
                ModelCallStartedPayload(
                    activity_id=model_activity_id,
                    model_call_id=model_call_id,
                ),
            ),
            make_event(
                run_id,
                5,
                "ModelCallCompleted",
                ModelCallCompletedPayload(
                    activity_id=model_activity_id,
                    model_call_id=model_call_id,
                    input_tokens=20,
                    output_tokens=10,
                    cost_microusd=5,
                ),
            ),
            make_event(
                run_id,
                6,
                "ToolCallRequested",
                ToolCallRequestedPayload(
                    activity_id=tool_activity_id,
                    tool_call_id=tool_call_id,
                    tool_name="read_file",
                ),
            ),
            make_event(
                run_id,
                7,
                "ToolCallStarted",
                ToolCallStartedPayload(
                    activity_id=tool_activity_id,
                    tool_call_id=tool_call_id,
                ),
            ),
            make_event(
                run_id,
                8,
                "ToolCallFailed",
                ToolCallFailedPayload(
                    activity_id=tool_activity_id,
                    tool_call_id=tool_call_id,
                    error=tool_error(),
                ),
            ),
        ]
    )

    state = reduce_events(events)

    assert [activity.status for activity in state.activities] == [
        ActivityStatus.SUCCEEDED,
        ActivityStatus.FAILED,
    ]
    assert state.activities[1].tool_name == "read_file"
    assert state.activities[1].error == tool_error()
    assert state.budget_usage.model_iterations == 1
    assert state.budget_usage.input_tokens == 20
    assert state.budget_usage.output_tokens == 10
    assert state.budget_usage.tokens == 30
    assert state.budget_usage.cost_microusd == 5
    assert state.budget_usage.tool_calls == 1


def test_failed_model_activity_keeps_reported_usage() -> None:
    run_id, _, events = started_run_events()
    activity_id = ActivityId.new()
    model_call_id = ModelCallId.new()
    events.extend(
        [
            make_event(
                run_id,
                3,
                "ModelCallRequested",
                ModelCallRequestedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                ),
            ),
            make_event(
                run_id,
                4,
                "ModelCallStarted",
                ModelCallStartedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                ),
            ),
            make_event(
                run_id,
                5,
                "ModelCallFailed",
                ModelCallFailedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                    error=provider_error(),
                    input_tokens=7,
                    output_tokens=3,
                    cost_microusd=2,
                ),
            ),
        ]
    )

    state = reduce_events(events)

    assert state.activities[0].status is ActivityStatus.FAILED
    assert state.budget_usage.tokens == 10
    assert state.budget_usage.cost_microusd == 2


def test_tool_activity_can_complete_successfully() -> None:
    run_id, _, events = started_run_events()
    activity_id = ActivityId.new()
    tool_call_id = ToolCallId.new()
    events.extend(
        [
            make_event(
                run_id,
                3,
                "ToolCallRequested",
                ToolCallRequestedPayload(
                    activity_id=activity_id,
                    tool_call_id=tool_call_id,
                    tool_name="search_files",
                ),
            ),
            make_event(
                run_id,
                4,
                "ToolCallStarted",
                ToolCallStartedPayload(
                    activity_id=activity_id,
                    tool_call_id=tool_call_id,
                ),
            ),
            make_event(
                run_id,
                5,
                "ToolCallCompleted",
                ToolCallCompletedPayload(
                    activity_id=activity_id,
                    tool_call_id=tool_call_id,
                ),
            ),
        ]
    )

    state = reduce_events(events)

    assert state.activities[0].status is ActivityStatus.SUCCEEDED
    assert state.activities[0].tool_name == "search_files"
    assert state.budget_usage.tool_calls == 1


def test_reducer_rejects_active_overlap_without_mutating_state() -> None:
    run_id, _, events = started_run_events()
    activity_id = ActivityId.new()
    model_call_id = ModelCallId.new()
    pending = reduce_events(
        [
            *events,
            make_event(
                run_id,
                3,
                "ModelCallRequested",
                ModelCallRequestedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                ),
            ),
        ]
    )
    before = pending.model_dump_json()
    overlapping = make_event(
        run_id,
        4,
        "ToolCallRequested",
        ToolCallRequestedPayload(
            activity_id=ActivityId.new(),
            tool_call_id=ToolCallId.new(),
            tool_name="read_file",
        ),
    )

    with pytest.raises(RunReducerError) as caught:
        reduce_event(pending, overlapping)

    assert caught.value.info.code is ErrorCode.INVALID_STATE_TRANSITION
    assert pending.model_dump_json() == before


def test_reducer_rejects_duplicate_and_mismatched_activity_ids() -> None:
    run_id, _, events = started_run_events()
    activity_id = ActivityId.new()
    model_call_id = ModelCallId.new()
    events.extend(
        [
            make_event(
                run_id,
                3,
                "ModelCallRequested",
                ModelCallRequestedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                ),
            ),
            make_event(
                run_id,
                4,
                "ModelCallStarted",
                ModelCallStartedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                ),
            ),
            make_event(
                run_id,
                5,
                "ModelCallCompleted",
                ModelCallCompletedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                    input_tokens=1,
                    output_tokens=1,
                    cost_microusd=1,
                ),
            ),
        ]
    )
    state = reduce_events(events)

    duplicate = make_event(
        run_id,
        6,
        "ModelCallRequested",
        ModelCallRequestedPayload(
            activity_id=activity_id,
            model_call_id=ModelCallId.new(),
        ),
    )
    with pytest.raises(RunReducerError, match="activity_id is already used"):
        reduce_event(state, duplicate)

    mismatched = make_event(
        run_id,
        6,
        "ModelCallStarted",
        ModelCallStartedPayload(
            activity_id=activity_id,
            model_call_id=ModelCallId.new(),
        ),
    )
    with pytest.raises(RunReducerError, match="must be pending"):
        reduce_event(state, mismatched)


def test_activity_call_ids_must_match_and_remain_unique() -> None:
    run_id, _, events = started_run_events()
    activity_id = ActivityId.new()
    model_call_id = ModelCallId.new()
    pending = reduce_events(
        [
            *events,
            make_event(
                run_id,
                3,
                "ModelCallRequested",
                ModelCallRequestedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                ),
            ),
        ]
    )
    wrong_start = make_event(
        run_id,
        4,
        "ModelCallStarted",
        ModelCallStartedPayload(
            activity_id=activity_id,
            model_call_id=ModelCallId.new(),
        ),
    )
    with pytest.raises(RunReducerError, match="model_call_id does not match"):
        reduce_event(pending, wrong_start)

    completed = reduce_events(
        [
            *events,
            make_event(
                run_id,
                3,
                "ModelCallRequested",
                ModelCallRequestedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                ),
            ),
            make_event(
                run_id,
                4,
                "ModelCallStarted",
                ModelCallStartedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                ),
            ),
            make_event(
                run_id,
                5,
                "ModelCallCompleted",
                ModelCallCompletedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                    input_tokens=1,
                    output_tokens=1,
                    cost_microusd=1,
                ),
            ),
        ]
    )
    duplicate_call = make_event(
        run_id,
        6,
        "ModelCallRequested",
        ModelCallRequestedPayload(
            activity_id=ActivityId.new(),
            model_call_id=model_call_id,
        ),
    )
    with pytest.raises(RunReducerError, match="model_call_id is already used"):
        reduce_event(completed, duplicate_call)


def test_reducer_rejects_empty_gap_cross_run_and_terminal_events() -> None:
    with pytest.raises(RunReducerError) as empty:
        reduce_events([])
    assert empty.value.info.code is ErrorCode.INVALID_EVENT

    run_id, _, events = started_run_events()
    queued = reduce_event(None, events[0])
    with pytest.raises(RunReducerError, match="not contiguous"):
        reduce_event(
            queued,
            make_event(run_id, 3, "RunStarted", RunStartedPayload()),
        )
    with pytest.raises(RunReducerError, match="run_id does not match"):
        reduce_event(
            queued,
            make_event(RunId.new(), 2, "RunStarted", RunStartedPayload()),
        )

    terminal = reduce_events(
        [*events, make_event(run_id, 3, "RunSucceeded", RunSucceededPayload())]
    )
    with pytest.raises(RunReducerError, match="Terminal Run"):
        reduce_event(
            terminal,
            make_event(run_id, 4, "RunFailed", RunFailedPayload(error=provider_error())),
        )


def test_reducer_is_deterministic_for_the_same_event_sequence() -> None:
    run_id, _, events = started_run_events()
    events.append(make_event(run_id, 3, "RunSucceeded", RunSucceededPayload()))

    first = reduce_events(events)
    second = reduce_events(tuple(events))

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_completion_after_deadline_is_recorded_but_next_request_is_blocked() -> None:
    run_id, _, events = started_run_events(
        budget_limits(
            max_model_iterations=2,
            max_tokens=10,
            max_cost_microusd=5,
            max_wall_time_ms=100,
            max_tool_calls=1,
        )
    )
    activity_id = ActivityId.new()
    model_call_id = ModelCallId.new()
    events.extend(
        [
            make_event(
                run_id,
                3,
                "ModelCallRequested",
                ModelCallRequestedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                ),
                occurred_at=BASE_TIME + timedelta(milliseconds=30),
            ),
            make_event(
                run_id,
                4,
                "ModelCallStarted",
                ModelCallStartedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                ),
                occurred_at=BASE_TIME + timedelta(milliseconds=40),
            ),
            make_event(
                run_id,
                5,
                "ModelCallCompleted",
                ModelCallCompletedPayload(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                    input_tokens=8,
                    output_tokens=4,
                    cost_microusd=6,
                ),
                occurred_at=BASE_TIME + timedelta(milliseconds=500),
            ),
        ]
    )
    state = reduce_events(events)

    assert state.budget_usage.tokens == 12
    blocked = make_event(
        run_id,
        6,
        "ToolCallRequested",
        ToolCallRequestedPayload(
            activity_id=ActivityId.new(),
            tool_call_id=ToolCallId.new(),
            tool_name="read_file",
        ),
        occurred_at=BASE_TIME + timedelta(milliseconds=600),
    )
    with pytest.raises(RunReducerError) as caught:
        reduce_event(state, blocked)
    assert caught.value.info.code is ErrorCode.BUDGET_EXHAUSTED

    succeeded = reduce_event(
        state,
        make_event(
            run_id,
            6,
            "RunSucceeded",
            RunSucceededPayload(),
            occurred_at=BASE_TIME + timedelta(milliseconds=600),
        ),
    )
    assert succeeded.status is RunStatus.SUCCEEDED
