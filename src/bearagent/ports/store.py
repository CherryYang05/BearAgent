"""Provider- and adapter-neutral durable EventStore contract."""

from typing import Protocol

from bearagent.domain.errors import BearAgentError
from bearagent.domain.events import Event
from bearagent.domain.ids import RunId
from bearagent.domain.runs import RunState

DEFAULT_EVENT_QUERY_LIMIT = 1_000
MAX_EVENT_QUERY_LIMIT = 10_000
MAX_EVENT_SEQUENCE = 9_223_372_036_854_775_807


class EventStoreError(BearAgentError):
    """Safe base failure for EventStore boundaries."""


class EventStoreConflictError(EventStoreError):
    """An immutable Event identity conflicts with a committed fact."""


class EventStoreCorruptionError(EventStoreError):
    """Persisted Event or projection data cannot be trusted."""


class EventStoreMigrationError(EventStoreError):
    """The durable schema cannot be safely initialized or upgraded."""


class EventStoreNotInitializedError(EventStoreError):
    """The configured store has not been explicitly initialized."""


def validate_event_query(after_sequence: object, limit: object) -> None:
    """Reject unbounded or ambiguously typed Event queries."""
    if (
        isinstance(after_sequence, bool)
        or not isinstance(after_sequence, int)
        or not 0 <= after_sequence <= MAX_EVENT_SEQUENCE
    ):
        raise ValueError("after_sequence must be an integer between 0 and 2^63-1")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_EVENT_QUERY_LIMIT
    ):
        raise ValueError(f"limit must be an integer between 1 and {MAX_EVENT_QUERY_LIMIT}")


class EventStore(Protocol):
    """Atomically append immutable facts and query their Run projection."""

    async def append(self, event: Event) -> RunState: ...

    async def list_events(
        self,
        run_id: RunId,
        *,
        after_sequence: int = 0,
        limit: int = DEFAULT_EVENT_QUERY_LIMIT,
    ) -> tuple[Event, ...]: ...

    async def get_run(self, run_id: RunId) -> RunState | None: ...
