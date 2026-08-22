import json
import sys

import pytest
from typer.testing import CliRunner

from bearagent import package_version
from bearagent.interfaces.cli.main import app, build_doctor_report

runner = CliRunner()


def test_help_exposes_doctor_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "doctor" in result.stdout


def test_run_help_explains_objective_and_query_subcommands() -> None:
    result = runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0
    assert "bearagent run OBJECTIVE" in result.stdout
    assert "inspect" in result.stdout
    assert "events" in result.stdout


def test_version_matches_installed_package() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == package_version()


def test_doctor_json_has_stable_non_sensitive_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "must-not-appear-in-doctor-output"
    monkeypatch.setenv("BEARAGENT_TEST_SECRET", secret)

    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["python_supported"] is True
    assert set(payload) == {
        "status",
        "bearagent_version",
        "python_version",
        "python_supported",
        "platform",
        "working_directory",
    }
    assert secret not in result.stdout


def test_doctor_report_rejects_unsupported_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "version_info", (3, 13, 0))
    assert build_doctor_report()["status"] == "error"
