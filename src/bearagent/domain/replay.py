"""Bounded snapshots and content-free reports for Event-only reconstruction."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from bearagent.domain._base import DomainModel
from bearagent.domain.errors import ErrorCode
from bearagent.domain.events import Event
from bearagent.domain.fingerprints import RunFingerprint
from bearagent.domain.ids import ActivityId, RunId
from bearagent.domain.runs import ActivityStatus, RunState, RunStatus

MAX_REPLAY_EVENTS = 10_000
MAX_REPLAY_BYTES = 16 * 1024 * 1024
MAX_SCAN_RUNS = 1_000
DEFAULT_SCAN_RUNS = 100
DEFAULT_REPLAY_TIMEOUT_MS = 30_000


class ReplayLimits(DomainModel):
    """Trusted ceilings; callers may lower but cannot bypass the hard limits."""

    max_events: int = Field(default=MAX_REPLAY_EVENTS, ge=1, le=MAX_REPLAY_EVENTS, strict=True)
    max_bytes: int = Field(default=MAX_REPLAY_BYTES, ge=1, le=MAX_REPLAY_BYTES, strict=True)
    timeout_ms: int = Field(default=DEFAULT_REPLAY_TIMEOUT_MS, ge=1, le=60_000, strict=True)


DEFAULT_REPLAY_LIMITS = ReplayLimits()


class ProjectionAvailability(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    UNREADABLE = "unreadable"


class ProjectionComparison(StrEnum):
    MATCHED = "matched"
    MISSING = "missing"
    MISMATCH = "mismatch"
    UNREADABLE = "unreadable"


class EventReplaySnapshot(DomainModel):
    """One complete committed Run prefix and its optional projection at the same instant."""

    run_id: RunId
    events: tuple[Event, ...] = Field(min_length=1, max_length=MAX_REPLAY_EVENTS)
    projection_availability: ProjectionAvailability
    projection: RunState | None = None

    @model_validator(mode="after")
    def require_complete_prefix(self) -> Self:
        if len({str(event.event_id) for event in self.events}) != len(self.events):
            raise ValueError("snapshot Event identities must be unique")
        for sequence, event in enumerate(self.events, 1):
            if event.run_id != self.run_id or event.sequence != sequence:
                raise ValueError("snapshot must contain one complete contiguous Run prefix")
        available = self.projection_availability is ProjectionAvailability.AVAILABLE
        if available != (self.projection is not None):
            raise ValueError("projection availability must agree with its value")
        if self.projection is not None and self.projection.run_id != self.run_id:
            raise ValueError("projection must belong to the snapshot Run")
        return self


class EventRunPage(DomainModel):
    """A page of identities discovered in Events, not a temporal or recovery order."""

    after_run_id: RunId | None = None
    limit: int = Field(ge=1, le=MAX_SCAN_RUNS, strict=True)
    run_ids: tuple[RunId, ...] = Field(max_length=MAX_SCAN_RUNS)
    next_after_run_id: RunId | None
    has_more: bool

    @model_validator(mode="after")
    def require_advancing_cursor(self) -> Self:
        keys = tuple(str(run_id) for run_id in self.run_ids)
        if len(keys) > self.limit or keys != tuple(sorted(set(keys))):
            raise ValueError("Run page must be bounded, unique and ordered")
        if self.after_run_id is not None and any(key <= str(self.after_run_id) for key in keys):
            raise ValueError("Run page must advance after its input cursor")
        expected = self.run_ids[-1] if self.run_ids else self.after_run_id
        if self.next_after_run_id != expected or (self.has_more and not self.run_ids):
            raise ValueError("Run page cursor is inconsistent")
        return self


class ReplaySummary(DomainModel):
    """Safe public summary; deliberately excludes historical content and error messages."""

    run_id: RunId
    status: RunStatus
    last_sequence: int = Field(ge=1, le=MAX_REPLAY_EVENTS, strict=True)
    last_event_type: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
    state_format_version: Literal[1] = 1
    state_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection: ProjectionComparison
    active_activity_id: ActivityId | None = None
    active_activity_status: ActivityStatus | None = None

    @property
    def needs_attention(self) -> bool:
        return self.status in {RunStatus.QUEUED, RunStatus.RUNNING} or (
            self.projection is not ProjectionComparison.MATCHED
        )


class RunReplay(DomainModel):
    """Internal reconstructed state; never serialize this object as a CLI report."""

    state: RunState
    summary: ReplaySummary
    run_fingerprint: RunFingerprint | None = None


class RunCheckItem(DomainModel):
    """One noteworthy Run or an explicit safe failure for that Run."""

    run_id: RunId
    summary: ReplaySummary | None = None
    error_code: ErrorCode | None = None

    @model_validator(mode="after")
    def require_one_outcome(self) -> Self:
        if (self.summary is None) == (self.error_code is None):
            raise ValueError("check item requires exactly one outcome")
        if self.summary is not None and self.summary.run_id != self.run_id:
            raise ValueError("check summary must belong to its Run")
        return self


class RunCheckPage(DomainModel):
    """Only noteworthy items; pagination counts all scanned Event-backed identities."""

    after_run_id: RunId | None = None
    limit: int = Field(ge=1, le=MAX_SCAN_RUNS, strict=True)
    scanned_count: int = Field(ge=0, le=MAX_SCAN_RUNS, strict=True)
    items: tuple[RunCheckItem, ...] = Field(max_length=MAX_SCAN_RUNS)
    next_after_run_id: RunId | None
    has_more: bool

    @property
    def exit_code(self) -> int:
        if any(item.error_code is not None for item in self.items):
            return 2
        return 1 if self.items else 0
