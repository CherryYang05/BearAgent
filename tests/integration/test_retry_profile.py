import asyncio
import json
from pathlib import Path

import pytest
from tests.agent_loop_fixtures import agent_settings, budget_limits, model_completed
from tests.unit.test_provider_config import catalog_data

from bearagent.adapters.testing import FakeModelProvider
from bearagent.bootstrap import BootstrapError, build_run_services, load_run_profile
from bearagent.domain.agent import RunInput, RunProfileV2, RunProfileV3
from bearagent.domain.attempts import RetryPolicy, RunStateV5
from bearagent.domain.ids import SessionId
from bearagent.domain.model import ModelFinishReason, ModelTextDelta


@pytest.mark.parametrize("version", [2, 3])
def test_composition_snapshots_profile_retry_policy(tmp_path: Path, version: int) -> None:
    profile = (
        RunProfileV3(
            provider_id="primary",
            agent_config=agent_settings(),
            budget_limits=budget_limits(),
            retry_policy=RetryPolicy(max_attempts=3),
        )
        if version == 3
        else RunProfileV2(
            provider_id="primary", agent_config=agent_settings(), budget_limits=budget_limits()
        )
    )
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")
    catalog = tmp_path / "config.json"
    catalog.write_text(json.dumps(catalog_data()), encoding="utf-8")
    assert load_run_profile(profile_path) == profile

    async def exercise() -> None:
        services = await build_run_services(
            profile_path=profile_path,
            config_path=catalog,
            workspace_path=tmp_path,
            database_path=tmp_path / "events.db",
            model_provider=FakeModelProvider(
                [ModelTextDelta(text="done"), model_completed(ModelFinishReason.STOP)]
            ),
        )
        result = await services.agent_loop.run(
            RunInput(
                session_id=SessionId.new(),
                objective="test",
                budget_limits=services.profile.budget_limits,
                agent_config=services.agent_config,
            )
        )
        assert isinstance(result.state, RunStateV5)
        assert result.state.retry_policy.max_attempts == (3 if version == 3 else 1)
        assert result.state.budget_usage.model_iterations == 1

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "policy",
    [
        {"max_attempts": 0},
        {"max_attempts": 4},
        {"max_attempts": True},
        {"max_attempts": "3"},
        {"initial_backoff_ms": 5001},
        {"initial_backoff_ms": 2000, "max_backoff_ms": 100},
        {"version": "unchecked"},
    ],
)
def test_invalid_retry_profiles_fail_before_database_creation(
    tmp_path: Path, policy: dict[str, object]
) -> None:
    data = RunProfileV3(
        provider_id="primary", agent_config=agent_settings(), budget_limits=budget_limits()
    ).model_dump(mode="json")
    data["retry_policy"] = policy
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BootstrapError):
        load_run_profile(path)
    assert not (tmp_path / "events.db").exists()
