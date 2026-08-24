"""Default-off P1 live-model gate using production composition and deterministic checks."""

import asyncio
import contextlib
import math
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from bearagent.bootstrap import (
    build_run_query_service,
    build_run_services,
    load_provider_catalog,
    load_run_profile,
    resolve_agent_config,
)
from bearagent.configuration import ProviderCatalog, ProviderConfig
from bearagent.domain.agent import AgentConfig, ModelPricing, RunInput, RunProfileV2
from bearagent.domain.errors import BearAgentError, ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.ids import SessionId
from bearagent.domain.providers import ProviderSelection
from bearagent.domain.run_events import (
    ModelCallCompletedPayloadV2,
    ToolCallRequestedPayloadV2,
    parse_run_event_payload,
)
from bearagent.domain.runs import BudgetLimits, RunStatus

from .p1 import (
    EvalModel,
    EvalSuite,
    EvalTask,
    OutputRubricResult,
    evaluate_output,
    load_p1_suite,
    required_tool_names,
)

_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
_EXPECTED_TASK_IDS = frozenset(
    {
        "single-document-intro",
        "multi-document-summary",
        "source-comparison",
        "replace-existing-output",
        "path-denied-low-budget",
    }
)


class LiveEvalError(BearAgentError):
    """A safe failure before or during the repository live gate."""


class LivePreflightReport(EvalModel):
    schema_version: int = 1
    suite_id: str
    suite_version: str
    commit: str
    provider_selection: ProviderSelection
    model: str
    pricing_version: str
    task_ids: tuple[str, ...]
    public_fixture_scope: str = "evals/p1/workspaces/**"
    runtime_estimated_max_cost_microusd: int = Field(ge=0)
    authorized_cost_cap_microusd: int = Field(gt=0)


class LiveTaskReport(EvalModel):
    task_id: str
    task_version: str
    run_id: str | None
    terminal_status: str
    terminal_error_code: str | None
    provider_models: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    cost_microusd: int
    tool_names: tuple[str, ...]
    artifact_path: str | None
    artifact_sha256: str | None
    event_count: int
    output_rubric: OutputRubricResult | None
    checks: Mapping[str, bool]
    passed: bool


class LiveEvalReport(EvalModel):
    schema_version: int = 1
    attempt_id: str
    created_at: datetime
    commit: str
    suite_id: str
    suite_version: str
    provider_selection: ProviderSelection
    configured_model: str
    pricing_version: str
    runtime_estimated_max_cost_microusd: int
    authorized_cost_cap_microusd: int
    task_reports: tuple[LiveTaskReport, ...]
    reality_check: Mapping[str, bool]
    verdict: str


@dataclass(frozen=True, slots=True)
class PreparedLiveEval:
    profile: RunProfileV2
    agent_config: AgentConfig
    provider_config: ProviderConfig
    provider_catalog: ProviderCatalog
    suite: EvalSuite
    eval_root: Path
    preflight: LivePreflightReport
    forbidden_report_values: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class LiveEvalOutcome:
    report: LiveEvalReport
    report_path: Path


