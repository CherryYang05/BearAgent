"""Immutable facts used by event store ports and test adapters."""

from collections.abc import Mapping
from dataclasses import dataclass, field


def _empty_payload() -> Mapping[str, object]:
    return {}


@dataclass(frozen=True, slots=True)
class Event:
    """A minimal P0 event envelope.

    F-0001 and F-0003 will extend and version the production envelope. P0 keeps
    only the fields required to verify store ordering and package boundaries.
    """

    event_id: str
    run_id: str
    sequence: int
    event_type: str
    payload: Mapping[str, object] = field(default_factory=_empty_payload)

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must not be empty")
        if not self.run_id:
            raise ValueError("run_id must not be empty")
        if self.sequence < 1:
            raise ValueError("sequence must be at least 1")
        if not self.event_type:
            raise ValueError("event_type must not be empty")
