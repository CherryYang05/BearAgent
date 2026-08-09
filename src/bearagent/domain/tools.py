"""Tool request and result types shared by ports and adapters."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


def _empty_arguments() -> Mapping[str, object]:
    return {}


class ToolStatus(StrEnum):
    """Terminal status returned by a P0 test tool."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ToolRequest:
    """A provider-neutral request to execute a named tool."""

    name: str
    arguments: Mapping[str, object] = field(default_factory=_empty_arguments)


@dataclass(frozen=True, slots=True)
class ToolResult:
    """A structured P0 tool result."""

    status: ToolStatus
    content: str = ""
    error_code: str | None = None
