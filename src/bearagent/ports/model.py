"""Model provider port."""

from collections.abc import AsyncIterator
from typing import Protocol

from bearagent.domain.model import ModelEvent, ModelRequest


class ModelProvider(Protocol):
    """Translate a provider-neutral request into provider-neutral events."""

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...
