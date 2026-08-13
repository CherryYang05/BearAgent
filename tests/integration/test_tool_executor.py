import asyncio

from tests.tool_fixtures import build_tool_request, build_tool_spec

from bearagent.adapters.testing import FakeTool
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.tools import (
    PolicyDecision,
    PolicyOutcome,
    PolicyReason,
    PreparedToolRequest,
    ToolResult,
    ToolSpec,
    ToolStatus,
)
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry


class RecordingAllowPolicy:
    def __init__(self) -> None:
        self.requests: list[PreparedToolRequest] = []

    def evaluate(self, spec: ToolSpec, request: PreparedToolRequest) -> PolicyDecision:
        self.requests.append(request)
        return PolicyDecision(outcome=PolicyOutcome.ALLOW, reason=PolicyReason.ALLOWED)


def test_executor_prepares_before_policy_and_executes_once() -> None:
    async def exercise() -> tuple[ToolResult, FakeTool, RecordingAllowPolicy]:
        request = build_tool_request(arguments={"path": "docs/./index.md"})
        tool = FakeTool(
            build_tool_spec(),
            data={"content": "BearAgent"},
            prepared_arguments={"path": "docs/index.md"},
        )
        policy = RecordingAllowPolicy()
        executor = ToolExecutor(ToolRegistry([tool]), policy)

        result = await executor.execute(request)
        return result, tool, policy

    result, tool, policy = asyncio.run(exercise())

    assert result.status is ToolStatus.SUCCEEDED
    assert len(tool.prepare_requests) == 1
    assert len(tool.requests) == 1
    assert policy.requests == tool.requests
    assert policy.requests[0].arguments == {"path": "docs/index.md"}


def test_executor_rejects_unknown_tool_before_any_adapter_call() -> None:
    result = asyncio.run(
        ToolExecutor(ToolRegistry([]), FixedToolPolicy()).execute(build_tool_request())
    )

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code is ErrorCode.TOOL_NOT_FOUND


def test_executor_rejects_denied_tool_before_execute() -> None:
    async def exercise() -> tuple[ToolResult, FakeTool]:
        tool = FakeTool(build_tool_spec(), data={"content": "not reached"})
        executor = ToolExecutor(ToolRegistry([tool]), FixedToolPolicy())
        return await executor.execute(build_tool_request()), tool

    result, tool = asyncio.run(exercise())

    assert len(tool.prepare_requests) == 1
    assert tool.requests == []
    assert result.error is not None
    assert result.error.code is ErrorCode.TOOL_PERMISSION_DENIED
    assert result.error.details == {"policy_reason": "tool_not_allowed"}


def test_executor_preserves_valid_tool_failure() -> None:
    async def exercise() -> ToolResult:
        failure = ErrorInfo(
            category=ErrorCategory.TOOL,
            code=ErrorCode.TOOL_ERROR,
            message="Read failed safely.",
        )
        tool = FakeTool(build_tool_spec(), failure=failure)
        executor = ToolExecutor(
            ToolRegistry([tool]),
            FixedToolPolicy(["workspace.read"]),
        )
        return await executor.execute(build_tool_request())

    result = asyncio.run(exercise())

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.message == "Read failed safely."
