"""Provider-neutral result contracts for querying committed Run facts."""

from typing import Self

from pydantic import Field, model_validator

from bearagent.domain._base import DomainModel
from bearagent.domain.artifacts import Artifact
from bearagent.domain.events import Event
from bearagent.domain.ids import RunId
from bearagent.domain.runs import RunState

MAX_EVENT_PAGE_LIMIT = 10_000
MAX_EVENT_SEQUENCE = 9_223_372_036_854_775_807


class RunInspection(DomainModel):
    """One trusted Run projection plus outputs recovered from committed Events."""

    run_id: RunId
    state: RunState
    artifacts: tuple[Artifact, ...] = ()

    @model_validator(mode="after")
    def require_one_consistent_run(self) -> Self:
        if self.state.run_id != self.run_id:
            raise ValueError("inspection state must belong to run_id")
        artifact_ids = [artifact.artifact_id for artifact in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("inspection artifact identities must be unique")
        return self


class EventPage(DomainModel):
    """A bounded, contiguous page of committed Events for one Run."""

    run_id: RunId
    after_sequence: int = Field(ge=0, le=MAX_EVENT_SEQUENCE, strict=True)
    limit: int = Field(ge=1, le=MAX_EVENT_PAGE_LIMIT, strict=True)
    events: tuple[Event, ...] = ()
    next_after_sequence: int = Field(ge=0, le=MAX_EVENT_SEQUENCE, strict=True)
    has_more: bool

    @model_validator(mode="after")
    def require_stable_contiguous_cursor(self) -> Self:
        if len(self.events) > self.limit:
            raise ValueError("event page exceeds its requested limit")
        if any(event.run_id != self.run_id for event in self.events):
            raise ValueError("all events must belong to run_id")

        expected_sequences = tuple(
            range(self.after_sequence + 1, self.after_sequence + 1 + len(self.events))
        )
        if tuple(event.sequence for event in self.events) != expected_sequences:
            raise ValueError("event page must be ordered and contiguous")

        expected_cursor = self.events[-1].sequence if self.events else self.after_sequence
        if self.next_after_sequence != expected_cursor:
            raise ValueError("next_after_sequence must identify the last returned event")
        if self.has_more and not self.events:
            raise ValueError("an empty event page cannot report more results")
        return self
