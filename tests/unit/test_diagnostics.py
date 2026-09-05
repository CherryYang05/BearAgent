import asyncio
import json
from datetime import UTC, datetime
from io import StringIO

import pytest
from pydantic import ValidationError
from tests.store_fixtures import failed_run_event, run_created_event, successful_run_events

from bearagent.adapters.diagnostics import (
    DiagnosticEventStore,
    JsonLinesDiagnosticSink,
    operation_failure_record,
)
from bearagent.adapters.testing import EventSequenceError, InMemoryEventStore
from bearagent.domain.diagnostics import DiagnosticLevel, DiagnosticRecord
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import RunId
from bearagent.ports.diagnostics import emit_safely


class RecordingSink:
    def __init__(self) -> None:
        self.records: list[DiagnosticRecord] = []

    def emit(self, record: DiagnosticRecord) -> None:
        self.records.append(record)


class FailingSink:
    def emit(self, record: DiagnosticRecord) -> None:
        del record
        raise OSError("diagnostic sink is unavailable")


def test_diagnostic_record_is_frozen_and_rejects_arbitrary_text_fields() -> None:
    record = DiagnosticRecord(
        emitted_at=datetime(2026, 9, 2, tzinfo=UTC),
        level=DiagnosticLevel.INFO,
        name="event.committed",
        component="event_store",
        operation="event_append",
    )

    with pytest.raises(ValidationError):
        DiagnosticRecord.model_validate(
            {
                **record.model_dump(mode="python"),
                "message": "arbitrary content must not fit the schema",
            }
        )
    with pytest.raises(ValidationError):
        record.level = DiagnosticLevel.ERROR  # type: ignore[misc]


def test_json_lines_sink_serializes_only_the_bounded_record() -> None:
    raw_secret = "raw-exception-secret"
    stream = StringIO()
    sink = JsonLinesDiagnosticSink(stream)

    sink.emit(
        operation_failure_record(
            component="bootstrap",
            operation="build_run_services",
            error=RuntimeError(raw_secret),
            emitted_at=datetime(2026, 9, 2, tzinfo=UTC),
        )
    )

    payload = json.loads(stream.getvalue())
    assert payload == {
        "component": "bootstrap",
        "emitted_at": "2026-09-02T00:00:00Z",
        "error_code": "internal_error",
        "exception_type": "RuntimeError",
        "level": "error",
        "name": "operation.failed",
        "operation": "build_run_services",
        "schema_version": 1,
    }
    assert raw_secret not in stream.getvalue()


def test_diagnostic_event_store_emits_only_after_successful_append() -> None:
    run_id = RunId.new()
    event = run_created_event(run_id)
    sink = RecordingSink()
    store = DiagnosticEventStore(InMemoryEventStore(), sink)

    state = asyncio.run(store.append(event))

    assert state.run_id == run_id
    assert len(sink.records) == 1
    committed = sink.records[0]
    assert committed.name == "event.committed"
    assert committed.run_id == run_id
    assert committed.event_id == event.event_id
    assert committed.event_type == "RunCreated"
    assert committed.sequence == 1
    assert committed.operation_duration_ms is not None

    with pytest.raises(EventSequenceError):
        asyncio.run(store.append(event))

    assert [record.name for record in sink.records] == [
        "event.committed",
        "event.append_failed",
    ]
    assert sink.records[-1].error_code is ErrorCode.PERSISTENCE_ERROR


def test_diagnostic_event_store_correlates_activity_duration_and_safe_error_code() -> None:
    sink = RecordingSink()
    ticks = iter(range(0, 100_000_000, 1_000_000))
    store = DiagnosticEventStore(
        InMemoryEventStore(),
        sink,
        monotonic_ns=lambda: next(ticks),
    )
    events = successful_run_events()[:5]

    for event in events:
        asyncio.run(store.append(event))

    terminal = sink.records[-1]
    assert terminal.event_type == "ModelCallCompleted"
    assert terminal.activity_id is not None
    assert terminal.activity_duration_ms is not None

    failed = failed_run_event(events[0].run_id, sequence=6, message="private failure body")
    asyncio.run(store.append(failed))
    failure_record = sink.records[-1]
    assert failure_record.level is DiagnosticLevel.ERROR
    assert failure_record.error_code is ErrorCode.INTERNAL_ERROR
    assert "private failure body" not in failure_record.model_dump_json()


def test_failing_sink_does_not_change_event_or_error_behavior() -> None:
    run_id = RunId.new()
    event = run_created_event(run_id)
    store = DiagnosticEventStore(InMemoryEventStore(), FailingSink())

    state = asyncio.run(store.append(event))

    assert state.run_id == run_id
    with pytest.raises(EventSequenceError):
        asyncio.run(store.append(event))


def test_emit_safely_contains_sink_failure() -> None:
    record = operation_failure_record(
        component="cli",
        operation="run",
        error=RuntimeError("not logged"),
    )

    emit_safely(FailingSink(), record)
