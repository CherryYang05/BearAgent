"""v5 Attempt transitions; logical Run/Activity rules are shared with the legacy reducer."""

from collections.abc import Callable
from datetime import timedelta

from bearagent.domain.attempts import (
    ActivityEvidence,
    AttemptFailedPayload,
    AttemptRequestedPayload,
    AttemptStartedPayload,
    AttemptState,
    AttemptStatus,
    AttemptSucceededPayload,
    ModelSubmission,
    RecoveryAction,
    RecoveryDecision,
    RecoveryDecisionPayload,
    RecoverySemantics,
    RunStateV5,
    classify_failure,
)
from bearagent.domain.events import Event
from bearagent.domain.run_events import (
    ModelCallCompletedPayloadV2,
    ModelCallFailedPayloadV2,
    ModelCallRequestedPayloadV2,
    RunCreatedPayloadV5,
    ToolCallCompletedPayloadV2,
    ToolCallFailedPayloadV2,
    ToolCallRequestedPayloadV2,
    parse_run_event_payload,
)
from bearagent.domain.runs import ActivityKind, ActivityStatus, BudgetUsage, RunState, RunStatus
from bearagent.domain.tools import PolicyOutcome
from bearagent.runtime.attempts import (
    activity_deadline,
    check_dispatch_budget,
    decide_recovery,
    evidence_hash,
)
from bearagent.runtime.budgets import check_activity_budget


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("inconsistent Attempt transition")


def _replace(state: RunStateV5, event: Event, **changes: object) -> RunStateV5:
    values = {name: getattr(state, name) for name in RunStateV5.model_fields}
    values.update(changes, last_sequence=event.sequence, last_occurred_at=event.occurred_at)
    return RunStateV5.model_validate(values)


