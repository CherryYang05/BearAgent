import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from bearagent.bootstrap import load_provider_catalog
from bearagent.configuration import ModelProtocol, ProviderCatalog


def provider_data(provider_id: str = "primary") -> dict[str, object]:
    return {
        "provider_id": provider_id,
        "name": "Example AI",
        "protocol": "openai_responses",
        "base_url": "https://api.example.com/v1",
        "api_key": "test-provider-secret",
        "models": [
            {
                "model_id": "test-model",
                "name": "Test Model",
            },
            {"model_id": "other-model"},
        ],
        "default_model": "test-model",
    }


def catalog_data(*providers: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "providers": list(providers or (provider_data(),)),
    }


def test_catalog_is_frozen_strict_and_selects_exact_provider() -> None:
    catalog = ProviderCatalog.model_validate(catalog_data())

    assert catalog.providers[0].protocol is ModelProtocol.OPENAI_RESPONSES
    provider = catalog.providers[0]
    assert provider.api_key.get_secret_value() == "test-provider-secret"
    assert provider.name == "Example AI"
    assert provider.default_model_config.model_id == "test-model"
    assert "pricing" not in provider.default_model_config.model_dump()
    assert provider.configuration_version.startswith("config-v1-")
    assert "test-provider-secret" not in repr(catalog)
    assert "test-provider-secret" not in catalog.model_dump_json()
    assert catalog.get("primary") == catalog.providers[0]
    with pytest.raises(KeyError):
        catalog.get("missing")
    with pytest.raises(ValidationError):
        ProviderCatalog.model_validate({**catalog_data(), "api_key": "secret"})


def test_catalog_requires_unique_bounded_entries_and_models() -> None:
    with pytest.raises(ValidationError):
        ProviderCatalog.model_validate(catalog_data(provider_data(), provider_data()))
    with pytest.raises(ValidationError):
        ProviderCatalog.model_validate(
            catalog_data(*(provider_data(f"provider-{index}") for index in range(33)))
        )

    entry = provider_data()
    entry["models"] = [{"model_id": "test-model"}, {"model_id": "test-model"}]
    with pytest.raises(ValidationError):
        ProviderCatalog.model_validate(catalog_data(entry))


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider_id", "../escape"),
        ("name", " "),
        ("protocol", "deepseek"),
        ("api_key", " leading-space"),
        ("default_model", "missing-model"),
    ],
)
def test_catalog_rejects_invalid_entry_fields(field: str, value: str) -> None:
    entry = provider_data()
    entry[field] = value

    with pytest.raises(ValidationError):
        ProviderCatalog.model_validate(catalog_data(entry))


def test_catalog_rejects_pricing_in_model_connection_config() -> None:
    entry = provider_data()
    models = entry["models"]
    assert isinstance(models, list)
    models[0]["pricing"] = {"version": "must-not-live-in-config"}

    with pytest.raises(ValidationError):
        ProviderCatalog.model_validate(catalog_data(entry))


def test_configuration_version_excludes_the_key_but_tracks_runtime_fields() -> None:
    first = ProviderCatalog.model_validate(catalog_data()).providers[0]
    rotated_data = provider_data()
    rotated_data["api_key"] = "rotated-test-secret"
    rotated = ProviderCatalog.model_validate(catalog_data(rotated_data)).providers[0]
    changed_data = provider_data()
    changed_data["default_model"] = "other-model"
    thinking_data = provider_data()
    thinking_data["protocol"] = "openai_chat_completions"
    models = thinking_data["models"]
    assert isinstance(models, list)
    models[0]["thinking_mode"] = "disabled"
    thinking = ProviderCatalog.model_validate(catalog_data(thinking_data)).providers[0]
    changed = ProviderCatalog.model_validate(catalog_data(changed_data)).providers[0]

    assert first.configuration_version == rotated.configuration_version
    assert first.configuration_version != changed.configuration_version
    assert first.configuration_version != thinking.configuration_version


def test_thinking_mode_is_bounded_to_chat_completions_models() -> None:
    entry = provider_data()
    models = entry["models"]
    assert isinstance(models, list)
    models[0]["thinking_mode"] = "disabled"

    with pytest.raises(ValidationError):
        ProviderCatalog.model_validate(catalog_data(entry))

    entry["protocol"] = "openai_chat_completions"
    catalog = ProviderCatalog.model_validate(catalog_data(entry))

    assert catalog.providers[0].default_model_config.thinking_mode == "disabled"


def test_catalog_loader_accepts_bounded_utf8_json(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(catalog_data()), encoding="utf-8")

    assert load_provider_catalog(path) == ProviderCatalog.model_validate(catalog_data())
