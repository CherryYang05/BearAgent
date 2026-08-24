import asyncio
import json
from typing import cast

import httpx
import pytest
from openai import AsyncOpenAI

from bearagent.adapters.model import OpenAIChatCompletionsProvider
from bearagent.domain.ids import ToolCallId
from bearagent.domain.messages import (
    Message,
    MessageRole,
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
    ModelToolDefinition,
    ModelUsage,
)
from bearagent.ports import ModelProviderError

from .test_model_provider_contract import build_request


def chat_chunk(
    *,
    choices: list[dict[str, object]],
    usage: bool = False,
    request_id: str = "chatcmpl_123",
    model: str = "test-model-2026-08-13",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": request_id,
        "choices": choices,
        "created": 0,
        "model": model,
        "object": "chat.completion.chunk",
    }
    if usage:
        payload["usage"] = {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_tokens": 14,
        }
    return payload


def choice(
    *,
    content: str | None = None,
    tool_calls: list[dict[str, object]] | None = None,
    finish_reason: str | None = None,
) -> dict[str, object]:
    delta: dict[str, object] = {}
    if content is not None:
        delta["content"] = content
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    return {
        "index": 0,
        "delta": delta,
        "finish_reason": finish_reason,
        "logprobs": None,
    }


def tool_delta(
    index: int,
    *,
    provider_call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> dict[str, object]:
    function: dict[str, object] = {}
    if name is not None:
        function["name"] = name
    if arguments is not None:
        function["arguments"] = arguments
    value: dict[str, object] = {"index": index}
    if provider_call_id is not None:
        value["id"] = provider_call_id
        value["type"] = "function"
    if function:
        value["function"] = function
    return value


def sse(*chunks: dict[str, object]) -> bytes:
    return (
        "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
    ).encode()


def chat_provider(
    chunks: bytes | None = None,
    *,
    request_bodies: list[dict[str, object]] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    thinking_mode: str = "provider_default",
) -> OpenAIChatCompletionsProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if request_bodies is not None:
            request_bodies.append(cast(dict[str, object], json.loads(request.content)))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"" if chunks is None else chunks,
        )

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler) if transport is None else transport
    )
    client = AsyncOpenAI(
        api_key="test-secret-key",
        base_url="https://provider.test/v1",
        http_client=http_client,
        max_retries=0,
    )
    return OpenAIChatCompletionsProvider(client, thinking_mode=thinking_mode)


async def collect(
    provider: OpenAIChatCompletionsProvider, request: ModelRequest
) -> tuple[ModelEvent, ...]:
    return tuple([event async for event in provider.stream(request)])


def test_chat_adapter_emits_text_usage_and_exact_request() -> None:
    request_bodies: list[dict[str, object]] = []
    provider = chat_provider(
        sse(
            chat_chunk(choices=[choice(content="hel")]),
            chat_chunk(choices=[choice(content="lo", finish_reason="stop")]),
            chat_chunk(choices=[], usage=True),
        ),
        request_bodies=request_bodies,
    )

    events = asyncio.run(collect(provider, build_request()))

    assert events == (
        ModelTextDelta(text="hel"),
        ModelTextDelta(text="lo"),
        ModelCompleted(
            provider_request_id="chatcmpl_123",
            model="test-model-2026-08-13",
            finish_reason=ModelFinishReason.STOP,
            usage=ModelUsage(input_tokens=10, output_tokens=4),
        ),
    )
    assert len(request_bodies) == 1
    body = request_bodies[0]
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}
    assert body["max_tokens"] == 100
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert "store" not in body
    assert "api_key" not in json.dumps(body)


