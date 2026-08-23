"""OpenAI Responses adapter for the Provider-neutral model port."""

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from typing import Literal, cast

import httpx
from openai import (
    AsyncOpenAI,
    OpenAIError,
)
from openai.types.responses import (
    EasyInputMessageParam,
    FunctionToolParam,
    Response,
    ResponseCompletedEvent,
    ResponseErrorEvent,
    ResponseFailedEvent,
    ResponseFunctionToolCallParam,
    ResponseIncompleteEvent,
    ResponseInputItemParam,
    ResponseOutputItemDoneEvent,
    ResponseRefusalDoneEvent,
    ResponseStreamEvent,
    ResponseTextDeltaEvent,
)
from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall
from openai.types.responses.response_input_param import FunctionCallOutput
from openai.types.responses.response_output_message import ResponseOutputMessage
from openai.types.responses.response_output_refusal import ResponseOutputRefusal
from pydantic import ValidationError

from bearagent.domain._base import thaw_json_mapping
from bearagent.domain.errors import ErrorCode, SafeDetailValue
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

from ._common import (
    canonical_json_mapping,
    canonical_json_text,
    protocol_error,
    provider_error,
    safe_detail_text,
    translate_json_tool_call,
)
from ._openai_errors import classify_openai_error

_IGNORED_EVENT_TYPES = frozenset(
    {
        "response.created",
        "response.in_progress",
        "response.output_item.added",
        "response.content_part.added",
        "response.content_part.done",
        "response.output_text.done",
        "response.function_call_arguments.delta",
        "response.function_call_arguments.done",
        "response.refusal.delta",
    }
)


class OpenAIResponsesProvider:
    """Translate OpenAI Responses streams into BearAgent model events."""

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        if client is not None and (api_key is not None or base_url is not None):
            raise ValueError("Pass either a client or client configuration, not both")
        if client is not None and client.max_retries != 0:
            raise ValueError("Injected OpenAI client must disable automatic retries")
        # Production credentials come from the process environment. Delay SDK
        # client creation until a model Activity actually starts so a zero-budget
        # Run can fail durably without requiring credentials it will never use.
        self._client = client
        self._api_key = api_key
        self._base_url = base_url

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        terminal_seen = False
        output_chars = 0
        provider_tool_calls: dict[str, tuple[str, str]] = {}
        try:
            client = self._client_or_create()
            stream = await client.responses.create(
                model=request.model,
                input=_translate_input(request),
                tools=_translate_tools(request),
                max_output_tokens=request.max_output_tokens,
                parallel_tool_calls=False,
                store=False,
                stream=True,
                timeout=request.timeout_ms / 1_000,
            )
            async for provider_event in stream:
                if terminal_seen:
                    raise protocol_error("Provider emitted an event after completion.")
                if isinstance(provider_event, ResponseCompletedEvent):
                    _validate_completion_tool_calls(provider_event.response, provider_tool_calls)
                translated = _translate_event(provider_event)
                if translated is None:
                    continue
                if isinstance(translated, ModelProviderError):
                    raise translated
                if isinstance(translated, ModelTextDelta):
                    output_chars += len(translated.text)
                elif isinstance(translated, ModelToolCall):
                    if translated.provider_call_id in provider_tool_calls:
                        raise protocol_error("Provider emitted a duplicate function call.")
                    canonical_arguments = canonical_json_mapping(translated.arguments)
                    provider_tool_calls[translated.provider_call_id] = (
                        translated.name,
                        canonical_arguments,
                    )
                    output_chars += len(canonical_arguments)
                if output_chars > MAX_MODEL_OUTPUT_CHARS:
                    raise protocol_error("Provider output exceeded the character limit.")
                terminal_seen = isinstance(translated, ModelCompleted)
                yield translated
        except asyncio.CancelledError:
            raise
        except ModelProviderError:
            raise
        except Exception as cause:
            raise classify_openai_error(cause) from cause
        if not terminal_seen:
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


def _translate_input(request: ModelRequest) -> list[ResponseInputItemParam]:
    items: list[ResponseInputItemParam] = []
    call_ids: dict[ToolCallId, str] = {}
    for message in request.messages:
        text_parts = [part.text for part in message.parts if isinstance(part, TextPart)]
        if text_parts:
            item: EasyInputMessageParam = {
                "role": _translate_message_role(message.role),
                "content": "\n".join(text_parts),
                "type": "message",
            }
            items.append(item)
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                if part.provider_call_id is None:
                    raise protocol_error(
                        "Model history Tool call is missing its Provider call identity."
                    )
                call_ids[part.tool_call_id] = part.provider_call_id
                tool_call: ResponseFunctionToolCallParam = {
                    "type": "function_call",
                    "call_id": part.provider_call_id,
                    "name": part.name,
                    "arguments": json.dumps(
                        thaw_json_mapping(part.arguments),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
                items.append(tool_call)
            elif isinstance(part, ToolResultPart):
                provider_call_id = call_ids.get(part.tool_call_id)
                if provider_call_id is None:
                    raise protocol_error(
                        "Tool result cannot be correlated to a Provider call identity."
                    )
                output: FunctionCallOutput = {
                    "type": "function_call_output",
                    "call_id": provider_call_id,
                    "output": part.content,
                    "status": "incomplete" if part.is_error else "completed",
                }
                items.append(output)
    return items


def _translate_tools(request: ModelRequest) -> list[FunctionToolParam]:
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": cast(dict[str, object], thaw_json_mapping(tool.input_schema)),
            "strict": True,
        }
        for tool in request.tools
    ]


