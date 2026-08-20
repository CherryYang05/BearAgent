"""Provider-neutral Run, Activity, and budget state contracts."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from bearagent.domain._base import DomainModel
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.ids import ActivityId, ModelCallId, RunId, SessionId, ToolCallId

MAX_MODEL_ITERATIONS = 100_000
MAX_TOKENS = 10_000_000_000
MAX_COST_MICROUSD = 1_000_000_000_000
MAX_MODEL_PRICING_RATE_MICROUSD = 1_000_000_000_000
MAX_CUMULATIVE_TOKENS = MAX_TOKENS * 2
MAX_CUMULATIVE_COST_MICROUSD = MAX_COST_MICROUSD + 2 * (
    (MAX_TOKENS * MAX_MODEL_PRICING_RATE_MICROUSD + 999_999) // 1_000_000
)
MAX_WALL_TIME_MS = 2_678_400_000  # 31 days
MAX_TOOL_CALLS = 1_000_000


class RunStatus(StrEnum):
    """P1-visible lifecycle states for one Run."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ActivityKind(StrEnum):
    """Kinds of serial operations tracked by the P1 reducer."""

    MODEL = "model"
    TOOL = "tool"


class ActivityStatus(StrEnum):
    """P1 Activity lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BudgetDimension(StrEnum):
    """Stable dimensions that can block a new Activity request."""

    MODEL_ITERATIONS = "model_iterations"
    TOKENS = "tokens"
    COST_MICROUSD = "cost_microusd"
    WALL_TIME_MS = "wall_time_ms"
    TOOL_CALLS = "tool_calls"


class BudgetLimits(DomainModel):
    """Finite limits selected by a trusted Run creation boundary."""

    max_model_iterations: int = Field(ge=0, le=MAX_MODEL_ITERATIONS, strict=True)
    max_tokens: int = Field(ge=0, le=MAX_TOKENS, strict=True)
    max_cost_microusd: int = Field(ge=0, le=MAX_COST_MICROUSD, strict=True)
    max_wall_time_ms: int = Field(ge=0, le=MAX_WALL_TIME_MS, strict=True)
    max_tool_calls: int = Field(ge=0, le=MAX_TOOL_CALLS, strict=True)


class BudgetUsage(DomainModel):
    """Actual usage derived only from accepted Run Events."""

    model_iterations: int = Field(default=0, ge=0, le=MAX_MODEL_ITERATIONS, strict=True)
    input_tokens: int = Field(default=0, ge=0, le=MAX_CUMULATIVE_TOKENS, strict=True)
    output_tokens: int = Field(default=0, ge=0, le=MAX_CUMULATIVE_TOKENS, strict=True)
    cost_microusd: int = Field(
        default=0,
        ge=0,
        le=MAX_CUMULATIVE_COST_MICROUSD,
        strict=True,
    )
    tool_calls: int = Field(default=0, ge=0, le=MAX_TOOL_CALLS, strict=True)

    @property
    def tokens(self) -> int:
        """Return provider-normalized input and output tokens together."""
        return self.input_tokens + self.output_tokens


class BudgetExhaustion(DomainModel):
    """A stable explanation for why another Activity cannot be requested."""

    dimension: BudgetDimension
    limit: int = Field(ge=0, strict=True)
    consumed: int = Field(ge=0, strict=True)
    requested: int = Field(default=0, ge=0, strict=True)

    def to_error_info(self) -> ErrorInfo:
        """Translate the decision into safe boundary data."""
        return ErrorInfo(
            category=ErrorCategory.BUDGET,
            code=ErrorCode.BUDGET_EXHAUSTED,
            message=f"Run budget exhausted: {self.dimension.value}.",
            retryable=False,
            details={
                "dimension": self.dimension.value,
                "limit": self.limit,
                "consumed": self.consumed,
                "requested": self.requested,
            },
        )


class ActivityState(DomainModel):
    """Immutable state for one model or Tool operation."""

    activity_id: ActivityId
    kind: ActivityKind
    status: ActivityStatus
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: ErrorInfo | None = None
    model_call_id: ModelCallId | None = None
    tool_call_id: ToolCallId | None = None
    tool_name: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")

    @field_validator("requested_at", "started_at", "completed_at")
    @classmethod
    def normalize_aware_times(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Activity times must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_kind_and_status_fields(self) -> Self:
        if self.kind is ActivityKind.MODEL:
            if self.model_call_id is None:
                raise ValueError("model Activity requires model_call_id")
            if self.tool_call_id is not None or self.tool_name is not None:
                raise ValueError("model Activity cannot contain Tool fields")
        else:
            if self.tool_call_id is None or self.tool_name is None:
                raise ValueError("Tool Activity requires tool_call_id and tool_name")
            if self.model_call_id is not None:
                raise ValueError("Tool Activity cannot contain model_call_id")

        if self.status is ActivityStatus.PENDING:
            if any(value is not None for value in (self.started_at, self.completed_at, self.error)):
                raise ValueError("pending Activity cannot contain terminal or started fields")
        elif self.status is ActivityStatus.RUNNING:
            if self.started_at is None or self.completed_at is not None or self.error is not None:
                raise ValueError("running Activity requires only started_at")
        elif self.status is ActivityStatus.SUCCEEDED:
            if self.started_at is None or self.completed_at is None or self.error is not None:
                raise ValueError("succeeded Activity requires start and completion without error")
        elif self.started_at is None or self.completed_at is None or self.error is None:
            raise ValueError("failed Activity requires start, completion, and error")
        return self


class RunState(DomainModel):
    """Immutable Run projection produced by the pure reducer."""

    run_id: RunId
    session_id: SessionId
    status: RunStatus
    budget_limits: BudgetLimits
    budget_usage: BudgetUsage = Field(default_factory=BudgetUsage)
    activities: tuple[ActivityState, ...] = ()
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    terminal_error: ErrorInfo | None = None
    last_sequence: int = Field(ge=1, strict=True)

    @field_validator("created_at", "started_at", "completed_at")
    @classmethod
    def normalize_aware_times(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Run times must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_consistent_projection(self) -> Self:
        active_count = sum(
            activity.status in {ActivityStatus.PENDING, ActivityStatus.RUNNING}
            for activity in self.activities
        )
        if active_count > 1:
            raise ValueError("Run may contain at most one active Activity")

        activity_ids = [activity.activity_id for activity in self.activities]
        model_call_ids = [
            activity.model_call_id
            for activity in self.activities
            if activity.model_call_id is not None
        ]
        tool_call_ids = [
            activity.tool_call_id
            for activity in self.activities
            if activity.tool_call_id is not None
        ]
        if len(activity_ids) != len(set(activity_ids)):
            raise ValueError("activity_id values must be unique within a Run")
        if len(model_call_ids) != len(set(model_call_ids)):
            raise ValueError("model_call_id values must be unique within a Run")
        if len(tool_call_ids) != len(set(tool_call_ids)):
            raise ValueError("tool_call_id values must be unique within a Run")

        if self.status is RunStatus.QUEUED:
            if self.activities or any(
                value is not None
                for value in (self.started_at, self.completed_at, self.terminal_error)
            ):
                raise ValueError("queued Run cannot contain execution or terminal fields")
        elif self.status is RunStatus.RUNNING:
            if (
                self.started_at is None
                or self.completed_at is not None
                or self.terminal_error is not None
            ):
                raise ValueError("running Run requires only started_at")
        elif self.status is RunStatus.SUCCEEDED:
            if (
                self.started_at is None
                or self.completed_at is None
                or self.terminal_error is not None
            ):
                raise ValueError("succeeded Run requires completion without terminal error")
            if active_count:
                raise ValueError("terminal Run cannot contain an active Activity")
        else:
            if self.started_at is None or self.completed_at is None or self.terminal_error is None:
                raise ValueError("failed Run requires completion and terminal error")
            if active_count:
                raise ValueError("terminal Run cannot contain an active Activity")
        return self
