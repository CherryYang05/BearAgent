import asyncio
import json
from pathlib import Path

import pytest
from tests.agent_loop_fixtures import (
    agent_config,
    agent_run_input,
    agent_settings,
    budget_limits,
    model_completed,
)
from tests.unit.test_provider_config import catalog_data, provider_data

from bearagent.adapters.model import (
    AnthropicMessagesProvider,
    OpenAIChatCompletionsProvider,
    OpenAIResponsesProvider,
)
from bearagent.adapters.testing import FakeModelProvider
from bearagent.bootstrap import BootstrapError, build_model_provider, build_run_services
from bearagent.configuration import ProviderCatalog, ProviderConfig
from bearagent.domain.agent import RunProfile, RunProfileV2
from bearagent.domain.errors import ErrorCode
from bearagent.domain.model import ModelFinishReason, ModelTextDelta
from bearagent.domain.providers import ModelProtocol


@pytest.mark.parametrize(
    ("protocol", "expected_type"),
    [
        (ModelProtocol.OPENAI_RESPONSES, OpenAIResponsesProvider),
        (ModelProtocol.OPENAI_CHAT_COMPLETIONS, OpenAIChatCompletionsProvider),
        (ModelProtocol.ANTHROPIC_MESSAGES, AnthropicMessagesProvider),
    ],
)
def test_factory_selects_only_the_explicit_protocol(
    protocol: ModelProtocol,
    expected_type: type[object],
) -> None:
    data = provider_data()
    data["protocol"] = protocol
    config = ProviderConfig.model_validate(data)

    provider = build_model_provider(config)

    assert isinstance(provider, expected_type)


def test_factory_uses_direct_key_without_exposing_it_in_config_output() -> None:
    secret = "selected-secret"
    data = provider_data()
    data["protocol"] = ModelProtocol.OPENAI_CHAT_COMPLETIONS
    data["api_key"] = secret
    config = ProviderConfig.model_validate(data)

    build_model_provider(config)

    assert config.api_key.get_secret_value() == secret
    assert secret not in repr(config)
    assert secret not in config.model_dump_json()


def test_factory_passes_explicit_chat_thinking_mode() -> None:
    data = provider_data()
    data["protocol"] = ModelProtocol.OPENAI_CHAT_COMPLETIONS
    models = data["models"]
    assert isinstance(models, list)
    models[0]["thinking_mode"] = "disabled"
    config = ProviderConfig.model_validate(data)

    provider = build_model_provider(config)

    assert isinstance(provider, OpenAIChatCompletionsProvider)
    assert provider.thinking_mode == "disabled"


def test_v2_composition_records_selected_provider_without_reading_key_when_injected(
    tmp_path: Path,
) -> None:
    profile = RunProfileV2(
        provider_id="primary",
        agent_config=agent_settings(),
        budget_limits=budget_limits(),
    )
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile.model_dump(mode="json")), encoding="utf-8")
    catalog_path = tmp_path / "config.json"
    catalog_path.write_text(json.dumps(catalog_data()), encoding="utf-8")
    database_path = tmp_path / "events.db"
    provider = FakeModelProvider(
        (
            ModelTextDelta(text="done"),
            model_completed(ModelFinishReason.STOP),
        )
    )

    services = asyncio.run(
        build_run_services(
            profile_path=profile_path,
            config_path=catalog_path,
            workspace_path=tmp_path,
            database_path=database_path,
            model_provider=provider,
        )
    )
    result = asyncio.run(services.agent_loop.run(agent_run_input()))
    inspection = asyncio.run(services.queries.inspect(result.run_id))

    assert inspection.provider_selection is not None
    assert inspection.provider_selection.provider_id == "primary"
    configured_provider = ProviderCatalog.model_validate(catalog_data()).providers[0]
    assert inspection.provider_selection.config_version == configured_provider.configuration_version
    assert inspection.provider_selection.protocol is ModelProtocol.OPENAI_RESPONSES
    assert services.agent_config.model == "test-model"
    assert services.agent_config.pricing.version == "unpriced"


def test_v1_composition_records_the_legacy_selection(tmp_path: Path) -> None:
    profile = RunProfile(
        agent_config=agent_config(),
        budget_limits=budget_limits(),
    )
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile.model_dump(mode="json")), encoding="utf-8")
    database_path = tmp_path / "events.db"
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
    result = asyncio.run(services.agent_loop.run(agent_run_input()))
    inspection = asyncio.run(services.queries.inspect(result.run_id))

    assert inspection.provider_selection is not None
    assert inspection.provider_selection.provider_id == "legacy-openai"
    assert inspection.provider_selection.config_version == "legacy-v1"
    assert inspection.provider_selection.protocol is ModelProtocol.OPENAI_RESPONSES


def test_unknown_v2_provider_fails_before_database_creation(tmp_path: Path) -> None:
    profile = RunProfileV2(
        provider_id="missing",
        agent_config=agent_settings(),
        budget_limits=budget_limits(),
    )
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile.model_dump(mode="json")), encoding="utf-8")
    catalog_path = tmp_path / "config.json"
    catalog_path.write_text(
        json.dumps(catalog_data(provider_data("primary"))),
        encoding="utf-8",
    )
    database_path = tmp_path / "must-not-exist.db"

    with pytest.raises(BootstrapError) as caught:
        asyncio.run(
            build_run_services(
                profile_path=profile_path,
                config_path=catalog_path,
                workspace_path=tmp_path,
                database_path=database_path,
            )
        )

    assert caught.value.info.code is ErrorCode.INVALID_INPUT
    assert not database_path.exists()
