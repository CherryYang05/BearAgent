"""Serial Attempt coordination; the Reducer validates every persisted decision."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime

from pydantic import BaseModel, ValidationError

from bearagent.domain.agent import ModelPricing
from bearagent.domain.attempts import (
    AttemptFailedPayload,
    AttemptRequestedPayload,
    AttemptStartedPayload,
    AttemptSucceededPayload,
    ModelFailureEvidence,
    ModelSubmission,
    RecoveryAction,
    RecoveryDecisionPayload,
    RunStateV5,
    classify_failure,
)
from bearagent.domain.errors import BearAgentError, ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import (
    ActivityId,
    AttemptId,
    CausationId,
    CorrelationId,
    EventId,
    IdGenerator,
    ModelCallId,
)
from bearagent.domain.messages import Message, ToolCallPart
from bearagent.domain.model import ModelRequest
from bearagent.domain.run_events import (
    ModelCallCompletedPayloadV2,
    ModelCallFailedPayloadV2,
    ToolCallCompletedPayloadV2,
    ToolCallFailedPayloadV2,
)
from bearagent.domain.runs import ActivityKind
from bearagent.domain.tools import (
    PolicyDecision,
    PreparedToolRequest,
    ToolExecutionRecord,
    ToolRequest,
    ToolResult,
    ToolStatus,
)
from bearagent.ports.model import ModelProvider, ModelProviderError
from bearagent.ports.store import EventStore
from bearagent.runtime.attempts import (
    activity_deadline,
    check_dispatch_budget,
    decide_recovery,
    evidence_hash,
)
from bearagent.runtime.model_stream import ModelStreamCollector, ModelStreamProtocolError
from bearagent.runtime.pricing import estimate_model_cost_microusd
from bearagent.runtime.tool_executor import ToolExecutor


class _DispatchRejected(BearAgentError):
    """Trusted pre-dispatch check rejected this Attempt, without entering the adapter."""


class AttemptRunner:
    def __init__(
        self,
        *,
        state: RunStateV5,
        activity_id: ActivityId,
        correlation_id: CorrelationId,
        store: EventStore,
        now: Callable[[], datetime],
        ids: IdGenerator,
        sleep: Callable[[float], Awaitable[None]],
        random_int: Callable[[int, int], int],
    ) -> None:
        self.state = state
        self.activity_id = activity_id
        self._correlation_id = correlation_id
        self._store = store
        self._clock = now
        self._ids = ids
        self._sleep = sleep
        self._random_int = random_int
        self.evidence = next(e for e in state.activity_evidence if e.activity_id == activity_id)

    def now(self) -> datetime:
        return max(self._clock(), self.state.last_occurred_at)

    def event(self, name: str, payload: BaseModel, *, now: datetime | None = None) -> Event:
        return Event(
            event_id=self._ids.new(EventId),
            run_id=self.state.run_id,
            sequence=self.state.last_sequence + 1,
            schema_version=5,
            event_type=name,
            occurred_at=self.now() if now is None else now,
            correlation_id=self._correlation_id,
            causation_id=self._ids.new(CausationId),
            payload=payload.model_dump(mode="json"),
        )

    async def append(self, name: str, payload: BaseModel, *, now: datetime | None = None) -> None:
        state = await self._store.append(self.event(name, payload, now=now))
        if not isinstance(state, RunStateV5):
            raise ValueError("Attempt append returned an incompatible state")
        self.state = state

    async def request_attempt(self) -> AttemptId:
        attempts = tuple(a for a in self.state.attempts if a.activity_id == self.activity_id)
        previous = self.state.recovery_decisions[-1] if attempts else None
        attempt_id = self._ids.new(AttemptId)
        await self.append(
            "AttemptRequested",
            AttemptRequestedPayload(
                activity_id=self.activity_id,
                attempt_id=attempt_id,
                number=len(attempts) + 1,
                request_event_id=self.evidence.request_event_id,
                deadline=activity_deadline(self.state, self.evidence),
                prior_decision_id=previous.event_id if previous else None,
            ),
        )
        return attempt_id

    def remaining_ms(self) -> int:
        return max(
            0,
            min(
                self.evidence.timeout_ms,
                int((self.state.attempts[-1].deadline - self.now()).total_seconds() * 1000),
            ),
        )

    def check_dispatch(self, kind: ActivityKind) -> None:
        exhaustion = check_dispatch_budget(self.state, kind, self.now())
        if exhaustion is not None:
            raise _DispatchRejected(exhaustion.to_error_info())
        if self.remaining_ms() <= 0:
            raise _DispatchRejected(
                ErrorInfo(
                    category=ErrorCategory.BUDGET,
                    code=ErrorCode.BUDGET_EXHAUSTED,
                    message="Activity deadline exhausted.",
                )
            )

    async def record_outcome(
        self,
        payload: ModelCallCompletedPayloadV2
        | ModelCallFailedPayloadV2
        | ToolCallCompletedPayloadV2
        | ToolCallFailedPayloadV2,
        *,
        model_evidence: ModelFailureEvidence | None = None,
    ) -> bool:
        """Record attempt result; return True only after a durable retry decision and wait."""
        attempt = self.state.attempts[-1]
        values: dict[str, object] = dict(
            activity_id=self.activity_id,
            attempt_id=attempt.attempt_id,
            outcome_sha256=evidence_hash(payload),
        )
        if isinstance(payload, ModelCallCompletedPayloadV2 | ModelCallFailedPayloadV2):
            values.update(
                input_tokens=payload.input_tokens,
                output_tokens=payload.output_tokens,
                cost_microusd=payload.cost_microusd,
            )
        if isinstance(payload, ModelCallCompletedPayloadV2 | ToolCallCompletedPayloadV2):
            await self.append("AttemptSucceeded", AttemptSucceededPayload.model_validate(values))
            return False
        values.update(
            error=payload.error,
            reached_adapter=attempt.reached_adapter,
            model_evidence=model_evidence,
            failure_class=classify_failure(
                payload.error.code,
                semantics=self.evidence.semantics,
                reached_adapter=attempt.reached_adapter,
            ),
        )
        await self.append("AttemptFailed", AttemptFailedPayload.model_validate(values))
        attempt = self.state.attempts[-1]
        delay_ms = 0
        if attempt.number < self.state.retry_policy.max_attempts:
            delay_ms = self._random_int(0, self.state.retry_policy.backoff_ceiling(attempt.number))
        now = self.now()
        decision = decide_recovery(self.state, attempt, now=now, delay_ms=delay_ms)
        await self.append("RecoveryDecisionRecorded", decision, now=now)
        if decision.action is not RecoveryAction.RETRY:
            return False
        await self._sleep(decision.delay_ms / 1000)
        now = self.now()
        checked = decide_recovery(self.state, attempt, now=now)
        if checked.action is RecoveryAction.RETRY:
            return True
        superseding = RecoveryDecisionPayload.model_validate(
            {
                **checked.model_dump(),
                "supersedes_decision_id": self.state.recovery_decisions[-1].event_id,
            }
        )
        await self.append("RecoveryDecisionRecorded", superseding, now=now)
        return False

    async def tool(
        self, request: ToolRequest, executor: ToolExecutor
    ) -> ToolCallCompletedPayloadV2 | ToolCallFailedPayloadV2:
        while True:
            attempt_id = await self.request_attempt()

            async def before_execute(
                prepared: PreparedToolRequest,
                policy: PolicyDecision,
                *,
                current_attempt_id: AttemptId = attempt_id,
            ) -> int:
                self.check_dispatch(ActivityKind.TOOL)
                contract = next(
                    (c for c in self.state.recovery_contracts if c.name == request.name), None
                )
                spec = next((s for s in executor.specs if s.name == request.name), None)
                previous = next(
                    (
                        a.prepared_sha256
                        for a in self.state.attempts
                        if a.activity_id == self.activity_id and a.prepared_sha256 is not None
                    ),
                    None,
                )
                if (
                    contract is None
                    or spec is None
                    or evidence_hash(spec) != contract.spec_sha256
                    or (previous is not None and previous != evidence_hash(prepared))
                ):
                    raise _DispatchRejected(
                        ErrorInfo(
                            category=ErrorCategory.TOOL,
                            code=ErrorCode.TOOL_INVALID_INPUT,
                            message="Tool preparation or contract changed between attempts.",
                        )
                    )
                await self.append(
                    "AttemptStarted",
                    AttemptStartedPayload(
                        activity_id=self.activity_id,
                        attempt_id=current_attempt_id,
                        prepared=prepared,
                        policy=policy,
                    ),
                )
                return self.remaining_ms()

            try:
                execution = await executor.execute_recorded(request, before_execute=before_execute)
            except _DispatchRejected as error:
                execution = ToolExecutionRecord(
                    request=request,
                    reached_adapter=False,
                    result=ToolResult(
                        tool_call_id=request.tool_call_id,
                        status=ToolStatus.FAILED,
                        error=error.info,
                    ),
                )
            if execution.result.status is ToolStatus.SUCCEEDED:
                terminal: ToolCallCompletedPayloadV2 | ToolCallFailedPayloadV2 = (
                    ToolCallCompletedPayloadV2(
                        activity_id=self.activity_id,
                        tool_call_id=request.tool_call_id,
                        execution=execution,
                    )
                )
            else:
                if execution.result.error is None:
                    raise ValueError("failed Tool result has no Error")
                terminal = ToolCallFailedPayloadV2(
                    activity_id=self.activity_id,
                    tool_call_id=request.tool_call_id,
                    execution=execution,
                    error=execution.result.error,
                )
            try:
                self.event(
                    "ToolCallCompleted"
                    if isinstance(terminal, ToolCallCompletedPayloadV2)
                    else "ToolCallFailed",
                    terminal,
                )
            except ValidationError:
                error = ErrorInfo(
                    category=ErrorCategory.TOOL,
                    code=ErrorCode.TOOL_OUTPUT_TOO_LARGE,
                    message="Tool execution evidence exceeds the Event persistence boundary.",
                )
                execution = ToolExecutionRecord(
                    request=request,
                    reached_adapter=execution.reached_adapter,
                    result=ToolResult(
                        tool_call_id=request.tool_call_id, status=ToolStatus.FAILED, error=error
                    ),
                    persistence_truncated=True,
                )
                terminal = ToolCallFailedPayloadV2(
                    activity_id=self.activity_id,
                    tool_call_id=request.tool_call_id,
                    execution=execution,
                    error=error,
                )
            if await self.record_outcome(terminal):
                continue
            await self.append(
                "ToolCallCompleted"
                if isinstance(terminal, ToolCallCompletedPayloadV2)
                else "ToolCallFailed",
                terminal,
            )
            return terminal

    async def model(
        self,
        request: ModelRequest,
        provider: ModelProvider,
        *,
        call_id: ModelCallId,
        pricing: ModelPricing,
    ) -> ModelCallCompletedPayloadV2 | ModelCallFailedPayloadV2:
        while True:
            attempt_id = await self.request_attempt()
            collector = ModelStreamCollector()
            evidence = ModelFailureEvidence()
            input_tokens = output_tokens = cost = 0
            try:
                self.check_dispatch(ActivityKind.MODEL)
            except _DispatchRejected as failure:
                error = failure.info
                evidence = ModelFailureEvidence(
                    submission=ModelSubmission.NOT_SUBMITTED, usage_known=True
                )
            else:
                # Never catch append failures in the Provider exception handler.
                await self.append(
                    "AttemptStarted",
                    AttemptStartedPayload(activity_id=self.activity_id, attempt_id=attempt_id),
                )
                try:
                    timeout = self.remaining_ms()
                    if timeout <= 0:
                        raise TimeoutError
                    async with asyncio.timeout(timeout / 1000):
                        response = await collector.collect(provider.stream(request))
                    usage = response.completion.usage
                    if usage is None:
                        raise ModelStreamProtocolError(
                            "Model completion did not include usage.",
                            collector.discarded_output_chars,
                        )
                    input_tokens, output_tokens = usage.input_tokens, usage.output_tokens
                    cost = estimate_model_cost_microusd(input_tokens, output_tokens, pricing)
                    evidence = ModelFailureEvidence(usage_known=True)
                    if _reused_tool_identity(request, response.message):
                        raise ModelStreamProtocolError(
                            "Model completion reused a Tool call identity.",
                            collector.discarded_output_chars,
                        )
                    terminal = ModelCallCompletedPayloadV2(
                        activity_id=self.activity_id,
                        model_call_id=call_id,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_microusd=cost,
                        message=response.message,
                        provider_request_id=response.completion.provider_request_id,
                        provider_model=response.completion.model,
                        finish_reason=response.completion.finish_reason,
                    )
                    self.event("ModelCallCompleted", terminal)
                except ModelProviderError as failure:
                    error, evidence = failure.info, failure.evidence
                    # A partial stream contradicts "not submitted", regardless of adapter claims.
                    if collector.received_event:
                        evidence = ModelFailureEvidence()
                except ModelStreamProtocolError as failure:
                    error = failure.info
                except ValidationError:
                    error = ErrorInfo(
                        category=ErrorCategory.PROVIDER,
                        code=ErrorCode.PROVIDER_PROTOCOL_ERROR,
                        message="Model completion exceeds the Event persistence boundary.",
                    )
                except TimeoutError:
                    error = ErrorInfo(
                        category=ErrorCategory.PROVIDER,
                        code=ErrorCode.PROVIDER_TIMEOUT,
                        message="Model call timed out.",
                    )
                except Exception:
                    error = ErrorInfo(
                        category=ErrorCategory.PROVIDER,
                        code=ErrorCode.PROVIDER_ERROR,
                        message="Model call failed.",
                    )
                else:
                    await self.record_outcome(terminal)
                    await self.append("ModelCallCompleted", terminal)
                    return terminal
            if collector.reported_usage is not None:
                input_tokens = collector.reported_usage.input_tokens
                output_tokens = collector.reported_usage.output_tokens
                cost = estimate_model_cost_microusd(input_tokens, output_tokens, pricing)
                evidence = ModelFailureEvidence(usage_known=True)
            failed = ModelCallFailedPayloadV2(
                activity_id=self.activity_id,
                model_call_id=call_id,
                error=error,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_microusd=cost,
                discarded_output_chars=collector.discarded_output_chars,
            )
            if await self.record_outcome(failed, model_evidence=evidence):
                continue
            await self.append("ModelCallFailed", failed)
            return failed


def _reused_tool_identity(request: ModelRequest, message: Message) -> bool:
    previous = tuple(p for m in request.messages for p in m.parts if isinstance(p, ToolCallPart))
    calls = {str(p.tool_call_id) for p in previous}
    provider_calls = {p.provider_call_id for p in previous if p.provider_call_id is not None}
    return any(
        isinstance(p, ToolCallPart)
        and (
            str(p.tool_call_id) in calls
            or p.provider_call_id is not None
            and p.provider_call_id in provider_calls
        )
        for p in message.parts
    )