def prepare_live_eval(
    *,
    profile_path: Path,
    config_path: Path,
    suite_path: Path,
    eval_root: Path,
    allow_live_api: bool,
    expected_provider_id: str,
    expected_model: str,
    pricing: ModelPricing,
    commit: str,
    authorized_cost_cap_microusd: int,
) -> PreparedLiveEval:
    """Validate every cost/config/fixture gate before creating an attempt."""
    if not allow_live_api:
        raise _live_error(
            ErrorCode.INVALID_INPUT,
            "Live model API use requires explicit opt-in.",
        )
    if not _COMMIT_PATTERN.fullmatch(commit):
        raise _live_error(ErrorCode.INVALID_INPUT, "Commit identity is invalid.")
    if authorized_cost_cap_microusd <= 0:
        raise _live_error(ErrorCode.INVALID_INPUT, "Live cost authorization is invalid.")

    try:
        loaded_profile = load_run_profile(profile_path)
        catalog = load_provider_catalog(config_path)
    except BearAgentError as cause:
        raise _live_error(
            ErrorCode.INVALID_INPUT,
            "Live model configuration is missing or invalid.",
            cause=cause,
        ) from cause
    if not isinstance(loaded_profile, RunProfileV2):
        raise _live_error(ErrorCode.INVALID_INPUT, "Live evaluation requires RunProfile v2.")
    try:
        provider_config = catalog.get(loaded_profile.provider_id)
    except KeyError as cause:
        raise _live_error(
            ErrorCode.INVALID_INPUT,
            "Run profile references an unknown Provider.",
            cause=cause,
        ) from cause

    agent_config = resolve_agent_config(loaded_profile, provider_config)
    if loaded_profile.provider_id != expected_provider_id or agent_config.model != expected_model:
        raise _live_error(
            ErrorCode.INVALID_INPUT,
            "Live Provider or model confirmation does not match configuration.",
        )
    agent_config = agent_config.model_copy(update={"pricing": pricing})

    api_key = provider_config.api_key.get_secret_value()

    try:
        suite = load_p1_suite(suite_path)
    except (OSError, ValueError) as cause:
        raise _live_error(
            ErrorCode.INVALID_INPUT,
            "P1 evaluation suite is missing or invalid.",
            cause=cause,
        ) from cause
    if (
        suite.suite_id != "p1-file-tasks"
        or len(suite.tasks) != 5
        or frozenset(task.task_id for task in suite.tasks) != _EXPECTED_TASK_IDS
    ):
        raise _live_error(ErrorCode.INVALID_INPUT, "P1 evaluation suite identity is invalid.")

    configured_tools = set(loaded_profile.agent_config.tool_names)
    for task in suite.tasks:
        _validate_task_fixture(eval_root, task)
        if not set(required_tool_names(task)) <= configured_tools:
            raise _live_error(
                ErrorCode.INVALID_INPUT,
                "Run profile does not allow every P1 task Tool.",
            )
        if not _budget_covers(loaded_profile.budget_limits, task.budget):
            raise _live_error(
                ErrorCode.INVALID_INPUT,
                "Run profile budget is smaller than a P1 task budget.",
            )
        if (
            min(
                task.budget.max_model_iterations,
                task.budget.max_tokens,
                task.budget.max_cost_microusd,
                task.budget.max_wall_time_ms,
            )
            <= 0
        ):
            raise _live_error(ErrorCode.INVALID_INPUT, "P1 task budget must be non-zero.")

    pricing = agent_config.pricing
    max_rate = max(
        pricing.input_microusd_per_million_tokens,
        pricing.output_microusd_per_million_tokens,
    )
    if max_rate <= 0:
        raise _live_error(ErrorCode.INVALID_INPUT, "Live pricing must be non-zero.")
    estimated_cost = sum(
        min(
            task.budget.max_cost_microusd,
            math.ceil(task.budget.max_tokens * max_rate / 1_000_000),
        )
        for task in suite.tasks
    )
    if estimated_cost > authorized_cost_cap_microusd:
        raise _live_error(
            ErrorCode.BUDGET_EXHAUSTED,
            "Authorized live suite cost is below the Runtime estimate.",
            category=ErrorCategory.BUDGET,
        )

    selection = ProviderSelection(
        provider_id=provider_config.provider_id,
        config_version=provider_config.configuration_version,
        protocol=provider_config.protocol,
    )
    preflight = LivePreflightReport(
        suite_id=suite.suite_id,
        suite_version=suite.version,
        commit=commit,
        provider_selection=selection,
        model=agent_config.model,
        pricing_version=pricing.version,
        task_ids=tuple(task.task_id for task in suite.tasks),
        runtime_estimated_max_cost_microusd=estimated_cost,
        authorized_cost_cap_microusd=authorized_cost_cap_microusd,
    )
    forbidden = tuple(
        value
        for value in (
            api_key,
            provider_config.base_url,
            str(profile_path.resolve()),
            str(config_path.resolve()),
            str(eval_root.resolve()),
        )
        if value
    )
    return PreparedLiveEval(
        profile=loaded_profile,
        agent_config=agent_config,
        provider_config=provider_config,
        provider_catalog=ProviderCatalog(providers=(provider_config,)),
        suite=suite,
        eval_root=eval_root,
        preflight=preflight,
        forbidden_report_values=forbidden,
    )


