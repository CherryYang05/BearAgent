"""Normalize OpenAI SDK failures without retaining untrusted response data."""

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)

from bearagent.domain.errors import ErrorCode, SafeDetailValue
from bearagent.ports.model import ModelProviderError

from ._common import provider_error, safe_detail_text


def classify_openai_error(cause: BaseException) -> ModelProviderError:
    details: dict[str, SafeDetailValue] = {}
    request_id = getattr(cause, "request_id", None)
    if safe_request_id := safe_detail_text(request_id):
        details["request_id"] = safe_request_id
    status_code = getattr(cause, "status_code", None)
    if isinstance(status_code, int):
        details["provider_status"] = status_code

    if isinstance(cause, APITimeoutError | TimeoutError):
        return provider_error(
            ErrorCode.PROVIDER_TIMEOUT,
            "The model Provider request timed out.",
            retryable=True,
            details=details,
            cause=cause,
        )
    if isinstance(cause, RateLimitError):
        return provider_error(
            ErrorCode.PROVIDER_RATE_LIMITED,
            "The model Provider rate limit was reached.",
            retryable=True,
            details=details,
            cause=cause,
        )
    if isinstance(cause, AuthenticationError):
        return provider_error(
            ErrorCode.PROVIDER_AUTHENTICATION,
            "The model Provider rejected authentication.",
            retryable=False,
            details=details,
            cause=cause,
        )
    if isinstance(cause, PermissionDeniedError):
        return provider_error(
            ErrorCode.PROVIDER_PERMISSION_DENIED,
            "The model Provider denied the request.",
            retryable=False,
            details=details,
            cause=cause,
        )
    if isinstance(cause, BadRequestError):
        return provider_error(
            ErrorCode.PROVIDER_INVALID_REQUEST,
            "The model Provider rejected the request parameters.",
            retryable=False,
            details=details,
            cause=cause,
        )
    if isinstance(cause, APIConnectionError | httpx.HTTPError):
        return provider_error(
            ErrorCode.PROVIDER_UNAVAILABLE,
            "The model Provider is temporarily unavailable.",
            retryable=True,
            details=details,
            cause=cause,
        )
    if isinstance(cause, APIStatusError):
        retryable = cause.status_code == 429 or cause.status_code >= 500
        return provider_error(
            ErrorCode.PROVIDER_UNAVAILABLE if retryable else ErrorCode.PROVIDER_ERROR,
            "The model Provider request failed.",
            retryable=retryable,
            details=details,
            cause=cause,
        )
    return provider_error(
        ErrorCode.PROVIDER_ERROR,
        "The model Provider request failed.",
        retryable=False,
        cause=cause,
    )
