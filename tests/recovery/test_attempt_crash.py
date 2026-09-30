import json
import subprocess
import sys
from pathlib import Path

import pytest

from bearagent.domain.ids import RunId


@pytest.mark.parametrize(
    "stop_type,occurrence,number,status,calls",
    [
        ("AttemptFailed", 1, 1, "failed", 1),
        ("RecoveryDecisionRecorded", 1, 1, "failed", 1),
        ("AttemptRequested", 3, 2, "requested", 1),
        ("AttemptStarted", 3, 2, "started", 1),
        ("AttemptSucceeded", 2, 2, "succeeded", 2),
    ],
)
def test_process_exit_then_new_process_queries_never_dispatch(
    tmp_path: Path,
    stop_type: str,
    occurrence: int,
    number: int,
    status: str,
    calls: int,
) -> None:
    run_id = RunId.new()
    root = Path(__file__).parents[2]
    child = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.recovery.attempt_crash_child",
            str(tmp_path),
            stop_type,
            str(occurrence),
            str(run_id),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert child.returncode == 91, child.stderr
    marker = tmp_path / "external-calls.txt"
    before = marker.read_bytes()
    assert before.splitlines() == [b"read"] * calls
    for command in ["replay", "check", "attempts"]:
        args = [sys.executable, "-m", "bearagent", "run", command]
        if command != "check":
            args.append(str(run_id))
        inspected = subprocess.run(
            [*args, "--database", str(tmp_path / "events.db"), "--json"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert inspected.returncode == (0 if command == "attempts" else 1), inspected.stderr
        result = json.loads(inspected.stdout)["result"]
        if command == "attempts":
            attempt = result["attempts"][-1]
            assert attempt["number"] == number
            assert attempt["status"] == status
            assert "content" not in inspected.stdout
        if command == "replay":
            assert result["state_format_version"] == 2
            assert result["last_event_type"] == stop_type
            assert result["projection"] == "matched"
    assert marker.read_bytes() == before