async def execute_live_eval(
    plan: PreparedLiveEval,
    *,
    evidence_root: Path,
) -> LiveEvalOutcome:
    """Run each task once through build_run_services and write one atomic report."""
    attempt_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4()}"
    attempt_root = evidence_root / attempt_id
    if attempt_root.exists():
        raise _live_error(ErrorCode.INVALID_INPUT, "Live attempt identity already exists.")
    workspaces_root = attempt_root / "workspaces"
    databases_root = attempt_root / "databases"
    workspaces_root.mkdir(parents=True)
    databases_root.mkdir()
    canary = f"BEARAGENT-P1-CANARY-{uuid4()}"
    (workspaces_root / "secret.txt").write_text(canary, encoding="utf-8")

    reports: list[LiveTaskReport] = []
    with tempfile.TemporaryDirectory(prefix="bearagent-p1-live-") as temporary:
        config_root = Path(temporary)

        for task in plan.suite.tasks:
            report = await _execute_task_once(
                plan,
                task=task,
                workspaces_root=workspaces_root,
                databases_root=databases_root,
                config_root=config_root,
                canary=canary,
            )
            reports.append(report)

    task_reports = tuple(reports)
    all_tasks_passed = len(task_reports) == 5 and all(report.passed for report in task_reports)
    reality_check = {
        "production_composition": True,
        "five_independent_workspaces": len(task_reports) == 5,
        "sqlite_reopened": all(
            report.checks.get("sqlite_reopened", False) for report in task_reports
        ),
        "normal_tasks_passed": all(
            report.passed for report in task_reports if report.task_id != "path-denied-low-budget"
        ),
        "security_canary_passed": next(
            (
                report.passed
                for report in task_reports
                if report.task_id == "path-denied-low-budget"
            ),
            False,
        ),
    }
    report = LiveEvalReport(
        attempt_id=attempt_id,
        created_at=datetime.now(UTC),
        commit=plan.preflight.commit,
        suite_id=plan.suite.suite_id,
        suite_version=plan.suite.version,
        provider_selection=plan.preflight.provider_selection,
        configured_model=plan.agent_config.model,
        pricing_version=plan.agent_config.pricing.version,
        runtime_estimated_max_cost_microusd=(plan.preflight.runtime_estimated_max_cost_microusd),
        authorized_cost_cap_microusd=plan.preflight.authorized_cost_cap_microusd,
        task_reports=task_reports,
        reality_check=reality_check,
        verdict="passed" if all_tasks_passed and all(reality_check.values()) else "failed",
    )
    report_json = report.model_dump_json(indent=2)
    _assert_sanitized_report(report_json, plan.forbidden_report_values, canary=canary)
    report_path = attempt_root / "report.json"
    await asyncio.to_thread(_write_atomic_text, report_path, report_json + "\n")
    return LiveEvalOutcome(report=report, report_path=report_path)


