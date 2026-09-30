"""Model provider port."""

from collections.abc import AsyncIterator
from typing import Protocol

from bearagent.domain.attempts import ModelFailureEvidence
from bearagent.domain.errors import BearAgentError, ErrorInfo
from bearagent.domain.model import ModelEvent, ModelRequest


class ModelProviderError(BearAgentError):
    """A safe model boundary failure with normalized retry semantics."""

    def __init__(
        self,
        info: ErrorInfo,
        *,
        cause: BaseException | None = None,
        evidence: ModelFailureEvidence | None = None,
    ) -> None:
        self.evidence = ModelFailureEvidence() if evidence is None else evidence
        super().__init__(info, cause=cause)


class ModelProvider(Protocol):
    """Translate a provider-neutral request into provider-neutral events."""

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...
