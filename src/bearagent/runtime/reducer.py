"""Strict, deterministic reducer for P1 Run Events."""

from collections.abc import Iterable
from typing import NoReturn

from pydantic import ValidationError

from bearagent.domain.errors import BearAgentError, ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import ActivityId, ModelCallId, ToolCallId
from bearagent.domain.run_events import (
    ModelCallCompletedPayload,
    ModelCallFailedPayload,
    ModelCallRequestedPayload,
    ModelCallStartedPayload,
    RunCreatedPayload,
    RunStartedPayload,
    RunSucceededPayload,
    ToolCallCompletedPayload,
    ToolCallFailedPayload,
    ToolCallRequestedPayload,
    ToolCallStartedPayload,
    parse_run_event_payload,
)
from bearagent.domain.runs import (
    ActivityKind,
    ActivityState,
    ActivityStatus,
    BudgetUsage,
    RunState,
    RunStatus,
)
from bearagent.runtime.budgets import check_activity_budget


class RunReducerError(BearAgentError):
    """A safe failure raised for an invalid Run Event stream."""


def reduce_events(events: Iterable[Event]) -> RunState:
    """Fold a non-empty ordered Event stream into one immutable Run state."""
    state: RunState | None = None
    for event in events:
        state = reduce_event(state, event)
    if state is None:
        raise RunReducerError(
            ErrorInfo(
                category=ErrorCategory.VALIDATION,
                code=ErrorCode.INVALID_EVENT,
                message="Run Event stream must not be empty.",
            )
        )
    return state


def reduce_event(state: RunState | None, event: Event) -> RunState:
    """Apply one validated Event without mutating the previous state."""
    try:
        payload = parse_run_event_payload(event)
    except KeyError as cause:
        _fail_event(
            event,
            "Unsupported Run Event type or schema version.",
            cause=cause,
        )
    except ValidationError as cause:
        _fail_event(event, "Run Event payload is invalid.", cause=cause)

    if state is None:
        if event.sequence != 1:
            _fail_event(event, "First Run Event must have sequence 1.")
        if not isinstance(payload, RunCreatedPayload):
            _fail_transition(event, "First Run Event must be RunCreated.")
        return RunState(
            run_id=event.run_id,
            session_id=payload.session_id,
            status=RunStatus.QUEUED,
            budget_limits=payload.budget_limits,
            created_at=event.occurred_at,
            last_sequence=event.sequence,
        )

    if event.run_id != state.run_id:
        _fail_event(event, "Run Event run_id does not match the current Run.")
    expected_sequence = state.last_sequence + 1
    if event.sequence != expected_sequence:
        _fail_event(
            event,
            "Run Event sequence is not contiguous.",
            details={"expected_sequence": expected_sequence},
        )
    if state.status in {RunStatus.SUCCEEDED, RunStatus.FAILED}:
        _fail_transition(event, "Terminal Run cannot accept another Event.")

    try:
        if isinstance(payload, RunCreatedPayload):
            _fail_transition(event, "RunCreated cannot be applied to an existing Run.")
        if isinstance(payload, RunStartedPayload):
            _require_status(state, event, RunStatus.QUEUED)
            return _replace_state(
                state,
                status=RunStatus.RUNNING,
                started_at=event.occurred_at,
                last_sequence=event.sequence,
            )
        if isinstance(payload, ModelCallRequestedPayload):
            return _request_model(state, event, payload)
        if isinstance(payload, ModelCallStartedPayload):
            return _start_model(state, event, payload)
        if isinstance(payload, ModelCallCompletedPayload):
            return _complete_model(state, event, payload)
        if isinstance(payload, ModelCallFailedPayload):
            return _fail_model(state, event, payload)
        if isinstance(payload, ToolCallRequestedPayload):
            return _request_tool(state, event, payload)
        if isinstance(payload, ToolCallStartedPayload):
            return _start_tool(state, event, payload)
        if isinstance(payload, ToolCallCompletedPayload):
            return _complete_tool(state, event, payload)
        if isinstance(payload, ToolCallFailedPayload):
            return _fail_tool(state, event, payload)
        if isinstance(payload, RunSucceededPayload):
            _require_terminal_ready(state, event)
            return _replace_state(
                state,
                status=RunStatus.SUCCEEDED,
                completed_at=event.occurred_at,
                last_sequence=event.sequence,
            )
        _require_terminal_ready(state, event)
        return _replace_state(
            state,
            status=RunStatus.FAILED,
            completed_at=event.occurred_at,
            terminal_error=payload.error,
            last_sequence=event.sequence,
        )
    except RunReducerError:
        raise
    except BearAgentError as cause:
        raise RunReducerError(cause.info, cause=cause) from cause
    except ValidationError as cause:
        _fail_event(event, "Run Event would produce invalid state.", cause=cause)

    _fail_event(event, "Unsupported Run Event payload.")