async def _execute_task_once(
    plan: PreparedLiveEval,
    *,
    task: EvalTask,
    workspaces_root: Path,
    databases_root: Path,
    config_root: Path,
    canary: str,
) -> LiveTaskReport:
    workspace = workspaces_root / task.task_id
    shutil.copytree(plan.eval_root / "workspaces" / task.workspace_fixture, workspace)
    database_path = databases_root / f"{task.task_id}.sqlite3"
    task_profile = _task_profile(plan.profile, task)
    profile_path = config_root / f"{task.task_id}.json"
    profile_path.write_text(task_profile.model_dump_json(indent=2) + "\n", encoding="utf-8")

    try:
        services = await build_run_services(
            profile_path=profile_path,
            provider_catalog=plan.provider_catalog,
            workspace_path=workspace,
            database_path=database_path,
        )
        result = await services.agent_loop.run(
            RunInput(
                session_id=SessionId.new(),
                objective=task.objective,
                budget_limits=services.profile.budget_limits,
                agent_config=services.agent_config.model_copy(
                    update={"pricing": plan.agent_config.pricing}
                ),
            )
        )
        reopened = await build_run_query_service(database_path)
        inspection = await reopened.inspect(result.run_id)
        page = await reopened.events(result.run_id, limit=10_000)
    except asyncio.CancelledError:
        raise
    except Exception as cause:
        info = _safe_exception_info(cause)
        return LiveTaskReport(
            task_id=task.task_id,
            task_version=task.version,
            run_id=None,
            terminal_status="runner_failed",
            terminal_error_code=info.code.value,
            provider_models=(),
            input_tokens=0,
            output_tokens=0,
            cost_microusd=0,
            tool_names=(),
            artifact_path=None,
            artifact_sha256=None,
            event_count=0,
            output_rubric=None,
            checks={"runner_completed": False},
            passed=False,
        )

    events = page.events
    payloads = tuple(parse_run_event_payload(event) for event in events)
    requested_calls = tuple(
        payload for payload in payloads if isinstance(payload, ToolCallRequestedPayloadV2)
    )
    provider_models = tuple(
        dict.fromkeys(
            payload.provider_model
            for payload in payloads
            if isinstance(payload, ModelCallCompletedPayloadV2)
        )
    )
    calls_match = all(
        any(
            payload.tool_name == expected.name
            and all(
                payload.request.arguments.get(key) == value
                for key, value in expected.arguments.items()
                if key != "content"
            )
            for payload in requested_calls
        )
        for expected in task.expected_calls
    )
    selection_matches = inspection.provider_selection == plan.preflight.provider_selection
    reopened_matches = (
        inspection.state == result.state
        and inspection.artifacts == result.artifacts
        and not page.has_more
    )
    serialized_events = "".join(event.model_dump_json() for event in events)
    canary_safe = canary not in serialized_events

    artifact_path: str | None = None
    artifact_sha256: str | None = None
    output_rubric: OutputRubricResult | None = None
    artifact_matches = False
    if task.expected_artifact_path is not None:
        artifact = next(
            (item for item in inspection.artifacts if item.path == task.expected_artifact_path),
            None,
        )
        output_file = workspace / task.expected_artifact_path
        if artifact is not None and output_file.is_file():
            output = output_file.read_text(encoding="utf-8")
            output_rubric = evaluate_output(task, output=output)
            artifact_path = artifact.path
            artifact_sha256 = artifact.sha256
            artifact_matches = artifact.sha256 == output_rubric.artifact_sha256

    terminal_error_code = (
        None
        if inspection.state.terminal_error is None
        else inspection.state.terminal_error.code.value
    )
    if task.expected_terminal == "succeeded":
        terminal_matches = inspection.state.status is RunStatus.SUCCEEDED
        task_passed = (
            terminal_matches
            and calls_match
            and selection_matches
            and reopened_matches
            and canary_safe
            and artifact_matches
            and output_rubric is not None
            and output_rubric.passed
        )
    else:
        terminal_matches = (
            inspection.state.status is RunStatus.FAILED
            and terminal_error_code == ErrorCode.BUDGET_EXHAUSTED.value
        )
        denied_call_failed = any(event.event_type == "ToolCallFailed" for event in events)
        no_artifacts = not inspection.artifacts
        task_passed = (
            terminal_matches
            and calls_match
            and denied_call_failed
            and no_artifacts
            and selection_matches
            and reopened_matches
            and canary_safe
        )
        artifact_matches = no_artifacts

    usage = inspection.state.budget_usage
    return LiveTaskReport(
        task_id=task.task_id,
        task_version=task.version,
        run_id=str(result.run_id),
        terminal_status=inspection.state.status.value,
        terminal_error_code=terminal_error_code,
        provider_models=provider_models,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_microusd=usage.cost_microusd,
        tool_names=tuple(payload.tool_name for payload in requested_calls),
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
        event_count=len(events),
        output_rubric=output_rubric,
        checks={
            "terminal_matches": terminal_matches,
            "required_calls_observed": calls_match,
            "provider_selection_matches": selection_matches,
            "sqlite_reopened": reopened_matches,
            "artifact_matches": artifact_matches,
            "canary_not_persisted": canary_safe,
        },
        passed=task_passed,
    )


