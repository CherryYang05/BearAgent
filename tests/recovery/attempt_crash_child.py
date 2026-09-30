"""Terminate after an Attempt ledger commit; external counters are test truth only."""

import asyncio
import os
import sys
from pathlib import Path

from tests.agent_loop_fixtures import agent_run_input, run_fingerprint
from tests.integration.test_attempt_execution import FailOnceRead, ManualClock, read_provider

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.application.agent_loop import AgentLoop
from bearagent.domain.attempts import RetryPolicy
from bearagent.domain.events import Event
from bearagent.domain.ids import RunId
from bearagent.domain.runs import RunState
from bearagent.domain.tools import PreparedToolRequest, ToolResult
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry


async def main() -> None:
    directory, stop_type, stop_occurrence, identity = sys.argv[1:]
    root = Path(directory)
    marker = root / "external-calls.txt"
    store = SqliteEventStore(root / "events.db")
    await store.initialize()

    class MarkedRead(FailOnceRead):
        async def execute(self, request: PreparedToolRequest) -> ToolResult:
            with marker.open("a", encoding="utf-8") as output:
                output.write("read\n")
                output.flush()
                os.fsync(output.fileno())
            return await super().execute(request)

    class CrashStore:
        occurrences = 0

        async def append(self, event: Event) -> RunState:
            state = await store.append(event)
            if event.event_type == stop_type:
                self.occurrences += 1
                if self.occurrences == int(stop_occurrence):
                    os._exit(91)
            return state

        async def list_events(
            self, run_id: RunId, *, after_sequence: int = 0, limit: int = 1000
        ) -> tuple[Event, ...]:
            return await store.list_events(run_id, after_sequence=after_sequence, limit=limit)

        async def get_run(self, run_id: RunId) -> RunState | None:
            return await store.get_run(run_id)

    tool, clock = MarkedRead(), ManualClock()
    await AgentLoop(
        model_provider=read_provider(),
        event_store=CrashStore(),
        tool_executor=ToolExecutor(ToolRegistry([tool]), FixedToolPolicy([tool.spec.name])),
        run_fingerprint=run_fingerprint(),
        clock=clock,
        sleep=clock.sleep,
        random_int=lambda low, high: 0,
        retry_policy=RetryPolicy(max_attempts=3),
    ).run(agent_run_input(), run_id=RunId.parse(identity))


if __name__ == "__main__":
    asyncio.run(main())
