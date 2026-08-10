"""Framework-independent BearAgent domain types."""

from bearagent.domain.errors import BearAgentError, ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import (
    ActivityId,
    ArtifactId,
    CausationId,
    CorrelationId,
    EventId,
    IdGenerator,
    ModelCallId,
    OpaqueId,
    RunId,
    SessionId,
    ToolCallId,
    Uuid4IdGenerator,
)
from bearagent.domain.messages import (
    Message,
    MessagePart,
    MessageRole,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from bearagent.domain.model import ModelEvent, ModelEventKind, ModelRequest
from bearagent.domain.tools import ToolRequest, ToolResult, ToolStatus

__all__ = [
    "ActivityId",
    "ArtifactId",
    "BearAgentError",
    "CausationId",
    "CorrelationId",
    "ErrorCategory",
    "ErrorCode",
    "Event",
    "EventId",
    "ErrorInfo",
    "IdGenerator",
    "Message",
    "ModelEvent",
    "ModelEventKind",
    "MessagePart",
    "MessageRole",
    "ModelCallId",
    "ModelRequest",
    "OpaqueId",
    "RunId",
    "SessionId",
    "TextPart",
    "ToolCallId",
    "ToolCallPart",
    "ToolRequest",
    "ToolResult",
    "ToolResultPart",
    "ToolStatus",
    "Uuid4IdGenerator",
]
