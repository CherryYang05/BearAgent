import asyncio
from pathlib import Path

from tests.agent_loop_fixtures import (
    TickingClock,
    agent_run_input,
    model_completed,
    tool_executor,
)

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.adapters.testing import ScriptedFakeModelProvider
from bearagent.application.agent_loop import AgentLoop
from bearagent.application.run_queries import RunQueryService
from bearagent.domain.model import ModelFinishReason, ModelTextDelta
from bearagent.domain.providers import ModelProtocol, ProviderSelection
from bearagent.domain.run_events import RUN_EVENT_SCHEMA_VERSION_V3


def test_sqlite_reopen_preserves_v3_provider_selection(tmp_path: Path) -> None:
    database_path = tmp_path / "events.sqlite3"
    selection = ProviderSelection(
        provider_id="primary",
        config_version="2026-08-22",
        protocol=ModelProtocol.OPENAI_RESPONSES,
    )
    provider = ScriptedFakeModelProvider(
        (
            (
                ModelTextDelta(text="Done."),
                model_completed(ModelFinishReason.STOP),
            ),
        )
    )

    async def exercise() -> None:
        store = SqliteEventStore(database_path)
        await store.initialize()
        result = await AgentLoop(
            model_provider=provider,
            event_store=store,
            tool_executor=tool_executor(),
            clock=TickingClock(),
            provider_selection=selection,
        ).run(agent_run_input())

        reopened = SqliteEventStore(database_path)
        await reopened.initialize()
        inspection = await RunQueryService(reopened).inspect(result.run_id)
        events = await reopened.list_events(result.run_id)

        assert inspection.provider_selection == selection
        assert all(event.schema_version == RUN_EVENT_SCHEMA_VERSION_V3 for event in events)

    asyncio.run(exercise())
