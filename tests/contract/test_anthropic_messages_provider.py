import asyncio
import json
from typing import cast

import httpx
import pytest
from anthropic import AsyncAnthropic

from bearagent.adapters.model.anthropic_messages import AnthropicMessagesProvider
from bearagent.domain.ids import ToolCallId
from bearagent.domain.messages import (
    Message,
    MessageRole,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from bearagent.domain.model import (
    ModelCompleted,
    ModelEvent,
    ModelFinishReason,
    ModelRequest,
    ModelTextDelta,
    ModelToolCall,
    ModelUsage,
)
from bearagent.ports import ModelProviderError

from .test_model_provider_contract import build_request


def message_start(
    *,
    request_id: str = "msg_123",
    model: str = "claude-test-20260813",
    input_tokens: int = 10,
) -> dict[str, object]:
    return {
        "type": "message_start",
        "message": {
            "id": request_id,
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "container": None,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": 1,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    }


def text_start(index: int = 0) -> dict[str, object]:
    return {
        "type": "content_block_start",
        "index": index,
        "content_block": {"type": "text", "text": "", "citations": None},
    }


def text_delta(text: str, index: int = 0) -> dict[str, object]:
    return {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": "text_delta", "text": text},
    }


def tool_start(index: int, provider_call_id: str, name: str = "read_file") -> dict[str, object]:
    return {
        "type": "content_block_start",
        "index": index,
        "content_block": {
            "type": "tool_use",
            "id": provider_call_id,
            "name": name,
            "input": {},
        },
    }


def input_delta(index: int, partial_json: str) -> dict[str, object]:
    return {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": "input_json_delta", "partial_json": partial_json},
    }


def block_stop(index: int) -> dict[str, object]:
    return {"type": "content_block_stop", "index": index}


def message_delta(stop_reason: str | None, *, output_tokens: int = 4) -> dict[str, object]:
    return {
        "type": "message_delta",
        "delta": {
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "container": None,
        },
        "usage": {"output_tokens": output_tokens},
    }


def message_stop() -> dict[str, object]:
    return {"type": "message_stop"}


def sse(*events: dict[str, object]) -> bytes:
    return "".join(
        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
    ).encode()


def anthropic_provider(
    events: bytes | None = None,
    *,
    request_bodies: list[dict[str, object]] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AnthropicMessagesProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if request_bodies is not None:
            request_bodies.append(cast(dict[str, object], json.loads(request.content)))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"" if events is None else events,
        )

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler) if transport is None else transport
    )
    client = AsyncAnthropic(
        api_key="test-secret-key",
        base_url="https://provider.test",
        http_client=http_client,
        max_retries=0,
    )
    return AnthropicMessagesProvider(client)


async def collect(
    provider: AnthropicMessagesProvider, request: ModelRequest
) -> tuple[ModelEvent, ...]:
    return tuple([event async for event in provider.stream(request)])


def test_messages_adapter_emits_text_usage_and_exact_request() -> None:
    request_bodies: list[dict[str, object]] = []
    request = build_request().model_copy(
        update={
            "messages": (
                Message(
                    role=MessageRole.SYSTEM,
                    parts=(TextPart(text="Follow the instructions."),),
                ),
                Message(
                    role=MessageRole.USER,
                    parts=(TextPart(text="hello"),),
                ),
            )
        }
    )
    provider = anthropic_provider(
        sse(
            message_start(),
            text_start(),
            text_delta("hel"),
            text_delta("lo"),
            block_stop(0),
            message_delta("end_turn"),
            message_stop(),
        ),
        request_bodies=request_bodies,
    )

    events = asyncio.run(collect(provider, request))

    assert events == (
        ModelTextDelta(text="hel"),
        ModelTextDelta(text="lo"),
        ModelCompleted(
            provider_request_id="msg_123",
            model="claude-test-20260813",
            finish_reason=ModelFinishReason.STOP,
            usage=ModelUsage(input_tokens=10, output_tokens=4),
        ),
    )
    assert len(request_bodies) == 1
    body = request_bodies[0]
    assert body["stream"] is True
    assert body["max_tokens"] == 100
    assert body["system"] == "Follow the instructions."
    assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
    assert "api_key" not in json.dumps(body)


def test_messages_adapter_translates_fragmented_multiple_tool_calls() -> None:
    provider = anthropic_provider(
        sse(
            message_start(),
            tool_start(0, "toolu_1"),
            input_delta(0, '{"path":"docs/'),
            input_delta(0, 'index.md"}'),
            block_stop(0),
            tool_start(1, "toolu_2"),
            input_delta(1, '{"path":"README.md"}'),
            block_stop(1),
            message_delta("tool_use"),
            message_stop(),
        )
    )

    events = asyncio.run(collect(provider, build_request(tools=True)))

    assert len(events) == 3
    first, second, completion = events
    assert isinstance(first, ModelToolCall)
    assert first.provider_call_id == "toolu_1"
    assert dict(first.arguments) == {"path": "docs/index.md"}
    assert isinstance(second, ModelToolCall)
    assert second.provider_call_id == "toolu_2"
    assert dict(second.arguments) == {"path": "README.md"}
    assert isinstance(completion, ModelCompleted)
    assert completion.finish_reason is ModelFinishReason.TOOL_CALLS
    assert completion.usage == ModelUsage(input_tokens=10, output_tokens=4)


def test_messages_adapter_serializes_tool_history() -> None:
    tool_call_id = ToolCallId.new()
    request = build_request(tools=True).model_copy(
        update={
            "messages": (
                Message(
                    role=MessageRole.ASSISTANT,
                    parts=(
                        ToolCallPart(
                            tool_call_id=tool_call_id,
                            provider_call_id="toolu_history",
                            name="read_file",
                            arguments={"path": "README.md"},
                        ),
                    ),
                ),
                Message(
                    role=MessageRole.TOOL,
                    parts=(
                        ToolResultPart(
                            tool_call_id=tool_call_id,
                            content="BearAgent",
                            is_error=True,
                        ),
                    ),
                ),
            )
        }
    )
    request_bodies: list[dict[str, object]] = []
    provider = anthropic_provider(
        sse(
            message_start(),
            text_start(),
            text_delta("done"),
            block_stop(0),
            message_delta("end_turn"),
            message_stop(),
        ),
        request_bodies=request_bodies,
    )

    asyncio.run(collect(provider, request))

    messages = cast(list[dict[str, object]], request_bodies[0]["messages"])
    assert messages[0] == {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_history",
                "name": "read_file",
                "input": {"path": "README.md"},
            }
        ],
    }
    assert messages[1] == {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_history",
                "content": "BearAgent",
                "is_error": True,
            }
        ],
    }


