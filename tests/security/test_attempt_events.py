from datetime import timedelta

import pytest
from tests.attempt_fixtures import AttemptHistory, retried_read_events

from bearagent.domain.attempts import (
    AttemptRequestedPayload,
    RecoveryAction,
    RecoveryDecisionPayload,
    RecoveryReason,
)
from bearagent.domain.events import Event
from bearagent.domain.ids import AttemptId, EventId
from bearagent.runtime.attempts import activity_deadline, decide_recovery
from bearagent.runtime.reducer import RunReducerError, reduce_event, reduce_events


@pytest.mark.parametrize(
    "change", ["number", "request", "deadline", "decision", "parallel", "version"]
)
def test_reject_forged_attempt_boundaries(change: str) -> None:
    h = AttemptHistory()
    if change == "parallel":
        h.start_attempt()
    assert h.state is not None
    payload = AttemptRequestedPayload(
        activity_id=h.activity_id,
        attempt_id=AttemptId.new(),
        number=1,
        request_event_id=h.requested.event_id,
        deadline=activity_deadline(h.state, h.state.activity_evidence[0]),
    )
    data = payload.model_dump(mode="json")
    if change == "number":
        data["number"] = 2
    if change == "request":
        data["request_event_id"] = str(EventId.new())
    if change == "decision":
        data["prior_decision_id"] = str(EventId.new())
    if change == "deadline":
        data["deadline"] = (payload.deadline + timedelta(seconds=1)).isoformat()
    event = h.event("AttemptRequested", AttemptRequestedPayload.model_validate(data))
    if change == "version":
        event = Event.model_validate({**event.model_dump(), "schema_version": 4})
    with pytest.raises(RunReducerError):
        reduce_event(h.state, event)


def test_budget_exhaustion_cannot_be_changed_to_a_retry_decision() -> None:
    h = AttemptHistory(max_tool_calls=1)
    h.start_attempt()
    h.fail()
    assert h.state is not None
    decision = decide_recovery(h.state, h.state.attempts[-1], now=h.now)
    assert decision.action is RecoveryAction.STOP_RUN
    assert decision.reason is RecoveryReason.BUDGET_EXHAUSTED
    forged = RecoveryDecisionPayload.model_validate(
        {**decision.model_dump(), "action": "retry", "reason": "safe_transient"}
    )
    with pytest.raises(RunReducerError):
        reduce_event(h.state, h.event("RecoveryDecisionRecorded", forged))


def test_terminal_cannot_replace_the_recorded_result() -> None:
    events = retried_read_events()
    index = next(i for i, e in enumerate(events) if e.event_type == "ToolCallCompleted")
    state = reduce_events(events[:index])
    data = events[index].model_dump(mode="json")
    data["payload"]["execution"]["result"]["data"] = {"content": "forged"}
    with pytest.raises(RunReducerError):
        reduce_event(state, Event.model_validate(data))


def test_a_decision_cannot_be_consumed_twice() -> None:
    events = retried_read_events()
    second = [e for e in events if e.event_type == "AttemptRequested"][1]
    state = reduce_events(events[: second.sequence])
    duplicate = Event.model_validate(
        {**second.model_dump(), "event_id": EventId.new(), "sequence": second.sequence + 1}
    )
    with pytest.raises(RunReducerError):
        reduce_event(state, duplicate)
