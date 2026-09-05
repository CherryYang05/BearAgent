"""BearAgent command-line interface and production Run entrypoint."""

import asyncio
import json
import platform
import sys
from pathlib import Path
from typing import Annotated, Literal, NoReturn, TypedDict

import typer
from pydantic import ValidationError
from typer import _click
from typer.core import TyperGroup

from bearagent import package_version
from bearagent.bootstrap import build_run_query_service, build_run_services
from bearagent.domain.agent import MAX_OBJECTIVE_CHARS, RunInput
from bearagent.domain.errors import BearAgentError, ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.ids import RunId, SessionId
from bearagent.domain.runs import RunStatus
from bearagent.interfaces.cli.contracts import (
    CommandErrorOutput,
    EventsCommandOutput,
    InspectCommandOutput,
    RunCommandOutput,
)
from bearagent.interfaces.cli.renderers import (
    render_error,
    render_events,
    render_inspection,
    render_json,
    render_run,
)

DEFAULT_PROFILE_PATH = Path("data/p1-run-profile.json")
DEFAULT_CONFIG_PATH = Path("data/config.json")
DEFAULT_DATABASE_PATH = Path("data/bearagent.db")
DEFAULT_WORKSPACE_PATH = Path(".")


class DoctorReport(TypedDict):
    """Stable P0 JSON payload returned by ``bearagent doctor --json``."""

    status: Literal["ok", "error"]
    bearagent_version: str
    python_version: str
    python_supported: bool
    platform: str
    working_directory: str


class DefaultRunGroup(TyperGroup):
    """Route unknown first tokens to the hidden objective command."""

    def parse_args(self, ctx: _click.Context, args: list[str]) -> list[str]:
        if args and args[0] not in self.commands and args[0] not in {"--help", "-h"}:
            args = ["execute", *args]
        return super().parse_args(ctx, args)


