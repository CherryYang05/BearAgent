"""Deterministic model adapter for runtime tests."""

from collections.abc import AsyncIterator, Iterable

from bearagent.domain.model import ModelEvent, ModelRequest


class FakeModelProvider:
    """Return configured events and retain requests for assertions."""

    def __init__(self, events: Iterable[ModelEvent]) -> None:
        self._events = tuple(events)
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        for event in self._events:
            yield event
