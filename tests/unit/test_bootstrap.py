import asyncio
import json
import os
from pathlib import Path

import pytest
from tests.agent_loop_fixtures import (
    agent_config,
    agent_run_input,
    budget_limits,
    model_completed,
)

import bearagent.bootstrap as bootstrap_module
from bearagent.adapters.testing import FakeModelProvider
from bearagent.application import RunQueryError
from bearagent.bootstrap import (
    BootstrapError,
    build_run_query_service,
    build_run_services,
    load_run_profile,
)
from bearagent.domain.agent import RunProfile
from bearagent.domain.diagnostics import DiagnosticRecord
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import RunId
from bearagent.domain.model import ModelFinishReason, ModelTextDelta


class RecordingSink:
    def __init__(self) -> None:
        self.records: list[DiagnosticRecord] = []

    def emit(self, record: DiagnosticRecord) -> None:
        self.records.append(record)


def _write_profile(path: Path, **extra: object) -> RunProfile:
    profile = RunProfile(
        agent_config=agent_config(),
        budget_limits=budget_limits(),
    )
    data = {**profile.model_dump(mode="json"), **extra}
    path.write_text(json.dumps(data), encoding="utf-8")
    return profile


def test_profile_loader_accepts_only_bounded_non_secret_json(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    expected = _write_profile(profile_path)

    assert load_run_profile(profile_path) == expected

    _write_profile(profile_path, api_key="must-not-enter-profile")
    with pytest.raises(BootstrapError) as captured:
        load_run_profile(profile_path)
    assert captured.value.info.code is ErrorCode.INVALID_INPUT
    assert "api_key" not in str(captured.value)


@pytest.mark.parametrize(
    "content",
    [b"\xff\xfe", b"{" + b"x" * (128 * 1_024)],
    ids=("invalid-utf8", "oversized"),
)
def test_profile_loader_rejects_invalid_or_oversized_bytes(
    tmp_path: Path,
    content: bytes,
) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_bytes(content)

    with pytest.raises(BootstrapError) as captured:
        load_run_profile(profile_path)

    assert captured.value.info.code is ErrorCode.INVALID_INPUT
    assert str(profile_path) not in str(captured.value)


def test_profile_loader_rejects_a_link_instead_of_following_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target.json"
    link = tmp_path / "profile.json"
    _write_profile(target)
    try:
        link.symlink_to(target)
    except OSError:
        # Some Windows hosts deny test symlink creation. Exercise the same
        # fail-closed branch while workspace link tests cover real reparse paths.
        def report_link_like(_path: Path, _stat: os.stat_result) -> bool:
            return True

        link = target
        monkeypatch.setattr(bootstrap_module, "_is_link_like", report_link_like)

    with pytest.raises(BootstrapError) as captured:
        load_run_profile(link)

    assert captured.value.info.code is ErrorCode.INVALID_INPUT


def test_build_run_services_uses_injected_provider_and_one_sqlite_store(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "profile.json"
    expected = _write_profile(profile_path)
    database_path = tmp_path / "data" / "bearagent.db"
    provider = FakeModelProvider(
        (
            ModelTextDelta(text="done"),
            model_completed(ModelFinishReason.STOP),
        )
    )

    services = asyncio.run(
        build_run_services(
            profile_path=profile_path,
            workspace_path=tmp_path,
            database_path=database_path,
            model_provider=provider,
        )
    )

    assert services.profile == expected
    assert database_path.is_file()
    asyncio.run(services.agent_loop.run(agent_run_input()))
    assert tuple(tool.name for tool in provider.requests[0].tools) == ("workspace.read",)
    with pytest.raises(RunQueryError) as captured:
        asyncio.run(services.queries.inspect(RunId.new()))
    assert captured.value.info.code is ErrorCode.RUN_NOT_FOUND


def test_build_run_services_wires_the_injected_diagnostic_sink(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    _write_profile(profile_path)
    sink = RecordingSink()
    provider = FakeModelProvider(
        (
            ModelTextDelta(text="done"),
            model_completed(ModelFinishReason.STOP),
        )
    )
    services = asyncio.run(
        build_run_services(
            profile_path=profile_path,
            workspace_path=tmp_path,
            database_path=tmp_path / "events.db",
            model_provider=provider,
            diagnostic_sink=sink,
        )
    )

    result = asyncio.run(services.agent_loop.run(agent_run_input()))

    assert result.state.last_sequence == len(sink.records)
    assert [record.sequence for record in sink.records] == list(
        range(1, result.state.last_sequence + 1)
    )
    assert all(record.name == "event.committed" for record in sink.records)


def test_query_bootstrap_does_not_create_a_missing_database(tmp_path: Path) -> None:
    database_path = tmp_path / "missing" / "bearagent.db"
    sink = RecordingSink()

    with pytest.raises(BootstrapError) as captured:
        asyncio.run(build_run_query_service(database_path, diagnostic_sink=sink))

    assert captured.value.info.code is ErrorCode.PERSISTENCE_ERROR
    assert not database_path.exists()
    assert len(sink.records) == 1
    assert sink.records[0].component == "bootstrap"
    assert sink.records[0].operation == "build_query_service"
    assert sink.records[0].error_code is ErrorCode.PERSISTENCE_ERROR
