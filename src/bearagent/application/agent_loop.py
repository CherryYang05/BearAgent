"""Serial P1 Agent Loop coordinated across persisted Activity boundaries."""

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ValidationError

from bearagent.domain.agent import RunInput, RunResult
from bearagent.domain.artifacts import Artifact
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import (
    ActivityId,
    CausationId,
    CorrelationId,
    EventId,
    IdGenerator,
    ModelCallId,
    RunId,
    Uuid4IdGenerator,
)
from bearagent.domain.messages import Message, TextPart, ToolCallPart
from bearagent.domain.model import ModelFinishReason, ModelRequest
from bearagent.domain.run_events import (
    RUN_EVENT_SCHEMA_VERSION_V2,
    ModelCallCompletedPayloadV2,
    ModelCallFailedPayloadV2,
    ModelCallRequestedPayloadV2,
    ModelCallStartedPayloadV2,
    RunCreatedPayloadV2,
    RunFailedPayloadV2,
    RunStartedPayloadV2,
    RunSucceededPayloadV2,
    ToolCallCompletedPayloadV2,
    ToolCallFailedPayloadV2,
    ToolCallRequestedPayloadV2,
    ToolCallStartedPayloadV2,
)
from bearagent.domain.runs import ActivityKind, RunState
from bearagent.domain.tools import ToolExecutionRecord, ToolRequest, ToolResult, ToolStatus
from bearagent.ports.model import ModelProvider, ModelProviderError
from bearagent.ports.store import MAX_EVENT_QUERY_LIMIT, EventStore
from bearagent.runtime.budgets import check_activity_budget
from bearagent.runtime.context import ContextBuilder, ContextBuilderError
from bearagent.runtime.model_stream import (
    ModelStreamCollector,
    ModelStreamProtocolError,
)
from bearagent.runtime.pricing import estimate_model_cost_microusd
from bearagent.runtime.tool_executor import ToolExecutor


class Clock(Protocol):
    """Supply aware timestamps without coupling tests to wall-clock time."""

    def now(self) -> datetime: ...


