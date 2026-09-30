"""Pure evidence checks and finite retry decisions shared by execution and replay."""

import hashlib
import json
from datetime import datetime, timedelta

from pydantic import BaseModel

from bearagent.domain.attempts import (
    ActivityEvidence,
    AttemptState,
    FailureClass,
    ModelSubmission,
    RecoveryAction,
    RecoveryDecisionPayload,
    RecoveryReason,
    RecoverySemantics,
    RunStateV5,
)
from bearagent.domain.runs import ActivityKind, BudgetExhaustion, RunState
from bearagent.runtime.budgets import check_activity_budget


def evidence_hash(value: BaseModel) -> str:
    encoded = json.dumps(
        value.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def activity_deadline(state: RunStateV5, evidence: ActivityEvidence) -> datetime:
    activity = next(a for a in state.activities if a.activity_id == evidence.activity_id)
    if state.started_at is None:
        raise ValueError("Run is not started")
    return min(
        state.started_at + timedelta(milliseconds=state.budget_limits.max_wall_time_ms),
        activity.requested_at
        + timedelta(milliseconds=state.retry_policy.window_ms(evidence.timeout_ms)),
    )


def check_dispatch_budget(
    state: RunStateV5, kind: ActivityKind, now: datetime
) -> BudgetExhaustion | None:
    """Recheck a reserved Attempt without charging its already-committed slot twice."""
    values = state.model_dump(include=set(RunState.model_fields))
    values["budget_usage"]["model_iterations" if kind is ActivityKind.MODEL else "tool_calls"] -= 1
    return check_activity_budget(RunState.model_validate(values), kind, now)


def decide_recovery(
    state: RunStateV5,
    attempt: AttemptState,
    *,
    now: datetime,
    delay_ms: int = 0,
) -> RecoveryDecisionPayload:
    """A RETRY result only permits scheduling checks, never bypasses Tool Policy."""
    activity = next(a for a in state.activities if a.activity_id == attempt.activity_id)
    evidence = next(a for a in state.activity_evidence if a.activity_id == attempt.activity_id)
    if attempt.terminal_event_id is None or attempt.error is None:
        raise ValueError("recovery requires a persisted failure")
    action = (
        RecoveryAction.STOP_RUN
        if activity.kind is ActivityKind.MODEL
        else RecoveryAction.RETURN_TO_MODEL
    )
    reason = RecoveryReason.NON_RETRYABLE
    if attempt.failure_class is FailureClass.EFFECT_INDETERMINATE:
        action, reason = RecoveryAction.STOP_RUN, RecoveryReason.EFFECT_INDETERMINATE
    elif activity.kind is ActivityKind.MODEL and (
        attempt.model_evidence is None
        or attempt.model_evidence.submission is not ModelSubmission.NOT_SUBMITTED
        or not attempt.model_evidence.usage_known
    ):
        reason = RecoveryReason.MODEL_SUBMISSION_UNKNOWN
    elif check_activity_budget(state, activity.kind, now) is not None:
        action, reason = RecoveryAction.STOP_RUN, RecoveryReason.BUDGET_EXHAUSTED
    elif now >= attempt.deadline:
        action, reason = RecoveryAction.STOP_RUN, RecoveryReason.DEADLINE_EXHAUSTED
    elif (
        attempt.failure_class is FailureClass.TRANSIENT_INFRASTRUCTURE
        and evidence.semantics is RecoverySemantics.READ_ONLY
    ):
        if attempt.number >= state.retry_policy.max_attempts:
            reason = RecoveryReason.ATTEMPTS_EXHAUSTED
        elif now + timedelta(milliseconds=delay_ms) >= attempt.deadline:
            action, reason = RecoveryAction.STOP_RUN, RecoveryReason.DEADLINE_EXHAUSTED
        else:
            action, reason = RecoveryAction.RETRY, RecoveryReason.SAFE_TRANSIENT
    if action is RecoveryAction.RETRY:
        if not 0 <= delay_ms <= state.retry_policy.backoff_ceiling(attempt.number):
            raise ValueError("backoff exceeds policy")
    else:
        delay_ms = 0
    return RecoveryDecisionPayload(
        activity_id=attempt.activity_id,
        attempt_id=attempt.attempt_id,
        failure_event_id=attempt.terminal_event_id,
        based_on_sequence=state.last_sequence,
        contract_sha256=evidence.contract_sha256,
        action=action,
        reason=reason,
        delay_ms=delay_ms,
    )
