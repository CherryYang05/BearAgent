import asyncio
from pathlib import Path

from bearagent.adapters.tools import build_workspace_read_tools, build_workspace_tools
from bearagent.domain.ids import ToolCallId
from bearagent.domain.tools import ToolRequest, ToolSideEffect, ToolStatus


def test_workspace_tool_specs_are_bounded_read_only_objects(tmp_path: Path) -> None:
    tools = build_workspace_read_tools(tmp_path)

    assert [tool.spec.name for tool in tools] == [
        "workspace.list",
        "workspace.read",
        "workspace.search",
    ]
    for tool in tools:
        assert tool.spec.side_effect is ToolSideEffect.READ_ONLY
        assert tool.spec.timeout_ms > 0
        assert tool.spec.max_input_bytes > 0
        assert tool.spec.max_output_bytes > 0
        assert tool.spec.input_schema["type"] == "object"
        assert tool.spec.output_schema["type"] == "object"


def test_each_workspace_tool_returns_correlated_result(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("BearAgent\n", encoding="utf-8")
    arguments_by_name = {
        "workspace.list": {"path": "."},
        "workspace.read": {"path": "readme.md"},
        "workspace.search": {"path": ".", "query": "BearAgent"},
    }

    async def exercise() -> None:
        for tool in build_workspace_read_tools(tmp_path):
            request = ToolRequest(
                tool_call_id=ToolCallId.new(),
                name=tool.spec.name,
                arguments=arguments_by_name[tool.spec.name],
            )
            result = await tool.execute(tool.prepare(request))
            assert result.tool_call_id == request.tool_call_id
            assert result.status is ToolStatus.SUCCEEDED

    asyncio.run(exercise())


def test_all_workspace_tool_specs_include_one_bounded_write(tmp_path: Path) -> None:
    tools = build_workspace_tools(tmp_path)

    assert [tool.spec.name for tool in tools] == [
        "workspace.list",
        "workspace.read",
        "workspace.search",
        "workspace.write",
    ]
    write_spec = tools[-1].spec
    assert write_spec.side_effect is ToolSideEffect.WORKSPACE_WRITE
    assert write_spec.retry_safety.value == "not_safe"
    assert write_spec.input_schema["type"] == "object"
    assert write_spec.output_schema["type"] == "object"
