import asyncio

import pytest
from pydantic import ValidationError
from tests.store_fixtures import successful_run_events

from bearagent.adapters.testing import InMemoryEventStore
from bearagent.application.run_queries import RunQueryError, RunQueryService
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import RunId
from bearagent.domain.queries import EventPage, RunInspection


def test_inspect_returns_the_store_projection_without_a_second_state_model() -> None:
    async def exercise() -> None:
        store = InMemoryEventStore()
        events = successful_run_events()
        for event in events:
            await store.append(event)

        result = await RunQueryService(store).inspect(events[0].run_id)

        assert isinstance(result, RunInspection)
        assert result.state == await store.get_run(events[0].run_id)
        assert result.run_id == events[0].run_id
        assert result.artifacts == ()

    asyncio.run(exercise())


def test_events_returns_a_bounded_page_and_cursor() -> None:
    async def exercise() -> None:
        store = InMemoryEventStore()
        events = successful_run_events()
        for event in events:
            await store.append(event)

        page = await RunQueryService(store).events(
            events[0].run_id,
            after_sequence=3,
            limit=2,
        )

        assert isinstance(page, EventPage)
        assert [event.sequence for event in page.events] == [4, 5]
        assert page.after_sequence == 3
        assert page.next_after_sequence == 5
        assert page.has_more is True

        final_page = await RunQueryService(store).events(
            events[0].run_id,
            after_sequence=8,
            limit=2,
        )
        assert [event.sequence for event in final_page.events] == [9]
        assert final_page.next_after_sequence == 9
        assert final_page.has_more is False

    asyncio.run(exercise())


def test_query_rejects_a_missing_run_with_a_stable_safe_error() -> None:
    async def exercise() -> None:
        service = RunQueryService(InMemoryEventStore())

        with pytest.raises(RunQueryError) as captured:
            await service.inspect(RunId.new())

        assert captured.value.info.code is ErrorCode.RUN_NOT_FOUND
        assert captured.value.info.details == {}

    asyncio.run(exercise())


def test_event_page_rejects_cross_run_or_non_contiguous_events() -> None:
    events = successful_run_events()

    with pytest.raises(ValidationError):
        EventPage(
            run_id=RunId.new(),
            after_sequence=0,
            limit=2,
            events=events[:2],
            next_after_sequence=2,
            has_more=True,
        )

    with pytest.raises(ValidationError):
        EventPage(
            run_id=events[0].run_id,
            after_sequence=0,
            limit=2,
            events=(events[0], events[2]),
            next_after_sequence=3,
            has_more=True,
        )


def test_inspect_fails_instead_of_returning_partial_artifacts_above_limit() -> None:
    class OversizedRunStore(InMemoryEventStore):
        def __init__(self) -> None:
            super().__init__()
            self.list_called = False

        async def list_events(
            self,
            run_id: RunId,
            *,
            after_sequence: int = 0,
            limit: int = 1_000,
        ):
            self.list_called = True
            return await super().list_events(
                run_id,
                after_sequence=after_sequence,
                limit=limit,
            )

        async def get_run(self, run_id: RunId):
            state = await super().get_run(run_id)
            assert state is not None
            return state.model_copy(update={"last_sequence": 10_001})

    async def exercise() -> None:
        store = OversizedRunStore()
        events = successful_run_events()
        for event in events:
            await store.append(event)

        with pytest.raises(RunQueryError) as captured:
            await RunQueryService(store).inspect(events[0].run_id)

        assert captured.value.info.code is ErrorCode.QUERY_LIMIT_EXCEEDED
        assert store.list_called is False

    asyncio.run(exercise())
