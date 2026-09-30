"""Content-free, versioned inspection of recorded execution attempts."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from bearagent.domain._base import DomainModel
from bearagent.domain.attempts import (
    AttemptStatus,
    FailureClass,
    ModelFailureEvidence,
    RecoveryDecision,
)
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import ActivityId, AttemptId, RunId
from bearagent.domain.replay import ProjectionComparison


class AttemptSummary(DomainModel):
    activity_id: ActivityId
    attempt_id: AttemptId
    number: int = Field(ge=1, le=3)
    requested_sequence: int = Field(ge=1)
    status: AttemptStatus
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    deadline: datetime
    reached_adapter: bool
    failure_class: FailureClass | None
    error_code: ErrorCode | None
    model_evidence: ModelFailureEvidence | None
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_microusd: int = Field(ge=0)
    decisions: tuple[RecoveryDecision, ...] = ()


class AttemptPage(DomainModel):
    run_id: RunId
    recording: Literal["recorded", "legacy_not_recorded"]
    last_sequence: int = Field(ge=1)
    projection: ProjectionComparison
    after_sequence: int = Field(ge=0)
    limit: int = Field(ge=1, le=1000)
    attempts: tuple[AttemptSummary, ...] = Field(max_length=1000)
    next_after_sequence: int = Field(ge=0)
    has_more: bool
