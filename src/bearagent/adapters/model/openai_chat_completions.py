"""OpenAI Chat Completions adapter for the Provider-neutral model port."""

import asyncio
import hashlib
import json
import re
from collections import Counter
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import cast

import httpx
from openai import AsyncOpenAI, OpenAIError
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_chunk import (
    ChatCompletionChunk,
    ChoiceDeltaToolCall,
)
from pydantic import ValidationError

from bearagent.domain._base import thaw_json_mapping
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import ToolCallId
from bearagent.domain.messages import MessageRole, TextPart, ToolCallPart, ToolResultPart
from bearagent.domain.model import (
    MAX_MODEL_OUTPUT_CHARS,
    ModelCompleted,
    ModelEvent,
    ModelFinishReason,
    ModelRequest,
    ModelTextDelta,
    ModelToolCall,
    ModelUsage,
)
from bearagent.ports.model import ModelProviderError

from ._common import protocol_error, provider_error, translate_json_tool_call
from ._openai_errors import classify_openai_error


@dataclass
class _ToolCallBuffer:
    provider_call_id: str | None = None
    name: str | None = None
    argument_fragments: list[str] = field(default_factory=list[str])


_WIRE_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_WIRE_TOOL_NAME_MAX_CHARS = 64


@dataclass(frozen=True, slots=True)
class _ToolNameMap:
    internal_to_wire: dict[str, str]
    wire_to_internal: dict[str, str]


class OpenAIChatCompletionsProvider:
    """Translate Chat Completions streams into BearAgent model events."""

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        thinking_mode: str = "provider_default",
    ) -> None:
        if client is not None and (api_key is not None or base_url is not None):
            raise ValueError("Pass either a client or client configuration, not both")
        if client is not None and client.max_retries != 0:
            raise ValueError("Injected OpenAI client must disable automatic retries")
        if thinking_mode not in {"provider_default", "disabled"}:
            raise ValueError("Unsupported Chat Completions thinking_mode")
        self._client = client
        self._api_key = api_key
        self._base_url = base_url
        self._thinking_mode = thinking_mode

    @property
    def thinking_mode(self) -> str:
        return self._thinking_mode

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        terminal_seen = False
        finish_reason: ModelFinishReason | None = None
        usage: ModelUsage | None = None
        provider_request_id: str | None = None
        actual_model: str | None = None
        output_chars = 0
        tool_calls: dict[int, _ToolCallBuffer] = {}
        tool_names = _build_tool_name_map(request)
        try:
            client = self._client_or_create()
            stream = await client.chat.completions.create(
                model=request.model,
                messages=_translate_messages(request, tool_names),
                tools=_translate_tools(request, tool_names),
                max_tokens=request.max_output_tokens,
                stream=True,
                stream_options={"include_usage": True},
                timeout=request.timeout_ms / 1_000,
                extra_body=(
                    {"thinking": {"type": "disabled"}}
                    if self._thinking_mode == "disabled"
                    else None
                ),
            )
            async for chunk in stream:
                if terminal_seen:
                    raise protocol_error("Provider emitted an event after completion.")
                provider_request_id, actual_model = _merge_metadata(
                    chunk,
                    provider_request_id=provider_request_id,
                    actual_model=actual_model,
                )
                if chunk.moderation is not None:
                    raise protocol_error("Provider emitted unsupported moderation data.")
                if chunk.usage is not None:
                    if usage is not None:
                        raise protocol_error("Provider emitted duplicate usage.")
                    usage = _translate_usage(chunk)
                if not chunk.choices:
                    if chunk.usage is None or finish_reason is None:
                        raise protocol_error("Provider emitted an empty choices chunk.")
                else:
                    if len(chunk.choices) != 1 or chunk.choices[0].index != 0:
                        raise protocol_error("Provider emitted unsupported completion choices.")
                    if finish_reason is not None:
                        raise protocol_error("Provider emitted output after a finish reason.")
                    choice = chunk.choices[0]
                    delta = choice.delta
                    reasoning_content = (delta.model_extra or {}).get("reasoning_content")
                    if reasoning_content is not None and reasoning_content != "":
                        raise protocol_error("Provider emitted unsupported reasoning content.")
                    if delta.refusal is not None:
                        raise provider_error(
                            ErrorCode.PROVIDER_REFUSED,
                            "The model Provider refused the request.",
                            retryable=False,
                        )
                    if delta.function_call is not None:
                        raise protocol_error("Provider emitted a deprecated function call.")
                    if delta.role not in {None, "assistant"}:
                        raise protocol_error("Provider emitted an unsupported message role.")
                    if delta.content:
                        output_chars += len(delta.content)
                        if output_chars > MAX_MODEL_OUTPUT_CHARS:
                            raise protocol_error("Provider output exceeded the character limit.")
                        yield ModelTextDelta(text=delta.content)
                    for tool_delta in delta.tool_calls or ():
                        output_chars += _merge_tool_call(tool_calls, tool_delta)
                        if output_chars > MAX_MODEL_OUTPUT_CHARS:
                            raise protocol_error("Provider output exceeded the character limit.")
                    if choice.finish_reason is not None:
                        finish_reason = _translate_finish_reason(choice.finish_reason)
                        completed_calls = _complete_tool_calls(
                            tool_calls, finish_reason, tool_names
                        )
                        for completed_call in completed_calls:
                            yield completed_call
                if finish_reason is not None and usage is not None:
                    try:
                        completion = ModelCompleted(
                            provider_request_id=provider_request_id,
                            model=actual_model,
                            finish_reason=finish_reason,
                            usage=usage,
                        )
                    except ValidationError as cause:
                        raise protocol_error(
                            "Provider completion carried invalid metadata.", cause=cause
                        ) from cause
                    terminal_seen = True
                    yield completion
        except asyncio.CancelledError:
            raise
        except ModelProviderError:
            raise
        except Exception as cause:
            raise classify_openai_error(cause) from cause
        if not terminal_seen:
            if finish_reason is not None and usage is None:
                raise protocol_error("Provider completion omitted required usage.")
            raise protocol_error("Provider stream ended without a completion event.")

    def _client_or_create(self) -> AsyncOpenAI:
        if self._client is not None:
            return self._client
        try:
            client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                max_retries=0,
                http_client=httpx.AsyncClient(follow_redirects=False),
            )
        except OpenAIError as cause:
            raise provider_error(
                ErrorCode.PROVIDER_AUTHENTICATION,
                "Model Provider credentials are not configured.",
                retryable=False,
                cause=cause,
            ) from cause
        self._client = client
        return client


