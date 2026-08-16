"""Tool preparation and execution port."""

from typing import Protocol

from bearagent.domain.tools import PreparedToolRequest, ToolRequest, ToolResult, ToolSpec


class Tool(Protocol):
    """Validate and execute one registered Tool without exposing adapter types."""

    spec: ToolSpec

    def prepare(self, request: ToolRequest) -> PreparedToolRequest:
        """Validate and normalize arguments without external side effects."""
        ...

    async def execute(self, request: PreparedToolRequest) -> ToolResult:
        """Perform the external operation once."""
        ...
