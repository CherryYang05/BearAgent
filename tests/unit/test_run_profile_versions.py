import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from tests.agent_loop_fixtures import agent_config, agent_settings, budget_limits

from bearagent.bootstrap import load_run_profile
from bearagent.domain.agent import RunProfile, RunProfileV2


def test_run_profile_v1_remains_the_default_legacy_shape() -> None:
    profile = RunProfile(
        agent_config=agent_config(),
        budget_limits=budget_limits(),
    )

    assert profile.schema_version == 1
    assert "provider_id" not in RunProfile.model_fields
    assert "provider_id" not in profile.model_dump(mode="json", exclude_none=True)


def test_run_profile_v1_rejects_provider_selection() -> None:
    with pytest.raises(ValidationError):
        RunProfile.model_validate(
            {
                "schema_version": 1,
                "provider_id": "primary",
                "agent_config": agent_settings(),
                "budget_limits": budget_limits(),
            }
        )


def test_run_profile_v2_requires_a_bounded_provider_id() -> None:
    profile = RunProfileV2(
        schema_version=2,
        provider_id="primary",
        agent_config=agent_settings(),
        budget_limits=budget_limits(),
    )

    assert profile.provider_id == "primary"
    assert "model" not in type(profile.agent_config).model_fields
    assert "pricing" not in type(profile.agent_config).model_fields

    with pytest.raises(ValidationError):
        RunProfileV2.model_validate(
            {
                "schema_version": 2,
                "agent_config": agent_settings(),
                "budget_limits": budget_limits(),
            }
        )
    with pytest.raises(ValidationError):
        RunProfileV2(
            schema_version=2,
            provider_id="../escape",
            agent_config=agent_settings(),
            budget_limits=budget_limits(),
        )


def test_run_profile_v2_rejects_model_and_pricing_duplicates() -> None:
    data = agent_settings().model_dump(mode="json")
    data["model"] = "must-not-be-duplicated"

    with pytest.raises(ValidationError):
        RunProfileV2.model_validate(
            {
                "provider_id": "primary",
                "agent_config": data,
                "budget_limits": budget_limits(),
            }
        )


def test_loader_discriminates_v1_and_v2_profiles(tmp_path: Path) -> None:
    v1 = RunProfile(agent_config=agent_config(), budget_limits=budget_limits())
    v2 = RunProfileV2(
        provider_id="primary",
        agent_config=agent_settings(),
        budget_limits=budget_limits(),
    )

    for expected in (v1, v2):
        path = tmp_path / f"profile-{expected.schema_version}.json"
        path.write_text(
            json.dumps(expected.model_dump(mode="json")),
            encoding="utf-8",
        )
        assert load_run_profile(path) == expected
