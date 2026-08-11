"""Public schema registry used by compatibility tests and generated reference."""

from pydantic import BaseModel

from bearagent.domain.errors import ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import (
    ActivityId,
    ArtifactId,
    CausationId,
    CorrelationId,
    EventId,
    ModelCallId,
    RunId,
    SessionId,
    ToolCallId,
)
from bearagent.domain.messages import Message
from bearagent.domain.run_events import (
    ModelCallCompletedPayload,
    ModelCallFailedPayload,
    ModelCallRequestedPayload,
    ModelCallStartedPayload,
    RunCreatedPayload,
    RunFailedPayload,
    RunStartedPayload,
    RunSucceededPayload,
    ToolCallCompletedPayload,
    ToolCallFailedPayload,
    ToolCallRequestedPayload,
    ToolCallStartedPayload,
)
from bearagent.domain.runs import (
    ActivityState,
    BudgetExhaustion,
    BudgetLimits,
    BudgetUsage,
    RunState,
)

PUBLIC_SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    ActivityId,
    ActivityState,
    ArtifactId,
    BudgetExhaustion,
    BudgetLimits,
    BudgetUsage,
    CausationId,
    CorrelationId,
    ErrorInfo,
    Event,
    EventId,
    Message,
    ModelCallCompletedPayload,
    ModelCallFailedPayload,
    ModelCallId,
    ModelCallRequestedPayload,
    ModelCallStartedPayload,
    RunId,
    RunCreatedPayload,
    RunFailedPayload,
    RunStartedPayload,
    RunState,
    RunSucceededPayload,
    SessionId,
    ToolCallId,
    ToolCallCompletedPayload,
    ToolCallFailedPayload,
    ToolCallRequestedPayload,
    ToolCallStartedPayload,
)


def public_domain_schemas() -> dict[str, dict[str, object]]:
    """Return deterministic JSON schemas keyed by domain model name."""
    return {
        model.__name__: model.model_json_schema(mode="serialization")
        for model in sorted(PUBLIC_SCHEMA_MODELS, key=lambda item: item.__name__)
    }
