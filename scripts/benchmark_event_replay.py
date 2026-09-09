"""Measure read-only replay of synthetic histories; never open a user's database."""

import asyncio
import json
import platform
import sqlite3
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.adapters.sqlite.replay import SqliteEventReplaySource
from bearagent.application.run_replay import RunReplayService
from bearagent.domain.errors import ErrorInfo
from bearagent.domain.ids import RunId
from bearagent.domain.replay import DEFAULT_REPLAY_LIMITS
from bearagent.ports.replay import EventReplayError


def identity(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012x}"


def seed(path: Path, count: int) -> tuple[RunId, int]:
    """Insert synthetic committed Events directly to exclude append cost from the measurement."""
    run_id = RunId.parse(identity(1))
    asyncio.run(SqliteEventStore(path).initialize())
    payloads: list[tuple[str, dict[str, object]]] = [
        (
            "RunCreated",
            {
                "session_id": identity(2),
                "budget_limits": {
                    "max_model_iterations": 10000,
                    "max_tokens": 10000,
                    "max_cost_microusd": 10000,
                    "max_wall_time_ms": 60000,
                    "max_tool_calls": 0,
                },
            },
        ),
        ("RunStarted", {}),
    ]
    while len(payloads) < count:
        activity = len(payloads) + 100
        common: dict[str, object] = {
            "activity_id": identity(activity),
            "model_call_id": identity(activity + 1),
        }
        payloads.extend(
            [
                ("ModelCallRequested", common),
                ("ModelCallStarted", common),
                (
                    "ModelCallCompleted",
                    {**common, "input_tokens": 1, "output_tokens": 0, "cost_microusd": 0},
                ),
            ]
        )
    rows = [
        (
            identity(i + 20000),
            str(run_id),
            i,
            kind,
            1,
            "2026-09-08T00:00:00+00:00",
            identity(3),
            identity(4),
            json.dumps(payload, separators=(",", ":")),
        )
        for i, (kind, payload) in enumerate(payloads[:count], 1)
    ]
    with sqlite3.connect(path) as connection:
        connection.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return run_id, sum(len(str(value).encode()) for row in rows for value in row)


def main() -> None:
    results: list[dict[str, object]] = []
    for count in (100, 1000, 10000):
        with tempfile.TemporaryDirectory(prefix="bearagent-replay-benchmark-") as temporary:
            path = Path(temporary) / "synthetic.db"
            run_id, raw_bytes = seed(path, count)
            start = time.perf_counter()
            failure: ErrorInfo | None = None
            last_sequence: int | None = None
            try:
                replay = asyncio.run(RunReplayService(SqliteEventReplaySource(path)).replay(run_id))
                last_sequence = replay.state.last_sequence
            except EventReplayError as error:
                failure = error.info
            results.append(
                {
                    "events": count,
                    "stored_field_bytes": raw_bytes,
                    "elapsed_seconds": round(time.perf_counter() - start, 3),
                    "last_sequence": last_sequence,
                    "error_code": failure.code.value if failure else None,
                }
            )
    print(
        json.dumps(
            {
                "measured_at": datetime.now(UTC).isoformat(),
                "python": sys.version.split()[0],
                "platform": platform.system(),
                "machine": platform.machine(),
                "sqlite": sqlite3.sqlite_version,
                "limits": DEFAULT_REPLAY_LIMITS.model_dump(),
                "runs": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
