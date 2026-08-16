from types import SimpleNamespace
from typing import cast

import pytest
from tests.tool_fixtures import build_tool_spec

from bearagent.domain.tools import ToolSideEffect
from bearagent.ports.tools import Tool
from bearagent.runtime.tool_registry import ToolRegistry


def stub_tool(name: str) -> Tool:
    return cast(Tool, SimpleNamespace(spec=build_tool_spec(name=name)))


def test_registry_resolves_exact_names_in_stable_order() -> None:
    search = stub_tool("workspace.search")
    read = stub_tool("workspace.read")

    registry = ToolRegistry([search, read])

    assert [spec.name for spec in registry.specs] == ["workspace.read", "workspace.search"]
    assert registry.get("workspace.read") is read
    assert registry.get("Workspace.Read") is None
    assert registry.get("workspace") is None


def test_registry_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError, match="duplicate Tool name: workspace.read"):
        ToolRegistry([stub_tool("workspace.read"), stub_tool("workspace.read")])


def test_registry_snapshots_the_input_collection() -> None:
    tools = [stub_tool("workspace.read")]
    registry = ToolRegistry(tools)

    tools.clear()

    assert registry.get("workspace.read") is not None
    assert len(registry.specs) == 1


def test_registry_snapshots_trusted_spec_before_tool_can_replace_it() -> None:
    tool = stub_tool("danger.run")
    tool.spec = build_tool_spec(
        name="danger.run",
        side_effect=ToolSideEffect.CODE_EXECUTION,
    )
    registry = ToolRegistry([tool])

    tool.spec = build_tool_spec(name="danger.run", side_effect=ToolSideEffect.READ_ONLY)

    registered_spec = registry.get_spec("danger.run")
    assert registered_spec is not None
    assert registered_spec.side_effect is ToolSideEffect.CODE_EXECUTION