def test_chat_adapter_translates_fragmented_multiple_tool_calls() -> None:
    provider = chat_provider(
        sse(
            chat_chunk(
                choices=[
                    choice(
                        tool_calls=[
                            tool_delta(
                                0,
                                provider_call_id="call_1",
                                name="read_file",
                                arguments='{"path":"docs/',
                            ),
                            tool_delta(
                                1,
                                provider_call_id="call_2",
                                name="read_file",
                                arguments='{"path":"README',
                            ),
                        ]
                    )
                ]
            ),
            chat_chunk(
                choices=[
                    choice(
                        tool_calls=[
                            tool_delta(0, arguments='index.md"}'),
                            tool_delta(1, arguments='.md"}'),
                        ],
                        finish_reason="tool_calls",
                    )
                ],
                usage=True,
            ),
        )
    )

    events = asyncio.run(collect(provider, build_request(tools=True)))

    assert len(events) == 3
    first, second, completion = events
    assert isinstance(first, ModelToolCall)
    assert first.provider_call_id == "call_1"
    assert dict(first.arguments) == {"path": "docs/index.md"}
    assert isinstance(second, ModelToolCall)
    assert second.provider_call_id == "call_2"
    assert dict(second.arguments) == {"path": "README.md"}
    assert isinstance(completion, ModelCompleted)
    assert completion.finish_reason is ModelFinishReason.TOOL_CALLS
    assert completion.usage == ModelUsage(input_tokens=10, output_tokens=4)


