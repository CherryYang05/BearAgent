import asyncio
import json
import sqlite3
from pathlib import Path

from tests.store_fixtures import run_created_event
from typer.testing import CliRunner

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.domain.ids import RunId
from bearagent.interfaces.cli.main import app

runner = CliRunner()


def test_invalid_profile_does_not_echo_secret_fields_or_host_paths(tmp_path: Path) -> None:
    secret = "private-profile-secret-value"
    profile_path = tmp_path / "sensitive-profile-name.json"
    profile_path.write_text(json.dumps({"api_key": secret}), encoding="utf-8")
    database_path = tmp_path / "must-not-be-created.db"

    result = runner.invoke(
        app,
        [
            "run",
            "objective that must not be persisted",
            "--profile",
            str(profile_path),
            "--workspace",
            str(tmp_path),
            "--database",
            str(database_path),
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_input"
    assert secret not in result.output
    assert str(profile_path) not in result.output
    assert not database_path.exists()


def test_corrupt_event_query_returns_only_safe_persistence_error(tmp_path: Path) -> None:
    database_path = tmp_path / "private-database-name.sqlite3"
    event = run_created_event(RunId.new())

    async def seed() -> None:
        store = SqliteEventStore(database_path)
        await store.initialize()
        await store.append(event)

    asyncio.run(seed())
    sensitive = "secret-corrupt-event-payload"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE event_id = ?",
            (sensitive, str(event.event_id)),
        )

    result = runner.invoke(
        app,
        ["run", "events", str(event.run_id), "--database", str(database_path), "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["category"] == "persistence"
    assert sensitive not in result.output
    assert str(database_path) not in result.output
    assert "SELECT" not in result.output


def test_future_database_migration_fails_without_schema_details(tmp_path: Path) -> None:
    database_path = tmp_path / "future.sqlite3"
    asyncio.run(SqliteEventStore(database_path).initialize())
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO schema_migrations(version, name, checksum) VALUES (?, ?, ?)",
            (2, "private-future-migration.sql", "a" * 64),
        )

    result = runner.invoke(
        app,
        ["run", "inspect", str(RunId.new()), "--database", str(database_path), "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["category"] == "persistence"
    assert "private-future-migration" not in result.output
    assert str(database_path) not in result.output
