"""Stable and safe error information for BearAgent boundaries."""

import re
from collections.abc import Mapping
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import Self

from pydantic import (
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_serializer,
    field_validator,
    model_validator,
)

from bearagent.domain._base import DomainModel

MAX_ERROR_MESSAGE_CHARS = 1_000
MAX_ERROR_DETAILS = 32
MAX_DETAIL_KEY_CHARS = 64
MAX_DETAIL_VALUE_CHARS = 512
_SENSITIVE_KEY_PARTS = frozenset(
    {
        "api_key",
        "authorization",
        "cookie",
        "credential",
        "password",
        "secret",
        "token",
    }
)


class ErrorCategory(StrEnum):
    """Stable high-level class used for handling and aggregation."""

    VALIDATION = "validation"
    BUDGET = "budget"
    PROVIDER = "provider"
    TOOL = "tool"
    PERSISTENCE = "persistence"
    INTERNAL = "internal"


class ErrorCode(StrEnum):
    """Initial stable error codes; later Features may add specific codes."""

    INVALID_INPUT = "invalid_input"
    INVALID_EVENT = "invalid_event"
    INVALID_STATE_TRANSITION = "invalid_state_transition"
    RUN_NOT_FOUND = "run_not_found"
    QUERY_LIMIT_EXCEEDED = "query_limit_exceeded"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PROVIDER_ERROR = "provider_error"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_AUTHENTICATION = "provider_authentication"
    PROVIDER_PERMISSION_DENIED = "provider_permission_denied"
    PROVIDER_INVALID_REQUEST = "provider_invalid_request"
    PROVIDER_REFUSED = "provider_refused"
    PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"
    TOOL_NOT_FOUND = "tool_not_found"
    TOOL_INVALID_INPUT = "tool_invalid_input"
    TOOL_PERMISSION_DENIED = "tool_permission_denied"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_OUTPUT_TOO_LARGE = "tool_output_too_large"
    TOOL_ERROR = "tool_error"
    WORKSPACE_PATH_DENIED = "workspace_path_denied"
    WORKSPACE_NOT_FOUND = "workspace_not_found"
    WORKSPACE_WRONG_TYPE = "workspace_wrong_type"
    WORKSPACE_NOT_TEXT = "workspace_not_text"
    WORKSPACE_LIMIT_EXCEEDED = "workspace_limit_exceeded"
    WORKSPACE_ACCESS_FAILED = "workspace_access_failed"
    PERSISTENCE_ERROR = "persistence_error"
    INTERNAL_ERROR = "internal_error"


_CODE_CATEGORIES = {
    ErrorCode.INVALID_INPUT: ErrorCategory.VALIDATION,
    ErrorCode.INVALID_EVENT: ErrorCategory.VALIDATION,
    ErrorCode.INVALID_STATE_TRANSITION: ErrorCategory.VALIDATION,
    ErrorCode.RUN_NOT_FOUND: ErrorCategory.VALIDATION,
    ErrorCode.QUERY_LIMIT_EXCEEDED: ErrorCategory.VALIDATION,
    ErrorCode.BUDGET_EXHAUSTED: ErrorCategory.BUDGET,
    ErrorCode.PROVIDER_ERROR: ErrorCategory.PROVIDER,
    ErrorCode.PROVIDER_TIMEOUT: ErrorCategory.PROVIDER,
    ErrorCode.PROVIDER_RATE_LIMITED: ErrorCategory.PROVIDER,
    ErrorCode.PROVIDER_UNAVAILABLE: ErrorCategory.PROVIDER,
    ErrorCode.PROVIDER_AUTHENTICATION: ErrorCategory.PROVIDER,
    ErrorCode.PROVIDER_PERMISSION_DENIED: ErrorCategory.PROVIDER,
    ErrorCode.PROVIDER_INVALID_REQUEST: ErrorCategory.PROVIDER,
    ErrorCode.PROVIDER_REFUSED: ErrorCategory.PROVIDER,
    ErrorCode.PROVIDER_PROTOCOL_ERROR: ErrorCategory.PROVIDER,
    ErrorCode.TOOL_NOT_FOUND: ErrorCategory.TOOL,
    ErrorCode.TOOL_INVALID_INPUT: ErrorCategory.TOOL,
    ErrorCode.TOOL_PERMISSION_DENIED: ErrorCategory.TOOL,
    ErrorCode.TOOL_TIMEOUT: ErrorCategory.TOOL,
    ErrorCode.TOOL_OUTPUT_TOO_LARGE: ErrorCategory.TOOL,
    ErrorCode.TOOL_ERROR: ErrorCategory.TOOL,
    ErrorCode.WORKSPACE_PATH_DENIED: ErrorCategory.TOOL,
    ErrorCode.WORKSPACE_NOT_FOUND: ErrorCategory.TOOL,
    ErrorCode.WORKSPACE_WRONG_TYPE: ErrorCategory.TOOL,
    ErrorCode.WORKSPACE_NOT_TEXT: ErrorCategory.TOOL,
    ErrorCode.WORKSPACE_LIMIT_EXCEEDED: ErrorCategory.TOOL,
    ErrorCode.WORKSPACE_ACCESS_FAILED: ErrorCategory.TOOL,
    ErrorCode.PERSISTENCE_ERROR: ErrorCategory.PERSISTENCE,
    ErrorCode.INTERNAL_ERROR: ErrorCategory.INTERNAL,
}


type SafeDetailValue = StrictStr | StrictInt | StrictFloat | StrictBool | None


class ErrorInfo(DomainModel):
    """Serializable error data that is safe to expose and persist."""

    category: ErrorCategory
    code: ErrorCode
    message: str = Field(min_length=1, max_length=MAX_ERROR_MESSAGE_CHARS)
    retryable: bool = Field(
        default=False,
        description=(
            "Source-side observation that another attempt may succeed; never Runtime "
            "permission to retry an Activity."
        ),
    )
    details: Mapping[str, SafeDetailValue] = Field(
        default_factory=dict,
        max_length=MAX_ERROR_DETAILS,
        json_schema_extra={"maxProperties": MAX_ERROR_DETAILS},
    )

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value

    @field_validator("details")
    @classmethod
    def validate_safe_details(
        cls, details: Mapping[str, SafeDetailValue]
    ) -> Mapping[str, SafeDetailValue]:
        for key, value in details.items():
            if not key or len(key) > MAX_DETAIL_KEY_CHARS:
                raise ValueError("detail keys must be non-empty and at most 64 characters")
            normalized_key = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
            if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
                raise ValueError(f"sensitive detail key is not allowed: {key}")
            if isinstance(value, str) and len(value) > MAX_DETAIL_VALUE_CHARS:
                raise ValueError(f"detail value is too long: {key}")
            if isinstance(value, float) and not isfinite(value):
                raise ValueError(f"detail value must be finite: {key}")
        return MappingProxyType(dict(details))

    @model_validator(mode="after")
    def require_matching_category_and_code(self) -> Self:
        expected_category = _CODE_CATEGORIES[self.code]
        if self.category is not expected_category:
            raise ValueError(
                f"error code {self.code.value} requires category {expected_category.value}"
            )
        return self

    @field_serializer("details")
    def serialize_details(
        self, details: Mapping[str, SafeDetailValue]
    ) -> dict[str, SafeDetailValue]:
        return dict(details)


class BearAgentError(Exception):
    """Exception wrapper whose visible text is limited to safe ErrorInfo."""

    def __init__(self, info: ErrorInfo, *, cause: BaseException | None = None) -> None:
        self.info = info
        super().__init__(info.message)
        if cause is not None:
            self.__cause__ = cause
