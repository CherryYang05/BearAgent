"""Immutable, versioned facts used across BearAgent ports."""

from collections.abc import Mapping
from datetime import UTC, datetime

from pydantic import Field, JsonValue, field_serializer, field_validator

from bearagent.domain._base import (
    DomainModel,
    freeze_json_mapping,
    thaw_json_mapping,
    validate_json_object,
)
from bearagent.domain.ids import CausationId, CorrelationId, EventId, RunId

EVENT_TYPE_PATTERN = r"^[A-Z][A-Za-z0-9]{0,127}$"


class Event(DomainModel):
    """Common envelope for an immutable domain fact."""

    event_id: EventId
    run_id: RunId
    sequence: int = Field(ge=1, strict=True)
    event_type: str = Field(pattern=EVENT_TYPE_PATTERN)
    schema_version: int = Field(default=1, ge=1, strict=True)
    occurred_at: datetime
    causation_id: CausationId
    correlation_id: CorrelationId
    payload: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_aware_utc_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(UTC)

    @field_validator("payload", mode="before")
    @classmethod
    def require_json_payload(cls, value: object) -> object:
        return validate_json_object(value)

    @field_validator("payload")
    @classmethod
    def freeze_payload(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return freeze_json_mapping(value)

    @field_serializer("payload")
    def serialize_payload(self, value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        return thaw_json_mapping(value)