def _build_tool_name_map(request: ModelRequest) -> _ToolNameMap:
    internal_names = tuple(tool.name for tool in request.tools)
    reserved = {name for name in internal_names if _WIRE_TOOL_NAME_PATTERN.fullmatch(name)}
    normalized = {
        name: re.sub(r"[^A-Za-z0-9_-]", "_", name)
        for name in internal_names
        if name not in reserved
    }
    normalized_counts = Counter(normalized.values())
    used = set(reserved)
    internal_to_wire = {name: name for name in reserved}

    for name in internal_names:
        if name in internal_to_wire:
            continue
        candidate = normalized[name]
        if (
            len(candidate) > _WIRE_TOOL_NAME_MAX_CHARS
            or normalized_counts[candidate] > 1
            or candidate in used
        ):
            attempt = 0
            while True:
                digest_source = name if attempt == 0 else f"{name}\0{attempt}"
                suffix = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:12]
                prefix = candidate[:51].rstrip("_-") or "tool"
                candidate = f"{prefix}_{suffix}"
                if candidate not in used:
                    break
                attempt += 1
        internal_to_wire[name] = candidate
        used.add(candidate)

    return _ToolNameMap(
        internal_to_wire=internal_to_wire,
        wire_to_internal={wire: internal for internal, wire in internal_to_wire.items()},
    )


def _history_wire_tool_name(name: str, tool_names: _ToolNameMap) -> str:
    try:
        return tool_names.internal_to_wire[name]
    except KeyError as cause:
        raise protocol_error(
            "Model history references a Tool missing from the current request."
        ) from cause


def _translate_messages(
    request: ModelRequest, tool_names: _ToolNameMap
) -> list[ChatCompletionMessageParam]:
    translated: list[ChatCompletionMessageParam] = []
    provider_call_ids: dict[ToolCallId, str] = {}
    for message in request.messages:
        text = "\n".join(part.text for part in message.parts if isinstance(part, TextPart))
        if message.role is MessageRole.SYSTEM:
            translated.append(
                cast(
                    ChatCompletionSystemMessageParam,
                    {"role": "system", "content": text},
                )
            )
        elif message.role is MessageRole.USER:
            translated.append(
                cast(
                    ChatCompletionUserMessageParam,
                    {"role": "user", "content": text},
                )
            )
        elif message.role is MessageRole.ASSISTANT:
            wire_tool_calls: list[dict[str, object]] = []
            for part in message.parts:
                if not isinstance(part, ToolCallPart):
                    continue
                if part.provider_call_id is None:
                    raise protocol_error(
                        "Model history Tool call is missing its Provider call identity."
                    )
                provider_call_ids[part.tool_call_id] = part.provider_call_id
                wire_tool_calls.append(
                    {
                        "id": part.provider_call_id,
                        "type": "function",
                        "function": {
                            "name": _history_wire_tool_name(part.name, tool_names),
                            "arguments": json.dumps(
                                thaw_json_mapping(part.arguments),
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        },
                    }
                )
            assistant: dict[str, object] = {
                "role": "assistant",
                "content": text or None,
            }
            if wire_tool_calls:
                assistant["tool_calls"] = wire_tool_calls
            translated.append(cast(ChatCompletionAssistantMessageParam, assistant))
        else:
            result = cast(ToolResultPart, message.parts[0])
            provider_call_id = provider_call_ids.get(result.tool_call_id)
            if provider_call_id is None:
                raise protocol_error(
                    "Tool result cannot be correlated to a Provider call identity."
                )
            translated.append(
                cast(
                    ChatCompletionToolMessageParam,
                    {
                        "role": "tool",
                        "tool_call_id": provider_call_id,
                        "content": result.content,
                    },
                )
            )
    return translated


def _translate_tools(
    request: ModelRequest, tool_names: _ToolNameMap
) -> list[ChatCompletionToolParam]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool_names.internal_to_wire[tool.name],
                "description": tool.description,
                "parameters": cast(dict[str, object], thaw_json_mapping(tool.input_schema)),
            },
        }
        for tool in request.tools
    ]


