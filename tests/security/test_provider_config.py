import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

import bearagent.bootstrap as bootstrap_module
from bearagent.bootstrap import BootstrapError, load_provider_catalog
from bearagent.configuration import ProviderCatalog
from bearagent.domain.errors import ErrorCode


def provider_data() -> dict[str, object]:
    return {
        "provider_id": "primary",
        "name": "Example AI",
        "protocol": "openai_responses",
        "base_url": "https://api.example.com/v1",
        "api_key": "test-provider-secret",
        "models": [{"model_id": "test-model"}],
        "default_model": "test-model",
    }


def catalog_data() -> dict[str, object]:
    return {"schema_version": 1, "providers": [provider_data()]}


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.example.com/v1",
        "https://user:password@api.example.com/v1",
        "https://api.example.com/v1?secret=value",
        "https://api.example.com/v1#fragment",
        "https://api.example.com\\v1",
        " https://api.example.com/v1",
    ],
)
def test_catalog_rejects_unsafe_base_urls(base_url: str) -> None:
    entry = provider_data()
    entry["base_url"] = base_url

    with pytest.raises(ValidationError):
        ProviderCatalog.model_validate({"schema_version": 1, "providers": [entry]})


def test_catalog_accepts_direct_key_but_masks_it_from_models_and_errors() -> None:
    secret = "private-provider-secret"
    entry = provider_data()
    entry["api_key"] = secret
    catalog = ProviderCatalog.model_validate({"schema_version": 1, "providers": [entry]})

    assert catalog.providers[0].api_key.get_secret_value() == secret
    assert secret not in repr(catalog)
    assert secret not in catalog.model_dump_json()

    entry["api_key"] = f" {secret}"
    with pytest.raises(ValidationError) as captured:
        ProviderCatalog.model_validate({"schema_version": 1, "providers": [entry]})
    assert secret not in str(captured.value)


@pytest.mark.parametrize(
    "content",
    [b"\xff\xfe", b"{" + b"x" * (128 * 1_024)],
    ids=("invalid-utf8", "oversized"),
)
def test_catalog_loader_returns_only_safe_errors(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "sensitive-provider-name.json"
    path.write_bytes(content)

    with pytest.raises(BootstrapError) as captured:
        load_provider_catalog(path)

    assert captured.value.info.code is ErrorCode.INVALID_INPUT
    assert str(path) not in str(captured.value)
    assert "sensitive-provider-name" not in str(captured.value)


def test_catalog_loader_rejects_link_like_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(catalog_data()), encoding="utf-8")

    def report_link_like(_path: Path, _stat: os.stat_result) -> bool:
        return True

    monkeypatch.setattr(bootstrap_module, "_is_link_like", report_link_like)

    with pytest.raises(BootstrapError) as captured:
        load_provider_catalog(path)

    assert captured.value.info.code is ErrorCode.INVALID_INPUT
