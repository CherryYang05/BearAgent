"""Provider-neutral model request and event types for P0 test adapters."""

from dataclasses import dataclass
from enum import StrEnum

from bearagent.domain.messages import Message


class ModelEventKind(StrEnum):
    """Kinds emitted by a model provider during P0 tests."""

    TEXT_DELTA = "text_delta"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """A minimal provider-neutral model request."""

    messages: tuple[Message, ...]


@dataclass(frozen=True, slots=True)
class ModelEvent:
    """A minimal provider-neutral streaming event."""

    kind: ModelEventKind
    text: str = ""
