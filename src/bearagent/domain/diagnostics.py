"""Typed diagnostics that help troubleshooting without deciding Run state."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator

from bearagent.domain._base import DomainModel
from bearagent.domain.errors import ErrorCode
from bearagent.domain.events import EVENT_TYPE_PATTERN
from bearagent.domain.ids import (
    ActivityId,
    CausationId,
    CorrelationId,
    EventId,
    RunId,
)

DIAGNOSTIC_NAME_PATTERN = r"^[a-z][a-z0-9_.-]{0,63}$"
EXCEPTION_TYPE_PATTERN = r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$"


class DiagnosticLevel(StrEnum):
    """Small fixed severity vocabulary for local operational signals."""

    INFO = "info"
    ERROR = "error"


class DiagnosticRecord(DomainModel):
    """A bounded signal that can never carry Event bodies or arbitrary text."""

    schema_version: Literal[1] = 1
    emitted_at: datetime
    level: DiagnosticLevel
    name: str = Field(pattern=DIAGNOSTIC_NAME_PATTERN)
    component: str = Field(pattern=DIAGNOSTIC_NAME_PATTERN)
    operation: str = Field(pattern=DIAGNOSTIC_NAME_PATTERN)
    run_id: RunId | None = None
    activity_id: ActivityId | None = None
    event_id: EventId | None = None
    event_type: str | None = Field(default=None, pattern=EVENT_TYPE_PATTERN)
    sequence: int | None = Field(default=None, ge=1, strict=True)
    correlation_id: CorrelationId | None = None
    causation_id: CausationId | None = None
    operation_duration_ms: int | None = Field(default=None, ge=0, strict=True)
    activity_duration_ms: int | None = Field(default=None, ge=0, strict=True)
    error_code: ErrorCode | None = None
    exception_type: str | None = Field(default=None, pattern=EXCEPTION_TYPE_PATTERN)

    @field_validator("emitted_at")
    @classmethod
    def require_aware_utc_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("emitted_at must include a timezone")
        return value.astimezone(UTC)