def reduce_attempt_event(
    prior: RunState | None,
    event: Event,
    *,
    apply_logical: Callable[[RunState | None, Event], RunState],
) -> RunStateV5:
    _require(event.schema_version == 5)
    payload = parse_run_event_payload(event)
    if prior is None:
        _require(isinstance(payload, RunCreatedPayloadV5))
        if not isinstance(payload, RunCreatedPayloadV5):
            raise ValueError("first Event is not v5 RunCreated")
        base = apply_logical(None, event)
        return RunStateV5(
            **base.model_dump(),
            retry_policy=payload.retry_policy,
            recovery_contracts=payload.recovery_contracts,
            last_occurred_at=event.occurred_at,
        )
    if not isinstance(prior, RunStateV5):
        raise ValueError("cannot mix historical and Attempt semantics")
    state = prior
    _require(event.run_id == state.run_id and event.sequence == state.last_sequence + 1)
    _require(event.occurred_at >= state.last_occurred_at)
    _require(state.status not in {RunStatus.FAILED, RunStatus.SUCCEEDED})

    if isinstance(payload, ModelCallRequestedPayloadV2 | ToolCallRequestedPayloadV2):
        if state.recovery_decisions:
            _require(state.recovery_decisions[-1].action is not RecoveryAction.STOP_RUN)
        logical = apply_logical(state, event)
        if isinstance(payload, ModelCallRequestedPayloadV2):
            evidence = ActivityEvidence(
                activity_id=payload.activity_id,
                request_event_id=event.event_id,
                request_sha256=evidence_hash(payload.request),
                contract_sha256=evidence_hash(payload.request),
                semantics=RecoverySemantics.READ_ONLY,
                timeout_ms=payload.request.timeout_ms,
            )
        else:
            contract = next(
                (c for c in state.recovery_contracts if c.name == payload.tool_name), None
            )
            # Unknown names still receive a denied Attempt through the Executor.
            evidence = ActivityEvidence(
                activity_id=payload.activity_id,
                request_event_id=event.event_id,
                request_sha256=evidence_hash(payload.request),
                contract_sha256=evidence_hash(contract)
                if contract
                else evidence_hash(payload.request),
                semantics=contract.semantics if contract else RecoverySemantics.NON_IDEMPOTENT,
                timeout_ms=contract.timeout_ms if contract else 1000,
            )
        if not isinstance(logical, RunStateV5):
            raise ValueError("logical transition lost state version")
        return _replace(logical, event, activity_evidence=(*state.activity_evidence, evidence))

    if isinstance(
        payload,
        AttemptRequestedPayload
        | AttemptStartedPayload
        | AttemptSucceededPayload
        | RecoveryDecisionPayload,
    ):
        _require(state.status is RunStatus.RUNNING)
        activity = next((a for a in state.activities if a.activity_id == payload.activity_id), None)
        _require(activity is not None and activity.status is ActivityStatus.RUNNING)
        if activity is None:
            raise ValueError("Attempt has no Activity")
        evidence = next(e for e in state.activity_evidence if e.activity_id == activity.activity_id)
        attempts = tuple(a for a in state.attempts if a.activity_id == activity.activity_id)
        attempt = attempts[-1] if attempts else None

        if isinstance(payload, AttemptRequestedPayload):
            _require(payload.number == len(attempts) + 1 <= state.retry_policy.max_attempts)
            _require(all(a.attempt_id != payload.attempt_id for a in state.attempts))
            _require(payload.request_event_id == evidence.request_event_id)
            _require(payload.deadline == activity_deadline(state, evidence))
            _require(event.occurred_at < payload.deadline)
            _require(check_activity_budget(state, activity.kind, event.occurred_at) is None)
            if attempt is None:
                _require(payload.prior_decision_id is None)
            else:
                _require(attempt.status is AttemptStatus.FAILED and bool(state.recovery_decisions))
                decision = state.recovery_decisions[-1]
                _require(
                    decision.attempt_id == attempt.attempt_id
                    and decision.action is RecoveryAction.RETRY
                )
                _require(payload.prior_decision_id == decision.event_id)
                _require(
                    event.occurred_at
                    >= decision.occurred_at + timedelta(milliseconds=decision.delay_ms)
                )
                # Re-evaluate after backoff: facts/clock/budget may have changed.
                _require(
                    decide_recovery(state, attempt, now=event.occurred_at).action
                    is RecoveryAction.RETRY
                )
            usage = state.budget_usage.model_dump()
            key = "model_iterations" if activity.kind is ActivityKind.MODEL else "tool_calls"
            usage[key] += 1
            created = AttemptState(
                **payload.model_dump(),
                requested_sequence=event.sequence,
                requested_at=event.occurred_at,
            )
            return _replace(
                state, event, attempts=(*state.attempts, created), budget_usage=BudgetUsage(**usage)
            )

        _require(attempt is not None and attempt.attempt_id == payload.attempt_id)
        if attempt is None:
            raise ValueError("Attempt not found")
        if isinstance(payload, RecoveryDecisionPayload):
            _require(attempt.status is AttemptStatus.FAILED)
            decisions = tuple(
                d for d in state.recovery_decisions if d.attempt_id == attempt.attempt_id
            )
            if decisions:
                _require(decisions[-1].action is RecoveryAction.RETRY)
                _require(payload.supersedes_decision_id == decisions[-1].event_id)
                _require(payload.action is RecoveryAction.STOP_RUN)
            else:
                _require(payload.supersedes_decision_id is None)
            expected = decide_recovery(
                state, attempt, now=event.occurred_at, delay_ms=payload.delay_ms
            )
            _require(
                payload.model_dump(exclude={"supersedes_decision_id"})
                == expected.model_dump(exclude={"supersedes_decision_id"})
            )
            decision = RecoveryDecision(
                **payload.model_dump(),
                event_id=event.event_id,
                sequence=event.sequence,
                occurred_at=event.occurred_at,
            )
            return _replace(state, event, recovery_decisions=(*state.recovery_decisions, decision))

        values = attempt.model_dump()
        if isinstance(payload, AttemptStartedPayload):
            _require(
                attempt.status is AttemptStatus.REQUESTED and event.occurred_at < attempt.deadline
            )
            _require(check_dispatch_budget(state, activity.kind, event.occurred_at) is None)
            if activity.kind is ActivityKind.TOOL:
                _require(payload.prepared is not None and payload.policy is not None)
                if payload.prepared is None or payload.policy is None:
                    raise ValueError("Tool start requires Policy and normalized request")
                _require(payload.policy.outcome is PolicyOutcome.ALLOW)
                _require(
                    payload.prepared.name == activity.tool_name
                    and payload.prepared.tool_call_id == activity.tool_call_id
                )
                prepared_hash = evidence_hash(payload.prepared)
                previous_hash = next(
                    (a.prepared_sha256 for a in attempts if a.prepared_sha256 is not None), None
                )
                _require(previous_hash is None or previous_hash == prepared_hash)
                values["prepared_sha256"] = prepared_hash
            else:
                _require(payload.prepared is None and payload.policy is None)
            values.update(
                status=AttemptStatus.STARTED, started_at=event.occurred_at, reached_adapter=True
            )
            return _replace_attempt(state, event, AttemptState.model_validate(values))

        _require(attempt.status in {AttemptStatus.REQUESTED, AttemptStatus.STARTED})
        if isinstance(payload, AttemptFailedPayload):
            _require(payload.reached_adapter == (attempt.status is AttemptStatus.STARTED))
            _require(
                payload.failure_class
                == classify_failure(
                    payload.error.code,
                    semantics=evidence.semantics,
                    reached_adapter=payload.reached_adapter,
                )
            )
            if activity.kind is ActivityKind.MODEL:
                _require(payload.model_evidence is not None)
                if (
                    payload.model_evidence
                    and payload.model_evidence.submission is ModelSubmission.NOT_SUBMITTED
                ):
                    _require(
                        payload.input_tokens == payload.output_tokens == payload.cost_microusd == 0
                    )
            else:
                _require(payload.model_evidence is None)
            values.update(
                status=AttemptStatus.FAILED,
                error=payload.error,
                failure_class=payload.failure_class,
                model_evidence=payload.model_evidence,
            )
        else:
            _require(attempt.status is AttemptStatus.STARTED)
            values["status"] = AttemptStatus.SUCCEEDED
        if activity.kind is ActivityKind.TOOL:
            _require(payload.input_tokens == payload.output_tokens == payload.cost_microusd == 0)
        values.update(
            completed_at=event.occurred_at,
            terminal_event_id=event.event_id,
            outcome_sha256=payload.outcome_sha256,
            input_tokens=payload.input_tokens,
            output_tokens=payload.output_tokens,
            cost_microusd=payload.cost_microusd,
        )
        usage = state.budget_usage.model_dump()
        for key in ("input_tokens", "output_tokens", "cost_microusd"):
            usage[key] += getattr(payload, key)
        return _replace_attempt(
            state, event, AttemptState.model_validate(values), budget_usage=BudgetUsage(**usage)
        )

    if isinstance(
        payload,
        ModelCallCompletedPayloadV2
        | ModelCallFailedPayloadV2
        | ToolCallCompletedPayloadV2
        | ToolCallFailedPayloadV2,
    ):
        attempts = tuple(a for a in state.attempts if a.activity_id == payload.activity_id)
        _require(bool(attempts))
        attempt = attempts[-1]
        failed = isinstance(payload, ModelCallFailedPayloadV2 | ToolCallFailedPayloadV2)
        _require(attempt.status is (AttemptStatus.FAILED if failed else AttemptStatus.SUCCEEDED))
        _require(attempt.outcome_sha256 == evidence_hash(payload))
        if failed:
            _require(bool(state.recovery_decisions))
            decision = state.recovery_decisions[-1]
            _require(
                decision.attempt_id == attempt.attempt_id
                and decision.action is not RecoveryAction.RETRY
            )
        if isinstance(payload, ToolCallCompletedPayloadV2 | ToolCallFailedPayloadV2):
            evidence = next(
                e for e in state.activity_evidence if e.activity_id == payload.activity_id
            )
            _require(evidence_hash(payload.execution.request) == evidence.request_sha256)
            _require(payload.execution.reached_adapter == attempt.reached_adapter)
            if (
                payload.execution.prepared_request is not None
                and attempt.prepared_sha256 is not None
            ):
                _require(
                    evidence_hash(payload.execution.prepared_request) == attempt.prepared_sha256
                )
        else:
            _require(
                (payload.input_tokens, payload.output_tokens, payload.cost_microusd)
                == (attempt.input_tokens, attempt.output_tokens, attempt.cost_microusd)
            )
    if event.event_type == "RunSucceeded" and state.recovery_decisions:
        _require(state.recovery_decisions[-1].action is not RecoveryAction.STOP_RUN)
    logical = apply_logical(state, event)
    if not isinstance(logical, RunStateV5):
        raise ValueError("logical transition lost state version")
    return _replace(logical, event)


def _replace_attempt(
    state: RunStateV5, event: Event, attempt: AttemptState, **changes: object
) -> RunStateV5:
    return _replace(
        state,
        event,
        attempts=tuple(
            attempt if a.attempt_id == attempt.attempt_id else a for a in state.attempts
        ),
        **changes,
    )
