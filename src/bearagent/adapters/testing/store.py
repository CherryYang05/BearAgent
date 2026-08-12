"""In-memory event store with strict per-Run ordering."""

from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import EventId, RunId
from bearagent.domain.runs import RunState
from bearagent.ports.store import (
    DEFAULT_EVENT_QUERY_LIMIT,
    EventStoreConflictError,
    validate_event_query,
)
from bearagent.runtime.reducer import reduce_event


class EventSequenceError(EventStoreConflictError):
    """Backward-compatible name for an immutable Event identity conflict."""


class InMemoryEventStore:
    """Store immutable events for deterministic tests.

    This adapter is deliberately small and single-process. It is not the
    production persistence implementation promised by P1.
    """

    def __init__(self) -> None:
        self._events_by_run: dict[RunId, list[Event]] = {}
        self._event_ids: set[EventId] = set()
        self._states_by_run: dict[RunId, RunState] = {}

    async def append(self, event: Event) -> RunState:
        if event.event_id in self._event_ids:
            raise EventSequenceError(
                ErrorInfo(
                    category=ErrorCategory.PERSISTENCE,
                    code=ErrorCode.PERSISTENCE_ERROR,
                    message="Event identity already exists.",
                    retryable=False,
                )
            )

        events = self._events_by_run.setdefault(event.run_id, [])
        previous_state = self._states_by_run.get(event.run_id)
        state = reduce_event(previous_state, event)

        events.append(event)
        self._event_ids.add(event.event_id)
        self._states_by_run[event.run_id] = state
        return state

    async def list_events(
        self,
        run_id: RunId,
        *,
        after_sequence: int = 0,
        limit: int = DEFAULT_EVENT_QUERY_LIMIT,
    ) -> tuple[Event, ...]:
        validate_event_query(after_sequence, limit)
        return tuple(
            event
            for event in self._events_by_run.get(run_id, ())
            if event.sequence > after_sequence
        )[:limit]

    async def get_run(self, run_id: RunId) -> RunState | None:
        return self._states_by_run.get(run_id)
