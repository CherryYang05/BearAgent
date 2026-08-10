"""Opaque identifiers shared by BearAgent domain contracts."""

from typing import Protocol, Self, TypeVar
from uuid import uuid4

from pydantic import UUID4, ConfigDict, RootModel


class OpaqueId(RootModel[UUID4]):
    """A UUID4 whose concrete subclass supplies its domain meaning."""

    model_config = ConfigDict(frozen=True)

    @classmethod
    def new(cls) -> Self:
        """Create a new identifier for convenience at composition boundaries."""
        return cls(root=uuid4())

    @classmethod
    def parse(cls, value: str) -> Self:
        """Validate a serialized identifier at a system boundary."""
        return cls.model_validate(value)

    def __str__(self) -> str:
        return str(self.root)


class SessionId(OpaqueId):
    """Identify a conversation container."""


class RunId(OpaqueId):
    """Identify one user-request execution."""


class ActivityId(OpaqueId):
    """Identify one model or tool operation."""


class EventId(OpaqueId):
    """Identify one immutable persisted fact."""


class ArtifactId(OpaqueId):
    """Identify one retrievable Run output."""


class ModelCallId(OpaqueId):
    """Identify one model call independently of provider request IDs."""


class ToolCallId(OpaqueId):
    """Correlate one tool request with its result."""


class CausationId(OpaqueId):
    """Identify the command, Activity, or Event that caused a fact."""


class CorrelationId(OpaqueId):
    """Correlate facts that belong to one diagnostic flow."""


IdT = TypeVar("IdT", bound=OpaqueId)


class IdGenerator(Protocol):
    """Create domain IDs without coupling runtime logic to randomness."""

    def new(self, id_type: type[IdT]) -> IdT: ...


class Uuid4IdGenerator:
    """Production ID generator backed by the Python standard library."""

    def new(self, id_type: type[IdT]) -> IdT:
        return id_type(root=uuid4())
