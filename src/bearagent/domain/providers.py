"""Provider protocol facts shared without leaking SDK types."""

from enum import StrEnum

from pydantic import Field

from bearagent.domain._base import DomainModel
from bearagent.domain.model import PROMPT_VERSION_PATTERN

PROVIDER_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9._-]{0,63}$"


class ModelProtocol(StrEnum):
    """An explicitly selected wire protocol implemented by a model adapter."""

    OPENAI_RESPONSES = "openai_responses"
    OPENAI_CHAT_COMPLETIONS = "openai_chat_completions"

    ANTHROPIC_MESSAGES = "anthropic_messages"


class ProviderSelection(DomainModel):
    """Non-secret Provider identity persisted with a Run."""

    provider_id: str = Field(pattern=PROVIDER_ID_PATTERN)
    config_version: str = Field(pattern=PROMPT_VERSION_PATTERN)
    protocol: ModelProtocol
