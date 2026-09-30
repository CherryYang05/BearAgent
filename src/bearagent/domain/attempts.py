"""Versioned, immutable execution evidence; no evidence grants permission."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from bearagent.domain._base import DomainModel
from bearagent.domain.errors import ErrorCode, ErrorInfo
from bearagent.domain.fingerprints import SHA256_PATTERN
from bearagent.domain.ids import ActivityId, AttemptId, EventId
from bearagent.domain.messages import TOOL_NAME_PATTERN
from bearagent.domain.runs import ActivityKind, RunState
from bearagent.domain.tools import PolicyDecision, PreparedToolRequest


class RetryPolicy(DomainModel):
    version: Literal["bounded-retry-v1"] = "bounded-retry-v1"
    max_attempts: int = Field(default=1, ge=1, le=3, strict=True)
    initial_backoff_ms: int = Field(default=250, ge=1, le=5000, strict=True)
    max_backoff_ms: int = Field(default=2000, ge=1, le=5000, strict=True)

    @model_validator(mode="after")
    def ordered_delays(self) -> Self:
        if self.initial_backoff_ms > self.max_backoff_ms:
            raise ValueError("initial backoff exceeds maximum")
        return self

    def backoff_ceiling(self, retry_number: int) -> int:
        if not 1 <= retry_number < self.max_attempts:
            raise ValueError("retry number exceeds policy")
        return min(self.max_backoff_ms, self.initial_backoff_ms * 2 ** (retry_number - 1))

    def window_ms(self, timeout_ms: int) -> int:
        return self.max_attempts * timeout_ms + sum(
            self.backoff_ceiling(n) for n in range(1, self.max_attempts)
        )


class RecoverySemantics(StrEnum):
    READ_ONLY = "read_only"
    IDEMPOTENT = "idempotent"
    RECONCILABLE = "reconcilable"
    NON_IDEMPOTENT = "non_idempotent"


class FailureClass(StrEnum):
    INVALID_INPUT = "invalid_input"
    TRANSIENT_INFRASTRUCTURE = "transient_infrastructure"
    PERMANENT_FAILURE = "permanent_failure"
    PERMISSION_DENIED = "permission_denied"
    EFFECT_INDETERMINATE = "effect_indeterminate"


class ModelSubmission(StrEnum):
    NOT_SUBMITTED = "not_submitted"
    UNKNOWN = "unknown"


class ModelFailureEvidence(DomainModel):
    submission: ModelSubmission = ModelSubmission.UNKNOWN
    usage_known: bool = False

    @model_validator(mode="after")
    def unsubmitted_usage(self) -> Self:
        if self.submission is ModelSubmission.NOT_SUBMITTED and not self.usage_known:
            raise ValueError("unsubmitted request requires known zero usage")
        return self


class ToolRecoveryContract(DomainModel):
    name: str = Field(pattern=TOOL_NAME_PATTERN)
    spec_sha256: str = Field(pattern=SHA256_PATTERN)
    semantics: RecoverySemantics
    timeout_ms: int = Field(ge=1, le=600_000, strict=True)


class AttemptStatus(StrEnum):
    REQUESTED = "requested"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RecoveryAction(StrEnum):
    RETRY = "retry"
    RETURN_TO_MODEL = "return_to_model"
    STOP_RUN = "stop_run"


class RecoveryReason(StrEnum):
    SAFE_TRANSIENT = "safe_transient"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    DEADLINE_EXHAUSTED = "deadline_exhausted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EFFECT_INDETERMINATE = "effect_indeterminate"
    MODEL_SUBMISSION_UNKNOWN = "model_submission_unknown"
    NON_RETRYABLE = "non_retryable"
    CONTRACT_CHANGED = "contract_changed"


class AttemptRequestedPayload(DomainModel):
    activity_id: ActivityId
    attempt_id: AttemptId
    number: int = Field(ge=1, le=3, strict=True)
    request_event_id: EventId
    deadline: datetime
    prior_decision_id: EventId | None = None

    @field_validator("deadline")
    @classmethod
    def aware_deadline(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("deadline must be timezone-aware")
        return value.astimezone(UTC)


class AttemptStartedPayload(DomainModel):
    activity_id: ActivityId
    attempt_id: AttemptId
    prepared: PreparedToolRequest | None = None
    policy: PolicyDecision | None = None


class AttemptSucceededPayload(DomainModel):
    activity_id: ActivityId
    attempt_id: AttemptId
    outcome_sha256: str = Field(pattern=SHA256_PATTERN)
    input_tokens: int = Field(default=0, ge=0, strict=True)
    output_tokens: int = Field(default=0, ge=0, strict=True)
    cost_microusd: int = Field(default=0, ge=0, strict=True)


class AttemptFailedPayload(AttemptSucceededPayload):
    error: ErrorInfo
    failure_class: FailureClass
    reached_adapter: bool
    model_evidence: ModelFailureEvidence | None = None


class RecoveryDecisionPayload(DomainModel):
    activity_id: ActivityId
    attempt_id: AttemptId
    failure_event_id: EventId
    based_on_sequence: int = Field(ge=1, strict=True)
    policy_version: Literal["bounded-retry-v1"] = "bounded-retry-v1"
    contract_sha256: str = Field(pattern=SHA256_PATTERN)
    action: RecoveryAction
    reason: RecoveryReason
    delay_ms: int = Field(default=0, ge=0, le=5000, strict=True)
    supersedes_decision_id: EventId | None = None


class ActivityEvidence(DomainModel):
    activity_id: ActivityId
    request_event_id: EventId
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_sha256: str = Field(pattern=SHA256_PATTERN)
    semantics: RecoverySemantics
    timeout_ms: int = Field(ge=1, le=600_000, strict=True)


class AttemptState(AttemptRequestedPayload):
    requested_sequence: int = Field(ge=1, strict=True)
    requested_at: datetime
    status: AttemptStatus = AttemptStatus.REQUESTED
    started_at: datetime | None = None
    prepared_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    terminal_event_id: EventId | None = None
    completed_at: datetime | None = None
    outcome_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    error: ErrorInfo | None = None
    failure_class: FailureClass | None = None
    reached_adapter: bool = False
    model_evidence: ModelFailureEvidence | None = None
    input_tokens: int = Field(default=0, ge=0, strict=True)
    output_tokens: int = Field(default=0, ge=0, strict=True)
    cost_microusd: int = Field(default=0, ge=0, strict=True)

    @field_validator("requested_at", "started_at", "completed_at")
    @classmethod
    def aware_times(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            return cls.aware_deadline(value)
        return None

    @model_validator(mode="after")
    def consistent_attempt(self) -> Self:
        if self.requested_at >= self.deadline:
            raise ValueError("Attempt was requested after its deadline")
        if self.started_at is not None and not self.requested_at <= self.started_at < self.deadline:
            raise ValueError("invalid Attempt start time")
        if self.reached_adapter != (self.started_at is not None):
            raise ValueError("Attempt dispatch evidence disagrees")
        terminal = self.status in {AttemptStatus.SUCCEEDED, AttemptStatus.FAILED}
        if terminal != (
            self.completed_at is not None
            and self.terminal_event_id is not None
            and self.outcome_sha256 is not None
        ):
            raise ValueError("Attempt terminal evidence is incomplete")
        if not terminal and any(
            value is not None
            for value in (self.completed_at, self.terminal_event_id, self.outcome_sha256)
        ):
            raise ValueError("nonterminal Attempt has a result")
        if self.completed_at is not None and self.completed_at < (
            self.started_at or self.requested_at
        ):
            raise ValueError("Attempt completed before it began")
        failed = self.status is AttemptStatus.FAILED
        if failed != (self.error is not None and self.failure_class is not None):
            raise ValueError("Attempt failure evidence disagrees")
        if not failed and (
            self.error is not None
            or self.failure_class is not None
            or self.model_evidence is not None
        ):
            raise ValueError("nonfailed Attempt has failure evidence")
        if self.status is AttemptStatus.REQUESTED and self.started_at is not None:
            raise ValueError("requested Attempt already started")
        if (
            self.status in {AttemptStatus.STARTED, AttemptStatus.SUCCEEDED}
            and self.started_at is None
        ):
            raise ValueError("Attempt requires dispatch evidence")
        return self


class RecoveryDecision(RecoveryDecisionPayload):
    event_id: EventId
    sequence: int = Field(ge=1, strict=True)
    occurred_at: datetime


class RunStateV5(RunState):
    """v2 state format, kept separate so historical v1 hashes never change."""

    event_schema_version: Literal[5] = 5
    retry_policy: RetryPolicy
    recovery_contracts: tuple[ToolRecoveryContract, ...] = ()
    activity_evidence: tuple[ActivityEvidence, ...] = ()
    attempts: tuple[AttemptState, ...] = ()
    recovery_decisions: tuple[RecoveryDecision, ...] = ()
    last_occurred_at: datetime

    @model_validator(mode="after")
    def consistent_attempt_projection(self) -> Self:
        activity_by_id = {a.activity_id: a for a in self.activities}
        if len({str(a.attempt_id) for a in self.attempts}) != len(self.attempts):
            raise ValueError("duplicate Attempt identity")
        if len({str(d.event_id) for d in self.recovery_decisions}) != len(self.recovery_decisions):
            raise ValueError("duplicate recovery decision identity")
        counts: dict[ActivityId, int] = {}
        for attempt in self.attempts:
            counts[attempt.activity_id] = counts.get(attempt.activity_id, 0) + 1
            if (
                attempt.activity_id not in activity_by_id
                or attempt.number != counts[attempt.activity_id]
            ):
                raise ValueError("Attempt sequence or parent is invalid")
            if (
                attempt.number > self.retry_policy.max_attempts
                or attempt.requested_sequence > self.last_sequence
            ):
                raise ValueError("Attempt exceeds recorded bounds")
        if (
            sum(a.status in {AttemptStatus.REQUESTED, AttemptStatus.STARTED} for a in self.attempts)
            > 1
        ):
            raise ValueError("multiple active Attempts")
        usage = self.budget_usage
        for kind, total in (
            (ActivityKind.MODEL, usage.model_iterations),
            (ActivityKind.TOOL, usage.tool_calls),
        ):
            if sum(activity_by_id[a.activity_id].kind is kind for a in self.attempts) != total:
                raise ValueError("Attempt and budget counts disagree")
        for key in ("input_tokens", "output_tokens", "cost_microusd"):
            if sum(getattr(a, key) for a in self.attempts) != getattr(usage, key):
                raise ValueError("Attempt and known usage disagree")
        for decision in self.recovery_decisions:
            attempt = next((a for a in self.attempts if a.attempt_id == decision.attempt_id), None)
            if (
                attempt is None
                or attempt.activity_id != decision.activity_id
                or attempt.terminal_event_id != decision.failure_event_id
            ):
                raise ValueError("decision references invalid failure")
            if (
                decision.sequence != decision.based_on_sequence + 1
                or decision.sequence > self.last_sequence
            ):
                raise ValueError("decision sequence is invalid")
        return self


def classify_failure(
    code: ErrorCode, *, semantics: RecoverySemantics, reached_adapter: bool
) -> FailureClass:
    """Use stable codes and trusted execution facts, never error text or retryable."""
    if semantics is not RecoverySemantics.READ_ONLY and reached_adapter:
        return FailureClass.EFFECT_INDETERMINATE
    if code in {
        ErrorCode.INVALID_INPUT,
        ErrorCode.TOOL_INVALID_INPUT,
        ErrorCode.TOOL_NOT_FOUND,
        ErrorCode.PROVIDER_INVALID_REQUEST,
    }:
        return FailureClass.INVALID_INPUT
    if code in {
        ErrorCode.TOOL_PERMISSION_DENIED,
        ErrorCode.WORKSPACE_PATH_DENIED,
        ErrorCode.PROVIDER_PERMISSION_DENIED,
        ErrorCode.PROVIDER_AUTHENTICATION,
    }:
        return FailureClass.PERMISSION_DENIED
    if code in {
        ErrorCode.TOOL_TIMEOUT,
        ErrorCode.PROVIDER_TIMEOUT,
        ErrorCode.PROVIDER_RATE_LIMITED,
        ErrorCode.PROVIDER_UNAVAILABLE,
    }:
        return FailureClass.TRANSIENT_INFRASTRUCTURE
    return FailureClass.PERMANENT_FAILURE
