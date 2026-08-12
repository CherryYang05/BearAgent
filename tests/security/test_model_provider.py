import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest
from openai import AsyncOpenAI

from bearagent.adapters.model import OpenAIResponsesProvider
from bearagent.domain.messages import Message, MessageRole, TextPart
from bearagent.domain.model import ModelEvent, ModelRequest
from bearagent.ports import ModelProviderError


def build_request() -> ModelRequest:
    return ModelRequest(
        model="test-model",
        messages=(Message(role=MessageRole.USER, parts=(TextPart(text="hello"),)),),
        max_output_tokens=100,
        timeout_ms=2_500,
        prompt_version="test-v1",
    )


async def collect(provider: OpenAIResponsesProvider) -> tuple[ModelEvent, ...]:
    return tuple([event async for event in provider.stream(build_request())])


def provider_for_handler(handler: httpx.AsyncBaseTransport) -> OpenAIResponsesProvider:
    client = AsyncOpenAI(
        api_key="sk-super-secret",
        base_url="https://provider.test/v1",
        http_client=httpx.AsyncClient(transport=handler),
        max_retries=0,
    )
    return OpenAIResponsesProvider(client)


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (400, "provider_invalid_request", False),
        (401, "provider_authentication", False),
        (403, "provider_permission_denied", False),
        (429, "provider_rate_limited", True),
        (500, "provider_unavailable", True),
    ],
)
def test_status_errors_are_classified_without_secret_or_body_leak(
    status: int, code: str, retryable: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers={
                "x-request-id": "req_safe",
                "authorization": "Bearer response-secret",
            },
            json={"error": {"message": "sensitive provider response body"}},
        )

    provider = provider_for_handler(httpx.MockTransport(handler))

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider))

    assert caught.value.info.code.value == code
    assert caught.value.info.retryable is retryable
    dumped = caught.value.info.model_dump_json()
    assert "req_safe" in dumped
    assert "sensitive provider response body" not in dumped
    assert "response-secret" not in dumped
    assert "sk-super-secret" not in dumped


def test_timeout_is_retryable_and_does_not_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("sensitive timeout context", request=request)

    provider = provider_for_handler(httpx.MockTransport(handler))

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider))

    assert caught.value.info.code.value == "provider_timeout"
    assert caught.value.info.retryable is True
    assert calls == 1
    assert "sensitive timeout context" not in caught.value.info.model_dump_json()


def test_partial_stream_failure_never_emits_completion() -> None:
    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield (
                b'data: {"type":"response.output_text.delta","sequence_number":1,'
                b'"item_id":"msg_1","output_index":0,"content_index":0,'
                b'"delta":"partial","logprobs":[]}\n\n'
            )
            raise httpx.ReadError("sensitive stream failure")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=BrokenStream(),
        )

    provider = provider_for_handler(httpx.MockTransport(handler))

    async def exercise() -> tuple[list[ModelEvent], ModelProviderError]:
        seen: list[ModelEvent] = []
        try:
            async for event in provider.stream(build_request()):
                seen.append(event)
        except ModelProviderError as error:
            return seen, error
        raise AssertionError("expected a Provider failure")

    events, error = asyncio.run(exercise())

    assert [event.kind.value for event in events] == ["text_delta"]
    assert error.info.code.value == "provider_unavailable"
    assert error.info.retryable is True
    assert "sensitive stream failure" not in error.info.model_dump_json()


def test_cancellation_propagates_unchanged() -> None:
    class CancelTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise asyncio.CancelledError

    provider = provider_for_handler(CancelTransport())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(collect(provider))


def test_provider_stream_error_ignores_untrusted_message() -> None:
    event = {
        "type": "error",
        "sequence_number": 1,
        "code": "server_error",
        "message": "secret-bearing Provider message",
        "param": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=f"data: {json.dumps(event)}\n\n".encode(),
        )

    provider = provider_for_handler(httpx.MockTransport(handler))

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider))

    assert caught.value.info.retryable is True
    assert "secret-bearing Provider message" not in caught.value.info.model_dump_json()
