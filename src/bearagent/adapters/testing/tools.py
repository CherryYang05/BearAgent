"""Deterministic Tool adapter for runtime tests."""

import asyncio
from collections.abc import Mapping

from pydantic import JsonValue

from bearagent.domain.errors import ErrorInfo
from bearagent.domain.tools import (
    PreparedToolRequest,
    ToolRequest,
    ToolResult,
    ToolSpec,
    ToolStatus,
)


class FakeTool:
    """Record each stage and return one configured result without external I/O."""

    def __init__(
        self,
        spec: ToolSpec,
        *,
        data: Mapping[str, JsonValue] | None = None,
        failure: ErrorInfo | None = None,
        prepared_arguments: Mapping[str, JsonValue] | None = None,
        prepare_error: Exception | None = None,
        execute_error: Exception | None = None,
        delay_seconds: float = 0,
    ) -> None:
        if data is not None and failure is not None:
            raise ValueError("FakeTool cannot configure both data and failure")
        if delay_seconds < 0:
            raise ValueError("delay_seconds must not be negative")
        self.spec = spec
        self._data = {} if data is None else dict(data)
        self._failure = failure
        self._prepared_arguments = None if prepared_arguments is None else dict(prepared_arguments)
        self._prepare_error = prepare_error
        self._execute_error = execute_error
        self._delay_seconds = delay_seconds
        self.prepare_requests: list[ToolRequest] = []
        self.requests: list[PreparedToolRequest] = []

    def prepare(self, request: ToolRequest) -> PreparedToolRequest:
        """Record and normalize one request without external I/O."""
        self.prepare_requests.append(request)
        if self._prepare_error is not None:
            raise self._prepare_error
        if request.name != self.spec.name:
            raise ValueError("request name does not match the Tool spec")
        arguments = (
            request.arguments if self._prepared_arguments is None else self._prepared_arguments
        )
        return PreparedToolRequest(
            tool_call_id=request.tool_call_id,
            name=request.name,
            arguments=arguments,
        )

    async def execute(self, request: PreparedToolRequest) -> ToolResult:
        """Return the configured result after an optional deterministic delay."""
        self.requests.append(request)
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)
        if self._execute_error is not None:
            raise self._execute_error
        if self._failure is not None:
            return ToolResult(
                tool_call_id=request.tool_call_id,
                status=ToolStatus.FAILED,
                error=self._failure,
            )
        return ToolResult(
            tool_call_id=request.tool_call_id,
            status=ToolStatus.SUCCEEDED,
            data=self._data,
        )