def test_messages_adapter_rejects_malformed_usage() -> None:
    start = message_start()
    message = cast(dict[str, object], start["message"])
    cast(dict[str, object], message["usage"]).pop("input_tokens")
    provider = anthropic_provider(sse(start))

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == "provider_protocol_error"


@pytest.mark.parametrize(
    "events",
    [
        (),
        (message_start(),),
        (
            message_start(),
            text_start(),
            text_delta("done"),
            message_delta("end_turn"),
            message_stop(),
        ),
        (
            message_start(),
            text_start(),
            text_delta("done"),
            block_stop(0),
            message_delta("end_turn"),
            message_stop(),
            message_stop(),
        ),
    ],
)
def test_messages_adapter_rejects_invalid_stream_lifecycle(
    events: tuple[dict[str, object], ...],
) -> None:
    provider = anthropic_provider(sse(*events))

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == "provider_protocol_error"
    assert caught.value.info.retryable is False


@pytest.mark.parametrize("arguments", ["not json", "[]", '"scalar"'])
def test_messages_adapter_rejects_malformed_tool_input(arguments: str) -> None:
    provider = anthropic_provider(
        sse(
            message_start(),
            tool_start(0, "toolu_1"),
            input_delta(0, arguments),
            block_stop(0),
        )
    )

    with pytest.raises(ModelProviderError, match="invalid function call"):
        asyncio.run(collect(provider, build_request(tools=True)))


@pytest.mark.parametrize(
    ("stop_reason", "expected_code"),
    [
        ("refusal", "provider_refused"),
        ("max_tokens", "provider_error"),
        ("pause_turn", "provider_error"),
        (None, "provider_protocol_error"),
    ],
)
def test_messages_adapter_classifies_non_success_stop_reasons(
    stop_reason: str | None, expected_code: str
) -> None:
    provider = anthropic_provider(
        sse(
            message_start(),
            text_start(),
            text_delta("partial"),
            block_stop(0),
            message_delta(stop_reason),
        )
    )

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == expected_code
    assert caught.value.info.retryable is False


def test_messages_adapter_rejects_hosted_tool_block() -> None:
    provider = anthropic_provider(
        sse(
            message_start(),
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "server_tool_use",
                    "id": "srvtoolu_1",
                    "name": "web_search",
                    "input": {},
                },
            },
        )
    )

    with pytest.raises(ModelProviderError, match="unsupported content block"):
        asyncio.run(collect(provider, build_request()))


def test_messages_adapter_classifies_status_without_secret_leak() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            headers={"request-id": "req_safe"},
            json={
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": "sensitive provider response body",
                },
            },
        )

    provider = anthropic_provider(transport=httpx.MockTransport(handler))

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == "provider_authentication"
    dumped = caught.value.info.model_dump_json()
    assert "sensitive provider response body" not in dumped
    assert "test-secret-key" not in dumped


def test_messages_adapter_does_not_retry_timeout() -> None:
    class TimeoutTransport(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.calls = 0

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.calls += 1
            raise httpx.ReadTimeout("sensitive timeout context", request=request)

    transport = TimeoutTransport()
    provider = anthropic_provider(transport=transport)

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == "provider_timeout"
    assert caught.value.info.retryable is True
    assert transport.calls == 1
    assert "sensitive timeout context" not in caught.value.info.model_dump_json()


def test_messages_adapter_propagates_cancellation() -> None:
    class CancelTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise asyncio.CancelledError

    provider = anthropic_provider(transport=CancelTransport())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(collect(provider, build_request()))


def test_messages_adapter_requires_no_retry_client() -> None:
    client = AsyncAnthropic(api_key="test", max_retries=2)

    with pytest.raises(ValueError, match="disable automatic retries"):
        AnthropicMessagesProvider(client)
