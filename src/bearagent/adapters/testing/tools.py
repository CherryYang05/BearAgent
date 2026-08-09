"""Deterministic tool adapter for runtime tests."""

from bearagent.domain.tools import ToolRequest, ToolResult


class FakeTool:
    """Return a configured result and retain requests for assertions."""

    def __init__(self, name: str, result: ToolResult) -> None:
        if not name:
            raise ValueError("name must not be empty")
        self.name = name
        self._result = result
        self.requests: list[ToolRequest] = []

    async def execute(self, request: ToolRequest) -> ToolResult:
        self.requests.append(request)
        return self._result
