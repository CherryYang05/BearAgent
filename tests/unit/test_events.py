import pytest

from bearagent.domain.events import Event


def test_event_requires_positive_sequence() -> None:
    with pytest.raises(ValueError, match="sequence"):
        Event(event_id="event-1", run_id="run-1", sequence=0, event_type="RunCreated")
