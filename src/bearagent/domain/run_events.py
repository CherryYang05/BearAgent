"""Typed v1 payloads for Events that change P1 Run state."""

from types import MappingProxyType
from typing import Self

from pydantic import Field, model_validator

from bearagent.domain._base import DomainModel, thaw_json_mapping
from bearagent.domain.agent import AgentConfig, ContextBuildReport
from bearagent.domain.errors import ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.fingerprints import RunFingerprint
from bearagent.domain.ids import ActivityId, ModelCallId, SessionId, ToolCallId
from bearagent.domain.messages import TOOL_NAME_PATTERN, Message, MessageRole, ToolCallPart
from bearagent.domain.model import (
    MAX_PROVIDER_IDENTIFIER_CHARS,
    MODEL_NAME_PATTERN,
    ModelFinishReason,
    ModelRequest,
)
from bearagent.domain.providers import ProviderSelection
from bearagent.domain.runs import BudgetLimits
from bearagent.domain.tools import ToolExecutionRecord, ToolRequest, ToolStatus

RUN_EVENT_SCHEMA_VERSION = 1
RUN_EVENT_SCHEMA_VERSION_V2 = 2
RUN_EVENT_SCHEMA_VERSION_V3 = 3
RUN_EVENT_SCHEMA_VERSION_V4 = 4
LATEST_RUN_EVENT_SCHEMA_VERSION = RUN_EVENT_SCHEMA_VERSION_V4


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


class RunCreatedPayloadV2(RunCreatedPayload):
    """Trusted objective and Agent configuration captured for a new Run."""

    objective: str = Field(min_length=1, max_length=1_000_000)
    agent_config: AgentConfig


class RunCreatedPayloadV3(RunCreatedPayloadV2):
    """v3 Run creation fact with a non-secret Provider selection."""

    provider_selection: ProviderSelection


class RunCreatedPayloadV4(RunCreatedPayloadV2):
    """v4 Run creation fact with trusted contract provenance."""

    run_fingerprint: RunFingerprint
    provider_selection: ProviderSelection | None = None


class RunStartedPayloadV2(RunStartedPayload):
    """v2 Run start marker."""


class RunSucceededPayloadV2(RunSucceededPayload):
    """v2 successful terminal marker."""


class RunFailedPayloadV2(RunFailedPayload):
    """v2 failed terminal marker."""


class ModelCallRequestedPayloadV2(ModelCallRequestedPayload):
    """Exact Provider-neutral request built from committed facts."""

    request: ModelRequest
    context_report: ContextBuildReport


class ModelCallStartedPayloadV2(ModelCallStartedPayload):
    """v2 model Activity start marker."""


class ModelCallCompletedPayloadV2(ModelCallCompletedPayload):
    """Complete assistant output and Provider metadata for one model Activity."""

    message: Message
    provider_request_id: str = Field(min_length=1, max_length=MAX_PROVIDER_IDENTIFIER_CHARS)
    provider_model: str = Field(pattern=MODEL_NAME_PATTERN)
    finish_reason: ModelFinishReason

    @model_validator(mode="after")
    def require_finish_reason_to_match_message(self) -> Self:
        if self.message.role is not MessageRole.ASSISTANT:
            raise ValueError("model completion requires an assistant message")
        tool_calls = tuple(part for part in self.message.parts if isinstance(part, ToolCallPart))
        if self.finish_reason is ModelFinishReason.TOOL_CALLS and not tool_calls:
            raise ValueError("tool_calls finish requires at least one Tool call")
        if self.finish_reason is ModelFinishReason.STOP and tool_calls:
            raise ValueError("stop finish cannot contain Tool calls")
        return self


class ModelCallFailedPayloadV2(ModelCallFailedPayload):
    """Safe model failure plus the amount of discarded partial output."""

    discarded_output_chars: int = Field(default=0, ge=0, strict=True)


class ToolCallRequestedPayloadV2(ToolCallRequestedPayload):
    """The exact untrusted Tool request emitted by the model."""

    request: ToolRequest

    @model_validator(mode="after")
    def require_request_identity(self) -> Self:
        if self.request.tool_call_id != self.tool_call_id:
            raise ValueError("Tool request identity must match its Activity payload")
        if self.request.name != self.tool_name:
            raise ValueError("Tool request name must match its Activity payload")
        return self


class ToolCallStartedPayloadV2(ToolCallStartedPayload):
    """v2 Tool Activity start marker."""


class ToolCallCompletedPayloadV2(ToolCallCompletedPayload):
    """Complete Tool execution evidence for a successful Activity."""

    execution: ToolExecutionRecord

    @model_validator(mode="after")
    def require_successful_execution(self) -> Self:
        if self.execution.request.tool_call_id != self.tool_call_id:
            raise ValueError("Tool execution identity must match its Activity payload")
        if self.execution.result.status is not ToolStatus.SUCCEEDED:
            raise ValueError("completed Tool Activity requires a successful result")
        return self


