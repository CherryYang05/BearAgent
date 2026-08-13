import asyncio
import json
from collections.abc import Mapping, Sequence
from typing import cast

import httpx
import pytest
from openai import AsyncOpenAI

from bearagent.adapters.model import OpenAIResponsesProvider
from bearagent.adapters.testing import FakeModelProvider
from bearagent.domain.ids import ToolCallId
from bearagent.domain.messages import (
    Message,
    MessageRole,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from bearagent.domain.model import (
    MAX_MODEL_OUTPUT_CHARS,
    ModelCompleted,
    ModelEvent,
    ModelFinishReason,
    ModelRequest,
    ModelTextDelta,
    ModelToolCall,
    ModelToolDefinition,
    ModelUsage,
)
from bearagent.ports import ModelProvider, ModelProviderError


def build_request(*, tools: bool = False) -> ModelRequest:
    definitions = ()
    if tools:
        definitions = (
            ModelToolDefinition(
                name="read_file",
                description="Read one workspace file.",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            ),
        )
    return ModelRequest(
        model="test-model",
        messages=(Message(role=MessageRole.USER, parts=(TextPart(text="hello"),)),),
        tools=definitions,
        max_output_tokens=100,
        timeout_ms=2_500,
        prompt_version="test-v1",
    )


def response_payload(
    *, output: Sequence[Mapping[str, object]] = (), usage: bool = True
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "resp_123",
        "created_at": 0,
        "model": "test-model-2026-08-13",
        "object": "response",
        "output": list(output),
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "status": "completed",
    }
    if usage:
        payload["usage"] = {
            "input_tokens": 10,
            "output_tokens": 4,
            "total_tokens": 14,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        }
    return payload


def sse(*events: dict[str, object]) -> bytes:
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events).encode()


