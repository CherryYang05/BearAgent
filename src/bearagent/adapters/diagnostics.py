"""Standard-library adapters for local structured diagnostics."""

import json
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TextIO

from bearagent.domain.diagnostics import DiagnosticLevel, DiagnosticRecord
from bearagent.domain.errors import BearAgentError, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import ActivityId, RunId
from bearagent.domain.run_events import parse_run_event_payload
from bearagent.domain.runs import RunState
from bearagent.ports.diagnostics import DiagnosticSink, emit_safely
from bearagent.ports.store import DEFAULT_EVENT_QUERY_LIMIT, EventStore

MAX_DIAGNOSTIC_LINE_BYTES = 4_096
_SAFE_EXCEPTION_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_ACTIVITY_STARTED_EVENTS = frozenset({"ModelCallStarted", "ToolCallStarted"})
_ACTIVITY_TERMINAL_EVENTS = frozenset(
    {"ModelCallCompleted", "ModelCallFailed", "ToolCallCompleted", "ToolCallFailed"}
)


class NullDiagnosticSink:
    """Explicitly discard diagnostics for embedding and deterministic tests."""

    def emit(self, record: DiagnosticRecord) -> None:
        del record


class JsonLinesDiagnosticSink:
    """Write one bounded JSON object per line to stderr by default."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream

    def emit(self, record: DiagnosticRecord) -> None:
        line = json.dumps(
            record.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if len(line.encode("utf-8")) > MAX_DIAGNOSTIC_LINE_BYTES:
            raise ValueError("diagnostic line exceeds the byte limit")
        stream = self._stream if self._stream is not None else sys.stderr
        stream.write(f"{line}\n")
        stream.flush()


class DiagnosticEventStore:
    """Decorate an EventStore with post-commit metadata-only diagnostics."""

    def __init__(
        self,
        delegate: EventStore,
        sink: DiagnosticSink,
        *,
        clock: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
    ) -> None:
        self._delegate = delegate
        self._sink = sink
        self._clock = clock or _utc_now
        self._monotonic_ns = monotonic_ns or time.perf_counter_ns
        self._activity_started_at: dict[ActivityId, int] = {}

    async def append(self, event: Event) -> RunState:
        started_at = self._monotonic_ns()
        try:
            state = await self._delegate.append(event)
        except Exception as error:
            emit_safely(
                self._sink,
                operation_failure_record(
                    component="event_store",
                    operation="event_append",
                    error=error,
                    emitted_at=self._clock(),
                    run_id=event.run_id,
                    event=event,
                    operation_duration_ms=_elapsed_ms(started_at, self._monotonic_ns()),
                    name="event.append_failed",
                ),
            )
            raise

        finished_at = self._monotonic_ns()
        activity_id, error_info = _event_diagnostic_fields(event)
        activity_duration_ms = self._activity_duration(
            event,
            activity_id=activity_id,
            finished_at=finished_at,
        )
        emit_safely(
            self._sink,
            DiagnosticRecord(
                emitted_at=self._clock(),
                level=(DiagnosticLevel.ERROR if error_info is not None else DiagnosticLevel.INFO),
                name="event.committed",
                component="event_store",
                operation="event_append",
                run_id=event.run_id,
                activity_id=activity_id,
                event_id=event.event_id,
                event_type=event.event_type,
                sequence=event.sequence,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                operation_duration_ms=_elapsed_ms(started_at, finished_at),
                activity_duration_ms=activity_duration_ms,
                error_code=error_info.code if error_info is not None else None,
            ),
        )
        return state

    async def list_events(
        self,
        run_id: RunId,
        *,
        after_sequence: int = 0,
        limit: int = DEFAULT_EVENT_QUERY_LIMIT,
    ) -> tuple[Event, ...]:
        started_at = self._monotonic_ns()
        try:
            return await self._delegate.list_events(
                run_id,
                after_sequence=after_sequence,
                limit=limit,
            )
        except Exception as error:
            emit_safely(
                self._sink,
                operation_failure_record(
                    component="event_store",
                    operation="event_list",
                    error=error,
                    emitted_at=self._clock(),
                    run_id=run_id,
                    operation_duration_ms=_elapsed_ms(started_at, self._monotonic_ns()),
                ),
            )
            raise

    async def get_run(self, run_id: RunId) -> RunState | None:
        started_at = self._monotonic_ns()
        try:
            return await self._delegate.get_run(run_id)
        except Exception as error:
            emit_safely(
                self._sink,
                operation_failure_record(
                    component="event_store",
                    operation="run_get",
                    error=error,
                    emitted_at=self._clock(),
                    run_id=run_id,
                    operation_duration_ms=_elapsed_ms(started_at, self._monotonic_ns()),
                ),
            )
            raise

    def _activity_duration(
        self,
        event: Event,
        *,
        activity_id: ActivityId | None,
        finished_at: int,
    ) -> int | None:
        if activity_id is None:
            return None
        if event.event_type in _ACTIVITY_STARTED_EVENTS:
            self._activity_started_at[activity_id] = finished_at
            return None
        if event.event_type not in _ACTIVITY_TERMINAL_EVENTS:
            return None
        started_at = self._activity_started_at.pop(activity_id, None)
        if started_at is None:
            return None
        return _elapsed_ms(started_at, finished_at)


def operation_failure_record(
    *,
    component: str,
    operation: str,
    error: BaseException,
    error_info: ErrorInfo | None = None,
    emitted_at: datetime | None = None,
    run_id: RunId | None = None,
    event: Event | None = None,
    operation_duration_ms: int | None = None,
    name: str = "operation.failed",
) -> DiagnosticRecord:
    """Build a failure signal without reading exception text or arbitrary details."""

    safe_error_info = (
        error_info
        if error_info is not None
        else error.info
        if isinstance(error, BearAgentError)
        else None
    )
    return DiagnosticRecord(
        emitted_at=emitted_at or _utc_now(),
        level=DiagnosticLevel.ERROR,
        name=name,
        component=component,
        operation=operation,
        run_id=run_id,
        event_id=event.event_id if event is not None else None,
        event_type=event.event_type if event is not None else None,
        sequence=event.sequence if event is not None else None,
        correlation_id=event.correlation_id if event is not None else None,
        causation_id=event.causation_id if event is not None else None,
        operation_duration_ms=operation_duration_ms,
        error_code=(
            safe_error_info.code if safe_error_info is not None else ErrorCode.INTERNAL_ERROR
        ),
        exception_type=_safe_exception_type(error),
    )


def _event_diagnostic_fields(event: Event) -> tuple[ActivityId | None, ErrorInfo | None]:
    try:
        payload = parse_run_event_payload(event)
    except (KeyError, ValueError):
        return None, None
    activity_id = getattr(payload, "activity_id", None)
    error_info = getattr(payload, "error", None)
    return (
        activity_id if isinstance(activity_id, ActivityId) else None,
        error_info if isinstance(error_info, ErrorInfo) else None,
    )


def _safe_exception_type(error: BaseException) -> str:
    name = type(error).__name__
    return name if _SAFE_EXCEPTION_TYPE.fullmatch(name) else "Exception"


def _elapsed_ms(started_at: int, finished_at: int) -> int:
    return max(0, (finished_at - started_at) // 1_000_000)


def _utc_now() -> datetime:
    return datetime.now(UTC)
