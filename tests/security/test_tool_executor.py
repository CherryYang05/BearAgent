import asyncio

import pytest
from tests.tool_fixtures import build_tool_request, build_tool_spec

from bearagent.adapters.testing import FakeTool
from bearagent.domain.errors import ErrorCode
from bearagent.domain.tools import ToolResult, ToolSideEffect, ToolStatus
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry


def executor_for(tool: FakeTool) -> ToolExecutor:
    return ToolExecutor(
        ToolRegistry([tool]),
        FixedToolPolicy([tool.spec.name]),
    )


def test_prepare_failure_is_safe_and_prevents_execution() -> None:
    secret = "secret-api-key-value"
    tool = FakeTool(build_tool_spec(), prepare_error=ValueError(secret))

    result = asyncio.run(executor_for(tool).execute(build_tool_request()))

    assert tool.requests == []
    assert result.error is not None
    assert result.error.code is ErrorCode.TOOL_INVALID_INPUT
    assert secret not in result.model_dump_json()


def test_oversized_input_is_rejected_before_prepare() -> None:
    tool = FakeTool(
        build_tool_spec(max_input_bytes=20),
        data={"content": "not reached"},
    )

    result = asyncio.run(
        executor_for(tool).execute(build_tool_request(arguments={"path": "x" * 100}))
    )

    assert tool.prepare_requests == []
    assert tool.requests == []
    assert result.error is not None
    assert result.error.code is ErrorCode.TOOL_INVALID_INPUT


def test_replacing_tool_spec_after_registration_cannot_weaken_policy() -> None:
    tool = FakeTool(
        build_tool_spec(name="danger.run", side_effect=ToolSideEffect.CODE_EXECUTION),
        data={"content": "not reached"},
    )
    registry = ToolRegistry([tool])
    tool.spec = build_tool_spec(name="danger.run", side_effect=ToolSideEffect.READ_ONLY)
    executor = ToolExecutor(registry, FixedToolPolicy(["danger.run"]))

    result = asyncio.run(executor.execute(build_tool_request(name="danger.run")))

    assert tool.requests == []
    assert result.error is not None
    assert result.error.code is ErrorCode.TOOL_PERMISSION_DENIED


def test_timeout_calls_tool_once_and_does_not_retry() -> None:
    tool = FakeTool(
        build_tool_spec(timeout_ms=10),
        data={"content": "late"},
        delay_seconds=0.1,
    )

    result = asyncio.run(executor_for(tool).execute(build_tool_request()))

    assert len(tool.requests) == 1
    assert result.error is not None
    assert result.error.code is ErrorCode.TOOL_TIMEOUT
    assert result.error.retryable is False


def test_execute_exception_is_safe_and_not_retried() -> None:
    secret = "authorization-bearer-secret"
    tool = FakeTool(build_tool_spec(), execute_error=RuntimeError(secret))

    result = asyncio.run(executor_for(tool).execute(build_tool_request()))

    assert len(tool.requests) == 1
    assert result.error is not None
    assert result.error.code is ErrorCode.TOOL_ERROR
    assert secret not in result.model_dump_json()


def test_oversized_structured_result_fails_without_returning_partial_data() -> None:
    tool = FakeTool(
        build_tool_spec(max_output_bytes=20),
        data={"content": "x" * 100},
    )

    result = asyncio.run(executor_for(tool).execute(build_tool_request()))

    assert len(tool.requests) == 1
    assert result.status is ToolStatus.FAILED
    assert result.data == {}
    assert result.error is not None
    assert result.error.code is ErrorCode.TOOL_OUTPUT_TOO_LARGE


def test_caller_cancellation_propagates_without_a_fake_result() -> None:
    async def exercise() -> tuple[FakeTool, ToolResult | None]:
        tool = FakeTool(
            build_tool_spec(timeout_ms=5_000),
            data={"content": "late"},
            delay_seconds=10,
        )
        task = asyncio.create_task(executor_for(tool).execute(build_tool_request()))
        await asyncio.sleep(0)
        task.cancel()
        result: ToolResult | None = None
        with pytest.raises(asyncio.CancelledError):
            result = await task
        return tool, result

    tool, result = asyncio.run(exercise())

    assert len(tool.requests) == 1
    assert result is None
