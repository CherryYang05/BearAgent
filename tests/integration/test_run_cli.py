import json
import os
from pathlib import Path

import pytest
from tests.agent_loop_fixtures import agent_config, agent_settings, budget_limits
from typer.testing import CliRunner

import bearagent.interfaces.cli.main as cli_main
from bearagent.adapters.testing import FakeModelProvider, ScriptedFakeModelProvider
from bearagent.bootstrap import RunServices, build_run_services
from bearagent.domain.agent import RunProfile, RunProfileV2
from bearagent.domain.model import ModelCompleted, ModelFinishReason, ModelTextDelta, ModelUsage
from bearagent.interfaces.cli.main import app
from bearagent.ports.model import ModelProvider

runner = CliRunner()


def test_fake_provider_cli_run_then_inspect_and_page_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_path = tmp_path / "profile.json"
    database_path = tmp_path / "data" / "bearagent.db"
    profile = RunProfile(
        agent_config=agent_config(),
        budget_limits=budget_limits(),
    )
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json")),
        encoding="utf-8",
    )
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelTextDelta(text="The offline task is complete."),
                ModelCompleted(
                    provider_request_id="fake-response-1",
                    model="test-model",
                    finish_reason=ModelFinishReason.STOP,
                    usage=ModelUsage(input_tokens=8, output_tokens=6),
                ),
            )
        ]
    )
    _inject_provider(monkeypatch, provider)
    objective = "private objective marker"

    run = runner.invoke(
        app,
        [
            "run",
            "--json",
            objective,
            "--profile",
            str(profile_path),
            "--workspace",
            str(tmp_path),
            "--database",
            str(database_path),
        ],
    )

    assert run.exit_code == 0, run.output
    run_payload = json.loads(run.stdout)
    assert run_payload["schema_version"] == 1
    assert run_payload["command"] == "run"
    assert run_payload["result"]["final_text"] == "The offline task is complete."
    run_id = run_payload["result"]["run_id"]
    assert "Allocated Run ID:" in run.stderr

    inspection = runner.invoke(
        app,
        ["run", "inspect", run_id, "--database", str(database_path), "--json"],
    )
    assert inspection.exit_code == 0, inspection.output
    inspection_payload = json.loads(inspection.stdout)
    assert inspection_payload["command"] == "inspect"
    assert inspection_payload["result"]["state"] == run_payload["result"]["state"]

    human_events = runner.invoke(
        app,
        ["run", "events", run_id, "--database", str(database_path), "--limit", "2"],
    )
    assert human_events.exit_code == 0, human_events.output
    assert "has_more=true" in human_events.stdout
    assert objective not in human_events.stdout

    event_page = runner.invoke(
        app,
        [
            "run",
            "events",
            run_id,
            "--database",
            str(database_path),
            "--after-sequence",
            "2",
            "--limit",
            "10",
            "--json",
        ],
    )
    assert event_page.exit_code == 0, event_page.output
    event_payload = json.loads(event_page.stdout)
    assert event_payload["command"] == "events"
    assert event_payload["result"]["events"][0]["sequence"] == 3
    assert event_payload["result"]["has_more"] is False


def test_run_group_preserves_inspect_and_rejects_invalid_ids_as_safe_json(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "missing.db"

    result = runner.invoke(
        app,
        ["run", "inspect", "not-a-uuid", "--database", str(database_path), "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["command"] == "inspect"
    assert payload["error"]["code"] == "invalid_input"
    assert not database_path.exists()


def test_terminal_provider_failure_is_safe_json_and_exit_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_path = tmp_path / "profile.json"
    profile = RunProfile(
        agent_config=agent_config(),
        budget_limits=budget_limits(),
    )
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json")),
        encoding="utf-8",
    )
    secret = "raw-provider-secret"
    _inject_provider(monkeypatch, FakeModelProvider((), failure=RuntimeError(secret)))

    result = runner.invoke(
        app,
        [
            "run",
            "must fail safely",
            "--profile",
            str(profile_path),
            "--workspace",
            str(tmp_path),
            "--database",
            str(tmp_path / "events.db"),
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["result"]["state"]["status"] == "failed"
    assert payload["result"]["state"]["terminal_error"]["code"] == "provider_error"
    assert secret not in result.output


def test_zero_model_budget_fails_as_a_durable_run_without_provider_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    profile_path = tmp_path / "profile.json"
    profile = RunProfile(
        agent_config=agent_config(),
        budget_limits=budget_limits(max_model_iterations=0),
    )
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json")),
        encoding="utf-8",
    )
    database_path = tmp_path / "events.db"

    result = runner.invoke(
        app,
        [
            "run",
            "must stop before a model call",
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
    assert payload["result"]["state"]["status"] == "failed"
    assert payload["result"]["state"]["terminal_error"]["code"] == "budget_exhausted"
    assert payload["result"]["state"]["budget_usage"]["model_iterations"] == 0
    assert database_path.is_file()


def test_missing_provider_credentials_are_a_safe_durable_run_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    profile_path = tmp_path / "profile.json"
    profile = RunProfile(
        agent_config=agent_config(),
        budget_limits=budget_limits(),
    )
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json")),
        encoding="utf-8",
    )
    database_path = tmp_path / "events.db"

    result = runner.invoke(
        app,
        [
            "run",
            "must report missing credentials safely",
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
    terminal_error = payload["result"]["state"]["terminal_error"]
    assert terminal_error["code"] == "provider_authentication"
    assert terminal_error["message"] == "Model Provider credentials are not configured."
    assert "OPENAI_API_KEY" not in result.output
    assert database_path.is_file()


def test_blank_objective_fails_before_database_or_provider_setup(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile = RunProfile(
        agent_config=agent_config(),
        budget_limits=budget_limits(),
    )
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json")),
        encoding="utf-8",
    )
    database_path = tmp_path / "must-not-be-created.db"

    result = runner.invoke(
        app,
        [
            "run",
            "   ",
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
    assert json.loads(result.stdout)["error"]["code"] == "invalid_input"
    assert not database_path.exists()


def test_v2_cli_rejects_missing_direct_key_before_database_creation(
    tmp_path: Path,
) -> None:
    secret = "must-not-appear"
    profile = RunProfileV2(
        provider_id="primary",
        agent_config=agent_settings(),
        budget_limits=budget_limits(),
    )
    profile_path = tmp_path / "profile-v2.json"
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json")),
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": [
                    {
                        "provider_id": "primary",
                        "name": "Private Provider",
                        "protocol": "openai_chat_completions",
                        "base_url": "https://private-provider.test/v1",
                        "models": [{"model_id": "test-model"}],
                        "default_model": "test-model",
                        "unexpected_secret": secret,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    database_path = tmp_path / "events.db"

    result = runner.invoke(
        app,
        [
            "run",
            "reject invalid provider configuration",
            "--profile",
            str(profile_path),
            "--config",
            str(config_path),
            "--workspace",
            str(tmp_path),
            "--database",
            str(database_path),
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "invalid_input"
    assert secret not in result.output
    assert not database_path.exists()


def _inject_provider(
    monkeypatch: pytest.MonkeyPatch,
    provider: ModelProvider,
) -> None:
    async def build_with_fake(
        *,
        profile_path: str | os.PathLike[str],
        config_path: str | os.PathLike[str],
        workspace_path: str | os.PathLike[str],
        database_path: str | os.PathLike[str],
    ) -> RunServices:
        return await build_run_services(
            profile_path=profile_path,
            config_path=config_path,
            workspace_path=workspace_path,
            database_path=database_path,
            model_provider=provider,
        )

    monkeypatch.setattr(cli_main, "build_run_services", build_with_fake)
