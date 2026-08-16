"""Policy port for prepared Tool requests."""

from typing import Protocol

from bearagent.domain.tools import PolicyDecision, PreparedToolRequest, ToolSpec


class ToolPolicy(Protocol):
    """Decide whether one normalized Tool request may execute."""

    def evaluate(self, spec: ToolSpec, request: PreparedToolRequest) -> PolicyDecision: ...
