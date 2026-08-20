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
    ToolExecutionRecord,
    ToolRequest,
    ToolResult,
    ToolSpec,
    ToolStatus,
)
from bearagent.ports.policy import ToolPolicy
from bearagent.runtime.tool_registry import ToolRegistry


class ToolExecutor:
    """Resolve, prepare, authorize, and execute one Tool call at most once."""

    def __init__(self, registry: ToolRegistry, policy: ToolPolicy) -> None:
        self._registry = registry
        self._policy = policy

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        """Return the exact registration snapshot used by this execution path."""
        return self._registry.specs

    async def execute(self, request: ToolRequest) -> ToolResult:
        """Run one request through the complete P1 Tool boundary."""
        return (await self._execute(request)).result

    async def execute_recorded(self, request: ToolRequest) -> ToolExecutionRecord:
        """Run one request and return safe evidence for Event persistence."""
        return await self._execute(request)

    async def _execute(self, request: ToolRequest) -> ToolExecutionRecord:
        tool = self._registry.get(request.name)
        spec = self._registry.get_spec(request.name)
        if tool is None or spec is None:
            return _record(
                request,
                _failure(
                    request,
                    ErrorCode.TOOL_NOT_FOUND,
                    "Tool is not registered.",
                ),
            )
        if _json_object_bytes(request.arguments) > spec.max_input_bytes:
            return _record(
                request,
                _failure(
                    request,
                    ErrorCode.TOOL_INVALID_INPUT,
                    "Tool request arguments exceed the input limit.",
                    details={"limit_bytes": spec.max_input_bytes},
                ),
            )

        try:
            prepared_value = _runtime_value(tool.prepare(request))
        except Exception:
            return _record(
                request,
                _failure(
                    request,
                    ErrorCode.TOOL_INVALID_INPUT,
                    "Tool request arguments are invalid.",
                ),
            )
        if not isinstance(prepared_value, PreparedToolRequest):
            return _record(
                request,
                _failure(
                    request,
                    ErrorCode.TOOL_INVALID_INPUT,
                    "Tool request preparation returned invalid data.",
                ),
            )
        prepared = prepared_value
        if prepared.tool_call_id != request.tool_call_id or prepared.name != request.name:
            return _record(
                request,
                _failure(
                    request,
                    ErrorCode.TOOL_INVALID_INPUT,
                    "Tool request preparation returned invalid identity.",
                ),
            )

        try:
            decision_value = _runtime_value(self._policy.evaluate(spec, prepared))
        except Exception:
            return _record(
                request,
                _failure(
                    request,
                    ErrorCode.TOOL_ERROR,
                    "Tool policy evaluation failed.",
                ),
                prepared=prepared,
            )
        if not isinstance(decision_value, PolicyDecision):
            return _record(
                request,
                _failure(
                    request,
                    ErrorCode.TOOL_ERROR,
                    "Tool policy returned an invalid decision.",
                ),
                prepared=prepared,
            )
        decision = decision_value
        if decision.outcome is PolicyOutcome.DENY:
            return _record(
                request,
                _failure(
                    request,
                    ErrorCode.TOOL_PERMISSION_DENIED,
                    "Tool request is not allowed.",
                    details={"policy_reason": decision.reason.value},
                ),
                prepared=prepared,
                decision=decision,
            )

        try:
            async with asyncio.timeout(spec.timeout_ms / 1_000):
                result_value = _runtime_value(await tool.execute(prepared))
        except TimeoutError:
            return _record(
                request,
                _failure(
                    request,
                    ErrorCode.TOOL_TIMEOUT,
                    "Tool execution timed out.",
                ),
                prepared=prepared,
                decision=decision,
                reached_adapter=True,
            )
        except Exception:
            return _record(
                request,
                _failure(
                    request,
                    ErrorCode.TOOL_ERROR,
                    "Tool execution failed.",
                ),
                prepared=prepared,
                decision=decision,
                reached_adapter=True,
            )

        if not isinstance(result_value, ToolResult):
            return _record(
                request,
                _failure(
                    request,
                    ErrorCode.TOOL_ERROR,
                    "Tool returned invalid result data.",
                ),
                prepared=prepared,
                decision=decision,
                reached_adapter=True,
            )
        result = result_value
        if result.tool_call_id != request.tool_call_id:
            return _record(
                request,
                _failure(
                    request,
                    ErrorCode.TOOL_ERROR,
                    "Tool returned an invalid result.",
                ),
                prepared=prepared,
                decision=decision,
                reached_adapter=True,
            )
        if result.status is ToolStatus.SUCCEEDED:
            output_bytes = _json_object_bytes(result.data)
            if output_bytes > spec.max_output_bytes:
                return _record(
                    request,
                    _failure(
                        request,
                        ErrorCode.TOOL_OUTPUT_TOO_LARGE,
                        "Tool result exceeds the output limit.",
                        details={"limit_bytes": spec.max_output_bytes},
                    ),
                    prepared=prepared,
                    decision=decision,
                    reached_adapter=True,
                )
        return _record(
            request,
            result,
            prepared=prepared,
            decision=decision,
            reached_adapter=True,
        )


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


def _record(
    request: ToolRequest,
    result: ToolResult,
    *,
    prepared: PreparedToolRequest | None = None,
    decision: PolicyDecision | None = None,
    reached_adapter: bool = False,
) -> ToolExecutionRecord:
    return ToolExecutionRecord(
        request=request,
        prepared_request=prepared,
        policy_decision=decision,
        reached_adapter=reached_adapter,
        result=result,
    )
