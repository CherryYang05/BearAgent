"""Versioned P1 file-task suite contracts and deterministic rubric helpers."""

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvalBudget(EvalModel):
    max_model_iterations: int = Field(ge=0)
    max_tokens: int = Field(ge=0)
    max_cost_microusd: int = Field(ge=0)
    max_wall_time_ms: int = Field(ge=0)
    max_tool_calls: int = Field(ge=0)


class ExpectedCall(EvalModel):
    name: str
    arguments: dict[str, str]


class EvalRubric(EvalModel):
    required_output_facts: tuple[str, ...]
    exact_output: bool


class EvalTask(EvalModel):
    task_id: str
    version: str
    objective: str
    workspace_fixture: str
    agent_config_version: str
    model_version: str
    prompt_version: str
    tool_version: str
    budget: EvalBudget
    expected_calls: tuple[ExpectedCall, ...]
    expected_event_types: tuple[str, ...]
    expected_terminal: Literal["succeeded", "budget_exhausted"]
    expected_artifact_path: str | None
    output_content: str | None
    rubric: EvalRubric


class EvalSuite(EvalModel):
    suite_id: str
    version: str
    tasks: tuple[EvalTask, ...]


class OutputRubricResult(EvalModel):
    passed: bool
    artifact_path: str | None
    artifact_sha256: str | None
    required_facts: tuple[str, ...]
    matched_facts: tuple[str, ...]
    exact_output_required: bool
    exact_output_matched: bool | None


def load_p1_suite(path: Path) -> EvalSuite:
    """Load the committed suite with strict schema validation."""
    return EvalSuite.model_validate_json(path.read_text(encoding="utf-8"))


def evaluate_output(task: EvalTask, *, output: str | None) -> OutputRubricResult:
    """Evaluate output using facts and hashes, never a model judge."""
    required = tuple(fact.casefold() for fact in task.rubric.required_output_facts)
    folded_output = "" if output is None else output.casefold()
    matched = tuple(
        original
        for original, folded in zip(task.rubric.required_output_facts, required, strict=True)
        if folded in folded_output
    )
    exact_matched: bool | None = None
    if task.rubric.exact_output:
        exact_matched = output is not None and output == task.output_content
    artifact_sha256 = None if output is None else hashlib.sha256(output.encode("utf-8")).hexdigest()
    passed = output is not None and len(matched) == len(required) and (exact_matched is not False)
    return OutputRubricResult(
        passed=passed,
        artifact_path=task.expected_artifact_path,
        artifact_sha256=artifact_sha256,
        required_facts=task.rubric.required_output_facts,
        matched_facts=matched,
        exact_output_required=task.rubric.exact_output,
        exact_output_matched=exact_matched,
    )


def required_tool_names(task: EvalTask) -> tuple[str, ...]:
    """Return the exact task Tool allowlist in stable first-use order."""
    return tuple(sorted({call.name for call in task.expected_calls}))