def _translate_message_role(
    role: MessageRole,
) -> Literal["user", "assistant", "system", "developer"]:
    if role is MessageRole.TOOL:
        raise protocol_error("Tool messages cannot contain direct text input.")
    return role.value


def _translate_event(
    event: ResponseStreamEvent,
) -> ModelEvent | ModelProviderError | None:
    if isinstance(event, ResponseTextDeltaEvent):
        if not event.delta:
            raise protocol_error("Provider emitted an empty text delta.")
        return ModelTextDelta(text=event.delta)
    if isinstance(event, ResponseOutputItemDoneEvent):
        if isinstance(event.item, ResponseFunctionToolCall):
            return translate_json_tool_call(
                provider_call_id=event.item.call_id,
                name=event.item.name,
                arguments_json=event.item.arguments,
            )
        if event.item.type in {"message", "reasoning"}:
            return None
        raise protocol_error("Provider emitted an unsupported output item.")
    if isinstance(event, ResponseCompletedEvent):
        return _translate_completion(event.response)
    if isinstance(event, ResponseIncompleteEvent):
        return _response_failure(event.response, incomplete=True)
    if isinstance(event, ResponseFailedEvent):
        return _response_failure(event.response, incomplete=False)
    if isinstance(event, ResponseRefusalDoneEvent):
        return provider_error(
            ErrorCode.PROVIDER_REFUSED,
            "The model Provider refused the request.",
            retryable=False,
        )
    if isinstance(event, ResponseErrorEvent):
        return _provider_event_error(code=event.code)
    if event.type in _IGNORED_EVENT_TYPES:
        return None
    raise protocol_error("Provider emitted an unsupported response event.")


def _translate_completion(response: Response) -> ModelCompleted:
    if response.status != "completed":
        raise protocol_error("Provider completion carried a non-completed status.")
    if not response.id or not response.model:
        raise protocol_error("Provider completion omitted required response metadata.")
    for item in response.output:
        if item.type not in {"message", "reasoning", "function_call"}:
            raise protocol_error("Provider completion carried an unsupported output item.")
        if isinstance(item, ResponseOutputMessage) and any(
            isinstance(content, ResponseOutputRefusal) for content in item.content
        ):
            raise provider_error(
                ErrorCode.PROVIDER_REFUSED,
                "The model Provider refused the request.",
                retryable=False,
            )
    if response.usage is None:
        raise protocol_error("Provider completion omitted required usage.")
    try:
        usage = ModelUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
    except (AttributeError, TypeError, ValidationError) as cause:
        raise protocol_error("Provider completion carried invalid usage.", cause=cause) from cause
    finish_reason = (
        ModelFinishReason.TOOL_CALLS
        if any(item.type == "function_call" for item in response.output)
        else ModelFinishReason.STOP
    )
    try:
        return ModelCompleted(
            provider_request_id=response.id,
            model=str(response.model),
            finish_reason=finish_reason,
            usage=usage,
        )
    except ValidationError as cause:
        raise protocol_error(
            "Provider completion carried invalid metadata.", cause=cause
        ) from cause


def _validate_completion_tool_calls(
    response: Response, streamed_tool_calls: Mapping[str, tuple[str, str]]
) -> None:
    completed_calls = [
        item for item in response.output if isinstance(item, ResponseFunctionToolCall)
    ]
    if len({item.call_id for item in completed_calls}) != len(completed_calls):
        raise protocol_error("Provider completion repeated a function call identity.")
    if {item.call_id for item in completed_calls} != set(streamed_tool_calls):
        raise protocol_error("Provider completion did not match the streamed function calls.")
    for item in completed_calls:
        streamed_name, streamed_arguments = streamed_tool_calls[item.call_id]
        if item.name != streamed_name or canonical_json_text(item.arguments) != streamed_arguments:
            raise protocol_error("Provider completion changed a streamed function call.")


def _response_failure(response: Response, *, incomplete: bool) -> ModelProviderError:
    details: dict[str, SafeDetailValue] = {}
    if safe_request_id := safe_detail_text(response.id):
        details["request_id"] = safe_request_id
    provider_code: str | None = None
    if response.error is not None:
        provider_code = response.error.code
    elif incomplete and response.incomplete_details is not None:
        provider_code = response.incomplete_details.reason
    if safe_provider_code := safe_detail_text(provider_code):
        details["provider_code"] = safe_provider_code
    code, retryable = _classify_provider_failure_code(provider_code)
    return provider_error(
        code,
        "The model Provider did not complete the request.",
        retryable=retryable,
        details=details,
    )


def _provider_event_error(*, code: str | None) -> ModelProviderError:
    error_code, retryable = _classify_provider_failure_code(code)
    details: dict[str, SafeDetailValue] = {}
    if safe_provider_code := safe_detail_text(code):
        details["provider_code"] = safe_provider_code
    return provider_error(
        error_code,
        "The model Provider stream failed.",
        retryable=retryable,
        details=details,
    )


def _classify_provider_failure_code(
    provider_code: str | None,
) -> tuple[ErrorCode, bool]:
    if provider_code in {"server_error", "rate_limit_exceeded", "vector_store_timeout"}:
        return ErrorCode.PROVIDER_UNAVAILABLE, True
    if provider_code in {"content_filter", "bio_policy", "image_content_policy_violation"}:
        return ErrorCode.PROVIDER_REFUSED, False
    if provider_code == "invalid_prompt" or (
        provider_code is not None and provider_code.startswith("invalid_image")
    ):
        return ErrorCode.PROVIDER_INVALID_REQUEST, False
    return ErrorCode.PROVIDER_ERROR, False
