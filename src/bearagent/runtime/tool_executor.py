"""Single bounded execution path for every P1 Tool request."""

import asyncio
import json
from collections.abc import Mapping

from pydantic import JsonValue

from bearagent.domain._base import thaw_json_mapping
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.tools import (
    PolicyDecision,
    PolicyOutcome,
    PreparedToolRequest,
    ToolRequest,
    ToolResult,
    ToolStatus,
)
from bearagent.ports.policy import ToolPolicy
from bearagent.runtime.tool_registry import ToolRegistry


class ToolExecutor:
    """Resolve, prepare, authorize, and execute one Tool call at most once."""

    def __init__(self, registry: ToolRegistry, policy: ToolPolicy) -> None:
        self._registry = registry
        self._policy = policy

    async def execute(self, request: ToolRequest) -> ToolResult:
        """Run one request through the complete P1 Tool boundary."""
        tool = self._registry.get(request.name)
        spec = self._registry.get_spec(request.name)
        if tool is None or spec is None:
            return _failure(
                request,
                ErrorCode.TOOL_NOT_FOUND,
                "Tool is not registered.",
            )
        if _json_object_bytes(request.arguments) > spec.max_input_bytes:
            return _failure(
                request,
                ErrorCode.TOOL_INVALID_INPUT,
                "Tool request arguments exceed the input limit.",
                details={"limit_bytes": spec.max_input_bytes},
            )

        try:
            prepared_value = _runtime_value(tool.prepare(request))
        except Exception:
            return _failure(
                request,
                ErrorCode.TOOL_INVALID_INPUT,
                "Tool request arguments are invalid.",
            )
        if not isinstance(prepared_value, PreparedToolRequest):
            return _failure(
                request,
                ErrorCode.TOOL_INVALID_INPUT,
                "Tool request preparation returned invalid data.",
            )
        prepared = prepared_value
        if prepared.tool_call_id != request.tool_call_id or prepared.name != request.name:
            return _failure(
                request,
                ErrorCode.TOOL_INVALID_INPUT,
                "Tool request preparation returned invalid identity.",
            )

        try:
            decision_value = _runtime_value(self._policy.evaluate(spec, prepared))
        except Exception:
            return _failure(
                request,
                ErrorCode.TOOL_ERROR,
                "Tool policy evaluation failed.",
            )
        if not isinstance(decision_value, PolicyDecision):
            return _failure(
                request,
                ErrorCode.TOOL_ERROR,
                "Tool policy returned an invalid decision.",
            )
        decision = decision_value
        if decision.outcome is PolicyOutcome.DENY:
            return _failure(
                request,
                ErrorCode.TOOL_PERMISSION_DENIED,
                "Tool request is not allowed.",
                details={"policy_reason": decision.reason.value},
            )

        try:
            async with asyncio.timeout(spec.timeout_ms / 1_000):
                result_value = _runtime_value(await tool.execute(prepared))
        except TimeoutError:
            return _failure(
                request,
                ErrorCode.TOOL_TIMEOUT,
                "Tool execution timed out.",
            )
        except Exception:
            return _failure(
                request,
                ErrorCode.TOOL_ERROR,
                "Tool execution failed.",
            )

        if not isinstance(result_value, ToolResult):
            return _failure(
                request,
                ErrorCode.TOOL_ERROR,
                "Tool returned invalid result data.",
            )
        result = result_value
        if result.tool_call_id != request.tool_call_id:
            return _failure(
                request,
                ErrorCode.TOOL_ERROR,
                "Tool returned an invalid result.",
            )
        if result.status is ToolStatus.SUCCEEDED:
            output_bytes = _json_object_bytes(result.data)
            if output_bytes > spec.max_output_bytes:
                return _failure(
                    request,
                    ErrorCode.TOOL_OUTPUT_TOO_LARGE,
                    "Tool result exceeds the output limit.",
                    details={"limit_bytes": spec.max_output_bytes},
                )
        return result


def _json_object_bytes(data: Mapping[str, JsonValue]) -> int:
    serialized = json.dumps(
        thaw_json_mapping(data),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return len(serialized.encode("utf-8"))


def _runtime_value(value: object) -> object:
    """Erase static adapter promises before checking the runtime boundary."""
    return value


def _failure(
    request: ToolRequest,
    code: ErrorCode,
    message: str,
    *,
    details: Mapping[str, str | int] | None = None,
) -> ToolResult:
    return ToolResult(
        tool_call_id=request.tool_call_id,
        status=ToolStatus.FAILED,
        error=ErrorInfo(
            category=ErrorCategory.TOOL,
            code=code,
            message=message,
            retryable=False,
            details={} if details is None else details,
        ),
    )