def _request_model(
    state: RunState,
    event: Event,
    payload: ModelCallRequestedPayload,
) -> RunState:
    _require_activity_request_ready(state, event)
    _require_unique_ids(state, event, payload.activity_id, model_call_id=payload.model_call_id)
    _require_budget(state, event, ActivityKind.MODEL)
    activity = ActivityState(
        activity_id=payload.activity_id,
        kind=ActivityKind.MODEL,
        status=ActivityStatus.PENDING,
        requested_at=event.occurred_at,
        model_call_id=payload.model_call_id,
    )
    usage = _replace_usage(
        state.budget_usage,
        model_iterations=state.budget_usage.model_iterations + 1,
    )
    return _replace_state(
        state,
        activities=(*state.activities, activity),
        budget_usage=usage,
        last_sequence=event.sequence,
    )


def _start_model(
    state: RunState,
    event: Event,
    payload: ModelCallStartedPayload,
) -> RunState:
    activity = _matching_activity(
        state,
        event,
        payload.activity_id,
        ActivityKind.MODEL,
        model_call_id=payload.model_call_id,
        required_status=ActivityStatus.PENDING,
    )
    updated = _replace_activity_state(
        activity,
        status=ActivityStatus.RUNNING,
        started_at=event.occurred_at,
    )
    return _with_activity(state, event, updated)


def _complete_model(
    state: RunState,
    event: Event,
    payload: ModelCallCompletedPayload,
) -> RunState:
    activity = _matching_activity(
        state,
        event,
        payload.activity_id,
        ActivityKind.MODEL,
        model_call_id=payload.model_call_id,
        required_status=ActivityStatus.RUNNING,
    )
    updated = _replace_activity_state(
        activity,
        status=ActivityStatus.SUCCEEDED,
        completed_at=event.occurred_at,
    )
    usage = _model_usage(state, payload.input_tokens, payload.output_tokens, payload.cost_microusd)
    return _with_activity(state, event, updated, budget_usage=usage)


def _fail_model(
    state: RunState,
    event: Event,
    payload: ModelCallFailedPayload,
) -> RunState:
    activity = _matching_activity(
        state,
        event,
        payload.activity_id,
        ActivityKind.MODEL,
        model_call_id=payload.model_call_id,
        required_status=ActivityStatus.RUNNING,
    )
    updated = _replace_activity_state(
        activity,
        status=ActivityStatus.FAILED,
        completed_at=event.occurred_at,
        error=payload.error,
    )
    usage = _model_usage(state, payload.input_tokens, payload.output_tokens, payload.cost_microusd)
    return _with_activity(state, event, updated, budget_usage=usage)


