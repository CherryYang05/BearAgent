"""Public schema registry used by compatibility tests and generated reference."""

from pydantic import BaseModel

from bearagent.domain.agent import (
    AgentConfig,
    ContextBuildReport,
    ContextBuildResult,
    ModelPricing,
    RunInput,
    RunResult,
)
from bearagent.domain.artifacts import Artifact
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
from bearagent.domain.model import (
    ModelCompleted,
    ModelRequest,
    ModelTextDelta,
    ModelToolCall,
    ModelToolDefinition,
    ModelUsage,
)
from bearagent.domain.run_events import (
    ModelCallCompletedPayload,
    ModelCallCompletedPayloadV2,
    ModelCallFailedPayload,
    ModelCallFailedPayloadV2,
    ModelCallRequestedPayload,
    ModelCallRequestedPayloadV2,
    ModelCallStartedPayload,
    ModelCallStartedPayloadV2,
    RunCreatedPayload,
    RunCreatedPayloadV2,
    RunFailedPayload,
    RunFailedPayloadV2,
    RunStartedPayload,
    RunStartedPayloadV2,
    RunSucceededPayload,
    RunSucceededPayloadV2,
    ToolCallCompletedPayload,
    ToolCallCompletedPayloadV2,
    ToolCallFailedPayload,
    ToolCallFailedPayloadV2,
    ToolCallRequestedPayload,
    ToolCallRequestedPayloadV2,
    ToolCallStartedPayload,
    ToolCallStartedPayloadV2,
)
from bearagent.domain.runs import (
    ActivityState,
    BudgetExhaustion,
    BudgetLimits,
    BudgetUsage,
    RunState,
)
from bearagent.domain.tools import (
    PolicyDecision,
    PreparedToolRequest,
    ToolExecutionRecord,
    ToolRequest,
    ToolResult,
    ToolSpec,
)

PUBLIC_SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    ActivityId,
    ActivityState,
    AgentConfig,
    Artifact,
    ArtifactId,
    BudgetExhaustion,
    BudgetLimits,
    BudgetUsage,
    CausationId,
    CorrelationId,
    ContextBuildResult,
    ContextBuildReport,
    ErrorInfo,
    Event,
    EventId,
    Message,
    ModelCompleted,
    ModelCallCompletedPayload,
    ModelCallCompletedPayloadV2,
    ModelCallFailedPayload,
    ModelCallFailedPayloadV2,
    ModelCallId,
    ModelCallRequestedPayload,
    ModelCallRequestedPayloadV2,
    ModelCallStartedPayload,
    ModelCallStartedPayloadV2,
    ModelRequest,
    ModelTextDelta,
    ModelToolCall,
    ModelToolDefinition,
    ModelUsage,
    ModelPricing,
    PolicyDecision,
    PreparedToolRequest,
    RunId,
    RunCreatedPayload,
    RunCreatedPayloadV2,
    RunFailedPayload,
    RunFailedPayloadV2,
    RunInput,
    RunStartedPayload,
    RunStartedPayloadV2,
    RunState,
    RunResult,
    RunSucceededPayload,
    RunSucceededPayloadV2,
    SessionId,
    ToolCallId,
    ToolCallCompletedPayload,
    ToolCallCompletedPayloadV2,
    ToolCallFailedPayload,
    ToolCallFailedPayloadV2,
    ToolCallRequestedPayload,
    ToolCallRequestedPayloadV2,
    ToolCallStartedPayload,
    ToolCallStartedPayloadV2,
    ToolExecutionRecord,
    ToolRequest,
    ToolResult,
    ToolSpec,
)


def public_domain_schemas() -> dict[str, dict[str, object]]:
    """Return deterministic JSON schemas keyed by domain model name."""
    return {
        model.__name__: model.model_json_schema(mode="serialization")
        for model in sorted(PUBLIC_SCHEMA_MODELS, key=lambda item: item.__name__)
    }
