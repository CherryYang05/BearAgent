import json
import os
from pathlib import Path

import pytest
from tests.agent_loop_fixtures import model_completed
from typer.testing import CliRunner

import bearagent.bootstrap as bootstrap
import bearagent.local_setup as setup
from bearagent.adapters.testing import FakeModelProvider
from bearagent.configuration import ProviderConfig
from bearagent.domain.model import ModelFinishReason, ModelTextDelta
from bearagent.interfaces.cli.main import app
from bearagent.ports.model import ModelProvider

runner = CliRunner()


def complete_config(root: Path) -> None:
    path = root / "data" / "config.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    provider = content["providers"][0]
    provider["api_key"] = "synthetic-setup-secret"
    provider["base_url"] = "https://api.example.com/v1"
    provider["models"] = [{"model_id": "test-model"}]
    provider["default_model"] = "test-model"
    path.write_text(json.dumps(content), encoding="utf-8")


def test_init_check_run_and_query_use_defaults_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    before = runner.invoke(app, ["doctor", "--check-config", "--json"])
    assert before.exit_code == 1
    assert json.loads(before.stdout)["configuration_ready"] is False
    assert not (tmp_path / "data" / "bearagent.db").exists()
    complete_config(tmp_path)
    provider = FakeModelProvider(
        (ModelTextDelta(text="done"), model_completed(ModelFinishReason.STOP))
    )
    constructions: list[str] = []

    def build(selected: ProviderConfig) -> ModelProvider:
        constructions.append(selected.provider_id)
        return provider

    monkeypatch.setattr(bootstrap, "build_model_provider", build)
    checked = runner.invoke(app, ["doctor", "--check-config", "--json"])
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.stdout)["configuration_ready"] is True
    assert constructions == [] and provider.requests == []
    assert not (tmp_path / "data" / "bearagent.db").exists()
    run = runner.invoke(app, ["run", "Complete this offline test.", "--json"])
    assert run.exit_code == 0, run.output
    run_id = json.loads(run.stdout)["result"]["run_id"]
    assert len(provider.requests) == 1
    for command in ("inspect", "events"):
        result = runner.invoke(app, ["run", command, run_id])
        assert result.exit_code == 0, result.output
        assert "synthetic-setup-secret" not in result.output


def test_repeated_init_preserves_user_files_and_only_fills_missing_templates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    original = b"user-owned even if not valid JSON"
    (tmp_path / "data" / "config.json").write_bytes(original)
    for _ in range(2):
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "user-owned" not in result.output
        assert (tmp_path / "data" / "config.json").read_bytes() == original
    assert (tmp_path / "data" / ".gitignore").read_text() == "*\n"


def test_config_check_rejects_zero_budget_and_unknown_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    setup.initialize_local_config()
    complete_config(tmp_path)
    path = tmp_path / "data" / "p1-run-profile.json"
    data = json.loads(path.read_text())
    data["budget_limits"]["max_model_iterations"] = 0
    path.write_text(json.dumps(data))
    result = runner.invoke(app, ["doctor", "--check-config"])
    assert result.exit_code == 1 and "budget is zero" in result.output
    data["budget_limits"]["max_model_iterations"] = 8
    data["agent_config"]["tool_names"] = ["unavailable.tool"]
    path.write_text(json.dumps(data))
    result = runner.invoke(app, ["doctor", "--check-config"])
    assert result.exit_code == 1
    assert not (tmp_path / "data" / "bearagent.db").exists()


def test_init_refuses_link_like_directory_without_writing_through_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def report_junction(_path: Path) -> bool:
        return True

    monkeypatch.setattr(Path, "is_junction", report_junction)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 1
    assert not (tmp_path / "data" / "config.json").exists()


def test_partial_init_failure_keeps_existing_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    original_open = os.open

    def fail_profile(path: str | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
        if Path(path).name == "p1-run-profile.json":
            raise PermissionError("sensitive-host-path")
        return original_open(path, flags, mode)

    monkeypatch.setattr(setup.os, "open", fail_profile)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 1 and "sensitive-host-path" not in result.output
    assert (tmp_path / "data" / "config.json").is_file()
    assert not (tmp_path / "data" / "p1-run-profile.json").exists()