def _request_tool(
    state: RunState,
    event: Event,
    payload: ToolCallRequestedPayload,
) -> RunState:
    _require_activity_request_ready(state, event)
    _require_unique_ids(state, event, payload.activity_id, tool_call_id=payload.tool_call_id)
    _require_budget(state, event, ActivityKind.TOOL)
    activity = ActivityState(
        activity_id=payload.activity_id,
        kind=ActivityKind.TOOL,
        status=ActivityStatus.PENDING,
        requested_at=event.occurred_at,
        tool_call_id=payload.tool_call_id,
        tool_name=payload.tool_name,
    )
    usage = _replace_usage(
        state.budget_usage,
        tool_calls=state.budget_usage.tool_calls + 1,
    )
    return _replace_state(
        state,
        activities=(*state.activities, activity),
        budget_usage=usage,
        last_sequence=event.sequence,
    )


def _start_tool(
    state: RunState,
    event: Event,
    payload: ToolCallStartedPayload,
) -> RunState:
    activity = _matching_activity(
        state,
        event,
        payload.activity_id,
        ActivityKind.TOOL,
        tool_call_id=payload.tool_call_id,
        required_status=ActivityStatus.PENDING,
    )
    updated = _replace_activity_state(
        activity,
        status=ActivityStatus.RUNNING,
        started_at=event.occurred_at,
    )
    return _with_activity(state, event, updated)


def _complete_tool(
    state: RunState,
    event: Event,
    payload: ToolCallCompletedPayload,
) -> RunState:
    activity = _matching_activity(
        state,
        event,
        payload.activity_id,
        ActivityKind.TOOL,
        tool_call_id=payload.tool_call_id,
        required_status=ActivityStatus.RUNNING,
    )
    updated = _replace_activity_state(
        activity,
        status=ActivityStatus.SUCCEEDED,
        completed_at=event.occurred_at,
    )
    return _with_activity(state, event, updated)


def _fail_tool(
    state: RunState,
    event: Event,
    payload: ToolCallFailedPayload,
) -> RunState:
    activity = _matching_activity(
        state,
        event,
        payload.activity_id,
        ActivityKind.TOOL,
        tool_call_id=payload.tool_call_id,
        required_status=ActivityStatus.RUNNING,
    )
    updated = _replace_activity_state(
        activity,
        status=ActivityStatus.FAILED,
        completed_at=event.occurred_at,
        error=payload.error,
    )
    return _with_activity(state, event, updated)


def _model_usage(
    state: RunState,
    input_tokens: int,
    output_tokens: int,
    cost_microusd: int,
) -> BudgetUsage:
    return _replace_usage(
        state.budget_usage,
        input_tokens=state.budget_usage.input_tokens + input_tokens,
        output_tokens=state.budget_usage.output_tokens + output_tokens,
        cost_microusd=state.budget_usage.cost_microusd + cost_microusd,
    )


def _require_status(state: RunState, event: Event, expected: RunStatus) -> None:
    if state.status is not expected:
        _fail_transition(
            event,
            f"Run must be {expected.value} for {event.event_type}.",
            details={"current_status": state.status.value},
        )


def _require_activity_request_ready(state: RunState, event: Event) -> None:
    _require_status(state, event, RunStatus.RUNNING)
    if any(
        activity.status in {ActivityStatus.PENDING, ActivityStatus.RUNNING}
        for activity in state.activities
    ):
        _fail_transition(event, "Run already contains an active Activity.")


def _require_terminal_ready(state: RunState, event: Event) -> None:
    _require_status(state, event, RunStatus.RUNNING)
    if any(
        activity.status in {ActivityStatus.PENDING, ActivityStatus.RUNNING}
        for activity in state.activities
    ):
        _fail_transition(event, "Run cannot terminate while an Activity is active.")


