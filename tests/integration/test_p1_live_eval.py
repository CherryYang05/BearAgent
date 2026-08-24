import asyncio
from pathlib import Path

import pytest
from tests.evals.test_p1_agent_loop_tasks import script_for
from tests.unit.test_p1_live_eval import prepare

import bearagent.bootstrap as bootstrap_module
from bearagent.adapters.testing import ScriptedFakeModelProvider
from bearagent.configuration import ProviderConfig
from bearagent.evaluation.p1_live import execute_live_eval
from bearagent.ports import ModelProvider


def test_live_runner_reuses_production_composition_and_writes_sanitized_5_of_5_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = prepare(tmp_path)
    tasks = iter(plan.suite.tasks)
    factory_calls: list[str] = []

    def fake_factory(
        provider_config: ProviderConfig,
    ) -> ModelProvider:
        task = next(tasks)
        factory_calls.append(provider_config.protocol.value)
        return ScriptedFakeModelProvider(script_for(task))

    monkeypatch.setattr(bootstrap_module, "build_model_provider", fake_factory)
    evidence_root = tmp_path / "evidence"

    outcome = asyncio.run(
        execute_live_eval(
            plan,
            evidence_root=evidence_root,
        )
    )

    assert outcome.report.verdict == "passed"
    assert outcome.report.commit == plan.preflight.commit == "abc1234"
    assert len(outcome.report.task_reports) == 5
    assert all(report.passed for report in outcome.report.task_reports)
    assert all(report.cost_microusd > 0 for report in outcome.report.task_reports)
    assert factory_calls == ["openai_chat_completions"] * 5
    assert all(outcome.report.reality_check.values())
    assert outcome.report_path.is_file()
    assert len(tuple((outcome.report_path.parent / "databases").glob("*.sqlite3"))) == 5
    assert len(tuple((outcome.report_path.parent / "workspaces").iterdir())) == 6

    report_json = outcome.report_path.read_text(encoding="utf-8")
    assert "test-secret" not in report_json
    assert "https://provider.test/v1" not in report_json
    assert str(tmp_path) not in report_json
    assert "BEARAGENT-P1-CANARY-" not in report_json
    for task in plan.suite.tasks:
        if task.output_content:
            assert task.output_content not in report_json


def test_live_runner_never_overwrites_an_attempt_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = prepare(tmp_path)

    def fake_factory(
        provider_config: ProviderConfig,
    ) -> ModelProvider:
        del provider_config
        return ScriptedFakeModelProvider(())

    monkeypatch.setattr(bootstrap_module, "build_model_provider", fake_factory)
    evidence_root = tmp_path / "evidence"

    first = asyncio.run(execute_live_eval(plan, evidence_root=evidence_root))
    second = asyncio.run(execute_live_eval(plan, evidence_root=evidence_root))

    assert first.report.attempt_id != second.report.attempt_id
    assert first.report_path != second.report_path
    assert first.report_path.is_file()
    assert second.report_path.is_file()
