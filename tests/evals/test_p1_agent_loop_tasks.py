import asyncio
import hashlib
import json
import shutil
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict
from tests.agent_loop_fixtures import TickingClock

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.adapters.testing import InMemoryEventStore, ScriptedFakeModelProvider
from bearagent.adapters.tools import build_workspace_tools
from bearagent.application.agent_loop import AgentLoop
from bearagent.bootstrap import build_run_query_service, build_run_services
from bearagent.domain.agent import AgentConfig, ModelPricing, RunInput, RunProfile, RunResult
from bearagent.domain.events import Event
from bearagent.domain.ids import SessionId, ToolCallId
from bearagent.domain.model import (
    ModelCompleted,
    ModelEvent,
    ModelFinishReason,
    ModelTextDelta,
    ModelToolCall,
    ModelUsage,
)
from bearagent.domain.run_events import (
    ToolCallRequestedPayloadV2,
    parse_run_event_payload,
)
from bearagent.domain.runs import BudgetLimits, RunStatus
from bearagent.ports.store import EventStore
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry

REPOSITORY_ROOT = Path(__file__).parents[2]
EVAL_ROOT = REPOSITORY_ROOT / "evals" / "p1"


class EvalTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    version: str
    objective: str
    workspace_fixture: str
    agent_config_version: str
    model_version: str
    prompt_version: str
    tool_version: str
    budget: "EvalBudget"
    expected_calls: tuple["ExpectedCall", ...]
    expected_event_types: tuple[str, ...]
    expected_terminal: Literal["succeeded", "budget_exhausted"]
    expected_artifact_path: str | None
    output_content: str | None


class EvalBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_model_iterations: int
    max_tokens: int
    max_cost_microusd: int
    max_wall_time_ms: int
    max_tool_calls: int


class ExpectedCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    arguments: dict[str, str]


class EvalSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    suite_id: str
    version: str
    tasks: tuple[EvalTask, ...]


def load_suite() -> EvalSuite:
    return EvalSuite.model_validate_json((EVAL_ROOT / "tasks.json").read_text(encoding="utf-8"))


TASKS = load_suite().tasks


def completion(index: int, reason: ModelFinishReason) -> ModelCompleted:
    return ModelCompleted(
        provider_request_id=f"eval-response-{index}",
        model="fake-p1-model",
        finish_reason=reason,
        usage=ModelUsage(input_tokens=10, output_tokens=5),
    )


def tool_round(
    index: int,
    calls: tuple[tuple[str, dict[str, str]], ...],
) -> tuple[ModelEvent, ...]:
    return (
        *(
            ModelToolCall(
                tool_call_id=ToolCallId.new(),
                provider_call_id=f"eval-call-{index}-{position}",
                name=name,
                arguments=arguments,
            )
            for position, (name, arguments) in enumerate(calls, start=1)
        ),
        completion(index, ModelFinishReason.TOOL_CALLS),
    )


def script_for(task: EvalTask) -> tuple[tuple[ModelEvent, ...], ...]:
    content = task.output_content
    if task.task_id == "single-document-intro":
        assert content is not None
        return (
            tool_round(1, (("workspace.read", {"path": "docs/intro.md"}),)),
            tool_round(
                2,
                (("workspace.write", {"path": "outputs/intro.md", "content": content}),),
            ),
            (ModelTextDelta(text="Introduction written."), completion(3, ModelFinishReason.STOP)),
        )
    if task.task_id == "multi-document-summary":
        assert content is not None
        return (
            tool_round(1, (("workspace.list", {"path": "docs"}),)),
            tool_round(
                2,
                (
                    ("workspace.read", {"path": "docs/a.md"}),
                    ("workspace.read", {"path": "docs/b.md"}),
                ),
            ),
            tool_round(
                3,
                (("workspace.write", {"path": "outputs/summary.md", "content": content}),),
            ),
            (ModelTextDelta(text="Summary written."), completion(4, ModelFinishReason.STOP)),
        )
    if task.task_id == "source-comparison":
        assert content is not None
        return (
            tool_round(
                1,
                (("workspace.search", {"path": "docs", "query": "Runtime"}),),
            ),
            tool_round(
                2,
                (
                    ("workspace.read", {"path": "docs/a.md"}),
                    ("workspace.read", {"path": "docs/b.md"}),
                ),
            ),
            tool_round(
                3,
                (
                    (
                        "workspace.write",
                        {"path": "outputs/comparison.md", "content": content},
                    ),
                ),
            ),
            (ModelTextDelta(text="Comparison written."), completion(4, ModelFinishReason.STOP)),
        )
    if task.task_id == "replace-existing-output":
        assert content is not None
        return (
            tool_round(
                1,
                (("workspace.write", {"path": "outputs/report.md", "content": content}),),
            ),
            (ModelTextDelta(text="Report replaced."), completion(2, ModelFinishReason.STOP)),
        )
    if task.task_id == "path-denied-low-budget":
        return (tool_round(1, (("workspace.read", {"path": "../secret.txt"}),)),)
    raise AssertionError(f"unsupported eval task: {task.task_id}")


def config_for(registry: ToolRegistry, task: EvalTask) -> AgentConfig:
    return AgentConfig(
        agent_id="p1-file-agent",
        agent_version=task.agent_config_version,
        instructions="Use only workspace Tools and write outputs only when requested.",
        model=task.model_version,
        prompt_version=task.prompt_version,
        context_version="eval-context-v1",
        max_output_tokens=1_024,
        model_timeout_ms=5_000,
        max_context_chars=524_288,
        max_tool_result_bytes=65_536,
        tool_names=tuple(spec.name for spec in registry.specs),
        pricing=ModelPricing(
            version="eval-pricing-v1",
            input_microusd_per_million_tokens=1_000,
            output_microusd_per_million_tokens=2_000,
        ),
    )


