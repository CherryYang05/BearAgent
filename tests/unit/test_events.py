from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import pytest
from pydantic import JsonValue, ValidationError

from bearagent.domain.events import MAX_EVENT_PAYLOAD_BYTES, Event
from bearagent.domain.ids import CausationId, CorrelationId, EventId, RunId


def build_event(**overrides: object) -> Event:
    values: dict[str, object] = {
        "event_id": str(EventId.new()),
        "run_id": str(RunId.new()),
        "sequence": 1,
        "event_type": "RunCreated",
        "schema_version": 1,
        "occurred_at": datetime(2026, 8, 10, 8, 0, tzinfo=UTC).isoformat(),
        "causation_id": str(CausationId.new()),
        "correlation_id": str(CorrelationId.new()),
        "payload": {"input": "hello", "budget": {"iterations": 8}},
    }
    values.update(overrides)
    return Event.model_validate(values)


def test_event_requires_positive_sequence() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        build_event(sequence=0)


def test_event_json_round_trip_has_complete_envelope() -> None:
    event = build_event()

    restored = Event.model_validate_json(event.model_dump_json())

    assert restored == event
    assert set(event.model_dump(mode="json")) == {
        "event_id",
        "run_id",
        "sequence",
        "event_type",
        "schema_version",
        "occurred_at",
        "causation_id",
        "correlation_id",
        "payload",
    }


def test_event_payload_is_recursively_immutable() -> None:
    event = build_event(payload={"nested": {"items": [1, 2]}})

    with pytest.raises(TypeError):
        cast(dict[str, JsonValue], event.payload)["new"] = "value"
    nested = cast(dict[str, JsonValue], event.payload["nested"])
    with pytest.raises(TypeError):
        nested["new"] = "value"
    assert isinstance(nested["items"], tuple)


def test_event_normalizes_aware_time_to_utc() -> None:
    occurred_at = datetime(2026, 8, 10, 16, 0, tzinfo=timezone(timedelta(hours=8)))

    event = build_event(occurred_at=occurred_at)

    assert event.occurred_at == datetime(2026, 8, 10, 8, 0, tzinfo=UTC)


def test_event_rejects_naive_time_and_non_json_payload() -> None:
    with pytest.raises(ValidationError, match="must include a timezone"):
        build_event(occurred_at=datetime(2026, 8, 10, 8, 0))

    with pytest.raises(ValidationError, match="unsupported value"):
        build_event(payload={"provider_response": object()})

    with pytest.raises(ValidationError, match="numbers must be finite"):
        build_event(payload={"usage": float("inf")})


def test_event_rejects_unknown_envelope_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        build_event(provider_request={"raw": "external"})


def test_event_payload_byte_limit_is_part_of_the_domain_contract() -> None:
    with pytest.raises(ValidationError, match="payload exceeds the byte limit"):
        build_event(payload={"value": "界" * (MAX_EVENT_PAYLOAD_BYTES // 3 + 1)})
