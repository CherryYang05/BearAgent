from typing import cast

import pytest
from pydantic import ValidationError

from bearagent.domain.errors import (
    MAX_DETAIL_VALUE_CHARS,
    MAX_ERROR_DETAILS,
    MAX_ERROR_MESSAGE_CHARS,
    BearAgentError,
    ErrorCategory,
    ErrorCode,
    ErrorInfo,
)


def test_error_exposes_only_safe_serializable_information() -> None:
    cause = RuntimeError("raw provider exception with private context")
    info = ErrorInfo(
        category=ErrorCategory.PROVIDER,
        code=ErrorCode.PROVIDER_ERROR,
        message="The model provider request failed.",
        retryable=True,
        details={"provider_status": 503, "request_id": "req-safe"},
    )
    error = BearAgentError(info, cause=cause)

    assert str(error) == info.message
    assert error.__cause__ is cause
    assert "raw provider exception" not in info.model_dump_json()
    assert set(info.model_dump(mode="json")) == {
        "category",
        "code",
        "message",
        "retryable",
        "details",
    }
    with pytest.raises(TypeError):
        cast(dict[str, object], info.details)["request_id"] = "changed"


def test_error_code_must_match_its_category() -> None:
    with pytest.raises(ValidationError, match="requires category provider"):
        ErrorInfo(
            category=ErrorCategory.INTERNAL,
            code=ErrorCode.PROVIDER_ERROR,
            message="Provider failed.",
        )


@pytest.mark.parametrize(
    "key",
    [
        "authorization",
        "rawCookie",
        "db_password",
        "provider-secret",
        "access_token",
        "OPENAI_API_KEY",
        "user_credentials",
    ],
)
def test_error_details_reject_sensitive_keys(key: str) -> None:
    with pytest.raises(ValidationError, match="sensitive detail key"):
        ErrorInfo(
            category=ErrorCategory.INTERNAL,
            code=ErrorCode.INTERNAL_ERROR,
            message="Internal failure.",
            details={key: "must-not-be-persisted"},
        )


def test_error_rejects_unknown_raw_exception_field() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ErrorInfo.model_validate(
            {
                "category": "internal",
                "code": "internal_error",
                "message": "Internal failure.",
                "raw_exception": "secret stack trace",
            }
        )


def test_error_rejects_oversized_or_non_finite_safe_data() -> None:
    with pytest.raises(ValidationError, match="at most 1000 characters"):
        ErrorInfo(
            category=ErrorCategory.INTERNAL,
            code=ErrorCode.INTERNAL_ERROR,
            message="x" * (MAX_ERROR_MESSAGE_CHARS + 1),
        )

    with pytest.raises(ValidationError, match="detail value is too long"):
        ErrorInfo(
            category=ErrorCategory.INTERNAL,
            code=ErrorCode.INTERNAL_ERROR,
            message="Internal failure.",
            details={"context": "x" * (MAX_DETAIL_VALUE_CHARS + 1)},
        )

    with pytest.raises(ValidationError, match="at most 32 items"):
        ErrorInfo(
            category=ErrorCategory.INTERNAL,
            code=ErrorCode.INTERNAL_ERROR,
            message="Internal failure.",
            details={f"item_{index}": index for index in range(MAX_ERROR_DETAILS + 1)},
        )

    with pytest.raises(ValidationError, match="must be finite"):
        ErrorInfo(
            category=ErrorCategory.INTERNAL,
            code=ErrorCode.INTERNAL_ERROR,
            message="Internal failure.",
            details={"latency": float("nan")},
        )
