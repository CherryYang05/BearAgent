"""Read-only access to Event facts independent of the ordinary EventStore contract."""

from typing import Protocol

from bearagent.domain.errors import BearAgentError, ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.ids import RunId
from bearagent.domain.replay import (
    DEFAULT_REPLAY_LIMITS,
    DEFAULT_SCAN_RUNS,
    EventReplaySnapshot,
    EventRunPage,
    ReplayLimits,
)


class EventReplayError(BearAgentError):
    """A safe failure; partial histories never become a successful reconstruction."""


def replay_error(code: ErrorCode) -> EventReplayError:
    messages = {
        ErrorCode.INVALID_INPUT: "Replay input is invalid.",
        ErrorCode.INVALID_EVENT: "Run Event history is incomplete or invalid.",
        ErrorCode.RUN_NOT_FOUND: "Run has no committed Events.",
        ErrorCode.QUERY_LIMIT_EXCEEDED: "Run Event history exceeds the replay limit.",
        ErrorCode.QUERY_TIMEOUT: "Event inspection exceeded its time limit.",
        ErrorCode.PERSISTENCE_ERROR: "Event facts could not be read.",
    }
    category = (
        ErrorCategory.PERSISTENCE
        if code in {ErrorCode.PERSISTENCE_ERROR, ErrorCode.QUERY_TIMEOUT}
        else ErrorCategory.VALIDATION
    )
    return EventReplayError(ErrorInfo(category=category, code=code, message=messages[code]))


class EventReplaySource(Protocol):
    """Never append Events, repair projections, or execute an external Activity."""

    async def read_run_events(
        self, run_id: RunId, *, limits: ReplayLimits = DEFAULT_REPLAY_LIMITS
    ) -> EventReplaySnapshot: ...

    async def list_event_run_ids(
        self,
        *,
        after_run_id: RunId | None = None,
        limit: int = DEFAULT_SCAN_RUNS,
        limits: ReplayLimits = DEFAULT_REPLAY_LIMITS,
    ) -> EventRunPage: ...