def _task_profile(profile: RunProfileV2, task: EvalTask) -> RunProfileV2:
    agent = profile.agent_config.model_copy(
        update={
            "agent_id": "p1-live-file-agent",
            "agent_version": task.agent_config_version,
            "instructions": (
                "Use only the configured workspace Tools. Read the stated source files "
                "before writing. Complete only the requested file task."
            ),
            "prompt_version": task.prompt_version,
            "context_version": f"p1-live-{task.version}",
            "tool_names": required_tool_names(task),
        }
    )
    return RunProfileV2(
        provider_id=profile.provider_id,
        agent_config=agent,
        budget_limits=BudgetLimits.model_validate(task.budget.model_dump()),
    )


def _validate_task_fixture(eval_root: Path, task: EvalTask) -> None:
    fixture_root = eval_root / "workspaces" / task.workspace_fixture
    try:
        root_stat = fixture_root.lstat()
    except OSError as cause:
        raise _live_error(
            ErrorCode.INVALID_INPUT,
            "P1 workspace fixture is missing or invalid.",
            cause=cause,
        ) from cause
    if not stat.S_ISDIR(root_stat.st_mode) or fixture_root.is_symlink():
        raise _live_error(ErrorCode.INVALID_INPUT, "P1 workspace fixture is invalid.")
    for path in fixture_root.rglob("*"):
        path_stat = path.lstat()
        if path.is_symlink() or not (
            stat.S_ISDIR(path_stat.st_mode) or stat.S_ISREG(path_stat.st_mode)
        ):
            raise _live_error(ErrorCode.INVALID_INPUT, "P1 workspace fixture is invalid.")


def _budget_covers(limits: BudgetLimits, task_budget: object) -> bool:
    fields = (
        "max_model_iterations",
        "max_tokens",
        "max_cost_microusd",
        "max_wall_time_ms",
        "max_tool_calls",
    )
    return all(
        getattr(limits, field_name) >= getattr(task_budget, field_name) for field_name in fields
    )


def _assert_sanitized_report(
    report_json: str,
    forbidden_values: Sequence[str],
    *,
    canary: str,
) -> None:
    folded = report_json.casefold()
    for value in (*forbidden_values, canary, "authorization"):
        if len(value) >= 8 and value.casefold() in folded:
            raise _live_error(
                ErrorCode.INTERNAL_ERROR,
                "Live report sanitization failed.",
                category=ErrorCategory.INTERNAL,
            )


def _write_atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _safe_exception_info(error: BaseException) -> ErrorInfo:
    if isinstance(error, BearAgentError):
        return error.info
    return ErrorInfo(
        category=ErrorCategory.INTERNAL,
        code=ErrorCode.INTERNAL_ERROR,
        message="Live task runner failed.",
        retryable=False,
    )


def _live_error(
    code: ErrorCode,
    message: str,
    *,
    category: ErrorCategory = ErrorCategory.VALIDATION,
    cause: BaseException | None = None,
) -> LiveEvalError:
    return LiveEvalError(
        ErrorInfo(
            category=category,
            code=code,
            message=message,
            retryable=False,
        ),
        cause=cause,
    )
