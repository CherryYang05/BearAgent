"""Default-deny fixed Tool policy for P1."""

import re
from collections.abc import Iterable

from bearagent.domain.messages import TOOL_NAME_PATTERN
from bearagent.domain.tools import (
    PolicyDecision,
    PolicyOutcome,
    PolicyReason,
    PreparedToolRequest,
    ToolSideEffect,
    ToolSpec,
)

_DENIED_SIDE_EFFECTS = frozenset(
    {
        ToolSideEffect.EXTERNAL_WRITE,
        ToolSideEffect.CODE_EXECUTION,
    }
)


class FixedToolPolicy:
    """Allow configured P1 Tools while hard-denying dangerous side effects."""

    def __init__(self, allowed_tool_names: Iterable[str] = ()) -> None:
        if isinstance(allowed_tool_names, str):
            raise ValueError("allowed Tool names must be a collection, not one string")
        names = _materialize_untrusted_names(allowed_tool_names)
        validated_names: list[str] = []
        for name in names:
            if not isinstance(name, str) or re.fullmatch(TOOL_NAME_PATTERN, name) is None:
                raise ValueError("allowed Tool name is invalid")
            validated_names.append(name)
        self._allowed_tool_names = frozenset(validated_names)

    @property
    def allowed_tool_names(self) -> frozenset[str]:
        """Return the immutable trusted allowlist snapshot."""
        return self._allowed_tool_names

    def evaluate(self, spec: ToolSpec, request: PreparedToolRequest) -> PolicyDecision:
        """Evaluate trusted Tool metadata and normalized arguments."""
        if spec.name != request.name or spec.name not in self._allowed_tool_names:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason=PolicyReason.TOOL_NOT_ALLOWED,
            )
        if spec.side_effect in _DENIED_SIDE_EFFECTS:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason=PolicyReason.SIDE_EFFECT_DENIED,
            )
        return PolicyDecision(
            outcome=PolicyOutcome.ALLOW,
            reason=PolicyReason.ALLOWED,
        )


def _materialize_untrusted_names(names: Iterable[object]) -> tuple[object, ...]:
    return tuple(names)