class ToolCallFailedPayloadV2(ToolCallFailedPayload):
    """Complete Tool execution evidence for a failed Activity."""

    execution: ToolExecutionRecord

    @model_validator(mode="after")
    def require_failed_execution(self) -> Self:
        if self.execution.request.tool_call_id != self.tool_call_id:
            raise ValueError("Tool execution identity must match its Activity payload")
        if self.execution.result.status is not ToolStatus.FAILED:
            raise ValueError("failed Tool Activity requires a failed result")
        if self.execution.result.error != self.error:
            raise ValueError("Tool failure Error must match its execution result")
        return self


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
    | RunCreatedPayloadV2
    | RunCreatedPayloadV3
    | RunCreatedPayloadV4
    | RunStartedPayloadV2
    | RunSucceededPayloadV2
    | RunFailedPayloadV2
    | ModelCallRequestedPayloadV2
    | ModelCallStartedPayloadV2
    | ModelCallCompletedPayloadV2
    | ModelCallFailedPayloadV2
    | ToolCallRequestedPayloadV2
    | ToolCallStartedPayloadV2
    | ToolCallCompletedPayloadV2
    | ToolCallFailedPayloadV2
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
    ("RunCreated", RUN_EVENT_SCHEMA_VERSION_V2): RunCreatedPayloadV2,
    ("RunStarted", RUN_EVENT_SCHEMA_VERSION_V2): RunStartedPayloadV2,
    ("RunSucceeded", RUN_EVENT_SCHEMA_VERSION_V2): RunSucceededPayloadV2,
    ("RunFailed", RUN_EVENT_SCHEMA_VERSION_V2): RunFailedPayloadV2,
    ("ModelCallRequested", RUN_EVENT_SCHEMA_VERSION_V2): ModelCallRequestedPayloadV2,
    ("ModelCallStarted", RUN_EVENT_SCHEMA_VERSION_V2): ModelCallStartedPayloadV2,
    ("ModelCallCompleted", RUN_EVENT_SCHEMA_VERSION_V2): ModelCallCompletedPayloadV2,
    ("ModelCallFailed", RUN_EVENT_SCHEMA_VERSION_V2): ModelCallFailedPayloadV2,
    ("ToolCallRequested", RUN_EVENT_SCHEMA_VERSION_V2): ToolCallRequestedPayloadV2,
    ("ToolCallStarted", RUN_EVENT_SCHEMA_VERSION_V2): ToolCallStartedPayloadV2,
    ("ToolCallCompleted", RUN_EVENT_SCHEMA_VERSION_V2): ToolCallCompletedPayloadV2,
    ("ToolCallFailed", RUN_EVENT_SCHEMA_VERSION_V2): ToolCallFailedPayloadV2,
    ("RunCreated", RUN_EVENT_SCHEMA_VERSION_V3): RunCreatedPayloadV3,
    ("RunStarted", RUN_EVENT_SCHEMA_VERSION_V3): RunStartedPayloadV2,
    ("RunSucceeded", RUN_EVENT_SCHEMA_VERSION_V3): RunSucceededPayloadV2,
    ("RunFailed", RUN_EVENT_SCHEMA_VERSION_V3): RunFailedPayloadV2,
    ("ModelCallRequested", RUN_EVENT_SCHEMA_VERSION_V3): ModelCallRequestedPayloadV2,
    ("ModelCallStarted", RUN_EVENT_SCHEMA_VERSION_V3): ModelCallStartedPayloadV2,
    ("ModelCallCompleted", RUN_EVENT_SCHEMA_VERSION_V3): ModelCallCompletedPayloadV2,
    ("ModelCallFailed", RUN_EVENT_SCHEMA_VERSION_V3): ModelCallFailedPayloadV2,
    ("ToolCallRequested", RUN_EVENT_SCHEMA_VERSION_V3): ToolCallRequestedPayloadV2,
    ("ToolCallStarted", RUN_EVENT_SCHEMA_VERSION_V3): ToolCallStartedPayloadV2,
    ("ToolCallCompleted", RUN_EVENT_SCHEMA_VERSION_V3): ToolCallCompletedPayloadV2,
    ("ToolCallFailed", RUN_EVENT_SCHEMA_VERSION_V3): ToolCallFailedPayloadV2,
    ("RunCreated", RUN_EVENT_SCHEMA_VERSION_V4): RunCreatedPayloadV4,
    ("RunStarted", RUN_EVENT_SCHEMA_VERSION_V4): RunStartedPayloadV2,
    ("RunSucceeded", RUN_EVENT_SCHEMA_VERSION_V4): RunSucceededPayloadV2,
    ("RunFailed", RUN_EVENT_SCHEMA_VERSION_V4): RunFailedPayloadV2,
    ("ModelCallRequested", RUN_EVENT_SCHEMA_VERSION_V4): ModelCallRequestedPayloadV2,
    ("ModelCallStarted", RUN_EVENT_SCHEMA_VERSION_V4): ModelCallStartedPayloadV2,
    ("ModelCallCompleted", RUN_EVENT_SCHEMA_VERSION_V4): ModelCallCompletedPayloadV2,
    ("ModelCallFailed", RUN_EVENT_SCHEMA_VERSION_V4): ModelCallFailedPayloadV2,
    ("ToolCallRequested", RUN_EVENT_SCHEMA_VERSION_V4): ToolCallRequestedPayloadV2,
    ("ToolCallStarted", RUN_EVENT_SCHEMA_VERSION_V4): ToolCallStartedPayloadV2,
    ("ToolCallCompleted", RUN_EVENT_SCHEMA_VERSION_V4): ToolCallCompletedPayloadV2,
    ("ToolCallFailed", RUN_EVENT_SCHEMA_VERSION_V4): ToolCallFailedPayloadV2,
}

RUN_EVENT_PAYLOAD_TYPES = MappingProxyType(_PAYLOAD_TYPES)


def parse_run_event_payload(event: Event) -> RunEventPayload:
    """Validate an Event payload against its exact type and schema version."""
    payload_type = RUN_EVENT_PAYLOAD_TYPES[(event.event_type, event.schema_version)]
    return payload_type.model_validate(thaw_json_mapping(event.payload))
