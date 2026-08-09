"""In-memory event store with strict per-Run ordering."""

from bearagent.domain.events import Event


class EventSequenceError(ValueError):
    """Raised when an event would break append-only Run ordering."""


class InMemoryEventStore:
    """Store immutable events for deterministic tests.

    This adapter is deliberately small and single-process. It is not the
    production persistence implementation promised by P1.
    """

    def __init__(self) -> None:
        self._events_by_run: dict[str, list[Event]] = {}
        self._event_ids: set[str] = set()

    async def append(self, event: Event) -> None:
        if event.event_id in self._event_ids:
            raise EventSequenceError(f"duplicate event_id: {event.event_id}")

        events = self._events_by_run.setdefault(event.run_id, [])
        expected_sequence = len(events) + 1
        if event.sequence != expected_sequence:
            raise EventSequenceError(
                f"run {event.run_id!r} expected sequence {expected_sequence}, "
                f"received {event.sequence}"
            )

        events.append(event)
        self._event_ids.add(event.event_id)

    async def list_events(self, run_id: str) -> tuple[Event, ...]:
        return tuple(self._events_by_run.get(run_id, ()))
