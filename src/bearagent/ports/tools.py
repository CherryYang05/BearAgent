"""Tool execution port."""

from typing import Protocol

from bearagent.domain.tools import ToolRequest, ToolResult


class Tool(Protocol):
    """Execute one typed tool request."""

    name: str

    async def execute(self, request: ToolRequest) -> ToolResult: ...