def test_chat_adapter_maps_non_wire_tool_names_round_trip() -> None:
    request = build_request(tools=True).model_copy(
        update={
            "tools": (
                ModelToolDefinition(
                    name="workspace.read",
                    description="Read a file.",
                    input_schema={
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                ),
            )
        }
    )
    request_bodies: list[dict[str, object]] = []
    provider = chat_provider(
        sse(
            chat_chunk(
                choices=[
                    choice(
                        tool_calls=[
                            tool_delta(
                                0,
                                provider_call_id="call_1",
                                name="workspace_read",
                                arguments='{"path":"README.md"}',
                            )
                        ],
                        finish_reason="tool_calls",
                    )
                ],
                usage=True,
            )
        ),
        request_bodies=request_bodies,
    )

    events = asyncio.run(collect(provider, request))

    tool = cast(list[dict[str, object]], request_bodies[0]["tools"])[0]
    function = cast(dict[str, object], tool["function"])
    assert function["name"] == "workspace_read"
    assert "strict" not in function
    assert isinstance(events[0], ModelToolCall)
    assert events[0].name == "workspace.read"


def test_chat_adapter_avoids_normalized_tool_name_collisions() -> None:
    original = build_request(tools=True).tools[0]
    request = build_request(tools=True).model_copy(
        update={
            "tools": (
                original.model_copy(update={"name": "workspace.read"}),
                original.model_copy(update={"name": "workspace_read"}),
            )
        }
    )
    request_bodies: list[dict[str, object]] = []
    provider = chat_provider(
        sse(
            chat_chunk(
                choices=[choice(content="done", finish_reason="stop")],
                usage=True,
            )
        ),
        request_bodies=request_bodies,
    )

    asyncio.run(collect(provider, request))

    tools = cast(list[dict[str, object]], request_bodies[0]["tools"])
    names = [cast(dict[str, object], tool["function"])["name"] for tool in tools]
    assert names[1] == "workspace_read"
    assert names[0] != names[1]
    assert all(isinstance(name, str) and "." not in name and len(name) <= 64 for name in names)


def test_chat_adapter_only_disables_thinking_when_explicitly_configured() -> None:
    default_bodies: list[dict[str, object]] = []
    disabled_bodies: list[dict[str, object]] = []
    chunks = sse(
        chat_chunk(
            choices=[choice(content="done", finish_reason="stop")],
            usage=True,
        )
    )

    asyncio.run(collect(chat_provider(chunks, request_bodies=default_bodies), build_request()))
    asyncio.run(
        collect(
            chat_provider(
                chunks,
                request_bodies=disabled_bodies,
                thinking_mode="disabled",
            ),
            build_request(),
        )
    )

    assert "thinking" not in default_bodies[0]
    assert disabled_bodies[0]["thinking"] == {"type": "disabled"}


def test_chat_adapter_serializes_tool_history() -> None:
    tool_call_id = ToolCallId.new()
    base_request = build_request(tools=True)
    request = base_request.model_copy(
        update={
            "tools": (base_request.tools[0].model_copy(update={"name": "workspace.read"}),),
            "messages": (
                Message(
                    role=MessageRole.ASSISTANT,
                    parts=(
                        ToolCallPart(
                            tool_call_id=tool_call_id,
                            provider_call_id="call_history",
                            name="workspace.read",
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
            ),
        }
    )
    request_bodies: list[dict[str, object]] = []
    provider = chat_provider(
        sse(
            chat_chunk(
                choices=[choice(content="done", finish_reason="stop")],
                usage=True,
            )
        ),
        request_bodies=request_bodies,
    )

    asyncio.run(collect(provider, request))

    messages = cast(list[dict[str, object]], request_bodies[0]["messages"])
    assistant = messages[0]
    calls = cast(list[dict[str, object]], assistant["tool_calls"])
    function = cast(dict[str, object], calls[0]["function"])
    assert json.loads(cast(str, function["arguments"])) == {"path": "README.md"}
    assert function["name"] == "workspace_read"
    assert messages[1] == {
        "role": "tool",
        "tool_call_id": "call_history",
        "content": "BearAgent",
    }


def test_chat_adapter_rejects_hidden_reasoning_content() -> None:
    chunk = chat_chunk(
        choices=[choice(content="visible", finish_reason="stop")],
        usage=True,
    )
    choices = cast(list[dict[str, object]], chunk["choices"])
    delta = cast(dict[str, object], choices[0]["delta"])
    delta["reasoning_content"] = "private-provider-reasoning"
    provider = chat_provider(sse(chunk))

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == "provider_protocol_error"
    assert "private-provider-reasoning" not in caught.value.info.model_dump_json()


def test_chat_adapter_rejects_malformed_usage() -> None:
    terminal = chat_chunk(
        choices=[choice(content="done", finish_reason="stop")],
        usage=True,
    )
    cast(dict[str, object], terminal["usage"]).pop("prompt_tokens")
    provider = chat_provider(sse(terminal))

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == "provider_protocol_error"


@pytest.mark.parametrize(
    "chunks",
    [
        (),
        (chat_chunk(choices=[choice(content="partial")]),),
        (
            chat_chunk(
                choices=[choice(content="done", finish_reason="stop")],
                usage=True,
            ),
            chat_chunk(choices=[], usage=True),
        ),
        (
            chat_chunk(
                choices=[choice(content="done", finish_reason="stop")],
                usage=False,
            ),
        ),
    ],
)
def test_chat_adapter_rejects_invalid_stream_lifecycle(
    chunks: tuple[dict[str, object], ...],
) -> None:
    provider = chat_provider(sse(*chunks))

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == "provider_protocol_error"
    assert caught.value.info.retryable is False


@pytest.mark.parametrize(
    "tool_calls",
    [
        [tool_delta(0, provider_call_id="call_1", name="read_file", arguments="[]")],
        [tool_delta(1, provider_call_id="call_1", name="read_file", arguments="{}")],
        [tool_delta(0, provider_call_id="call_1", arguments="{}")],
    ],
)
def test_chat_adapter_rejects_invalid_completed_tool_call(
    tool_calls: list[dict[str, object]],
) -> None:
    provider = chat_provider(
        sse(
            chat_chunk(
                choices=[choice(tool_calls=tool_calls, finish_reason="tool_calls")],
                usage=True,
            )
        )
    )

    with pytest.raises(ModelProviderError):
        asyncio.run(collect(provider, build_request(tools=True)))


@pytest.mark.parametrize(
    ("finish_reason", "expected_code"),
    [
        ("content_filter", "provider_refused"),
        ("length", "provider_error"),
        ("function_call", "provider_protocol_error"),
    ],
)
def test_chat_adapter_classifies_non_success_finish_reasons(
    finish_reason: str, expected_code: str
) -> None:
    provider = chat_provider(
        sse(
            chat_chunk(
                choices=[choice(content="partial", finish_reason=finish_reason)],
                usage=True,
            )
        )
    )

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == expected_code
    assert caught.value.info.retryable is False


def test_chat_adapter_does_not_retry_timeout() -> None:
    class TimeoutTransport(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.calls = 0

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.calls += 1
            raise httpx.ReadTimeout("sensitive timeout context", request=request)

    transport = TimeoutTransport()
    provider = chat_provider(transport=transport)

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == "provider_timeout"
    assert caught.value.info.retryable is True
    assert transport.calls == 1
    assert "sensitive timeout context" not in caught.value.info.model_dump_json()


def test_chat_adapter_propagates_cancellation() -> None:
    class CancelTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise asyncio.CancelledError

    provider = chat_provider(transport=CancelTransport())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(collect(provider, build_request()))


def test_chat_adapter_requires_no_retry_client() -> None:
    client = AsyncOpenAI(api_key="test", max_retries=2)

    with pytest.raises(ValueError, match="disable automatic retries"):
        OpenAIChatCompletionsProvider(client)
