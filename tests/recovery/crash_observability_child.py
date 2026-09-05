"""Child process that terminates at one committed P1 crash boundary."""

import argparse
import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import NoReturn

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.adapters.tools.workspace_boundary import StagedWorkspaceOutput, WorkspaceBoundary
from bearagent.adapters.tools.workspace_write import WorkspaceWriteTool
from bearagent.application.agent_loop import AgentLoop
from bearagent.domain.agent import AgentConfig, ModelPricing, RunInput
from bearagent.domain.events import Event
from bearagent.domain.ids import RunId, SessionId, ToolCallId
from bearagent.domain.model import (
    ModelCompleted,
    ModelEvent,
    ModelFinishReason,
    ModelRequest,
    ModelToolCall,
    ModelUsage,
)
from bearagent.domain.runs import BudgetLimits, RunState
from bearagent.runtime.fingerprints import build_run_fingerprint
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry

CRASH_EXIT_CODE = 91
OUTPUT_PATH = "outputs/crash-evidence.txt"
OUTPUT_CONTENT = "committed before process termination\n"


class CrashAfterAppendStore:
    """Delegate durability, then terminate after one selected commit returns."""

    def __init__(
        self,
        inner: SqliteEventStore,
        *,
        event_type: str,
        crash_marker: Path,
    ) -> None:
        self._inner = inner
        self._event_type = event_type
        self._crash_marker = crash_marker

    async def append(self, event: Event) -> RunState:
        state = await self._inner.append(event)
        if event.event_type == self._event_type:
            _crash(self._crash_marker, event.event_type)
        return state

    async def list_events(
        self,
        run_id: RunId,
        *,
        after_sequence: int = 0,
        limit: int = 1_000,
    ) -> tuple[Event, ...]:
        return await self._inner.list_events(
            run_id,
            after_sequence=after_sequence,
            limit=limit,
        )

    async def get_run(self, run_id: RunId) -> RunState | None:
        return await self._inner.get_run(run_id)


class CrashBeforeReplaceBoundary(WorkspaceBoundary):
    """Terminate after staging but before the atomic target replacement."""

    def __init__(self, root: Path, crash_marker: Path) -> None:
        super().__init__(root)
        self._crash_marker = crash_marker

    def commit_output(self, staged: StagedWorkspaceOutput, *, deadline: float) -> None:
        del staged, deadline
        _crash(self._crash_marker, "before_replace")


class CrashAfterReplaceBoundary(WorkspaceBoundary):
    """Terminate immediately after the atomic target replacement returns."""

    def __init__(self, root: Path, crash_marker: Path) -> None:
        super().__init__(root)
        self._crash_marker = crash_marker

    def commit_output(self, staged: StagedWorkspaceOutput, *, deadline: float) -> None:
        super().commit_output(staged, deadline=deadline)
        _crash(self._crash_marker, "after_replace")


class MarkerModelProvider:
    """Emit one write request and record every externally observable invocation."""

    def __init__(self, call_marker: Path) -> None:
        self._call_marker = call_marker
        self._tool_call_id = ToolCallId.new()

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        del request
        _append_durable_line(self._call_marker, "model_call")
        yield ModelToolCall(
            tool_call_id=self._tool_call_id,
            provider_call_id="crash-observability-write",
            name="workspace.write",
            arguments={"path": OUTPUT_PATH, "content": OUTPUT_CONTENT},
        )
        yield ModelCompleted(
            provider_request_id="crash-observability-response",
            model="crash-test-model",
            finish_reason=ModelFinishReason.TOOL_CALLS,
            usage=ModelUsage(input_tokens=1, output_tokens=1),
        )


def _agent_config() -> AgentConfig:
    return AgentConfig(
        agent_id="crash-observability-agent",
        agent_version="p1-v1",
        instructions="Write the requested bounded output once.",
        model="crash-test-model",
        prompt_version="crash-prompt-v1",
        context_version="crash-context-v1",
        max_output_tokens=128,
        model_timeout_ms=5_000,
        max_context_chars=100_000,
        max_tool_result_bytes=10_000,
        tool_names=("workspace.write",),
        pricing=ModelPricing(
            version="crash-pricing-v1",
            input_microusd_per_million_tokens=0,
            output_microusd_per_million_tokens=0,
        ),
    )


async def _run(args: argparse.Namespace) -> None:
    workspace = Path(args.workspace)
    await asyncio.to_thread(workspace.mkdir, parents=True, exist_ok=True)
    database_path = Path(args.database)
    crash_marker = Path(args.crash_marker)
    model_calls = Path(args.model_calls)

    if args.point == "k3_before_replace":
        boundary: WorkspaceBoundary = CrashBeforeReplaceBoundary(workspace, crash_marker)
    elif args.point == "k4_after_replace":
        boundary = CrashAfterReplaceBoundary(workspace, crash_marker)
    else:
        boundary = WorkspaceBoundary(workspace)

    tool = WorkspaceWriteTool(boundary)
    registry = ToolRegistry((tool,))
    policy = FixedToolPolicy((tool.spec.name,))
    executor = ToolExecutor(registry, policy)
    durable_store = SqliteEventStore(database_path)
    await durable_store.initialize()
    crash_event_types = {
        "k1_after_tool_requested": "ToolCallRequested",
        "k2_after_tool_started": "ToolCallStarted",
        "k6_after_model_started": "ModelCallStarted",
    }
    event_type = crash_event_types.get(args.point)
    store = (
        durable_store
        if event_type is None
        else CrashAfterAppendStore(
            durable_store,
            event_type=event_type,
            crash_marker=crash_marker,
        )
    )
    loop = AgentLoop(
        model_provider=MarkerModelProvider(model_calls),
        event_store=store,
        tool_executor=executor,
        run_fingerprint=build_run_fingerprint(
            bearagent_version="0.1.0+crash-test",
            policy=policy.fingerprint,
            tool_specs=registry.specs,
        ),
    )
    await loop.run(
        RunInput(
            session_id=SessionId.new(),
            objective="Write one crash-observability output.",
            budget_limits=BudgetLimits(
                max_model_iterations=2,
                max_tokens=100,
                max_cost_microusd=1_000,
                max_wall_time_ms=30_000,
                max_tool_calls=1,
            ),
            agent_config=_agent_config(),
        ),
        run_id=RunId.parse(args.run_id),
    )
    raise AssertionError("selected crash boundary was not reached")


def _append_durable_line(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(value + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _crash(marker: Path, value: str) -> NoReturn:
    _append_durable_line(marker, value)
    os._exit(CRASH_EXIT_CODE)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--point",
        required=True,
        choices=(
            "k1_after_tool_requested",
            "k2_after_tool_started",
            "k3_before_replace",
            "k4_after_replace",
            "k6_after_model_started",
        ),
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--crash-marker", required=True)
    parser.add_argument("--model-calls", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(_run(_parse_args()))