async def execute_task(
    task: EvalTask,
    workspace: Path,
    store: EventStore,
) -> tuple[ScriptedFakeModelProvider, RunResult, tuple[Event, ...]]:
    tools = build_workspace_tools(workspace)
    registry = ToolRegistry(tools)
    provider = ScriptedFakeModelProvider(script_for(task))
    loop = AgentLoop(
        model_provider=provider,
        event_store=store,
        tool_executor=ToolExecutor(
            registry,
            FixedToolPolicy(spec.name for spec in registry.specs),
        ),
        clock=TickingClock(),
    )
    result = await loop.run(
        RunInput(
            session_id=SessionId.new(),
            objective=task.objective,
            budget_limits=BudgetLimits.model_validate(task.budget.model_dump()),
            agent_config=config_for(registry, task),
        )
    )
    events = await store.list_events(result.run_id)
    return provider, result, events


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
@pytest.mark.parametrize("task", TASKS, ids=lambda task: task.task_id)
def test_p1_fixed_task_suite_reaches_5_of_5_on_both_stores(
    task: EvalTask,
    store_kind: str,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(EVAL_ROOT / "workspaces" / task.workspace_fixture, workspace)

    async def exercise() -> tuple[ScriptedFakeModelProvider, RunResult, tuple[Event, ...]]:
        if store_kind == "sqlite":
            sqlite_store = SqliteEventStore(tmp_path / "state.sqlite3")
            await sqlite_store.initialize()
            store: EventStore = sqlite_store
        else:
            store = InMemoryEventStore()
        return await execute_task(task, workspace, store)

    provider, result, events = asyncio.run(exercise())

    assert tuple(event.sequence for event in events) == tuple(range(1, len(events) + 1))
    assert tuple(event.event_type for event in events) == task.expected_event_types
    requested_calls = tuple(
        (payload.tool_name, dict(payload.request.arguments))
        for event in events
        if isinstance(payload := parse_run_event_payload(event), ToolCallRequestedPayloadV2)
    )
    assert requested_calls == tuple((call.name, call.arguments) for call in task.expected_calls)

    if task.expected_terminal == "succeeded":
        assert result.state.status is RunStatus.SUCCEEDED
        assert task.output_content is not None
        assert task.expected_artifact_path is not None
        assert (workspace / task.expected_artifact_path).read_text(
            encoding="utf-8"
        ) == task.output_content
        assert result.artifacts[-1].path == task.expected_artifact_path
        assert (
            result.artifacts[-1].sha256
            == hashlib.sha256(task.output_content.encode("utf-8")).hexdigest()
        )
    else:
        assert result.state.status is RunStatus.FAILED
        assert result.state.terminal_error is not None
        assert result.state.terminal_error.code.value == "budget_exhausted"
        assert result.artifacts == ()
        assert "ToolCallFailed" in tuple(event.event_type for event in events)

    assert len(provider.requests) == len(script_for(task))


@pytest.mark.parametrize("task", TASKS, ids=lambda task: f"production-{task.task_id}")
def test_p1_fixed_task_suite_reaches_5_of_5_through_production_composition(
    task: EvalTask,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(EVAL_ROOT / "workspaces" / task.workspace_fixture, workspace)
    registry = ToolRegistry(build_workspace_tools(workspace))
    profile = RunProfile(
        agent_config=config_for(registry, task),
        budget_limits=BudgetLimits.model_validate(task.budget.model_dump()),
    )
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json")),
        encoding="utf-8",
    )
    database_path = tmp_path / "state.sqlite3"
    provider = ScriptedFakeModelProvider(script_for(task))

    async def exercise() -> tuple[RunResult, tuple[Event, ...]]:
        services = await build_run_services(
            profile_path=profile_path,
            workspace_path=workspace,
            database_path=database_path,
            model_provider=provider,
        )
        result = await services.agent_loop.run(
            RunInput(
                session_id=SessionId.new(),
                objective=task.objective,
                budget_limits=services.profile.budget_limits,
                agent_config=services.profile.agent_config,
            )
        )
        reopened_queries = await build_run_query_service(database_path)
        inspection = await reopened_queries.inspect(result.run_id)
        page = await reopened_queries.events(result.run_id)
        assert inspection.state == result.state
        assert inspection.artifacts == result.artifacts
        return result, page.events

    result, events = asyncio.run(exercise())

    assert tuple(event.event_type for event in events) == task.expected_event_types
    requested_calls = tuple(
        (payload.tool_name, dict(payload.request.arguments))
        for event in events
        if isinstance(payload := parse_run_event_payload(event), ToolCallRequestedPayloadV2)
    )
    assert requested_calls == tuple((call.name, call.arguments) for call in task.expected_calls)
    if task.expected_terminal == "succeeded":
        assert result.state.status is RunStatus.SUCCEEDED
        assert task.output_content is not None
        assert task.expected_artifact_path is not None
        assert (workspace / task.expected_artifact_path).read_text(
            encoding="utf-8"
        ) == task.output_content
        assert (
            result.artifacts[-1].sha256
            == hashlib.sha256(task.output_content.encode("utf-8")).hexdigest()
        )
    else:
        assert result.state.status is RunStatus.FAILED
        assert result.state.terminal_error is not None
        assert result.state.terminal_error.code.value == "budget_exhausted"
    assert len(provider.requests) == len(script_for(task))
