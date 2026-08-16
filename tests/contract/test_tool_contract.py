import asyncio

from tests.tool_fixtures import build_tool_request, build_tool_spec

from bearagent.adapters.testing import FakeTool
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.tools import ToolStatus


def test_fake_tool_prepares_executes_and_records_one_request() -> None:
    async def exercise() -> None:
        request = build_tool_request(arguments={"path": "docs/./index.md"})
        tool = FakeTool(
            build_tool_spec(),
            data={"content": "BearAgent"},
            prepared_arguments={"path": "docs/index.md"},
        )

        prepared = tool.prepare(request)
        result = await tool.execute(prepared)

        assert tool.prepare_requests == [request]
        assert tool.requests == [prepared]
        assert prepared.arguments == {"path": "docs/index.md"}
        assert result.tool_call_id == request.tool_call_id
        assert result.status is ToolStatus.SUCCEEDED
        assert result.data == {"content": "BearAgent"}

    asyncio.run(exercise())


def test_fake_tool_returns_configured_safe_failure() -> None:
    async def exercise() -> None:
        failure = ErrorInfo(
            category=ErrorCategory.TOOL,
            code=ErrorCode.TOOL_ERROR,
            message="Test Tool failed.",
        )
        request = build_tool_request()
        tool = FakeTool(build_tool_spec(), failure=failure)

        result = await tool.execute(tool.prepare(request))

        assert result.status is ToolStatus.FAILED
        assert result.error == failure
        assert result.data == {}

    asyncio.run(exercise())