def _require_unique_ids(
    state: RunState,
    event: Event,
    activity_id: ActivityId,
    *,
    model_call_id: ModelCallId | None = None,
    tool_call_id: ToolCallId | None = None,
) -> None:
    if any(activity.activity_id == activity_id for activity in state.activities):
        _fail_event(event, "activity_id is already used in this Run.")
    if model_call_id is not None and any(
        activity.model_call_id == model_call_id for activity in state.activities
    ):
        _fail_event(event, "model_call_id is already used in this Run.")
    if tool_call_id is not None and any(
        activity.tool_call_id == tool_call_id for activity in state.activities
    ):
        _fail_event(event, "tool_call_id is already used in this Run.")


def _require_budget(state: RunState, event: Event, kind: ActivityKind) -> None:
    exhaustion = check_activity_budget(state, kind, event.occurred_at)
    if exhaustion is not None:
        raise RunReducerError(exhaustion.to_error_info())


def _matching_activity(
    state: RunState,
    event: Event,
    activity_id: ActivityId,
    kind: ActivityKind,
    *,
    model_call_id: ModelCallId | None = None,
    tool_call_id: ToolCallId | None = None,
    required_status: ActivityStatus,
) -> ActivityState:
    activity = next(
        (item for item in state.activities if item.activity_id == activity_id),
        None,
    )
    if activity is None:
        _fail_event(event, "Activity does not exist in this Run.")
    if activity.kind is not kind:
        _fail_transition(event, "Activity kind does not match the Event.")
    if activity.status is not required_status:
        _fail_transition(
            event,
            f"Activity must be {required_status.value} for {event.event_type}.",
            details={"current_activity_status": activity.status.value},
        )
    if model_call_id is not None and activity.model_call_id != model_call_id:
        _fail_event(event, "model_call_id does not match the Activity.")
    if tool_call_id is not None and activity.tool_call_id != tool_call_id:
        _fail_event(event, "tool_call_id does not match the Activity.")
    return activity


def _with_activity(
    state: RunState,
    event: Event,
    updated: ActivityState,
    *,
    budget_usage: BudgetUsage | None = None,
) -> RunState:
    activities = tuple(
        updated if item.activity_id == updated.activity_id else item for item in state.activities
    )
    changes: dict[str, object] = {
        "activities": activities,
        "last_sequence": event.sequence,
    }
    if budget_usage is not None:
        changes["budget_usage"] = budget_usage
    return _replace_state(state, **changes)


def _replace_state(state: RunState, **changes: object) -> RunState:
    values = {name: getattr(state, name) for name in RunState.model_fields}
    values.update(changes)
    return RunState.model_validate(values)


def _replace_activity_state(activity: ActivityState, **changes: object) -> ActivityState:
    values = {name: getattr(activity, name) for name in ActivityState.model_fields}
    values.update(changes)
    return ActivityState.model_validate(values)


def _replace_usage(usage: BudgetUsage, **changes: object) -> BudgetUsage:
    values = {name: getattr(usage, name) for name in BudgetUsage.model_fields}
    values.update(changes)
    return BudgetUsage.model_validate(values)


def _fail_event(
    event: Event,
    message: str,
    *,
    details: dict[str, str | int] | None = None,
    cause: BaseException | None = None,
) -> NoReturn:
    safe_details: dict[str, str | int] = {
        "event_type": event.event_type,
        "sequence": event.sequence,
    }
    if details:
        safe_details.update(details)
    raise RunReducerError(
        ErrorInfo(
            category=ErrorCategory.VALIDATION,
            code=ErrorCode.INVALID_EVENT,
            message=message,
            retryable=False,
            details=safe_details,
        ),
        cause=cause,
    )


def _fail_transition(
    event: Event,
    message: str,
    *,
    details: dict[str, str | int] | None = None,
) -> NoReturn:
    safe_details: dict[str, str | int] = {
        "event_type": event.event_type,
        "sequence": event.sequence,
    }
    if details:
        safe_details.update(details)
    raise RunReducerError(
        ErrorInfo(
            category=ErrorCategory.VALIDATION,
            code=ErrorCode.INVALID_STATE_TRANSITION,
            message=message,
            retryable=False,
            details=safe_details,
        )
    )
