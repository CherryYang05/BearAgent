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

PUBLIC_SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    ActivityId,
    ArtifactId,
    CausationId,
    CorrelationId,
    ErrorInfo,
    Event,
    EventId,
    Message,
    ModelCallId,
    RunId,
    SessionId,
    ToolCallId,
)


def public_domain_schemas() -> dict[str, dict[str, object]]:
    """Return deterministic JSON schemas keyed by domain model name."""
    return {
        model.__name__: model.model_json_schema(mode="serialization")
        for model in sorted(PUBLIC_SCHEMA_MODELS, key=lambda item: item.__name__)
    }
