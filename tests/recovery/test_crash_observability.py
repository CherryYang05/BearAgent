import asyncio
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.store_fixtures import make_event, payload_json, run_created_event

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.application.run_queries import RunQueryService
from bearagent.domain.ids import ActivityId, ModelCallId, RunId
from bearagent.domain.queries import RunInspection
from bearagent.domain.run_events import ModelCallRequestedPayload, RunStartedPayload
from bearagent.domain.runs import ActivityStatus, RunStatus
from bearagent.interfaces.cli.contracts import InspectCommandOutput
from bearagent.ports.store import EventStoreError

REPOSITORY_ROOT = Path(__file__).parents[2]
CHILD_PROCESS = Path(__file__).with_name("crash_observability_child.py")
CRASH_EXIT_CODE = 91
OUTPUT_RELATIVE_PATH = Path("outputs/crash-evidence.txt")
OUTPUT_CONTENT = "committed before process termination\n"
TERMINAL_EVENT_TYPES = frozenset({"RunSucceeded", "RunFailed"})


@dataclass(frozen=True, slots=True)
class CrashExpectation:
    point: str
    last_event_type: str
    activity_status: ActivityStatus
    crash_marker: str
    model_calls: int
    output_committed: bool


CRASH_EXPECTATIONS = (
    CrashExpectation(
        point="k1_after_tool_requested",
        last_event_type="ToolCallRequested",
        activity_status=ActivityStatus.PENDING,
        crash_marker="ToolCallRequested",
        model_calls=1,
        output_committed=False,
    ),
    CrashExpectation(
        point="k2_after_tool_started",
        last_event_type="ToolCallStarted",
        activity_status=ActivityStatus.RUNNING,
        crash_marker="ToolCallStarted",
        model_calls=1,
        output_committed=False,
    ),
    CrashExpectation(
        point="k3_before_replace",
        last_event_type="ToolCallStarted",
        activity_status=ActivityStatus.RUNNING,
        crash_marker="before_replace",
        model_calls=1,
        output_committed=False,
    ),
    CrashExpectation(
        point="k4_after_replace",
        last_event_type="ToolCallStarted",
        activity_status=ActivityStatus.RUNNING,
        crash_marker="after_replace",
        model_calls=1,
        output_committed=True,
    ),
    CrashExpectation(
        point="k6_after_model_started",
        last_event_type="ModelCallStarted",
        activity_status=ActivityStatus.RUNNING,
        crash_marker="ModelCallStarted",
        model_calls=0,
        output_committed=False,
    ),
)


@pytest.mark.parametrize("expectation", CRASH_EXPECTATIONS, ids=lambda item: item.point)
def test_committed_crash_boundary_is_visible_after_process_restart(
    expectation: CrashExpectation,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "events.sqlite3"
    workspace = tmp_path / "workspace"
    crash_marker = tmp_path / "crash.marker"
    model_calls = tmp_path / "model.calls"
    run_id = RunId.new()

    child = subprocess.run(
        (
            sys.executable,
            str(CHILD_PROCESS),
            "--point",
            expectation.point,
            "--database",
            str(database_path),
            "--workspace",
            str(workspace),
            "--run-id",
            str(run_id),
            "--crash-marker",
            str(crash_marker),
            "--model-calls",
            str(model_calls),
        ),
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert child.returncode == CRASH_EXIT_CODE, child.stderr
    assert crash_marker.read_text(encoding="utf-8").splitlines() == [expectation.crash_marker]
    assert _line_count(model_calls) == expectation.model_calls

    inspection, event_types = asyncio.run(_reopen(database_path, run_id))

    assert inspection.state.status is RunStatus.RUNNING
    assert event_types[-1] == expectation.last_event_type
    assert not TERMINAL_EVENT_TYPES.intersection(event_types)
    assert inspection.state.activities[-1].status is expectation.activity_status
    assert inspection.artifacts == ()
    assert inspection.run_fingerprint is not None

    output_path = workspace / OUTPUT_RELATIVE_PATH
    if expectation.output_committed:
        assert output_path.read_text(encoding="utf-8") == OUTPUT_CONTENT
    else:
        assert not output_path.exists()
    if expectation.point == "k3_before_replace":
        assert tuple((workspace / "outputs").glob(".bearagent-*.tmp"))

    calls_before_cli = _line_count(model_calls)
    cli_result = _inspect_with_cli(database_path, run_id)

    assert cli_result.result.state.status is RunStatus.RUNNING
    assert cli_result.result.state.last_sequence == len(event_types)
    assert _line_count(model_calls) == calls_before_cli


def test_k5_projection_failure_rolls_back_event_and_projection_together(tmp_path: Path) -> None:
    database_path = tmp_path / "events.sqlite3"
    run_id = RunId.new()
    created = run_created_event(run_id)
    started = make_event(run_id, 2, "RunStarted", payload_json(RunStartedPayload()))
    requested = make_event(
        run_id,
        3,
        "ModelCallRequested",
        payload_json(
            ModelCallRequestedPayload(
                activity_id=ActivityId.new(),
                model_call_id=ModelCallId.new(),
            )
        ),
    )

    async def inject_failure() -> None:
        store = SqliteEventStore(database_path)
        await store.initialize()
        await store.append(created)
        await store.append(started)
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                CREATE TRIGGER reject_pending_activity
                BEFORE INSERT ON activity_projections
                WHEN NEW.status = 'pending'
                BEGIN
                    SELECT RAISE(ABORT, 'injected projection failure');
                END
                """
            )
        with pytest.raises(EventStoreError, match="projection update failed"):
            await store.append(requested)

    asyncio.run(inject_failure())
    inspection, event_types = asyncio.run(_reopen(database_path, run_id))

    assert event_types == ("RunCreated", "RunStarted")
    assert inspection.state.status is RunStatus.RUNNING
    assert inspection.state.last_sequence == 2
    assert inspection.state.activities == ()

    cli_result = _inspect_with_cli(database_path, run_id)
    assert cli_result.result.state.last_sequence == 2


async def _reopen(
    database_path: Path,
    run_id: RunId,
) -> tuple[RunInspection, tuple[str, ...]]:
    store = SqliteEventStore(database_path)
    await store.initialize()
    events = await store.list_events(run_id)
    inspection = await RunQueryService(store).inspect(run_id)
    return inspection, tuple(event.event_type for event in events)


def _inspect_with_cli(database_path: Path, run_id: RunId) -> InspectCommandOutput:
    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "bearagent",
            "run",
            "inspect",
            str(run_id),
            "--database",
            str(database_path),
            "--json",
        ),
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return InspectCommandOutput.model_validate_json(completed.stdout)


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(path.read_text(encoding="utf-8").splitlines())