app = typer.Typer(
    name="bearagent",
    help="Durable and secure personal AI Agent Runtime.",
    no_args_is_help=True,
    add_completion=False,
)
run_app = typer.Typer(
    name="run",
    cls=DefaultRunGroup,
    help="Execute `bearagent run OBJECTIVE`, or inspect an existing durable Run.",
    epilog=(
        "Run options may appear before or after OBJECTIVE. "
        "Use `bearagent run -- OBJECTIVE` when the objective is named inspect/events "
        "or begins with a dash."
    ),
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(run_app, name="run")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(package_version())
        raise typer.Exit()


def build_doctor_report() -> DoctorReport:
    """Build a non-sensitive environment report without reading credentials."""
    python_supported = sys.version_info[:2] == (3, 12)
    return {
        "status": "ok" if python_supported else "error",
        "bearagent_version": package_version(),
        "python_version": platform.python_version(),
        "python_supported": python_supported,
        "platform": platform.platform(),
        "working_directory": str(Path.cwd()),
    }


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the BearAgent version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Run BearAgent commands."""
    del version


@app.command()
def doctor(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable JSON report."),
    ] = False,
) -> None:
    """Check whether the local environment can run this BearAgent version."""
    report = build_doctor_report()
    if json_output:
        typer.echo(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        typer.echo(f"BearAgent: {report['bearagent_version']}")
        typer.echo(f"Python: {report['python_version']}")
        typer.echo(f"Platform: {report['platform']}")
        typer.echo(f"Working directory: {report['working_directory']}")
        typer.echo(f"Status: {report['status']}")

    if not report["python_supported"]:
        raise typer.Exit(code=1)


@run_app.command("execute", hidden=True)
def run_objective(
    objective: Annotated[str, typer.Argument(help="The objective for this Run.")],
    profile: Annotated[
        Path,
        typer.Option("--profile", help="Path to a version 1 or 2 Run profile."),
    ] = DEFAULT_PROFILE_PATH,
    config: Annotated[
        Path,
        typer.Option("--config", help="Path to a version 1 BearAgent config."),
    ] = DEFAULT_CONFIG_PATH,
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Workspace root available to Tools."),
    ] = DEFAULT_WORKSPACE_PATH,
    database: Annotated[
        Path,
        typer.Option("--database", help="SQLite EventStore path."),
    ] = DEFAULT_DATABASE_PATH,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit one versioned JSON result."),
    ] = False,
) -> None:
    """Execute one objective through the durable Agent Loop."""
    try:
        output = asyncio.run(
            _execute_objective(
                objective=objective,
                profile=profile,
                config=config,
                workspace=workspace,
                database=database,
            )
        )
    except Exception as error:
        _exit_with_error("run", error, json_output=json_output)

    typer.echo(render_json(output) if json_output else render_run(output.result))
    if output.result.state.status is RunStatus.FAILED:
        raise typer.Exit(code=1)


@run_app.command("inspect")
def inspect_run(
    run_id: Annotated[str, typer.Argument(help="UUID4 Run identifier.")],
    database: Annotated[
        Path,
        typer.Option("--database", help="Existing SQLite EventStore path."),
    ] = DEFAULT_DATABASE_PATH,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit one versioned JSON result."),
    ] = False,
) -> None:
    """Show the reducer projection and committed Artifact metadata."""
    try:
        output = asyncio.run(_inspect_existing_run(run_id=run_id, database=database))
    except Exception as error:
        _exit_with_error("inspect", error, json_output=json_output)
    typer.echo(render_json(output) if json_output else render_inspection(output.result))


@run_app.command("events")
def list_run_events(
    run_id: Annotated[str, typer.Argument(help="UUID4 Run identifier.")],
    after_sequence: Annotated[
        int,
        typer.Option("--after-sequence", min=0, help="Return Events after this sequence."),
    ] = 0,
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=10_000, help="Maximum Events to return."),
    ] = 1_000,
    database: Annotated[
        Path,
        typer.Option("--database", help="Existing SQLite EventStore path."),
    ] = DEFAULT_DATABASE_PATH,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit one versioned JSON result."),
    ] = False,
) -> None:
    """Show one bounded page of committed Event facts."""
    try:
        output = asyncio.run(
            _list_existing_run_events(
                run_id=run_id,
                database=database,
                after_sequence=after_sequence,
                limit=limit,
            )
        )
    except Exception as error:
        _exit_with_error("events", error, json_output=json_output)
    typer.echo(render_json(output) if json_output else render_events(output.result))


async def _execute_objective(
    *,
    objective: str,
    profile: Path,
    config: Path,
    workspace: Path,
    database: Path,
) -> RunCommandOutput:
    if not objective.strip() or len(objective) > MAX_OBJECTIVE_CHARS:
        raise ValueError("objective is invalid")
    services = await build_run_services(
        profile_path=profile,
        config_path=config,
        workspace_path=workspace,
        database_path=database,
    )
    # stderr keeps JSON stdout machine-readable. "Allocated" deliberately does
    # not claim RunCreated has committed yet.
    run_id = RunId.new()
    typer.echo(f"Allocated Run ID: {run_id}", err=True)
    result = await services.agent_loop.run(
        RunInput(
            session_id=SessionId.new(),
            objective=objective,
            budget_limits=services.profile.budget_limits,
            agent_config=services.agent_config,
        ),
        run_id=run_id,
    )
    return RunCommandOutput(result=result)


async def _inspect_existing_run(*, run_id: str, database: Path) -> InspectCommandOutput:
    parsed_run_id = RunId.parse(run_id)
    service = await build_run_query_service(database)
    return InspectCommandOutput(result=await service.inspect(parsed_run_id))


async def _list_existing_run_events(
    *,
    run_id: str,
    database: Path,
    after_sequence: int,
    limit: int,
) -> EventsCommandOutput:
    parsed_run_id = RunId.parse(run_id)
    service = await build_run_query_service(database)
    return EventsCommandOutput(
        result=await service.events(
            parsed_run_id,
            after_sequence=after_sequence,
            limit=limit,
        )
    )


def _exit_with_error(
    command: Literal["run", "inspect", "events"],
    error: BaseException,
    *,
    json_output: bool,
) -> NoReturn:
    info = _safe_error_info(error)
    output = CommandErrorOutput(command=command, error=info)
    typer.echo(render_json(output) if json_output else f"Error: {render_error(info)}")
    raise typer.Exit(code=1)


def _safe_error_info(error: BaseException) -> ErrorInfo:
    if isinstance(error, BearAgentError):
        return error.info
    if isinstance(error, ValidationError | ValueError):
        return ErrorInfo(
            category=ErrorCategory.VALIDATION,
            code=ErrorCode.INVALID_INPUT,
            message="Command input is invalid.",
        )
    return ErrorInfo(
        category=ErrorCategory.INTERNAL,
        code=ErrorCode.INTERNAL_ERROR,
        message="Command could not be completed.",
    )