def _merge_metadata(
    chunk: ChatCompletionChunk,
    *,
    provider_request_id: str | None,
    actual_model: str | None,
) -> tuple[str, str]:
    if not chunk.id or not chunk.model:
        raise protocol_error("Provider chunk omitted required response metadata.")
    if provider_request_id is not None and chunk.id != provider_request_id:
        raise protocol_error("Provider changed the response identity during streaming.")
    if actual_model is not None and chunk.model != actual_model:
        raise protocol_error("Provider changed the model identity during streaming.")
    return chunk.id, chunk.model


def _translate_usage(chunk: ChatCompletionChunk) -> ModelUsage:
    if chunk.usage is None:
        raise AssertionError("usage must be present")
    try:
        return ModelUsage(
            input_tokens=chunk.usage.prompt_tokens,
            output_tokens=chunk.usage.completion_tokens,
        )
    except (AttributeError, TypeError, ValidationError) as cause:
        raise protocol_error("Provider completion carried invalid usage.", cause=cause) from cause


def _merge_tool_call(
    calls: dict[int, _ToolCallBuffer],
    delta: ChoiceDeltaToolCall,
) -> int:
    if delta.index < 0 or delta.index > 127:
        raise protocol_error("Provider emitted an invalid function call index.")
    call = calls.setdefault(delta.index, _ToolCallBuffer())
    if delta.id is not None:
        if call.provider_call_id is not None and delta.id != call.provider_call_id:
            raise protocol_error("Provider changed a function call identity.")
        call.provider_call_id = delta.id
    if delta.type not in {None, "function"}:
        raise protocol_error("Provider emitted an unsupported Tool call type.")
    if delta.function is not None:
        if delta.function.name is not None:
            if call.name is not None and delta.function.name != call.name:
                raise protocol_error("Provider changed a function call name.")
            call.name = delta.function.name
        if delta.function.arguments is not None:
            call.argument_fragments.append(delta.function.arguments)
            return len(delta.function.arguments)
    return 0


def _complete_tool_calls(
    calls: dict[int, _ToolCallBuffer],
    finish_reason: ModelFinishReason,
    tool_names: _ToolNameMap,
) -> tuple[ModelToolCall, ...]:
    if finish_reason is ModelFinishReason.STOP:
        if calls:
            raise protocol_error("Provider stop completion carried function calls.")
        return ()
    if not calls or sorted(calls) != list(range(len(calls))):
        raise protocol_error("Provider tool_calls completion omitted a function call.")
    translated: list[ModelToolCall] = []
    for index in sorted(calls):
        call = calls[index]
        if call.provider_call_id is None or call.name is None:
            raise protocol_error("Provider emitted an incomplete function call.")
        translated.append(
            translate_json_tool_call(
                provider_call_id=call.provider_call_id,
                name=tool_names.wire_to_internal.get(call.name, call.name),
                arguments_json="".join(call.argument_fragments),
            )
        )
    return tuple(translated)


def _translate_finish_reason(value: object) -> ModelFinishReason:
    if value == "stop":
        return ModelFinishReason.STOP
    if value == "tool_calls":
        return ModelFinishReason.TOOL_CALLS
    if value == "content_filter":
        raise provider_error(
            ErrorCode.PROVIDER_REFUSED,
            "The model Provider refused the request.",
            retryable=False,
        )
    if value == "length":
        raise provider_error(
            ErrorCode.PROVIDER_ERROR,
            "The model Provider did not complete the request.",
            retryable=False,
        )
    raise protocol_error("Provider emitted an unsupported finish reason.")
