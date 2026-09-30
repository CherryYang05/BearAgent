import asyncio
import json
import sqlite3
from pathlib import Path

import pytest
from tests.attempt_fixtures import retried_read_events
from tests.replay_fixtures import persist, tool_history
from typer.testing import CliRunner

import bearagent.interfaces.cli.main as cli_main
from bearagent.domain.ids import RunId
from bearagent.interfaces.cli.contracts import AttemptsCommandOutput


@pytest.mark.parametrize("legacy", [False, True])
def test_attempts_are_read_only_paginated_and_content_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy: bool
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "data/bearagent.db"
    events = tool_history(4) if legacy else retried_read_events()
    asyncio.run(persist(path, events))
    (path.parent / "config.json").write_text("PRIVATE-KEY invalid config")

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("query constructed execution services")

    monkeypatch.setattr(cli_main, "build_run_services", forbidden)
    with sqlite3.connect(path) as connection:
        before = connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        connection.execute("DELETE FROM run_projections")
    cli = CliRunner()
    args = ["run", "attempts", str(events[0].run_id)]
    first = cli.invoke(cli_main.app, [*args, "--limit", "1", "--json"])
    assert first.exit_code == 0, first.output
    page = AttemptsCommandOutput.model_validate_json(first.stdout).result
    assert page.recording == ("legacy_not_recorded" if legacy else "recorded")
    if not legacy:
        assert page.has_more
        assert page.attempts[0].number == 1
        second = cli.invoke(
            cli_main.app, [*args, "--after-sequence", str(page.next_after_sequence), "--json"]
        )
        assert second.exit_code == 0, second.output
        last = AttemptsCommandOutput.model_validate_json(second.stdout).result
        assert last.attempts[0].number == 2
        assert not last.has_more
    human = cli.invoke(cli_main.app, args)
    assert human.exit_code == 0, human.output
    assert "Read-only" in human.stdout
    for canary in ["PRIVATE-", "docs/index.md", str(tmp_path), "content", "arguments", "objective"]:
        assert canary not in first.stdout
        assert canary not in human.stdout
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM events ORDER BY sequence").fetchall() == before
        assert connection.execute("SELECT count(*) FROM run_projections").fetchone() == (0,)


def test_attempts_missing_database_and_invalid_limits(tmp_path: Path) -> None:
    path = tmp_path / "missing/secret.db"
    cli = CliRunner()
    args = ["run", "attempts", str(RunId.new()), "--database", str(path), "--json"]
    result = cli.invoke(cli_main.app, args)
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "persistence_error"
    assert str(path) not in result.stdout
    for value in ["0", "1001"]:
        assert cli.invoke(cli_main.app, [*args, "--limit", value]).exit_code == 2
    assert not path.parent.exists()
