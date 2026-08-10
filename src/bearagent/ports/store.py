"""Durable event store port."""

from typing import Protocol

from bearagent.domain.events import Event
from bearagent.domain.ids import RunId


class EventStore(Protocol):
    """Append and query immutable events for one Run."""

    async def append(self, event: Event) -> None: ...

    async def list_events(self, run_id: RunId) -> tuple[Event, ...]: ...
