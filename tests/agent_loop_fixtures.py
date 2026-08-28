from datetime import UTC, datetime, timedelta

from bearagent.adapters.testing import FakeTool
from bearagent.domain.agent import AgentConfig, AgentSettings, ModelPricing, RunInput
from bearagent.domain.fingerprints import RunFingerprint
from bearagent.domain.ids import SessionId
from bearagent.domain.model import ModelCompleted, ModelFinishReason, ModelUsage
from bearagent.domain.runs import BudgetLimits
from bearagent.domain.tools import ToolRetrySafety, ToolSideEffect, ToolSpec
from bearagent.runtime.fingerprints import build_run_fingerprint
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry

BASE_TIME = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)


class TickingClock:
    def __init__(self) -> None:
        self._ticks = 0

    def now(self) -> datetime:
        value = BASE_TIME + timedelta(milliseconds=self._ticks)
        self._ticks += 1
        return value


def read_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="workspace.read",
        spec_version="1",
        description="Read one workspace text file.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        output_schema={"type": "object"},
        side_effect=ToolSideEffect.READ_ONLY,
        timeout_ms=1_000,
        max_input_bytes=1_024,
        max_output_bytes=4_096,
        retry_safety=ToolRetrySafety.SAFE,
    )


def agent_config() -> AgentConfig:
    return AgentConfig(
        agent_id="test-agent",
        agent_version="p1-v1",
        instructions="Use the workspace read Tool when needed.",
        model="test-model",
        prompt_version="prompt-p1-v1",
        context_version="context-p1-v1",
        max_output_tokens=512,
        model_timeout_ms=1_000,
        max_context_chars=100_000,
        max_tool_result_bytes=10_000,
        tool_names=("workspace.read",),
        pricing=ModelPricing(
            version="pricing-v1",
            input_microusd_per_million_tokens=2_000_000,
            output_microusd_per_million_tokens=8_000_000,
        ),
    )


def agent_settings() -> AgentSettings:
    return AgentSettings.model_validate(agent_config().model_dump(exclude={"model", "pricing"}))


def budget_limits(**overrides: int) -> BudgetLimits:
    values = {
        "max_model_iterations": 5,
        "max_tokens": 10_000,
        "max_cost_microusd": 1_000_000,
        "max_wall_time_ms": 60_000,
        "max_tool_calls": 5,
    }
    values.update(overrides)
    return BudgetLimits(**values)


def agent_run_input(**budget_overrides: int) -> RunInput:
    return RunInput(
        session_id=SessionId.new(),
        objective="Summarize docs/index.md.",
        budget_limits=budget_limits(**budget_overrides),
        agent_config=agent_config(),
    )


def tool_executor(tool: FakeTool | None = None) -> ToolExecutor:
    registered = (
        FakeTool(read_tool_spec(), data={"content": "default test content"})
        if tool is None
        else tool
    )
    return ToolExecutor(ToolRegistry([registered]), FixedToolPolicy(["workspace.read"]))


def run_fingerprint(
    specs: tuple[ToolSpec, ...] | None = None,
    *,
    allowed_tool_names: tuple[str, ...] = ("workspace.read",),
) -> RunFingerprint:
    """Build a deterministic trusted composition identity for AgentLoop tests."""
    policy = FixedToolPolicy(allowed_tool_names)
    return build_run_fingerprint(
        bearagent_version="0.1.0+test",
        policy=policy.fingerprint,
        tool_specs=(read_tool_spec(),) if specs is None else specs,
    )


def model_completed(
    reason: ModelFinishReason,
    *,
    input_tokens: int = 10,
    request_id: str = "response-1",
) -> ModelCompleted:
    return ModelCompleted(
        provider_request_id=request_id,
        model="test-model",
        finish_reason=reason,
        usage=ModelUsage(input_tokens=input_tokens, output_tokens=5),
    )
