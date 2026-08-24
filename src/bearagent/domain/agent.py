"""Versioned Agent configuration and application boundary data."""

from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from bearagent.domain._base import DomainModel
from bearagent.domain.artifacts import Artifact
from bearagent.domain.ids import RunId, SessionId, ToolCallId
from bearagent.domain.messages import TOOL_NAME_PATTERN
from bearagent.domain.model import (
    MAX_MODEL_INPUT_CHARS,
    MAX_MODEL_OUTPUT_CHARS,
    MAX_MODEL_TIMEOUT_MS,
    MODEL_NAME_PATTERN,
    PROMPT_VERSION_PATTERN,
    ModelRequest,
)
from bearagent.domain.providers import PROVIDER_ID_PATTERN
from bearagent.domain.runs import (
    MAX_MODEL_PRICING_RATE_MICROUSD,
    MAX_TOKENS,
    BudgetLimits,
    RunState,
    RunStatus,
)

AGENT_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9._-]{0,127}$"
MAX_AGENT_INSTRUCTIONS_CHARS = 65_536
MAX_OBJECTIVE_CHARS = 1_000_000
MAX_CONTEXT_REPORT_SEQUENCES = 10_000


class ModelPricing(DomainModel):
    """Versioned integer rates used for deterministic local cost estimates."""

    version: str = Field(pattern=PROMPT_VERSION_PATTERN)
    input_microusd_per_million_tokens: int = Field(
        ge=0,
        le=MAX_MODEL_PRICING_RATE_MICROUSD,
        strict=True,
    )
    output_microusd_per_million_tokens: int = Field(
        ge=0,
        le=MAX_MODEL_PRICING_RATE_MICROUSD,
        strict=True,
    )


class AgentSettings(DomainModel):
    """User-editable Agent behavior without Provider-owned model fields."""

    agent_id: str = Field(pattern=AGENT_ID_PATTERN)
    agent_version: str = Field(pattern=PROMPT_VERSION_PATTERN)
    instructions: str = Field(min_length=1, max_length=MAX_AGENT_INSTRUCTIONS_CHARS)
    prompt_version: str = Field(pattern=PROMPT_VERSION_PATTERN)
    context_version: str = Field(pattern=PROMPT_VERSION_PATTERN)
    max_output_tokens: int = Field(gt=0, le=MAX_TOKENS, strict=True)
    model_timeout_ms: int = Field(gt=0, le=MAX_MODEL_TIMEOUT_MS, strict=True)
    max_context_chars: int = Field(gt=0, le=MAX_MODEL_INPUT_CHARS, strict=True)
    max_tool_result_bytes: int = Field(ge=128, le=MAX_MODEL_OUTPUT_CHARS, strict=True)
    tool_names: tuple[str, ...] = Field(default=(), max_length=128)

    @field_validator("instructions")
    @classmethod
    def reject_blank_instructions(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("instructions must not be blank")
        return value

    @field_validator("tool_names")
    @classmethod
    def require_stable_unique_tool_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        import re

        if any(re.fullmatch(TOOL_NAME_PATTERN, name) is None for name in value):
            raise ValueError("tool_names contains an invalid Tool name")
        if len(value) != len(set(value)):
            raise ValueError("tool_names must be unique")
        if value != tuple(sorted(value)):
            raise ValueError("tool_names must be sorted")
        return tuple(value)

    @model_validator(mode="after")
    def require_result_preview_to_fit_context(self) -> Self:
        if self.max_tool_result_bytes > self.max_context_chars:
            raise ValueError("max_tool_result_bytes cannot exceed max_context_chars")
        return self


class AgentConfig(AgentSettings):
    """Resolved non-secret Agent snapshot persisted for one Run."""

    model: str = Field(pattern=MODEL_NAME_PATTERN)
    pricing: ModelPricing


class ContextBuildReport(DomainModel):
    """Bounded evidence describing what a deterministic Context build omitted."""

    context_version: str = Field(pattern=PROMPT_VERSION_PATTERN)
    input_chars: int = Field(ge=0, le=MAX_MODEL_INPUT_CHARS, strict=True)
    omitted_event_sequences: tuple[int, ...] = Field(
        default=(),
        max_length=MAX_CONTEXT_REPORT_SEQUENCES,
    )
    truncated_tool_call_ids: tuple[ToolCallId, ...] = Field(
        default=(),
        max_length=MAX_CONTEXT_REPORT_SEQUENCES,
    )

    @field_validator("omitted_event_sequences")
    @classmethod
    def require_stable_sequences(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(sequence < 1 for sequence in value):
            raise ValueError("omitted Event sequences must be positive")
        if len(value) != len(set(value)) or value != tuple(sorted(value)):
            raise ValueError("omitted Event sequences must be sorted and unique")
        return tuple(value)

    @field_validator("truncated_tool_call_ids")
    @classmethod
    def require_unique_tool_call_ids(
        cls,
        value: tuple[ToolCallId, ...],
    ) -> tuple[ToolCallId, ...]:
        if len(value) != len({str(tool_call_id) for tool_call_id in value}):
            raise ValueError("truncated Tool call IDs must be unique")
        return tuple(value)


class ContextBuildResult(DomainModel):
    """The exact model request and bounded evidence for one Context build."""

    request: ModelRequest
    report: ContextBuildReport


class RunInput(DomainModel):
    """Validated application input for creating and executing one Run."""

    session_id: SessionId
    objective: str = Field(min_length=1, max_length=MAX_OBJECTIVE_CHARS)
    budget_limits: BudgetLimits
    agent_config: AgentConfig

    @field_validator("objective")
    @classmethod
    def reject_blank_objective(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("objective must not be blank")
        return value


class RunProfile(DomainModel):
    """Versioned, non-secret configuration loaded by a trusted interface."""

    schema_version: Literal[1] = 1
    agent_config: AgentConfig
    budget_limits: BudgetLimits


class RunProfileV2(DomainModel):
    """Version 2 Run configuration selecting one catalog Provider and its default model."""

    schema_version: Literal[2] = 2
    provider_id: str = Field(pattern=PROVIDER_ID_PATTERN)
    agent_config: AgentSettings
    budget_limits: BudgetLimits


type RunProfileDocument = Annotated[
    RunProfile | RunProfileV2,
    Field(discriminator="schema_version"),
]


class RunResult(DomainModel):
    """Terminal application result without adapter-specific state."""

    run_id: RunId
    state: RunState
    final_text: str | None = Field(default=None, min_length=1, max_length=MAX_MODEL_OUTPUT_CHARS)
    artifacts: tuple[Artifact, ...] = ()

    @model_validator(mode="after")
    def require_matching_terminal_run(self) -> Self:
        if self.state.run_id != self.run_id:
            raise ValueError("Run result identity must match its state")
        if self.state.status not in {RunStatus.SUCCEEDED, RunStatus.FAILED}:
            raise ValueError("Run result requires a terminal state")
        if self.state.status is RunStatus.SUCCEEDED and self.final_text is None:
            raise ValueError("successful Run result requires final text")
        if self.state.status is RunStatus.FAILED and self.final_text is not None:
            raise ValueError("failed Run result cannot contain final text")
        return self
