"""Real persisted histories shared by replay contract and corruption tests."""

from collections.abc import Mapping
from pathlib import Path

from pydantic import JsonValue

from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.domain.events import Event
from bearagent.domain.ids import ActivityId, RunId, SessionId, ToolCallId
from bearagent.domain.providers import ModelProtocol, ProviderSelection
from bearagent.domain.run_events import (
    RunCreatedPayload,
    RunCreatedPayloadV2,
    RunCreatedPayloadV3,
    RunCreatedPayloadV4,
    ToolCallCompletedPayloadV2,
    ToolCallRequestedPayloadV2,
    ToolCallStartedPayload,
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
from tests.agent_loop_fixtures import agent_config, run_fingerprint
from tests.store_fixtures import DEFAULT_LIMITS, make_event, payload_json


def versioned_history(version: int, run_id: RunId | None = None) -> tuple[Event, ...]:
    run_id = run_id or RunId.new()
    session = SessionId.parse("00000000-0000-4000-8000-000000000001")
    base = {"session_id": session, "budget_limits": DEFAULT_LIMITS}
    created: RunCreatedPayload
    if version == 1:
        created = RunCreatedPayload.model_validate(base)
    else:
        extended = {**base, "objective": "PRIVATE-OBJECTIVE", "agent_config": agent_config()}
        if version == 2:
            created = RunCreatedPayloadV2.model_validate(extended)
        elif version == 3:
            created = RunCreatedPayloadV3.model_validate(
                {
                    **extended,
                    "provider_selection": ProviderSelection(
                        provider_id="test",
                        config_version="v1",
                        protocol=ModelProtocol.OPENAI_RESPONSES,
                    ),
                }
            )
        else:
            created = RunCreatedPayloadV4.model_validate(
                {
                    **extended,
                    "run_fingerprint": run_fingerprint(),
                }
            )
    payloads: tuple[tuple[str, Mapping[str, JsonValue]], ...] = (
        ("RunCreated", payload_json(created)),
        ("RunStarted", {}),
        ("RunSucceeded", {}),
    )
    return tuple(
        make_event(run_id, i, name, payload, schema_version=version)
        for i, (name, payload) in enumerate(payloads, 1)
    )


def tool_history(version: int, *, mismatch: bool = False) -> tuple[Event, ...]:
    started = versioned_history(version)[:2]
    run_id = started[0].run_id
    activity_id, call_id = ActivityId.new(), ToolCallId.new()
    request = ToolRequest(
        tool_call_id=call_id, name="workspace.read", arguments={"path": "PRIVATE-PATH"}
    )
    executed = (
        request.model_copy(update={"arguments": {"path": "different"}}) if mismatch else request
    )
    payloads = (
        (
            "ToolCallRequested",
            ToolCallRequestedPayloadV2(
                activity_id=activity_id,
                tool_call_id=call_id,
                tool_name=request.name,
                request=request,
            ),
        ),
        ("ToolCallStarted", ToolCallStartedPayload(activity_id=activity_id, tool_call_id=call_id)),
        (
            "ToolCallCompleted",
            ToolCallCompletedPayloadV2(
                activity_id=activity_id,
                tool_call_id=call_id,
                execution=ToolExecutionRecord(
                    request=executed,
                    prepared_request=PreparedToolRequest.model_validate(executed.model_dump()),
                    policy_decision=PolicyDecision(
                        outcome=PolicyOutcome.ALLOW, reason=PolicyReason.ALLOWED
                    ),
                    reached_adapter=True,
                    result=ToolResult(
                        tool_call_id=call_id,
                        status=ToolStatus.SUCCEEDED,
                        data={"content": "PRIVATE-RESULT"},
                    ),
                ),
            ),
        ),
    )
    return (
        *started,
        *(
            make_event(run_id, i, name, payload_json(payload), schema_version=version)
            for i, (name, payload) in enumerate(payloads, 3)
        ),
    )


async def persist(database: Path, events: tuple[Event, ...]) -> SqliteEventStore:
    store = SqliteEventStore(database)
    await store.initialize()
    for event in events:
        await store.append(event)
    return store
