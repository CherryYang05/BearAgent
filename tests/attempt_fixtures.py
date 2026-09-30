"""Small inspectable v5 histories, built without Provider or filesystem side effects."""

from datetime import timedelta

from pydantic import BaseModel

from bearagent.domain.attempts import (
    AttemptFailedPayload,
    AttemptRequestedPayload,
    AttemptStartedPayload,
    AttemptSucceededPayload,
    FailureClass,
    RecoverySemantics,
    RetryPolicy,
    RunStateV5,
    ToolRecoveryContract,
)
from bearagent.domain.errors import ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import (
    ActivityId,
    AttemptId,
    CausationId,
    CorrelationId,
    EventId,
    RunId,
    SessionId,
    ToolCallId,
)
from bearagent.domain.run_events import (
    RunCreatedPayloadV5,
    RunStartedPayloadV2,
    RunSucceededPayloadV2,
    ToolCallCompletedPayloadV2,
    ToolCallFailedPayloadV2,
    ToolCallRequestedPayloadV2,
    ToolCallStartedPayloadV2,
)
from bearagent.domain.tools import (
    PolicyDecision,
    PolicyOutcome,
    PolicyReason,
    PreparedToolRequest,
    ToolExecutionRecord,
    ToolRequest,
    ToolResult,
    ToolStatus,
)
from bearagent.runtime.attempts import activity_deadline, decide_recovery, evidence_hash
from bearagent.runtime.reducer import reduce_event
from tests.agent_loop_fixtures import (
    BASE_TIME,
    agent_config,
    budget_limits,
    read_tool_spec,
    run_fingerprint,
)


class AttemptHistory:
    def __init__(self, *, max_attempts: int = 3, max_tool_calls: int = 5) -> None:
        self.run_id = RunId.new()
        self.activity_id = ActivityId.new()
        self.call_id = ToolCallId.new()
        self.state: RunStateV5 | None = None
        self.events: list[Event] = []
        self.now = BASE_TIME
        self.request = ToolRequest(
            tool_call_id=self.call_id, name="workspace.read", arguments={"path": "docs/index.md"}
        )
        self.prepared = PreparedToolRequest(**self.request.model_dump())
        self.policy = PolicyDecision(outcome=PolicyOutcome.ALLOW, reason=PolicyReason.ALLOWED)
        fingerprint = run_fingerprint()
        self.add(
            "RunCreated",
            RunCreatedPayloadV5(
                session_id=SessionId.new(),
                budget_limits=budget_limits(max_tool_calls=max_tool_calls),
                objective="Read one document",
                agent_config=agent_config(),
                run_fingerprint=fingerprint,
                retry_policy=RetryPolicy(max_attempts=max_attempts),
                recovery_contracts=(
                    ToolRecoveryContract(
                        name="workspace.read",
                        spec_sha256=fingerprint.tools[0].sha256,
                        semantics=RecoverySemantics.READ_ONLY,
                        timeout_ms=read_tool_spec().timeout_ms,
                    ),
                ),
            ),
        )
        self.add("RunStarted", RunStartedPayloadV2())
        self.requested = self.add(
            "ToolCallRequested",
            ToolCallRequestedPayloadV2(
                activity_id=self.activity_id,
                tool_call_id=self.call_id,
                tool_name=self.request.name,
                request=self.request,
            ),
        )
        self.add(
            "ToolCallStarted",
            ToolCallStartedPayloadV2(activity_id=self.activity_id, tool_call_id=self.call_id),
        )

    def event(self, event_type: str, payload: BaseModel) -> Event:
        return Event(
            event_id=EventId.new(),
            run_id=self.run_id,
            sequence=len(self.events) + 1,
            event_type=event_type,
            schema_version=5,
            occurred_at=self.now,
            causation_id=CausationId.new(),
            correlation_id=CorrelationId.new(),
            payload=payload.model_dump(mode="json"),
        )

    def add(self, event_type: str, payload: BaseModel) -> Event:
        event = self.event(event_type, payload)
        result = reduce_event(self.state, event)
        assert isinstance(result, RunStateV5)
        self.state = result
        self.events.append(event)
        self.now += timedelta(milliseconds=1)
        return event

    def start_attempt(self) -> AttemptId:
        assert self.state is not None
        attempt_id = AttemptId.new()
        decision_id = (
            self.state.recovery_decisions[-1].event_id if self.state.recovery_decisions else None
        )
        self.add(
            "AttemptRequested",
            AttemptRequestedPayload(
                activity_id=self.activity_id,
                attempt_id=attempt_id,
                number=len(self.state.attempts) + 1,
                request_event_id=self.requested.event_id,
                deadline=activity_deadline(self.state, self.state.activity_evidence[0]),
                prior_decision_id=decision_id,
            ),
        )
        self.add(
            "AttemptStarted",
            AttemptStartedPayload(
                activity_id=self.activity_id,
                attempt_id=attempt_id,
                prepared=self.prepared,
                policy=self.policy,
            ),
        )
        return attempt_id

    def fail(self) -> ToolCallFailedPayloadV2:
        assert self.state is not None
        error = ErrorInfo(
            category=ErrorCategory.TOOL,
            code=ErrorCode.TOOL_TIMEOUT,
            message="Read timed out.",
            retryable=False,
        )
        terminal = ToolCallFailedPayloadV2(
            activity_id=self.activity_id,
            tool_call_id=self.call_id,
            error=error,
            execution=ToolExecutionRecord(
                request=self.request,
                prepared_request=self.prepared,
                policy_decision=self.policy,
                reached_adapter=True,
                result=ToolResult(tool_call_id=self.call_id, status=ToolStatus.FAILED, error=error),
            ),
        )
        self.add(
            "AttemptFailed",
            AttemptFailedPayload(
                activity_id=self.activity_id,
                attempt_id=self.state.attempts[-1].attempt_id,
                outcome_sha256=evidence_hash(terminal),
                error=error,
                failure_class=FailureClass.TRANSIENT_INFRASTRUCTURE,
                reached_adapter=True,
            ),
        )
        return terminal

    def decide(self, *, delay_ms: int = 0) -> None:
        assert self.state is not None
        self.add(
            "RecoveryDecisionRecorded",
            decide_recovery(self.state, self.state.attempts[-1], now=self.now, delay_ms=delay_ms),
        )
        self.now += timedelta(milliseconds=delay_ms)

    def succeed(self) -> None:
        assert self.state is not None
        terminal = ToolCallCompletedPayloadV2(
            activity_id=self.activity_id,
            tool_call_id=self.call_id,
            execution=ToolExecutionRecord(
                request=self.request,
                prepared_request=self.prepared,
                policy_decision=self.policy,
                reached_adapter=True,
                result=ToolResult(
                    tool_call_id=self.call_id,
                    status=ToolStatus.SUCCEEDED,
                    data={"content": "Read once successfully."},
                ),
            ),
        )
        self.add(
            "AttemptSucceeded",
            AttemptSucceededPayload(
                activity_id=self.activity_id,
                attempt_id=self.state.attempts[-1].attempt_id,
                outcome_sha256=evidence_hash(terminal),
            ),
        )
        self.add("ToolCallCompleted", terminal)
        self.add("RunSucceeded", RunSucceededPayloadV2())


def retried_read_events() -> tuple[Event, ...]:
    history = AttemptHistory()
    history.start_attempt()
    history.fail()
    history.decide(delay_ms=10)
    history.start_attempt()
    history.succeed()
    return tuple(history.events)
