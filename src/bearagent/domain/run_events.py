"""Typed v1 payloads for Events that change P1 Run state."""

from types import MappingProxyType

from pydantic import Field

from bearagent.domain._base import DomainModel
from bearagent.domain.errors import ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import ActivityId, ModelCallId, SessionId, ToolCallId
from bearagent.domain.messages import TOOL_NAME_PATTERN
from bearagent.domain.runs import BudgetLimits

RUN_EVENT_SCHEMA_VERSION = 1


class RunCreatedPayload(DomainModel):
    """Trusted configuration captured when a Run is created."""

    session_id: SessionId
    budget_limits: BudgetLimits


class RunStartedPayload(DomainModel):
    """Payload for the transition from queued to running."""


class RunSucceededPayload(DomainModel):
    """Payload for a successful terminal transition."""


class RunFailedPayload(DomainModel):
    """Safe failure information for a terminal Run."""

    error: ErrorInfo


class ModelCallRequestedPayload(DomainModel):
    """Identity of a model Activity accepted for scheduling."""

    activity_id: ActivityId
    model_call_id: ModelCallId


class ModelCallStartedPayload(DomainModel):
    """Identity of a model Activity that has started."""

    activity_id: ActivityId
    model_call_id: ModelCallId


class ModelCallCompletedPayload(DomainModel):
    """Actual normalized usage for a completed model Activity."""

    activity_id: ActivityId
    model_call_id: ModelCallId
    input_tokens: int = Field(ge=0, strict=True)
    output_tokens: int = Field(ge=0, strict=True)
    cost_microusd: int = Field(ge=0, strict=True)


class ModelCallFailedPayload(DomainModel):
    """Safe error and any known usage for a failed model Activity."""

    activity_id: ActivityId
    model_call_id: ModelCallId
    error: ErrorInfo
    input_tokens: int = Field(ge=0, strict=True)
    output_tokens: int = Field(ge=0, strict=True)
    cost_microusd: int = Field(ge=0, strict=True)


class ToolCallRequestedPayload(DomainModel):
    """Identity and bounded name of a Tool Activity accepted for scheduling."""

    activity_id: ActivityId
    tool_call_id: ToolCallId
    tool_name: str = Field(pattern=TOOL_NAME_PATTERN)


class ToolCallStartedPayload(DomainModel):
    """Identity of a Tool Activity that has started."""

    activity_id: ActivityId
    tool_call_id: ToolCallId


class ToolCallCompletedPayload(DomainModel):
    """Identity of a successfully completed Tool Activity."""

    activity_id: ActivityId
    tool_call_id: ToolCallId


class ToolCallFailedPayload(DomainModel):
    """Safe error for a failed Tool Activity."""

    activity_id: ActivityId
    tool_call_id: ToolCallId
    error: ErrorInfo


type RunEventPayload = (
    RunCreatedPayload
    | RunStartedPayload
    | RunSucceededPayload
    | RunFailedPayload
    | ModelCallRequestedPayload
    | ModelCallStartedPayload
    | ModelCallCompletedPayload
    | ModelCallFailedPayload
    | ToolCallRequestedPayload
    | ToolCallStartedPayload
    | ToolCallCompletedPayload
    | ToolCallFailedPayload
)


_PAYLOAD_TYPES = {
    ("RunCreated", RUN_EVENT_SCHEMA_VERSION): RunCreatedPayload,
    ("RunStarted", RUN_EVENT_SCHEMA_VERSION): RunStartedPayload,
    ("RunSucceeded", RUN_EVENT_SCHEMA_VERSION): RunSucceededPayload,
    ("RunFailed", RUN_EVENT_SCHEMA_VERSION): RunFailedPayload,
    ("ModelCallRequested", RUN_EVENT_SCHEMA_VERSION): ModelCallRequestedPayload,
    ("ModelCallStarted", RUN_EVENT_SCHEMA_VERSION): ModelCallStartedPayload,
    ("ModelCallCompleted", RUN_EVENT_SCHEMA_VERSION): ModelCallCompletedPayload,
    ("ModelCallFailed", RUN_EVENT_SCHEMA_VERSION): ModelCallFailedPayload,
    ("ToolCallRequested", RUN_EVENT_SCHEMA_VERSION): ToolCallRequestedPayload,
    ("ToolCallStarted", RUN_EVENT_SCHEMA_VERSION): ToolCallStartedPayload,
    ("ToolCallCompleted", RUN_EVENT_SCHEMA_VERSION): ToolCallCompletedPayload,
    ("ToolCallFailed", RUN_EVENT_SCHEMA_VERSION): ToolCallFailedPayload,
}

RUN_EVENT_PAYLOAD_TYPES = MappingProxyType(_PAYLOAD_TYPES)


def parse_run_event_payload(event: Event) -> RunEventPayload:
    """Validate an Event payload against its exact type and schema version."""
    payload_type = RUN_EVENT_PAYLOAD_TYPES[(event.event_type, event.schema_version)]
    return payload_type.model_validate(event.payload)
