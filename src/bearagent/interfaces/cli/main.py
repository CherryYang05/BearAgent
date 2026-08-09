"""P0 command-line interface and environment diagnostics."""

import json
import platform
import sys
from pathlib import Path
from typing import Annotated, Literal, TypedDict

import typer

from bearagent import package_version


class DoctorReport(TypedDict):
    """Stable P0 JSON payload returned by ``bearagent doctor --json``."""

    status: Literal["ok", "error"]
    bearagent_version: str
    python_version: str
    python_supported: bool
    platform: str
    working_directory: str


app = typer.Typer(
    name="bearagent",
    help="Durable and secure personal AI Agent Runtime.",
    no_args_is_help=True,
    add_completion=False,
)


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
