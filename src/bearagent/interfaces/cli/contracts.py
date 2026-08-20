"""Versioned machine-readable contracts emitted by the CLI."""

from typing import Literal

from pydantic import BaseModel

from bearagent.domain._base import DomainModel
from bearagent.domain.agent import RunResult
from bearagent.domain.errors import ErrorInfo
from bearagent.domain.queries import EventPage, RunInspection


class RunCommandOutput(DomainModel):
    """Successful or terminal result of ``bearagent run OBJECTIVE``."""

    schema_version: Literal[1] = 1
    command: Literal["run"] = "run"
    result: RunResult


class InspectCommandOutput(DomainModel):
    """Result of ``bearagent run inspect RUN_ID``."""

    schema_version: Literal[1] = 1
    command: Literal["inspect"] = "inspect"
    result: RunInspection


class EventsCommandOutput(DomainModel):
    """Result of ``bearagent run events RUN_ID``."""

    schema_version: Literal[1] = 1
    command: Literal["events"] = "events"
    result: EventPage


class CommandErrorOutput(DomainModel):
    """Safe failure object shared by all Run commands."""

    schema_version: Literal[1] = 1
    command: Literal["run", "inspect", "events"]
    error: ErrorInfo


PUBLIC_CLI_SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    CommandErrorOutput,
    EventsCommandOutput,
    InspectCommandOutput,
    RunCommandOutput,
)


def public_cli_schemas() -> dict[str, dict[str, object]]:
    """Return deterministic JSON schemas keyed by output model name."""
    return {
        model.__name__: model.model_json_schema(mode="serialization")
        for model in sorted(PUBLIC_CLI_SCHEMA_MODELS, key=lambda item: item.__name__)
    }