class SystemClock:
    """Production clock backed by the Python standard library."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class AgentLoop:
    """Execute one Run serially using only ports and persisted facts."""

    def __init__(
        self,
        *,
        model_provider: ModelProvider,
        event_store: EventStore,
        tool_executor: ToolExecutor,
        context_builder: ContextBuilder | None = None,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._model_provider = model_provider
        self._event_store = event_store
        self._tool_executor = tool_executor
        self._tool_specs = tool_executor.specs
        self._context_builder = ContextBuilder() if context_builder is None else context_builder
        self._clock = SystemClock() if clock is None else clock
        self._id_generator = Uuid4IdGenerator() if id_generator is None else id_generator

    async def run(self, run_input: RunInput) -> RunResult:
        """Create and drive one Run until it reaches a persisted terminal state."""
        available_tool_names = {spec.name for spec in self._tool_specs}
        if any(name not in available_tool_names for name in run_input.agent_config.tool_names):
            raise ValueError("AgentConfig references a Tool that is not registered")
        run_id = self._id_generator.new(RunId)
        correlation_id = self._id_generator.new(CorrelationId)
        state = await self._append(
            None,
            run_id,
            correlation_id,
            "RunCreated",
            RunCreatedPayloadV2(
                session_id=run_input.session_id,
                budget_limits=run_input.budget_limits,
                objective=run_input.objective,
                agent_config=run_input.agent_config,
            ),
        )
        state = await self._append(
            state,
            run_id,
            correlation_id,
            "RunStarted",
            RunStartedPayloadV2(),
        )
        artifacts: list[Artifact] = []

        while True:
            exhaustion = check_activity_budget(state, ActivityKind.MODEL, self._clock.now())
            if exhaustion is not None:
                return await self._fail_run(
                    state,
                    correlation_id,
                    exhaustion.to_error_info(),
                    artifacts,
                )

            try:
                events = await self._events_for(state)
                context = self._context_builder.build(events, self._tool_specs)
            except ContextBuilderError as error:
                return await self._fail_run(
                    state,
                    correlation_id,
                    error.info,
                    artifacts,
                )

            activity_id = self._id_generator.new(ActivityId)
            model_call_id = self._id_generator.new(ModelCallId)
            try:
                requested_event = self._build_event(
                    state,
                    run_id,
                    correlation_id,
                    "ModelCallRequested",
                    ModelCallRequestedPayloadV2(
                        activity_id=activity_id,
                        model_call_id=model_call_id,
                        request=context.request,
                        context_report=context.report,
                    ),
                )
            except ValidationError:
                return await self._fail_run(
                    state,
                    correlation_id,
                    _context_persistence_error(),
                    artifacts,
                )
            state = await self._event_store.append(requested_event)
            state = await self._append(
                state,
                run_id,
                correlation_id,
                "ModelCallStarted",
                ModelCallStartedPayloadV2(
                    activity_id=activity_id,
                    model_call_id=model_call_id,
                ),
            )

            collector = ModelStreamCollector()
            try:
                async with asyncio.timeout(context.request.timeout_ms / 1_000):
                    response = await collector.collect(self._model_provider.stream(context.request))
            except asyncio.CancelledError:
                raise
            except ModelStreamProtocolError as error:
                return await self._fail_model(
                    state,
                    correlation_id,
                    activity_id,
                    model_call_id,
                    error.info,
                    error.discarded_output_chars,
                    artifacts,
                )
            except ModelProviderError as error:
                return await self._fail_model(
                    state,
                    correlation_id,
                    activity_id,
                    model_call_id,
                    error.info,
                    collector.discarded_output_chars,
                    artifacts,
                )
            except TimeoutError:
                return await self._fail_model(
                    state,
                    correlation_id,
                    activity_id,
                    model_call_id,
                    _provider_error(ErrorCode.PROVIDER_TIMEOUT, "Model call timed out."),
                    collector.discarded_output_chars,
                    artifacts,
                )
            except Exception:
                return await self._fail_model(
                    state,
                    correlation_id,
                    activity_id,
                    model_call_id,
                    _provider_error(ErrorCode.PROVIDER_ERROR, "Model call failed."),
                    collector.discarded_output_chars,
                    artifacts,
                )

            identity_error = _reused_tool_identity_error(context.request, response.message)
            if identity_error is not None:
                return await self._fail_model(
                    state,
                    correlation_id,
                    activity_id,
                    model_call_id,
                    identity_error,
                    collector.discarded_output_chars,
                    artifacts,
                )

            usage = response.completion.usage
            if usage is None:
                return await self._fail_model(
                    state,
                    correlation_id,
                    activity_id,
                    model_call_id,
                    _provider_error(
                        ErrorCode.PROVIDER_PROTOCOL_ERROR,
                        "Model completion did not include usage.",
                    ),
                    collector.discarded_output_chars,
                    artifacts,
                )
            cost_microusd = estimate_model_cost_microusd(
                usage.input_tokens,
                usage.output_tokens,
                run_input.agent_config.pricing,
            )
            try:
                completed_event = self._build_event(
                    state,
                    run_id,
                    correlation_id,
                    "ModelCallCompleted",
                    ModelCallCompletedPayloadV2(
                        activity_id=activity_id,
                        model_call_id=model_call_id,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        cost_microusd=cost_microusd,
                        message=response.message,
                        provider_request_id=response.completion.provider_request_id,
                        provider_model=response.completion.model,
                        finish_reason=response.completion.finish_reason,
                    ),
                )
            except ValidationError:
                return await self._fail_model(
                    state,
                    correlation_id,
                    activity_id,
                    model_call_id,
                    _provider_error(
                        ErrorCode.PROVIDER_PROTOCOL_ERROR,
                        "Model completion exceeds the Event persistence boundary.",
                    ),
                    collector.discarded_output_chars,
                    artifacts,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cost_microusd=cost_microusd,
                )
            state = await self._event_store.append(completed_event)

            if response.completion.finish_reason is ModelFinishReason.STOP:
                final_text = "".join(
                    part.text for part in response.message.parts if isinstance(part, TextPart)
                )
                state = await self._append(
                    state,
                    run_id,
                    correlation_id,
                    "RunSucceeded",
                    RunSucceededPayloadV2(),
                )
                return RunResult(
                    run_id=run_id,
                    state=state,
                    final_text=final_text,
                    artifacts=tuple(artifacts),
                )

            for part in response.message.parts:
                if not isinstance(part, ToolCallPart):
                    continue
                exhaustion = check_activity_budget(
                    state,
                    ActivityKind.TOOL,
                    self._clock.now(),
                )
                if exhaustion is not None:
                    return await self._fail_run(
                        state,
                        correlation_id,
                        exhaustion.to_error_info(),
                        artifacts,
                    )
                request = ToolRequest(
                    tool_call_id=part.tool_call_id,
                    name=part.name,
                    arguments=part.arguments,
                )
                tool_activity_id = self._id_generator.new(ActivityId)
                state = await self._append(
                    state,
                    run_id,
                    correlation_id,
                    "ToolCallRequested",
                    ToolCallRequestedPayloadV2(
                        activity_id=tool_activity_id,
                        tool_call_id=request.tool_call_id,
                        tool_name=request.name,
                        request=request,
                    ),
                )
                state = await self._append(
                    state,
                    run_id,
                    correlation_id,
                    "ToolCallStarted",
                    ToolCallStartedPayloadV2(
                        activity_id=tool_activity_id,
                        tool_call_id=request.tool_call_id,
                    ),
                )
                execution = await self._tool_executor.execute_recorded(request)
                if execution.result.status is ToolStatus.SUCCEEDED:
                    terminal_type = "ToolCallCompleted"
                    terminal_payload: BaseModel = ToolCallCompletedPayloadV2(
                        activity_id=tool_activity_id,
                        tool_call_id=request.tool_call_id,
                        execution=execution,
                    )
                else:
                    error = execution.result.error
                    if error is None:
                        return await self._fail_run(
                            state,
                            correlation_id,
                            _internal_error(),
                            artifacts,
                        )
                    terminal_type = "ToolCallFailed"
                    terminal_payload = ToolCallFailedPayloadV2(
                        activity_id=tool_activity_id,
                        tool_call_id=request.tool_call_id,
                        error=error,
                        execution=execution,
                    )
                try:
                    terminal_event = self._build_event(
                        state,
                        run_id,
                        correlation_id,
                        terminal_type,
                        terminal_payload,
                    )
                except ValidationError:
                    persistence_error = _tool_persistence_error()
                    compact_execution = _compact_execution_failure(
                        execution,
                        persistence_error,
                    )
                    state = await self._append(
                        state,
                        run_id,
                        correlation_id,
                        "ToolCallFailed",
                        ToolCallFailedPayloadV2(
                            activity_id=tool_activity_id,
                            tool_call_id=request.tool_call_id,
                            error=persistence_error,
                            execution=compact_execution,
                        ),
                    )
                    return await self._fail_run(
                        state,
                        correlation_id,
                        persistence_error,
                        artifacts,
                    )
                state = await self._event_store.append(terminal_event)
                try:
                    artifact = _artifact_from_execution(
                        execution.request.name, execution.result.data
                    )
                except ValidationError:
                    return await self._fail_run(
                        state,
                        correlation_id,
                        _internal_error(),
                        artifacts,
                    )
                if artifact is not None:
                    artifacts.append(artifact)

    async def _events_for(self, state: RunState) -> tuple[Event, ...]:
        events = await self._event_store.list_events(
            state.run_id,
            limit=MAX_EVENT_QUERY_LIMIT,
        )
        if len(events) != state.last_sequence:
            raise ContextBuilderError(
                ErrorInfo(
                    category=ErrorCategory.VALIDATION,
                    code=ErrorCode.INVALID_EVENT,
                    message="Run Event history exceeds the Context query boundary.",
                )
            )
        return events

    async def _fail_model(
        self,
        state: RunState,
        correlation_id: CorrelationId,
        activity_id: ActivityId,
        model_call_id: ModelCallId,
        error: ErrorInfo,
        discarded_output_chars: int,
        artifacts: list[Artifact],
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_microusd: int = 0,
    ) -> RunResult:
        state = await self._append(
            state,
            state.run_id,
            correlation_id,
            "ModelCallFailed",
            ModelCallFailedPayloadV2(
                activity_id=activity_id,
                model_call_id=model_call_id,
                error=error,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_microusd=cost_microusd,
                discarded_output_chars=discarded_output_chars,
            ),
        )
        return await self._fail_run(state, correlation_id, error, artifacts)

    async def _fail_run(
        self,
        state: RunState,
        correlation_id: CorrelationId,
        error: ErrorInfo,
        artifacts: list[Artifact],
    ) -> RunResult:
        state = await self._append(
            state,
            state.run_id,
            correlation_id,
            "RunFailed",
            RunFailedPayloadV2(error=error),
        )
        return RunResult(
            run_id=state.run_id,
            state=state,
            artifacts=tuple(artifacts),
        )

    async def _append(
        self,
        state: RunState | None,
        run_id: RunId,
        correlation_id: CorrelationId,
        event_type: str,
        payload: BaseModel,
    ) -> RunState:
        event = self._build_event(
            state,
            run_id,
            correlation_id,
            event_type,
            payload,
        )
        return await self._event_store.append(event)

    def _build_event(
        self,
        state: RunState | None,
        run_id: RunId,
        correlation_id: CorrelationId,
        event_type: str,
        payload: BaseModel,
    ) -> Event:
        return Event(
            event_id=self._id_generator.new(EventId),
            run_id=run_id,
            sequence=1 if state is None else state.last_sequence + 1,
            event_type=event_type,
            schema_version=RUN_EVENT_SCHEMA_VERSION_V2,
            occurred_at=self._clock.now(),
            causation_id=self._id_generator.new(CausationId),
            correlation_id=correlation_id,
            payload=payload.model_dump(mode="json"),
        )


def _provider_error(code: ErrorCode, message: str) -> ErrorInfo:
    return ErrorInfo(
        category=ErrorCategory.PROVIDER,
        code=code,
        message=message,
    )


def _reused_tool_identity_error(request: ModelRequest, message: Message) -> ErrorInfo | None:
    previous_calls = tuple(
        part
        for previous_message in request.messages
        for part in previous_message.parts
        if isinstance(part, ToolCallPart)
    )
    previous_tool_call_ids = {str(part.tool_call_id) for part in previous_calls}
    previous_provider_call_ids = {
        part.provider_call_id for part in previous_calls if part.provider_call_id is not None
    }
    if any(
        isinstance(part, ToolCallPart)
        and (
            str(part.tool_call_id) in previous_tool_call_ids
            or (
                part.provider_call_id is not None
                and part.provider_call_id in previous_provider_call_ids
            )
        )
        for part in message.parts
    ):
        return _provider_error(
            ErrorCode.PROVIDER_PROTOCOL_ERROR,
            "Model completion reused a Tool call identity.",
        )
    return None


def _internal_error() -> ErrorInfo:
    return ErrorInfo(
        category=ErrorCategory.INTERNAL,
        code=ErrorCode.INTERNAL_ERROR,
        message="Run encountered an invalid internal boundary result.",
    )


def _context_persistence_error() -> ErrorInfo:
    return ErrorInfo(
        category=ErrorCategory.VALIDATION,
        code=ErrorCode.INVALID_INPUT,
        message="Model request exceeds the Event persistence boundary.",
    )


def _tool_persistence_error() -> ErrorInfo:
    return ErrorInfo(
        category=ErrorCategory.TOOL,
        code=ErrorCode.TOOL_OUTPUT_TOO_LARGE,
        message="Tool execution evidence exceeds the Event persistence boundary.",
    )


def _compact_execution_failure(
    execution: ToolExecutionRecord,
    error: ErrorInfo,
) -> ToolExecutionRecord:
    return ToolExecutionRecord(
        request=execution.request,
        reached_adapter=execution.reached_adapter,
        result=ToolResult(
            tool_call_id=execution.request.tool_call_id,
            status=ToolStatus.FAILED,
            error=error,
        ),
        persistence_truncated=True,
    )


def _artifact_from_execution(
    tool_name: str,
    data: Mapping[str, object],
) -> Artifact | None:
    if tool_name != "workspace.write" or "artifact" not in data:
        return None
    return Artifact.model_validate(data["artifact"])
