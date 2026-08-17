import asyncio
from collections.abc import Mapping
from pathlib import Path

from bearagent.adapters.tools import build_workspace_read_tools, build_workspace_tools
from bearagent.domain.ids import ToolCallId
from bearagent.domain.tools import (
    PolicyDecision,
    PreparedToolRequest,
    ToolRequest,
    ToolSpec,
    ToolStatus,
)
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry


class RecordingFixedPolicy:
    def __init__(self, allowed_names: list[str]) -> None:
        self._delegate = FixedToolPolicy(allowed_names)
        self.requests: list[PreparedToolRequest] = []

    def evaluate(self, spec: ToolSpec, request: PreparedToolRequest) -> PolicyDecision:
        self.requests.append(request)
        return self._delegate.evaluate(spec, request)


def test_executor_runs_all_workspace_tools_through_one_boundary(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("BearAgent guide\n", encoding="utf-8")
    tools = build_workspace_read_tools(tmp_path)
    registry = ToolRegistry(tools)
    policy = RecordingFixedPolicy([spec.name for spec in registry.specs])
    executor = ToolExecutor(registry, policy)

    async def exercise() -> None:
        requests = (
            ToolRequest(
                tool_call_id=ToolCallId.new(),
                name="workspace.list",
                arguments={"path": r".\docs"},
            ),
            ToolRequest(
                tool_call_id=ToolCallId.new(),
                name="workspace.read",
                arguments={"path": r"docs\guide.md"},
            ),
            ToolRequest(
                tool_call_id=ToolCallId.new(),
                name="workspace.search",
                arguments={"path": "docs", "query": "BearAgent"},
            ),
        )
        results = [await executor.execute(request) for request in requests]
        assert all(result.status is ToolStatus.SUCCEEDED for result in results)
        assert [result.data["path"] for result in results] == [
            "docs",
            "docs/guide.md",
            "docs",
        ]
        assert [request.arguments["path"] for request in policy.requests] == [
            "docs",
            "docs/guide.md",
            "docs",
        ]

    asyncio.run(exercise())


def test_executor_default_policy_denies_before_workspace_execute(tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    tools = build_workspace_read_tools(tmp_path)
    executor = ToolExecutor(ToolRegistry(tools), FixedToolPolicy())
    request = ToolRequest(
        tool_call_id=ToolCallId.new(),
        name="workspace.read",
        arguments={"path": "secret.txt"},
    )

    result = asyncio.run(executor.execute(request))

    assert result.status is ToolStatus.FAILED
    assert "secret" not in result.model_dump_json()


def test_executor_writes_then_reads_one_complete_artifact(tmp_path: Path) -> None:
    tools = build_workspace_tools(tmp_path)
    registry = ToolRegistry(tools)
    policy = RecordingFixedPolicy([spec.name for spec in registry.specs])
    executor = ToolExecutor(registry, policy)

    async def exercise() -> None:
        write = await executor.execute(
            ToolRequest(
                tool_call_id=ToolCallId.new(),
                name="workspace.write",
                arguments={
                    "path": r"outputs\reports\intro.md",
                    "content": "# BearAgent\n完整结果。\n",
                },
            )
        )
        read = await executor.execute(
            ToolRequest(
                tool_call_id=ToolCallId.new(),
                name="workspace.read",
                arguments={"path": "outputs/reports/intro.md"},
            )
        )

        assert write.status is ToolStatus.SUCCEEDED
        assert read.status is ToolStatus.SUCCEEDED
        assert read.data["text"] == "# BearAgent\n完整结果。\n"
        assert policy.requests[-2].arguments["path"] == "outputs/reports/intro.md"
        artifact = write.data["artifact"]
        assert isinstance(artifact, Mapping)
        assert artifact["path"] == "outputs/reports/intro.md"

    asyncio.run(exercise())
