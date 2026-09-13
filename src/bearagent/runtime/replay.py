"""Reconstruct state using the existing reducer, without reading clocks or doing I/O."""

import hashlib
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from uuid import UUID

from bearagent.domain.errors import ErrorCode
from bearagent.domain.events import Event
from bearagent.domain.replay import (
    EventReplaySnapshot,
    ProjectionAvailability,
    ProjectionComparison,
    ReplayLimits,
    ReplaySummary,
    RunReplay,
)
from bearagent.domain.run_events import RunCreatedPayloadV4, parse_run_event_payload
from bearagent.domain.runs import ActivityStatus, RunState
from bearagent.ports.replay import replay_error
from bearagent.runtime.reducer import reduce_events


def state_hash(state: RunState) -> str:
    """Hash format v1: complete state, UTC microseconds, lowercase UUIDs, canonical JSON."""
    encoded = json.dumps(
        {"state_format_version": 1, "state": state.model_dump(mode="python")},
        default=_canonical_value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_value(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value)
    raise TypeError("Unsupported state hash value")


def reconstruct_run(
    snapshot: EventReplaySnapshot, *, limits: ReplayLimits, check: Callable[[], None]
) -> RunReplay:
    """Only complete, validated histories produce a result; check can stop bounded work."""
    if not snapshot.events or len(snapshot.events) > limits.max_events:
        raise replay_error(ErrorCode.QUERY_LIMIT_EXCEEDED)

    def checked_events() -> Iterator[Event]:
        size = 0
        for event in snapshot.events:
            check()
            if event.run_id != snapshot.run_id:
                raise replay_error(ErrorCode.INVALID_EVENT)
            size += len(event.model_dump_json().encode("utf-8"))
            if size > limits.max_bytes:
                raise replay_error(ErrorCode.QUERY_LIMIT_EXCEEDED)
            yield event

    state = reduce_events(checked_events())
    check()
    comparison = {
        ProjectionAvailability.MISSING: ProjectionComparison.MISSING,
        ProjectionAvailability.UNREADABLE: ProjectionComparison.UNREADABLE,
        ProjectionAvailability.AVAILABLE: (
            ProjectionComparison.MATCHED
            if snapshot.projection == state
            else ProjectionComparison.MISMATCH
        ),
    }[snapshot.projection_availability]
    active = next(
        (
            a
            for a in state.activities
            if a.status in {ActivityStatus.PENDING, ActivityStatus.RUNNING}
        ),
        None,
    )
    created = parse_run_event_payload(snapshot.events[0])
    summary = ReplaySummary(
        run_id=state.run_id,
        status=state.status,
        last_sequence=state.last_sequence,
        last_event_type=snapshot.events[-1].event_type,
        state_hash=state_hash(state),
        projection=comparison,
        active_activity_id=active.activity_id if active else None,
        active_activity_status=active.status if active else None,
    )
    check()
    return RunReplay(
        state=state,
        summary=summary,
        run_fingerprint=created.run_fingerprint
        if isinstance(created, RunCreatedPayloadV4)
        else None,
    )
