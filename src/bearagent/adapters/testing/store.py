"""In-memory event store with strict per-Run ordering."""

from collections.abc import Iterator
from heapq import nsmallest

from bearagent._bounded_read import ReadControl, run_bounded_read
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import EventId, RunId
from bearagent.domain.replay import (
    DEFAULT_REPLAY_LIMITS,
    DEFAULT_SCAN_RUNS,
    MAX_SCAN_RUNS,
    EventReplaySnapshot,
    EventRunPage,
    ProjectionAvailability,
    ReplayLimits,
)
from bearagent.domain.runs import RunState
from bearagent.ports.replay import replay_error
from bearagent.ports.store import (
    DEFAULT_EVENT_QUERY_LIMIT,
    EventStoreConflictError,
    validate_event_query,
)
from bearagent.runtime.reducer import reduce_event, validate_event_history


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
        validate_event_history(events, event)
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

    async def read_run_events(
        self, run_id: RunId, *, limits: ReplayLimits = DEFAULT_REPLAY_LIMITS
    ) -> EventReplaySnapshot:
        events = self._events_by_run.get(run_id, ())
        if not events:
            raise replay_error(ErrorCode.RUN_NOT_FOUND)
        if len(events) > limits.max_events:
            raise replay_error(ErrorCode.QUERY_LIMIT_EXCEEDED)
        # Capture before yielding: append is synchronous within this adapter's event loop.
        captured = tuple(events)
        projection = self._states_by_run.get(run_id)

        def read(control: ReadControl) -> EventReplaySnapshot:
            size = 0
            for event in captured:
                control.check()
                size += len(event.model_dump_json().encode("utf-8"))
                if size > limits.max_bytes:
                    raise replay_error(ErrorCode.QUERY_LIMIT_EXCEEDED)
            return EventReplaySnapshot(
                run_id=run_id,
                events=captured,
                projection=projection,
                projection_availability=(
                    ProjectionAvailability.AVAILABLE
                    if projection is not None
                    else ProjectionAvailability.MISSING
                ),
            )

        return await run_bounded_read(read, timeout_ms=limits.timeout_ms)

    async def list_event_run_ids(
        self,
        *,
        after_run_id: RunId | None = None,
        limit: int = DEFAULT_SCAN_RUNS,
        limits: ReplayLimits = DEFAULT_REPLAY_LIMITS,
    ) -> EventRunPage:
        if type(limit) is not int or not 1 <= limit <= MAX_SCAN_RUNS:
            raise replay_error(ErrorCode.INVALID_INPUT)
        identities = tuple(run_id for run_id, events in self._events_by_run.items() if events)

        def read(control: ReadControl) -> EventRunPage:
            def keys() -> Iterator[str]:
                for run_id in identities:
                    control.check()
                    if after_run_id is None or str(run_id) > str(after_run_id):
                        yield str(run_id)

            ordered = nsmallest(limit + 1, keys())
            ids = tuple(RunId.parse(value) for value in ordered[:limit])
            return EventRunPage(
                after_run_id=after_run_id,
                limit=limit,
                run_ids=ids,
                next_after_run_id=ids[-1] if ids else after_run_id,
                has_more=len(ordered) > limit,
            )

        return await run_bounded_read(read, timeout_ms=limits.timeout_ms)
