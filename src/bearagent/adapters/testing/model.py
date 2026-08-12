"""Deterministic model adapter for runtime and contract tests."""

from collections.abc import AsyncIterator, Iterable

from bearagent.domain.model import ModelEvent, ModelRequest


class FakeModelProvider:
    """Replay one configured stream and retain Provider-neutral requests."""

    def __init__(
        self,
        events: Iterable[ModelEvent],
        *,
        failure: BaseException | None = None,
        fail_after_events: int | None = None,
    ) -> None:
        self._events = tuple(events)
        self._failure = failure
        self._fail_after_events = (
            len(self._events) if fail_after_events is None else fail_after_events
        )
        if not 0 <= self._fail_after_events <= len(self._events):
            raise ValueError("fail_after_events must select a position in the event stream")
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        for index, event in enumerate(self._events):
            if self._failure is not None and index == self._fail_after_events:
                raise self._failure
            yield event
        if self._failure is not None:
            raise self._failure
