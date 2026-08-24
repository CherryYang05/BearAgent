"""Strict outer-layer configuration for user-selected model services."""

import hashlib
import json
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from bearagent.domain.model import MODEL_NAME_PATTERN
from bearagent.domain.providers import PROVIDER_ID_PATTERN, ModelProtocol

MAX_PROVIDER_CATALOG_ENTRIES = 32
MAX_PROVIDER_MODELS = 128
MAX_PROVIDER_NAME_CHARS = 128
MAX_MODEL_DISPLAY_NAME_CHARS = 128
MAX_PROVIDER_BASE_URL_CHARS = 2_048
MAX_PROVIDER_API_KEY_CHARS = 8_192


class ConfigurationModel(BaseModel):
    """Immutable configuration schema that rejects undeclared fields."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        validate_default=True,
    )


def _require_display_name(value: str, *, field_name: str) -> str:
    if value != value.strip() or not value:
        raise ValueError(f"{field_name} must be a non-empty string without outer whitespace")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError(f"{field_name} cannot contain control characters")
    return value


class ProviderModelConfig(ConfigurationModel):
    """One explicitly configured model offered by a Provider service."""

    model_id: str = Field(pattern=MODEL_NAME_PATTERN)
    name: str | None = Field(default=None, min_length=1, max_length=MAX_MODEL_DISPLAY_NAME_CHARS)
    thinking_mode: Literal["provider_default", "disabled"] = "provider_default"

    @field_validator("name")
    @classmethod
    def require_normalized_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_display_name(value, field_name="model name")


class ProviderConfig(ConfigurationModel):
    """One local model service and its explicitly configured models."""

    provider_id: str = Field(pattern=PROVIDER_ID_PATTERN)
    name: str = Field(min_length=1, max_length=MAX_PROVIDER_NAME_CHARS)
    protocol: ModelProtocol
    base_url: str = Field(min_length=1, max_length=MAX_PROVIDER_BASE_URL_CHARS)
    api_key: SecretStr = Field(min_length=1, max_length=MAX_PROVIDER_API_KEY_CHARS)
    models: tuple[ProviderModelConfig, ...] = Field(min_length=1, max_length=MAX_PROVIDER_MODELS)
    default_model: str = Field(pattern=MODEL_NAME_PATTERN)

    @field_validator("name")
    @classmethod
    def require_normalized_name(cls, value: str) -> str:
        return _require_display_name(value, field_name="provider name")

    @field_validator("api_key", mode="before")
    @classmethod
    def require_nonblank_api_key(cls, value: object) -> object:
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(raw_value, str) or raw_value != raw_value.strip() or not raw_value:
            raise ValueError("api_key must be a non-empty string without outer whitespace")
        if any(ord(character) <= 0x20 or ord(character) == 0x7F for character in raw_value):
            raise ValueError("api_key cannot contain control or whitespace characters")
        return value

    @field_validator("base_url")
    @classmethod
    def require_explicit_safe_https_url(cls, value: str) -> str:
        if value != value.strip() or "\\" in value:
            raise ValueError("base_url must be a normalized HTTPS URL")
        if any(ord(character) <= 0x20 or ord(character) == 0x7F for character in value):
            raise ValueError("base_url cannot contain control or whitespace characters")

        parsed = urlsplit(value)
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("base_url has an invalid port") from error
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or port is not None
            and not 1 <= port <= 65_535
        ):
            raise ValueError(
                "base_url must be an absolute HTTPS URL without credentials/query/fragment"
            )
        return value

    @model_validator(mode="after")
    def require_unique_models_and_known_default(self) -> Self:
        model_ids = tuple(model.model_id for model in self.models)
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("model_id values must be unique within a Provider")
        if self.default_model not in set(model_ids):
            raise ValueError("default_model must reference a configured model_id")
        if self.protocol is not ModelProtocol.OPENAI_CHAT_COMPLETIONS and any(
            model.thinking_mode != "provider_default" for model in self.models
        ):
            raise ValueError("thinking_mode is only supported by openai_chat_completions")

        return self

    def get_model(self, model_id: str) -> ProviderModelConfig:
        """Return one exact configured model without aliases or fallback."""

        for model in self.models:
            if model.model_id == model_id:
                return model
        raise KeyError(model_id)

    @property
    def default_model_config(self) -> ProviderModelConfig:
        """Return the explicitly selected default model."""

        return self.get_model(self.default_model)

    @property
    def configuration_version(self) -> str:
        """Derive a stable non-secret audit identity for this runtime configuration."""

        payload = {
            "provider_id": self.provider_id,
            "name": self.name,
            "protocol": self.protocol.value,
            "base_url": self.base_url,
            "models": [
                {
                    "model_id": model.model_id,
                    "name": model.name,
                    **(
                        {"thinking_mode": model.thinking_mode}
                        if model.thinking_mode != "provider_default"
                        else {}
                    ),
                }
                for model in sorted(self.models, key=lambda item: item.model_id)
            ],
            "default_model": self.default_model,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"config-v1-{hashlib.sha256(encoded).hexdigest()}"


class ProviderCatalog(ConfigurationModel):
    """Version 1 bounded catalog of user-configured model services."""

    schema_version: Literal[1] = 1
    providers: tuple[ProviderConfig, ...] = Field(
        min_length=1,
        max_length=MAX_PROVIDER_CATALOG_ENTRIES,
    )

    @model_validator(mode="after")
    def require_unique_provider_ids(self) -> Self:
        provider_ids = tuple(provider.provider_id for provider in self.providers)
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("provider_id values must be unique")
        return self

    def get(self, provider_id: str) -> ProviderConfig:
        """Return an exact provider entry without aliases or fallback."""

        for provider in self.providers:
            if provider.provider_id == provider_id:
                return provider
        raise KeyError(provider_id)
