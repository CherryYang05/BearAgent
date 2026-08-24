"""Anthropic Messages adapter for the Provider-neutral model port."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import cast

import httpx
from anthropic import AnthropicError, AsyncAnthropic, omit
from anthropic.types import (
    InputJSONDelta,
    MessageParam,
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
    RawContentBlockStopEvent,
    RawMessageDeltaEvent,
    RawMessageStartEvent,
    RawMessageStopEvent,
    TextBlock,
    TextDelta,
    ToolParam,
    ToolUseBlock,
)
from pydantic import ValidationError

from bearagent.domain._base import thaw_json_mapping
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import ToolCallId
from bearagent.domain.messages import MessageRole, TextPart, ToolCallPart
from bearagent.domain.model import (
    MAX_MODEL_OUTPUT_CHARS,
    ModelCompleted,
    ModelEvent,
    ModelFinishReason,
    ModelRequest,
    ModelTextDelta,
    ModelUsage,
)
from bearagent.ports.model import ModelProviderError

from ._anthropic_errors import classify_anthropic_error
from ._common import protocol_error, provider_error, translate_json_tool_call


@dataclass
class _TextBlockState:
    stopped: bool = False


@dataclass
class _ToolBlockState:
    provider_call_id: str
    name: str
    initial_input: dict[str, object]
    argument_fragments: list[str] = field(default_factory=list[str])
    stopped: bool = False


_ContentBlockState = _TextBlockState | _ToolBlockState


class AnthropicMessagesProvider:
    """Translate Anthropic Messages streams into BearAgent model events."""

    def __init__(
        self,
        client: AsyncAnthropic | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        if client is not None and (api_key is not None or base_url is not None):
            raise ValueError("Pass either a client or client configuration, not both")
        if client is not None and client.max_retries != 0:
            raise ValueError("Injected Anthropic client must disable automatic retries")
        self._client = client
        self._api_key = api_key
        self._base_url = base_url

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        terminal_seen = False
        message_started = False
        message_delta_seen = False
        provider_request_id: str | None = None
        actual_model: str | None = None
        input_tokens: int | None = None
        completion: ModelCompleted | None = None
        output_chars = 0
        blocks: dict[int, _ContentBlockState] = {}
        completed_tool_calls = 0

        system, messages = _translate_messages(request)
        try:
            client = self._client_or_create()
            stream = await client.messages.create(
                model=request.model,
                max_tokens=request.max_output_tokens,
                messages=messages,
                system=system if system else omit,
                tools=_translate_tools(request) or omit,
                stream=True,
                timeout=request.timeout_ms / 1_000,
            )
            async for raw_event in stream:
                event = _runtime_value(raw_event)
                if terminal_seen:
                    raise protocol_error("Provider emitted an event after completion.")
                if isinstance(event, RawMessageStartEvent):
                    if message_started:
                        raise protocol_error("Provider emitted duplicate message_start.")
                    message_started = True
                    message = event.message
                    if (
                        message.type != "message"
                        or message.role != "assistant"
                        or message.content
                        or message.stop_reason is not None
                        or message.container is not None
                    ):
                        raise protocol_error("Provider emitted an invalid message_start.")
                    if not message.id or not message.model:
                        raise protocol_error(
                            "Provider completion omitted required response metadata."
                        )
                    if message.usage.server_tool_use is not None:
                        raise protocol_error("Provider emitted hosted Tool usage.")
                    provider_request_id = message.id
                    actual_model = str(message.model)
                    try:
                        input_tokens = _total_input_tokens(
                            message.usage.input_tokens,
                            message.usage.cache_creation_input_tokens,
                            message.usage.cache_read_input_tokens,
                        )
                    except (AttributeError, TypeError, ValueError) as cause:
                        raise protocol_error(
                            "Provider completion carried invalid usage.", cause=cause
                        ) from cause
                elif isinstance(event, RawContentBlockStartEvent):
                    _require_message_body(message_started, message_delta_seen)
                    if any(not state.stopped for state in blocks.values()):
                        raise protocol_error("Provider overlapped content blocks.")
                    if event.index < 0 or event.index > 127 or event.index in blocks:
                        raise protocol_error("Provider emitted an invalid content block index.")
                    if event.index != len(blocks):
                        raise protocol_error("Provider omitted a content block index.")
                    block = event.content_block
                    if isinstance(block, TextBlock):
                        if block.citations:
                            raise protocol_error("Provider emitted unsupported citations.")
                        state: _ContentBlockState = _TextBlockState()
                        blocks[event.index] = state
                        if block.text:
                            output_chars += len(block.text)
                            _require_output_limit(output_chars)
                            yield ModelTextDelta(text=block.text)
                    elif isinstance(block, ToolUseBlock):
                        if block.caller is not None or block.toolset_name is not None:
                            raise protocol_error("Provider emitted a hosted Tool call.")
                        blocks[event.index] = _ToolBlockState(
                            provider_call_id=block.id,
                            name=block.name,
                            initial_input=block.input,
                        )
                    else:
                        raise protocol_error("Provider emitted an unsupported content block.")
                elif isinstance(event, RawContentBlockDeltaEvent):
                    _require_message_body(message_started, message_delta_seen)
                    state = _active_block(blocks, event.index)
                    if isinstance(event.delta, TextDelta):
                        if not isinstance(state, _TextBlockState):
                            raise protocol_error(
                                "Provider changed a content block type during streaming."
                            )
                        if not event.delta.text:
                            raise protocol_error("Provider emitted an empty text delta.")
                        output_chars += len(event.delta.text)
                        _require_output_limit(output_chars)
                        yield ModelTextDelta(text=event.delta.text)
                    elif isinstance(event.delta, InputJSONDelta):
                        if not isinstance(state, _ToolBlockState):
                            raise protocol_error(
                                "Provider changed a content block type during streaming."
                            )
                        if state.initial_input:
                            raise protocol_error(
                                "Provider changed completed Tool input during streaming."
                            )
                        state.argument_fragments.append(event.delta.partial_json)
                        output_chars += len(event.delta.partial_json)
                        _require_output_limit(output_chars)
                    else:
                        raise protocol_error("Provider emitted an unsupported content delta.")
                elif isinstance(event, RawContentBlockStopEvent):
                    _require_message_body(message_started, message_delta_seen)
                    state = _active_block(blocks, event.index)
                    state.stopped = True
                    if isinstance(state, _ToolBlockState):
                        arguments_json = (
                            "".join(state.argument_fragments)
                            if state.argument_fragments
                            else json.dumps(
                                state.initial_input,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                        )
                        yield translate_json_tool_call(
                            provider_call_id=state.provider_call_id,
                            name=state.name,
                            arguments_json=arguments_json,
                        )
                        completed_tool_calls += 1
                elif isinstance(event, RawMessageDeltaEvent):
                    _require_message_body(message_started, message_delta_seen)
                    if any(not state.stopped for state in blocks.values()):
                        raise protocol_error(
                            "Provider completed before all content blocks stopped."
                        )
                    if event.delta.container is not None:
                        raise protocol_error("Provider emitted server-side message state.")
                    if event.usage.server_tool_use is not None:
                        raise protocol_error("Provider emitted hosted Tool usage.")
                    if input_tokens is None:
                        raise protocol_error("Provider completion omitted required usage.")
                    if event.usage.input_tokens is not None:
                        try:
                            delta_input_tokens = _total_input_tokens(
                                event.usage.input_tokens,
                                event.usage.cache_creation_input_tokens,
                                event.usage.cache_read_input_tokens,
                            )
                        except (AttributeError, TypeError, ValueError) as cause:
                            raise protocol_error(
                                "Provider completion carried invalid usage.", cause=cause
                            ) from cause
                        if delta_input_tokens != input_tokens:
                            raise protocol_error("Provider changed input usage during streaming.")
                    finish_reason = _translate_finish_reason(event.delta.stop_reason)
                    if finish_reason is ModelFinishReason.STOP and completed_tool_calls:
                        raise protocol_error("Provider stop completion carried Tool calls.")
                    if finish_reason is ModelFinishReason.TOOL_CALLS and completed_tool_calls == 0:
                        raise protocol_error("Provider tool_use completion omitted a Tool call.")
                    try:
                        usage = ModelUsage(
                            input_tokens=input_tokens,
                            output_tokens=event.usage.output_tokens,
                        )
                        if provider_request_id is None or actual_model is None:
                            raise ValueError("response metadata is missing")
                        completion = ModelCompleted(
                            provider_request_id=provider_request_id,
                            model=actual_model,
                            finish_reason=finish_reason,
                            usage=usage,
                        )
                    except (ValidationError, ValueError) as cause:
                        raise protocol_error(
                            "Provider completion carried invalid metadata.", cause=cause
                        ) from cause
                    message_delta_seen = True
                elif isinstance(event, RawMessageStopEvent):
                    if not message_delta_seen or completion is None:
                        raise protocol_error("Provider emitted message_stop before completion.")
                    terminal_seen = True
                    yield completion
                else:
                    raise protocol_error("Provider emitted an unsupported message event.")
        except asyncio.CancelledError:
            raise
        except ModelProviderError:
            raise
        except Exception as cause:
            raise classify_anthropic_error(cause) from cause
        if not terminal_seen:
            raise protocol_error("Provider stream ended without a completion event.")

    def _client_or_create(self) -> AsyncAnthropic:
        if self._client is not None:
            return self._client
        try:
            client = AsyncAnthropic(
                api_key=self._api_key,
                base_url=self._base_url,
                max_retries=0,
                http_client=httpx.AsyncClient(follow_redirects=False),
            )
        except AnthropicError as cause:
            raise provider_error(
                ErrorCode.PROVIDER_AUTHENTICATION,
                "Model Provider credentials are not configured.",
                retryable=False,
                cause=cause,
            ) from cause
        self._client = client
        return client


def _translate_messages(request: ModelRequest) -> tuple[str, list[MessageParam]]:
    system_parts: list[str] = []
    translated: list[MessageParam] = []
    provider_call_ids: dict[ToolCallId, str] = {}
    non_system_seen = False
    for message in request.messages:
        if message.role is MessageRole.SYSTEM:
            if non_system_seen:
                raise protocol_error("System messages must precede conversation messages.")
            system_parts.extend(part.text for part in message.parts if isinstance(part, TextPart))
            continue
        non_system_seen = True
        content: list[dict[str, object]] = []
        for part in message.parts:
            if isinstance(part, TextPart):
                content.append({"type": "text", "text": part.text})
            elif isinstance(part, ToolCallPart):
                if part.provider_call_id is None:
                    raise protocol_error(
                        "Model history Tool call is missing its Provider call identity."
                    )
                provider_call_ids[part.tool_call_id] = part.provider_call_id
                content.append(
                    {
                        "type": "tool_use",
                        "id": part.provider_call_id,
                        "name": part.name,
                        "input": cast(dict[str, object], thaw_json_mapping(part.arguments)),
                    }
                )
            else:
                result = part
                provider_call_id = provider_call_ids.get(result.tool_call_id)
                if provider_call_id is None:
                    raise protocol_error(
                        "Tool result cannot be correlated to a Provider call identity."
                    )
                content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": provider_call_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                )
        role = "assistant" if message.role is MessageRole.ASSISTANT else "user"
        translated.append(cast(MessageParam, {"role": role, "content": content}))
    return "\n".join(system_parts), translated


def _translate_tools(request: ModelRequest) -> list[ToolParam]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": cast(dict[str, object], thaw_json_mapping(tool.input_schema)),
        }
        for tool in request.tools
    ]


def _require_message_body(message_started: bool, message_delta_seen: bool) -> None:
    if not message_started or message_delta_seen:
        raise protocol_error("Provider emitted a content event outside the message body.")


def _active_block(blocks: dict[int, _ContentBlockState], index: int) -> _ContentBlockState:
    state = blocks.get(index)
    if state is None or state.stopped:
        raise protocol_error("Provider emitted an event for an inactive content block.")
    return state


def _require_output_limit(output_chars: int) -> None:
    if output_chars > MAX_MODEL_OUTPUT_CHARS:
        raise protocol_error("Provider output exceeded the character limit.")


def _total_input_tokens(
    input_tokens: object,
    cache_creation_input_tokens: object,
    cache_read_input_tokens: object,
) -> int:
    values = (input_tokens, cache_creation_input_tokens, cache_read_input_tokens)
    if (
        any(
            value is not None
            and (not isinstance(value, int) or isinstance(value, bool) or value < 0)
            for value in values
        )
        or input_tokens is None
    ):
        raise ValueError("usage tokens must be non-negative integers")
    return sum(value for value in values if isinstance(value, int) and not isinstance(value, bool))


def _runtime_value(value: object) -> object:
    return value


def _translate_finish_reason(value: object) -> ModelFinishReason:
    if value in {"end_turn", "stop_sequence"}:
        return ModelFinishReason.STOP
    if value == "tool_use":
        return ModelFinishReason.TOOL_CALLS
    if value == "refusal":
        raise provider_error(
            ErrorCode.PROVIDER_REFUSED,
            "The model Provider refused the request.",
            retryable=False,
        )
    if value in {"max_tokens", "model_context_window_exceeded", "pause_turn"}:
        raise provider_error(
            ErrorCode.PROVIDER_ERROR,
            "The model Provider did not complete the request.",
            retryable=False,
        )
    raise protocol_error("Provider completion omitted a supported stop reason.")
