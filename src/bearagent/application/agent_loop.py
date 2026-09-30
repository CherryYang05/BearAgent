"""Serial P1 Agent Loop coordinated across persisted Activity boundaries."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ValidationError

from bearagent.application.attempt_execution import AttemptRunner
from bearagent.domain.agent import RunInput, RunResult
from bearagent.domain.artifacts import Artifact, artifact_from_tool_result_data
from bearagent.domain.attempts import (
    RecoveryAction,
    RecoveryReason,
    RecoverySemantics,
    RetryPolicy,
    RunStateV5,
    ToolRecoveryContract,
)
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.fingerprints import RunFingerprint
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
from bearagent.domain.messages import TextPart, ToolCallPart
from bearagent.domain.model import ModelFinishReason
from bearagent.domain.providers import ProviderSelection
from bearagent.domain.run_events import (
    RUN_EVENT_SCHEMA_VERSION_V5,
    ModelCallFailedPayloadV2,
    ModelCallRequestedPayloadV2,
    ModelCallStartedPayloadV2,
    RunCreatedPayloadV5,
    RunFailedPayloadV2,
    RunStartedPayloadV2,
    RunSucceededPayloadV2,
    ToolCallFailedPayloadV2,
    ToolCallRequestedPayloadV2,
    ToolCallStartedPayloadV2,
)
from bearagent.domain.runs import ActivityKind, RunState
from bearagent.domain.tools import (
    ToolRequest,
    ToolSideEffect,
)
from bearagent.ports.model import ModelProvider
from bearagent.ports.store import MAX_EVENT_QUERY_LIMIT, EventStore
from bearagent.runtime.attempts import evidence_hash
from bearagent.runtime.budgets import check_activity_budget
from bearagent.runtime.context import ContextBuilder, ContextBuilderError
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
        run_fingerprint: RunFingerprint,
        context_builder: ContextBuilder | None = None,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
        provider_selection: ProviderSelection | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_int: Callable[[int, int], int] = random.randint,
    ) -> None:
        self._retry_policy = RetryPolicy() if retry_policy is None else retry_policy
        self._sleep = sleep
        self._random_int = random_int
        self._model_provider = model_provider
        self._event_store = event_store
        self._tool_executor = tool_executor
        self._tool_specs = tool_executor.specs
        self._context_builder = ContextBuilder() if context_builder is None else context_builder
        self._clock = SystemClock() if clock is None else clock
        self._provider_selection = provider_selection
        self._run_fingerprint = run_fingerprint
        self._id_generator = Uuid4IdGenerator() if id_generator is None else id_generator

    async def run(self, run_input: RunInput, *, run_id: RunId | None = None) -> RunResult:
        """Create and drive one Run until it reaches a persisted terminal state."""
        available_tool_names = {spec.name for spec in self._tool_specs}
        if any(name not in available_tool_names for name in run_input.agent_config.tool_names):
            raise ValueError("AgentConfig references a Tool that is not registered")
        # A composition root may allocate the ID for early CLI visibility. The
        # identifier carries no authority; all execution still starts at append.
        run_id = self._id_generator.new(RunId) if run_id is None else run_id
        correlation_id = self._id_generator.new(CorrelationId)
        run_created = RunCreatedPayloadV5(
            session_id=run_input.session_id,
            budget_limits=run_input.budget_limits,
            objective=run_input.objective,
            agent_config=run_input.agent_config,
            run_fingerprint=self._run_fingerprint,
            provider_selection=self._provider_selection,
            retry_policy=self._retry_policy,
            recovery_contracts=tuple(
                ToolRecoveryContract(
                    name=spec.name,
                    spec_sha256=evidence_hash(spec),
                    semantics=RecoverySemantics.READ_ONLY
                    if spec.side_effect is ToolSideEffect.READ_ONLY
                    else RecoverySemantics.NON_IDEMPOTENT,
                    timeout_ms=spec.timeout_ms,
                )
                for spec in sorted(self._tool_specs, key=lambda spec: spec.name)
            ),
        )
        state = await self._append(
            None,
            run_id,
            correlation_id,
            "RunCreated",
            run_created,
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

            runner = self._attempt_runner(state, activity_id, correlation_id)
            response = await runner.model(
                context.request,
                self._model_provider,
                call_id=model_call_id,
                pricing=run_input.agent_config.pricing,
            )
            state = runner.state
            if isinstance(response, ModelCallFailedPayloadV2):
                return await self._fail_run(state, correlation_id, response.error, artifacts)

            if response.finish_reason is ModelFinishReason.STOP:
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
                runner = self._attempt_runner(state, tool_activity_id, correlation_id)
                terminal = await runner.tool(request, self._tool_executor)
                state = runner.state
                execution = terminal.execution
                if isinstance(terminal, ToolCallFailedPayloadV2):
                    decision = state.recovery_decisions[-1]
                    if (
                        decision.action is RecoveryAction.STOP_RUN
                        or execution.persistence_truncated
                    ):
                        error = terminal.error
                        if decision.reason is RecoveryReason.EFFECT_INDETERMINATE:
                            error = ErrorInfo(
                                category=ErrorCategory.TOOL,
                                code=ErrorCode.EFFECT_INDETERMINATE,
                                message="Tool effect is indeterminate; Run stopped.",
                            )
                        return await self._fail_run(state, correlation_id, error, artifacts)
                try:
                    artifact = artifact_from_tool_result_data(
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

    def _attempt_runner(
        self,
        state: RunState,
        activity_id: ActivityId,
        correlation_id: CorrelationId,
    ) -> AttemptRunner:
        if not isinstance(state, RunStateV5):
            raise ValueError("AgentLoop requires a v5 Run")
        return AttemptRunner(
            state=state,
            activity_id=activity_id,
            correlation_id=correlation_id,
            store=self._event_store,
            now=self._clock.now,
            ids=self._id_generator,
            sleep=self._sleep,
            random_int=self._random_int,
        )

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
            schema_version=RUN_EVENT_SCHEMA_VERSION_V5,
            occurred_at=max(self._clock.now(), state.last_occurred_at)
            if isinstance(state, RunStateV5)
            else self._clock.now(),
            causation_id=self._id_generator.new(CausationId),
            correlation_id=correlation_id,
            payload=payload.model_dump(mode="json"),
        )


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
