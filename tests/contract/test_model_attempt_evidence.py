import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from tests.agent_loop_fixtures import agent_run_input, run_fingerprint, tool_executor
from tests.integration.test_attempt_execution import ManualClock

from bearagent.adapters.model import (
    AnthropicMessagesProvider,
    OpenAIChatCompletionsProvider,
    OpenAIResponsesProvider,
)
from bearagent.adapters.testing import InMemoryEventStore
from bearagent.application.agent_loop import AgentLoop
from bearagent.domain.attempts import ModelSubmission, RetryPolicy, RunStateV5
from bearagent.ports.model import ModelProvider


@pytest.mark.parametrize("protocol", ["responses", "chat", "anthropic"])
@pytest.mark.parametrize(
    "failure,expected",
    [
        ("connect", 3),
        ("connect_timeout", 3),
        ("read_timeout", 1),
        ("read_error", 1),
        ("read_after_connect", 1),
        ("write_after_connect", 1),
        ("429", 1),
        ("500", 1),
        ("after_headers", 1),
    ],
)
def test_real_sdk_transport_evidence_and_total_request_bound(
    protocol: str, failure: str, expected: int
) -> None:
    bodies: list[bytes] = []

    class FailedStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            # Even no translated output is sufficient once response headers arrived.
            yield b": keepalive\n\n"
            raise httpx.ConnectError("PRIVATE-STREAM-ERROR")

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        if failure == "connect":
            raise httpx.ConnectError("PRIVATE-CONNECT-ERROR", request=request)
        if failure == "connect_timeout":
            raise httpx.ConnectTimeout("PRIVATE-CONNECT-TIMEOUT", request=request)
        if failure == "read_timeout":
            raise httpx.ReadTimeout("PRIVATE-READ-TIMEOUT", request=request)
        if failure == "read_error":
            raise httpx.ReadError("PRIVATE-READ-ERROR", request=request)
        if failure in {"read_after_connect", "write_after_connect"}:
            # The outer transport phase makes submission uncertain, even when
            # an earlier connection failure remains in the exception chain.
            error_type = httpx.ReadError if failure == "read_after_connect" else httpx.WriteError
            raise error_type("PRIVATE-IO-ERROR", request=request) from httpx.ConnectError(
                "PRIVATE-EARLIER-CONNECT-ERROR", request=request
            )
        if failure == "after_headers":
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=FailedStream()
            )
        return httpx.Response(
            int(failure), json={"error": {"message": "PRIVATE-ERROR", "type": "api_error"}}
        )

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            provider: ModelProvider
            if protocol == "anthropic":
                client = AsyncAnthropic(api_key="PRIVATE-KEY", max_retries=0, http_client=http)
                provider = AnthropicMessagesProvider(client)
            else:
                openai = AsyncOpenAI(api_key="PRIVATE-KEY", max_retries=0, http_client=http)
                provider = (
                    OpenAIResponsesProvider(openai)
                    if protocol == "responses"
                    else OpenAIChatCompletionsProvider(openai)
                )
            clock = ManualClock()
            result = await AgentLoop(
                model_provider=provider,
                event_store=InMemoryEventStore(),
                tool_executor=tool_executor(),
                run_fingerprint=run_fingerprint(),
                clock=clock,
                sleep=clock.sleep,
                random_int=lambda low, high: 0,
                retry_policy=RetryPolicy(max_attempts=3),
            ).run(
                agent_run_input().model_copy(
                    update={
                        "agent_config": agent_run_input().agent_config.model_copy(
                            update={"model_timeout_ms": 10_000}
                        )
                    }
                )
            )
            assert isinstance(result.state, RunStateV5)
            assert len(bodies) == result.state.budget_usage.model_iterations == expected
            assert len(set(bodies)) == 1
            evidence = result.state.attempts[0].model_evidence
            assert evidence is not None
            assert evidence.submission is (
                ModelSubmission.NOT_SUBMITTED if expected == 3 else ModelSubmission.UNKNOWN
            )
            assert evidence.usage_known is (expected == 3)
            assert result.state.budget_usage.tokens == 0
            assert "PRIVATE-" not in result.state.model_dump_json()

    asyncio.run(exercise())