def openai_provider(
    events: bytes | None = None,
    *,
    status_code: int = 200,
    request_bodies: list[dict[str, object]] | None = None,
) -> OpenAIResponsesProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if request_bodies is not None:
            request_bodies.append(cast(dict[str, object], json.loads(request.content)))
        if status_code != 200:
            return httpx.Response(
                status_code,
                headers={"x-request-id": "req_safe"},
                json={"error": {"message": "sensitive provider body"}},
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"" if events is None else events,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncOpenAI(
        api_key="test-secret-key",
        base_url="https://provider.test/v1",
        http_client=http_client,
        max_retries=0,
    )
    return OpenAIResponsesProvider(client)


async def collect(provider: ModelProvider, request: ModelRequest) -> tuple[ModelEvent, ...]:
    return tuple([event async for event in provider.stream(request)])


@pytest.mark.parametrize("provider_kind", ["fake", "openai"])
def test_providers_emit_ordered_text_and_one_completion(provider_kind: str) -> None:
    expected: tuple[ModelEvent, ...] = (
        ModelTextDelta(text="hel"),
        ModelTextDelta(text="lo"),
        ModelCompleted(
            provider_request_id="resp_123",
            model="test-model-2026-08-13",
            finish_reason=ModelFinishReason.STOP,
            usage=ModelUsage(input_tokens=10, output_tokens=4),
        ),
    )
    provider: ModelProvider
    if provider_kind == "fake":
        provider = FakeModelProvider(expected)
    else:
        provider = openai_provider(
            sse(
                {
                    "type": "response.output_text.delta",
                    "sequence_number": 1,
                    "item_id": "msg_1",
                    "output_index": 0,
                    "content_index": 0,
                    "delta": "hel",
                    "logprobs": [],
                },
                {
                    "type": "response.output_text.delta",
                    "sequence_number": 2,
                    "item_id": "msg_1",
                    "output_index": 0,
                    "content_index": 0,
                    "delta": "lo",
                    "logprobs": [],
                },
                {
                    "type": "response.completed",
                    "sequence_number": 3,
                    "response": response_payload(),
                },
            )
        )

    assert asyncio.run(collect(provider, build_request())) == expected


def test_openai_adapter_translates_complete_function_call_and_request() -> None:
    request_bodies: list[dict[str, object]] = []
    function_call = {
        "type": "function_call",
        "id": "item_1",
        "call_id": "call_123",
        "name": "read_file",
        "arguments": '{"path":"docs/index.md"}',
        "status": "completed",
    }
    provider = openai_provider(
        sse(
            {
                "type": "response.output_item.done",
                "sequence_number": 1,
                "output_index": 0,
                "item": function_call,
            },
            {
                "type": "response.completed",
                "sequence_number": 2,
                "response": response_payload(output=(function_call,)),
            },
        ),
        request_bodies=request_bodies,
    )

    events = asyncio.run(collect(provider, build_request(tools=True)))

    assert isinstance(events[0], ModelToolCall)
    assert events[0].provider_call_id == "call_123"
    assert events[0].name == "read_file"
    assert dict(events[0].arguments) == {"path": "docs/index.md"}
    assert isinstance(events[1], ModelCompleted)
    assert events[1].finish_reason is ModelFinishReason.TOOL_CALLS
    assert len(request_bodies) == 1
    body = request_bodies[0]
    assert body["stream"] is True
    assert body["store"] is False
    assert body["parallel_tool_calls"] is False
    assert body["max_output_tokens"] == 100
    assert cast(list[dict[str, object]], body["tools"])[0]["name"] == "read_file"
    assert "api_key" not in json.dumps(body)


def test_openai_adapter_serializes_deeply_frozen_tool_history() -> None:
    tool_call_id = ToolCallId.new()
    request = build_request().model_copy(
        update={
            "messages": (
                Message(
                    role=MessageRole.ASSISTANT,
                    parts=(
                        ToolCallPart(
                            tool_call_id=tool_call_id,
                            provider_call_id="call_history",
                            name="read_file",
                            arguments={"path": "README.md", "options": {"limit": 20}},
                        ),
                    ),
                ),
                Message(
                    role=MessageRole.TOOL,
                    parts=(ToolResultPart(tool_call_id=tool_call_id, content="BearAgent"),),
                ),
            )
        }
    )
    request_bodies: list[dict[str, object]] = []
    provider = openai_provider(
        sse(
            {
                "type": "response.completed",
                "sequence_number": 1,
                "response": response_payload(),
            }
        ),
        request_bodies=request_bodies,
    )

    asyncio.run(collect(provider, request))

    inputs = cast(list[dict[str, object]], request_bodies[0]["input"])
    assert json.loads(cast(str, inputs[0]["arguments"])) == {
        "path": "README.md",
        "options": {"limit": 20},
    }
    assert inputs[1]["call_id"] == "call_history"


@pytest.mark.parametrize(
    "events",
    [
        (),
        (
            {
                "type": "response.completed",
                "sequence_number": 1,
                "response": response_payload(),
            },
            {
                "type": "response.output_text.delta",
                "sequence_number": 2,
                "item_id": "msg_1",
                "output_index": 0,
                "content_index": 0,
                "delta": "late",
                "logprobs": [],
            },
        ),
        (
            {
                "type": "response.audio.done",
                "sequence_number": 1,
            },
        ),
    ],
)
def test_openai_adapter_rejects_invalid_stream_lifecycle(
    events: tuple[dict[str, object], ...],
) -> None:
    provider = openai_provider(sse(*events))

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == "provider_protocol_error"
    assert caught.value.info.retryable is False


@pytest.mark.parametrize("arguments", ["not json", "[]", '"scalar"'])
def test_openai_adapter_rejects_malformed_function_arguments(arguments: str) -> None:
    provider = openai_provider(
        sse(
            {
                "type": "response.output_item.done",
                "sequence_number": 1,
                "output_index": 0,
                "item": {
                    "type": "function_call",
                    "id": "item_1",
                    "call_id": "call_1",
                    "name": "read_file",
                    "arguments": arguments,
                    "status": "completed",
                },
            },
        )
    )

    with pytest.raises(ModelProviderError, match="invalid function call"):
        asyncio.run(collect(provider, build_request(tools=True)))


def test_openai_adapter_preserves_missing_usage_without_guessing() -> None:
    provider = openai_provider(
        sse(
            {
                "type": "response.completed",
                "sequence_number": 1,
                "response": response_payload(usage=False),
            }
        )
    )

    events = asyncio.run(collect(provider, build_request()))

    assert isinstance(events[-1], ModelCompleted)
    assert events[-1].usage is None


def test_openai_adapter_rejects_refusal_in_completed_output() -> None:
    refusal_message = {
        "type": "message",
        "id": "msg_1",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "refusal", "refusal": "untrusted refusal text"}],
    }
    provider = openai_provider(
        sse(
            {
                "type": "response.completed",
                "sequence_number": 1,
                "response": response_payload(output=(refusal_message,)),
            }
        )
    )

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == "provider_refused"
    assert caught.value.info.retryable is False
    assert "untrusted refusal text" not in caught.value.info.model_dump_json()


