import asyncio
import json
import sqlite3
from pathlib import Path

import pytest
from tests.replay_fixtures import persist, tool_history, versioned_history
from tests.store_fixtures import failed_run_event
from typer.testing import CliRunner

import bearagent.interfaces.cli.main as cli_main
from bearagent.domain.ids import RunId
from bearagent.interfaces.cli.contracts import CheckCommandOutput, ReplayCommandOutput

runner = CliRunner()


@pytest.mark.parametrize("json_output", (False, True))
def test_replay_and_check_only_show_safe_facts_without_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    json_output: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "data" / "bearagent.db"
    events = tool_history(4)
    asyncio.run(persist(path, events))
    config = path.parent / "config.json"
    config.write_text("INVALID CONFIG PRIVATE-KEY", encoding="utf-8")

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("execution services must not be constructed")

    monkeypatch.setattr(cli_main, "build_run_services", forbidden)
    for args in (["replay", str(events[0].run_id)], ["check"]):
        result = runner.invoke(cli_main.app, ["run", *args, *(["--json"] if json_output else [])])
        assert result.exit_code == 1, result.output
        assert str(events[0].run_id) in result.stdout
        for sensitive in (
            "PRIVATE-OBJECTIVE",
            "PRIVATE-PATH",
            "PRIVATE-RESULT",
            "PRIVATE-KEY",
            str(tmp_path),
        ):
            assert sensitive not in result.output
        if json_output and args[0] == "replay":
            assert ReplayCommandOutput.model_validate_json(result.stdout).result.last_sequence == 5
        if json_output and args[0] == "check":
            assert CheckCommandOutput.model_validate_json(result.stdout).result.scanned_count == 1
        if not json_output:
            assert "Read-only" in result.stdout


@pytest.mark.parametrize("command", ("replay", "check"))
def test_nonexistent_database_is_not_created(tmp_path: Path, command: str) -> None:
    path = tmp_path / "missing" / "secret.db"
    args = [
        "run",
        command,
        *([str(RunId.new())] if command == "replay" else []),
        "--database",
        str(path),
        "--json",
    ]
    result = runner.invoke(cli_main.app, args)
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "persistence_error"
    assert not path.parent.exists()
    assert str(path) not in result.output


def test_json_reports_healthy_anomaly_and_corrupt_history_exit_codes(tmp_path: Path) -> None:
    path = tmp_path / "events.db"
    events = versioned_history(4)
    asyncio.run(persist(path, events))
    for mutation, code in (
        (None, 0),
        ("DELETE FROM run_projections", 1),
        ("DELETE FROM events WHERE sequence=2", 2),
    ):
        if mutation:
            with sqlite3.connect(path) as connection:
                connection.execute(mutation)
        for args in (["replay", str(events[0].run_id)], ["check"]):
            result = runner.invoke(cli_main.app, ["run", *args, "--database", str(path), "--json"])
            assert result.exit_code == code, result.output
            assert json.loads(result.stdout)["command"] == args[0]


def test_historical_error_message_does_not_leak_from_state_or_projection(tmp_path: Path) -> None:
    path = tmp_path / "events.db"
    events = versioned_history(1)[:2]
    asyncio.run(persist(path, (*events, failed_run_event(events[0].run_id, 3, "PRIVATE-ERROR"))))
    for args in (["replay", str(events[0].run_id)], ["check"]):
        result = runner.invoke(cli_main.app, ["run", *args, "--database", str(path), "--json"])
        assert result.exit_code == 0, result.output
        assert "PRIVATE-ERROR" not in result.output


@pytest.mark.parametrize(
    "args", (["replay", "not-a-uuid"], ["check", "--after-run-id", "not-a-uuid"])
)
def test_invalid_identity_is_safe_json(args: list[str]) -> None:
    result = runner.invoke(cli_main.app, ["run", *args, "--json"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "invalid_input"
    assert "not-a-uuid" not in result.output


@pytest.mark.parametrize("objective", ("replay", "check"))
def test_query_names_can_still_be_escaped_objectives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    objective: str,
) -> None:
    # Missing local config fails in execution setup; it must not run the query command.
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli_main.app, ["run", "--json", "--", objective])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["command"] == "run"
