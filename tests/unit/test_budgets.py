from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from bearagent.domain.errors import BearAgentError, ErrorCode
from bearagent.domain.ids import RunId, SessionId
from bearagent.domain.runs import (
    MAX_MODEL_ITERATIONS,
    ActivityKind,
    BudgetDimension,
    BudgetLimits,
    BudgetUsage,
    RunState,
    RunStatus,
)
from bearagent.runtime.budgets import check_activity_budget

STARTED_AT = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)


def limits(**overrides: int) -> BudgetLimits:
    values = {
        "max_model_iterations": 2,
        "max_tokens": 100,
        "max_cost_microusd": 100,
        "max_wall_time_ms": 1_000,
        "max_tool_calls": 2,
    }
    values.update(overrides)
    return BudgetLimits.model_validate(values)


def running_state(
    budget_limits: BudgetLimits | None = None,
    usage: BudgetUsage | None = None,
) -> RunState:
    return RunState(
        run_id=RunId.new(),
        session_id=SessionId.new(),
        status=RunStatus.RUNNING,
        budget_limits=budget_limits or limits(),
        budget_usage=usage or BudgetUsage(),
        created_at=STARTED_AT,
        started_at=STARTED_AT,
        last_sequence=2,
    )


def test_relevant_activity_counts_are_prospective_and_independent() -> None:
    state = running_state(
        limits(max_model_iterations=1, max_tool_calls=1),
        BudgetUsage(model_iterations=1),
    )

    model_result = check_activity_budget(
        state,
        ActivityKind.MODEL,
        STARTED_AT + timedelta(milliseconds=1),
    )
    tool_result = check_activity_budget(
        state,
        ActivityKind.TOOL,
        STARTED_AT + timedelta(milliseconds=1),
    )

    assert model_result is not None
    assert model_result.dimension is BudgetDimension.MODEL_ITERATIONS
    assert model_result.consumed == 1
    assert model_result.requested == 1
    assert tool_result is None


@pytest.mark.parametrize(
    ("budget_limits", "usage", "expected_dimension"),
    [
        (
            limits(max_tokens=10),
            BudgetUsage(input_tokens=7, output_tokens=3),
            BudgetDimension.TOKENS,
        ),
        (
            limits(max_cost_microusd=5),
            BudgetUsage(cost_microusd=5),
            BudgetDimension.COST_MICROUSD,
        ),
    ],
)
def test_token_and_cost_limits_block_both_activity_kinds(
    budget_limits: BudgetLimits,
    usage: BudgetUsage,
    expected_dimension: BudgetDimension,
) -> None:
    state = running_state(budget_limits, usage)

    for kind in ActivityKind:
        result = check_activity_budget(
            state,
            kind,
            STARTED_AT + timedelta(milliseconds=1),
        )
        assert result is not None
        assert result.dimension is expected_dimension


def test_deadline_uses_explicit_utc_time_and_exact_boundary() -> None:
    state = running_state(limits(max_wall_time_ms=1_000))

    before = check_activity_budget(
        state,
        ActivityKind.MODEL,
        STARTED_AT + timedelta(milliseconds=999),
    )
    at_deadline = check_activity_budget(
        state,
        ActivityKind.MODEL,
        STARTED_AT + timedelta(milliseconds=1_000),
    )

    assert before is None
    assert at_deadline is not None
    assert at_deadline.dimension is BudgetDimension.WALL_TIME_MS
    assert at_deadline.consumed == 1_000


def test_zero_limit_can_block_the_first_activity_deterministically() -> None:
    state = running_state(
        limits(
            max_model_iterations=0,
            max_tokens=0,
            max_cost_microusd=0,
            max_wall_time_ms=0,
            max_tool_calls=0,
        )
    )

    result = check_activity_budget(state, ActivityKind.MODEL, STARTED_AT)

    assert result is not None
    assert result.dimension is BudgetDimension.MODEL_ITERATIONS
    assert result.limit == 0
    assert result.requested == 1


def test_budget_exhaustion_translates_to_safe_stable_error() -> None:
    state = running_state(limits(max_tool_calls=0))
    result = check_activity_budget(state, ActivityKind.TOOL, STARTED_AT)

    assert result is not None
    info = result.to_error_info()
    assert info.code is ErrorCode.BUDGET_EXHAUSTED
    assert info.details == {
        "dimension": "tool_calls",
        "limit": 0,
        "consumed": 0,
        "requested": 1,
    }


def test_budget_check_rejects_non_running_or_invalid_times() -> None:
    queued = RunState(
        run_id=RunId.new(),
        session_id=SessionId.new(),
        status=RunStatus.QUEUED,
        budget_limits=limits(),
        created_at=STARTED_AT,
        last_sequence=1,
    )
    with pytest.raises(BearAgentError) as wrong_status:
        check_activity_budget(queued, ActivityKind.MODEL, STARTED_AT)
    assert wrong_status.value.info.code is ErrorCode.INVALID_STATE_TRANSITION

    state = running_state()
    with pytest.raises(BearAgentError, match="include a timezone"):
        check_activity_budget(state, ActivityKind.MODEL, datetime(2026, 8, 11, 8, 0))
    with pytest.raises(BearAgentError, match="cannot precede"):
        check_activity_budget(
            state,
            ActivityKind.MODEL,
            STARTED_AT - timedelta(milliseconds=1),
        )


def test_budget_limits_reject_negative_boolean_and_unsafe_large_values() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        limits(max_tokens=-1)
    with pytest.raises(ValidationError, match="valid integer"):
        BudgetLimits.model_validate(
            {
                "max_model_iterations": True,
                "max_tokens": 1,
                "max_cost_microusd": 1,
                "max_wall_time_ms": 1,
                "max_tool_calls": 1,
            }
        )
    with pytest.raises(ValidationError, match="less than or equal"):
        limits(max_model_iterations=MAX_MODEL_ITERATIONS + 1)
