"""Finite assembly of one Provider-neutral model event stream."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from bearagent.domain.errors import BearAgentError, ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.messages import (
    MAX_MESSAGE_PARTS,
    MAX_TEXT_CHARS,
    Message,
    MessageRole,
    TextPart,
    ToolCallPart,
)
from bearagent.domain.model import (
    ModelCompleted,
    ModelEvent,
    ModelFinishReason,
    ModelTextDelta,
    ModelToolCall,
)
from bearagent.domain.tools import ToolRequest


class ModelStreamProtocolError(BearAgentError):
    """A model stream cannot be assembled into one valid assistant Message."""

    def __init__(self, message: str, discarded_output_chars: int) -> None:
        self.discarded_output_chars = discarded_output_chars
        super().__init__(
            ErrorInfo(
                category=ErrorCategory.PROVIDER,
                code=ErrorCode.PROVIDER_PROTOCOL_ERROR,
                message=message,
            )
        )


@dataclass(frozen=True)
class CollectedModelResponse:
    message: Message
    completion: ModelCompleted


class ModelStreamCollector:
    """Assemble a finite stream and retain only a safe partial-size counter on failure."""

    def __init__(self) -> None:
        self.discarded_output_chars = 0

    async def collect(
        self,
        stream: AsyncIterator[ModelEvent],
    ) -> CollectedModelResponse:
        text_fragments: list[str] = []
        tool_calls: list[ModelToolCall] = []
        provider_call_ids: set[str] = set()
        completion: ModelCompleted | None = None

        async for event in stream:
            event_value = _runtime_value(event)
            if completion is not None:
                raise self._error("Model stream emitted data after completion.")
            if isinstance(event_value, ModelTextDelta):
                self.discarded_output_chars += len(event_value.text)
                if self.discarded_output_chars > MAX_TEXT_CHARS:
                    raise self._error("Model text output exceeds the message limit.")
                if not text_fragments and len(tool_calls) >= MAX_MESSAGE_PARTS:
                    raise self._error("Model output contains too many message parts.")
                text_fragments.append(event_value.text)
            elif isinstance(event_value, ModelToolCall):
                if len(tool_calls) + (1 if text_fragments else 0) >= MAX_MESSAGE_PARTS:
                    raise self._error("Model output contains too many message parts.")
                if event_value.provider_call_id in provider_call_ids:
                    raise self._error("Model output repeats a provider Tool call identity.")
                provider_call_ids.add(event_value.provider_call_id)
                tool_calls.append(event_value)
            elif isinstance(event_value, ModelCompleted):
                completion = event_value
            else:
                raise self._error("Model stream emitted an unsupported event.")

        if completion is None:
            raise self._error("Model stream ended without completion.")

        text = "".join(text_fragments)
        if completion.finish_reason is ModelFinishReason.STOP:
            if not text.strip() or tool_calls:
                raise self._error("Model stop requires non-empty text and no Tool calls.")
        elif not tool_calls:
            raise self._error("Model tool_calls finish requires at least one Tool call.")

        try:
            parts: list[TextPart | ToolCallPart] = []
            if text:
                parts.append(TextPart(text=text))
            for call in tool_calls:
                request = ToolRequest(
                    tool_call_id=call.tool_call_id,
                    name=call.name,
                    arguments=call.arguments,
                )
                parts.append(
                    ToolCallPart(
                        tool_call_id=request.tool_call_id,
                        provider_call_id=call.provider_call_id,
                        name=request.name,
                        arguments=request.arguments,
                    )
                )
            message = Message(role=MessageRole.ASSISTANT, parts=tuple(parts))
        except ValueError as cause:
            raise self._error("Model output is not a valid bounded assistant message.") from cause
        return CollectedModelResponse(message=message, completion=completion)

    def _error(self, message: str) -> ModelStreamProtocolError:
        return ModelStreamProtocolError(message, self.discarded_output_chars)


def _runtime_value(value: object) -> object:
    """Erase static port promises before validating an adapter at runtime."""
    return value
