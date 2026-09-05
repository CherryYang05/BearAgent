import asyncio

from tests.agent_loop_fixtures import (
    agent_run_input,
    model_completed,
    read_tool_spec,
    run_fingerprint,
    tool_executor,
)

from bearagent.adapters.diagnostics import DiagnosticEventStore
from bearagent.adapters.testing import FakeTool, InMemoryEventStore, ScriptedFakeModelProvider
from bearagent.application import AgentLoop
from bearagent.domain.diagnostics import DiagnosticRecord
from bearagent.domain.ids import ToolCallId
from bearagent.domain.model import (
    ModelCompleted,
    ModelFinishReason,
    ModelTextDelta,
    ModelToolCall,
    ModelUsage,
)


class RecordingSink:
    def __init__(self) -> None:
        self.records: list[DiagnosticRecord] = []

    def emit(self, record: DiagnosticRecord) -> None:
        self.records.append(record)


def test_execution_diagnostics_do_not_copy_event_payload_content() -> None:
    objective_secret = "objective-secret-marker"
    argument_secret = "argument-secret-marker"
    result_secret = "result-secret-marker"
    model_secret = "model-secret-marker"
    call_id = ToolCallId.new()
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelToolCall(
                    tool_call_id=call_id,
                    provider_call_id="call-1",
                    name="workspace.read",
                    arguments={"path": argument_secret},
                ),
                model_completed(ModelFinishReason.TOOL_CALLS),
            ),
            (
                ModelTextDelta(text=model_secret),
                ModelCompleted(
                    provider_request_id="response-2",
                    model="test-model",
                    finish_reason=ModelFinishReason.STOP,
                    usage=ModelUsage(input_tokens=3, output_tokens=4),
                ),
            ),
        ]
    )
    sink = RecordingSink()
    loop = AgentLoop(
        model_provider=provider,
        event_store=DiagnosticEventStore(InMemoryEventStore(), sink),
        tool_executor=tool_executor(FakeTool(read_tool_spec(), data={"content": result_secret})),
        run_fingerprint=run_fingerprint(),
    )
    run_input = agent_run_input().model_copy(update={"objective": objective_secret})

    result = asyncio.run(loop.run(run_input))

    serialized = "\n".join(record.model_dump_json() for record in sink.records)
    assert result.final_text == model_secret
    assert sink.records
    assert objective_secret not in serialized
    assert argument_secret not in serialized
    assert result_secret not in serialized
    assert model_secret not in serialized
    assert '"payload"' not in serialized
    assert '"message"' not in serialized
    assert '"details"' not in serialized
