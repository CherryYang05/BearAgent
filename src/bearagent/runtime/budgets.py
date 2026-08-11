"""Pure budget decisions for requesting the next serial Activity."""

from datetime import UTC, datetime

from bearagent.domain.errors import BearAgentError, ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.runs import (
    ActivityKind,
    BudgetDimension,
    BudgetExhaustion,
    RunState,
    RunStatus,
)


def check_activity_budget(
    state: RunState,
    activity_kind: ActivityKind,
    occurred_at: datetime,
) -> BudgetExhaustion | None:
    """Return why a new Activity is blocked, or ``None`` when it may be requested."""
    if state.status is not RunStatus.RUNNING or state.started_at is None:
        raise BearAgentError(
            ErrorInfo(
                category=ErrorCategory.VALIDATION,
                code=ErrorCode.INVALID_STATE_TRANSITION,
                message="Budget can be checked only for a running Run.",
            )
        )
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise BearAgentError(
            ErrorInfo(
                category=ErrorCategory.VALIDATION,
                code=ErrorCode.INVALID_INPUT,
                message="Budget check time must include a timezone.",
            )
        )

    candidate_time = occurred_at.astimezone(UTC)
    if candidate_time < state.started_at:
        raise BearAgentError(
            ErrorInfo(
                category=ErrorCategory.VALIDATION,
                code=ErrorCode.INVALID_INPUT,
                message="Budget check time cannot precede Run start time.",
            )
        )

    limits = state.budget_limits
    usage = state.budget_usage
    if activity_kind is ActivityKind.MODEL:
        requested_iterations = usage.model_iterations + 1
        if requested_iterations > limits.max_model_iterations:
            return BudgetExhaustion(
                dimension=BudgetDimension.MODEL_ITERATIONS,
                limit=limits.max_model_iterations,
                consumed=usage.model_iterations,
                requested=1,
            )
    else:
        requested_calls = usage.tool_calls + 1
        if requested_calls > limits.max_tool_calls:
            return BudgetExhaustion(
                dimension=BudgetDimension.TOOL_CALLS,
                limit=limits.max_tool_calls,
                consumed=usage.tool_calls,
                requested=1,
            )

    if usage.tokens >= limits.max_tokens:
        return BudgetExhaustion(
            dimension=BudgetDimension.TOKENS,
            limit=limits.max_tokens,
            consumed=usage.tokens,
        )
    if usage.cost_microusd >= limits.max_cost_microusd:
        return BudgetExhaustion(
            dimension=BudgetDimension.COST_MICROUSD,
            limit=limits.max_cost_microusd,
            consumed=usage.cost_microusd,
        )

    elapsed = candidate_time - state.started_at
    elapsed_ms = elapsed.days * 86_400_000 + elapsed.seconds * 1_000 + elapsed.microseconds // 1_000
    if elapsed_ms >= limits.max_wall_time_ms:
        return BudgetExhaustion(
            dimension=BudgetDimension.WALL_TIME_MS,
            limit=limits.max_wall_time_ms,
            consumed=elapsed_ms,
        )
    return None