@pytest.mark.parametrize(
    ("event_type", "status", "provider_code", "expected_code", "retryable"),
    [
        ("response.failed", "failed", "invalid_prompt", "provider_invalid_request", False),
        ("response.failed", "failed", "server_error", "provider_unavailable", True),
        ("response.incomplete", "incomplete", "max_output_tokens", "provider_error", False),
        ("response.incomplete", "incomplete", "content_filter", "provider_refused", False),
    ],
)
def test_openai_adapter_classifies_terminal_response_failures(
    event_type: str,
    status: str,
    provider_code: str,
    expected_code: str,
    retryable: bool,
) -> None:
    response = response_payload()
    response["status"] = status
    if status == "failed":
        response["error"] = {
            "code": provider_code,
            "message": "untrusted failure message",
        }
    else:
        response["incomplete_details"] = {"reason": provider_code}
    provider = openai_provider(
        sse({"type": event_type, "sequence_number": 1, "response": response})
    )

    with pytest.raises(ModelProviderError) as caught:
        asyncio.run(collect(provider, build_request()))

    assert caught.value.info.code.value == expected_code
    assert caught.value.info.retryable is retryable
    assert caught.value.info.details["provider_code"] == provider_code
    assert "untrusted failure message" not in caught.value.info.model_dump_json()


def test_openai_adapter_rejects_completion_that_omits_streamed_tool_call() -> None:
    function_call = {
        "type": "function_call",
        "id": "item_1",
        "call_id": "call_123",
        "name": "read_file",
        "arguments": '{"path":"docs/index.md"}',
        "status": "completed",
    }
    provider = openai_provider(
        sse(
            {
                "type": "response.output_item.done",
                "sequence_number": 1,
                "output_index": 0,
                "item": function_call,
            },
            {
                "type": "response.completed",
                "sequence_number": 2,
                "response": response_payload(),
            },
        )
    )

    with pytest.raises(ModelProviderError, match="did not match"):
        asyncio.run(collect(provider, build_request(tools=True)))


def test_openai_adapter_rejects_completion_that_changes_streamed_tool_call() -> None:
    streamed_call = {
        "type": "function_call",
        "id": "item_1",
        "call_id": "call_123",
        "name": "read_file",
        "arguments": '{"path":"docs/index.md"}',
        "status": "completed",
    }
    changed_call = {**streamed_call, "arguments": '{"path":"README.md"}'}
    provider = openai_provider(
        sse(
            {
                "type": "response.output_item.done",
                "sequence_number": 1,
                "output_index": 0,
                "item": streamed_call,
            },
            {
                "type": "response.completed",
                "sequence_number": 2,
                "response": response_payload(output=(changed_call,)),
            },
        )
    )

    with pytest.raises(ModelProviderError, match="changed"):
        asyncio.run(collect(provider, build_request(tools=True)))


def test_openai_adapter_enforces_aggregate_output_limit() -> None:
    chunk = "x" * (MAX_MODEL_OUTPUT_CHARS // 2 + 1)
    provider = openai_provider(
        sse(
            {
                "type": "response.output_text.delta",
                "sequence_number": 1,
                "item_id": "msg_1",
                "output_index": 0,
                "content_index": 0,
                "delta": chunk,
                "logprobs": [],
            },
            {
                "type": "response.output_text.delta",
                "sequence_number": 2,
                "item_id": "msg_1",
                "output_index": 0,
                "content_index": 0,
                "delta": chunk,
                "logprobs": [],
            },
        )
    )

    with pytest.raises(ModelProviderError, match="character limit"):
        asyncio.run(collect(provider, build_request()))


def test_openai_adapter_requires_no_retry_client() -> None:
    client = AsyncOpenAI(api_key="test", max_retries=2)

    with pytest.raises(ValueError, match="disable automatic retries"):
        OpenAIResponsesProvider(client)
