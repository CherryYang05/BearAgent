"""Application queries over committed Run facts."""

from pydantic import ValidationError

from bearagent.domain.artifacts import Artifact, artifact_from_tool_result_data
from bearagent.domain.errors import BearAgentError, ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.events import Event
from bearagent.domain.ids import RunId
from bearagent.domain.queries import EventPage, RunInspection
from bearagent.domain.run_events import (
    RunCreatedPayloadV3,
    ToolCallCompletedPayloadV2,
    parse_run_event_payload,
)
from bearagent.domain.runs import RunState
from bearagent.ports.store import (
    DEFAULT_EVENT_QUERY_LIMIT,
    MAX_EVENT_QUERY_LIMIT,
    EventStore,
    validate_event_query,
)

MAX_INSPECT_EVENTS = MAX_EVENT_QUERY_LIMIT


class RunQueryError(BearAgentError):
    """A safe failure while reading committed Run facts."""


class RunQueryService:
    """Build reusable query results without knowing the persistence adapter."""

    def __init__(self, event_store: EventStore) -> None:
        self._event_store = event_store

    async def inspect(self, run_id: RunId) -> RunInspection:
        """Return the Run projection and its complete bounded Artifact set."""
        state = await self._require_run(run_id)
        # A partial Artifact list would look complete to callers, so fail closed
        # before scanning when the committed history exceeds the trusted bound.
        if state.last_sequence > MAX_INSPECT_EVENTS:
            raise RunQueryError(
                ErrorInfo(
                    category=ErrorCategory.VALIDATION,
                    code=ErrorCode.QUERY_LIMIT_EXCEEDED,
                    message="Run Event history exceeds the inspect boundary.",
                )
            )

        events: list[Event] = []
        after_sequence = 0
        while after_sequence < state.last_sequence:
            remaining = state.last_sequence - after_sequence
            page_limit = min(DEFAULT_EVENT_QUERY_LIMIT, remaining)
            page = await self._event_store.list_events(
                run_id,
                after_sequence=after_sequence,
                limit=page_limit,
            )
            if not page:
                raise _invalid_history()
            expected_sequences = tuple(range(after_sequence + 1, after_sequence + 1 + len(page)))
            if (
                len(page) > page_limit
                or tuple(event.sequence for event in page) != expected_sequences
                or page[-1].sequence > state.last_sequence
            ):
                raise _invalid_history()
            events.extend(page)
            after_sequence = page[-1].sequence

        if len(events) != state.last_sequence:
            raise _invalid_history()

        artifacts: list[Artifact] = []
        provider_selection = None
        try:
            for event in events:
                payload = parse_run_event_payload(event)
                if isinstance(payload, RunCreatedPayloadV3):
                    provider_selection = payload.provider_selection
                if not isinstance(payload, ToolCallCompletedPayloadV2):
                    continue
                artifact = artifact_from_tool_result_data(
                    payload.execution.request.name,
                    payload.execution.result.data,
                )
                if artifact is not None:
                    artifacts.append(artifact)
            return RunInspection(
                run_id=run_id,
                state=state,
                artifacts=tuple(artifacts),
                provider_selection=provider_selection,
            )
        except (KeyError, ValidationError, ValueError) as error:
            raise _invalid_history(cause=error) from error

    async def events(
        self,
        run_id: RunId,
        *,
        after_sequence: int = 0,
        limit: int = DEFAULT_EVENT_QUERY_LIMIT,
    ) -> EventPage:
        """Return one bounded Event page from a consistent committed prefix."""
        try:
            validate_event_query(after_sequence, limit)
        except ValueError as error:
            raise RunQueryError(
                ErrorInfo(
                    category=ErrorCategory.VALIDATION,
                    code=ErrorCode.INVALID_INPUT,
                    message="Event query pagination is invalid.",
                ),
                cause=error,
            ) from error

        state = await self._require_run(run_id)
        available = max(0, state.last_sequence - after_sequence)
        query_limit = min(limit, available) if available else 0
        events = (
            await self._event_store.list_events(
                run_id,
                after_sequence=after_sequence,
                limit=query_limit,
            )
            if query_limit
            else ()
        )
        next_after_sequence = events[-1].sequence if events else after_sequence
        try:
            return EventPage(
                run_id=run_id,
                after_sequence=after_sequence,
                limit=limit,
                events=events,
                next_after_sequence=next_after_sequence,
                has_more=next_after_sequence < state.last_sequence,
            )
        except ValidationError as error:
            raise _invalid_history(cause=error) from error

    async def _require_run(self, run_id: RunId) -> RunState:
        state = await self._event_store.get_run(run_id)
        if state is None:
            raise RunQueryError(
                ErrorInfo(
                    category=ErrorCategory.VALIDATION,
                    code=ErrorCode.RUN_NOT_FOUND,
                    message="Run was not found.",
                )
            )
        return state


def _invalid_history(*, cause: BaseException | None = None) -> RunQueryError:
    return RunQueryError(
        ErrorInfo(
            category=ErrorCategory.VALIDATION,
            code=ErrorCode.INVALID_EVENT,
            message="Run Event history is incomplete or invalid.",
        ),
        cause=cause,
    )
