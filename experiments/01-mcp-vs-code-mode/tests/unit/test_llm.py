"""Unit tests for OpenAIChatModel using an injected fake client (no network)."""

import asyncio
from typing import Any

import httpx2
import openai
import pytest
from openai.types.chat import ChatCompletion

from mcp_vs_code_mode.agent import LLMInfraError, OpenAIChatModel

pytestmark = [pytest.mark.unit, pytest.mark.anyio]

_REQUEST = httpx2.Request("POST", "https://example.invalid")


def _status_error(cls: type[openai.APIStatusError], status: int) -> openai.APIStatusError:
    return cls("boom", response=httpx2.Response(status, request=_REQUEST), body=None)


def _completion(**overrides: Any) -> ChatCompletion:
    data: dict[str, Any] = {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 1,
        "model": "some/model",
        "provider": "SomeProvider",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "hello"},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    }
    data.update(overrides)
    return ChatCompletion.model_validate(data)


class _Completions:
    def __init__(self, items: list[Any]) -> None:
        self.items = list(items)
        self.kwargs: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> ChatCompletion:
        self.kwargs.append(kwargs)
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        assert isinstance(item, ChatCompletion)
        return item


class _Chat:
    def __init__(self, completions: _Completions) -> None:
        self.completions = completions


class _FakeClient:
    def __init__(self, items: list[Any]) -> None:
        self.completions = _Completions(items)
        self.chat = _Chat(self.completions)


class _Sleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def _model(
    items: list[Any], sleeper: _Sleeper | None = None, **kwargs: Any
) -> tuple[OpenAIChatModel, _FakeClient]:
    client = _FakeClient(items)
    model = OpenAIChatModel(
        client=client,  # type: ignore[arg-type]
        model="test-model",
        temperature=0.0,
        max_tokens=100,
        sleep=sleeper or _Sleeper(),
        **kwargs,
    )
    return model, client


async def test_parses_content_usage_and_provider() -> None:
    completion = _completion(
        usage={
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_tokens": 14,
            "completion_tokens_details": {"reasoning_tokens": 3},
            "prompt_tokens_details": {"cached_tokens": 6},
        }
    )
    model, _ = _model([completion])
    response = await model.complete([{"role": "user", "content": "hi"}], [])
    assert response.content == "hello"
    assert response.tool_calls == ()
    assert response.usage.reasoning_tokens == 3
    assert response.usage.cached_tokens == 6
    assert response.provider == "SomeProvider"
    assert response.model == "some/model"
    assert response.request_id == "gen-1"
    assert response.attempts == 1
    assert response.simulated is False
    assert response.assistant_message == {"role": "assistant", "content": "hello"}


async def test_details_missing_are_none() -> None:
    model, _ = _model([_completion()])
    response = await model.complete([], [])
    assert response.usage.reasoning_tokens is None
    assert response.usage.cached_tokens is None


async def test_tool_calls_and_reasoning_details_copied() -> None:
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "get_balance", "arguments": "{}"}}
        ],
        "reasoning_details": [{"type": "reasoning.text", "text": "thinking"}],
    }
    completion = _completion(
        choices=[{"index": 0, "finish_reason": "tool_calls", "message": message}]
    )
    model, _ = _model([completion])
    response = await model.complete([], [])
    assert [(c.id, c.name, c.arguments) for c in response.tool_calls] == [
        ("c1", "get_balance", "{}")
    ]
    assert response.assistant_message["tool_calls"] == [
        {"id": "c1", "type": "function", "function": {"name": "get_balance", "arguments": "{}"}}
    ]
    assert response.assistant_message["reasoning_details"] == [
        {"type": "reasoning.text", "text": "thinking"}
    ]
    assert response.finish_reason == "tool_calls"


@pytest.mark.parametrize(
    "error",
    [
        _status_error(openai.RateLimitError, 429),
        _status_error(openai.InternalServerError, 500),
        openai.APITimeoutError(request=_REQUEST),
    ],
    ids=["rate_limit", "server_error", "timeout"],
)
async def test_retries_then_succeeds(error: Exception) -> None:
    sleeper = _Sleeper()
    model, client = _model([error, _completion()], sleeper)
    response = await model.complete([], [])
    assert response.attempts == 2
    assert sleeper.delays == [5.0]
    assert len(client.completions.kwargs) == 2


async def test_persistent_failure_raises_after_max_attempts() -> None:
    sleeper = _Sleeper()
    errors = [_status_error(openai.RateLimitError, 429) for _ in range(3)]
    model, client = _model(errors, sleeper)
    with pytest.raises(LLMInfraError, match="RateLimitError"):
        await model.complete([], [])
    assert len(client.completions.kwargs) == 3
    assert sleeper.delays == [5.0, 20.0]


async def test_bad_request_not_retried() -> None:
    sleeper = _Sleeper()
    model, client = _model([_status_error(openai.BadRequestError, 400)], sleeper)
    with pytest.raises(LLMInfraError, match="BadRequestError"):
        await model.complete([], [])
    assert len(client.completions.kwargs) == 1
    assert sleeper.delays == []


async def test_empty_choices_retried_then_error_reported() -> None:
    empty = _completion(choices=[], error={"message": "upstream down"})
    model, client = _model([empty, empty, empty])
    with pytest.raises(LLMInfraError, match="upstream down"):
        await model.complete([], [])
    assert len(client.completions.kwargs) == 3


async def test_empty_choices_then_success() -> None:
    model, _ = _model([_completion(choices=[]), _completion()])
    assert (await model.complete([], [])).attempts == 2


async def test_missing_usage_is_infra_error_without_retry() -> None:
    model, client = _model([_completion(usage=None)])
    with pytest.raises(LLMInfraError, match="no usage"):
        await model.complete([], [])
    assert len(client.completions.kwargs) == 1


async def test_seed_omitted_when_none_and_passed_when_set() -> None:
    model, client = _model([_completion()])
    await model.complete([], [])
    assert "seed" not in client.completions.kwargs[0]
    for forbidden in ("parallel_tool_calls", "tool_choice", "extra_body"):
        assert forbidden not in client.completions.kwargs[0]
    seeded, seeded_client = _model([_completion()], seed=7)
    await seeded.complete([], [])
    assert seeded_client.completions.kwargs[0]["seed"] == 7
    assert seeded_client.completions.kwargs[0]["model"] == "test-model"


async def test_before_request_awaited_per_attempt() -> None:
    count = 0

    async def hook() -> None:
        nonlocal count
        count += 1

    model, _ = _model(
        [_status_error(openai.InternalServerError, 500), _completion()], before_request=hook
    )
    await model.complete([], [])
    assert count == 2


async def test_before_request_wait_is_client_wait_not_latency() -> None:
    async def slow_hook() -> None:
        await asyncio.sleep(0.05)

    model, _ = _model([_completion()], before_request=slow_hook)
    response = await model.complete([], [])
    assert response.client_wait_ms >= 40
    assert response.latency_ms < 40


class _SlowFailingCompletions(_Completions):
    async def create(self, **kwargs: Any) -> ChatCompletion:
        if not self.kwargs:
            await asyncio.sleep(0.02)
        return await super().create(**kwargs)


async def test_client_wait_includes_failed_attempt() -> None:
    client = _FakeClient([_status_error(openai.InternalServerError, 500), _completion()])
    client.completions = _SlowFailingCompletions(client.completions.items)
    client.chat = _Chat(client.completions)
    model = OpenAIChatModel(
        client=client,  # type: ignore[arg-type]
        model="m",
        temperature=0.0,
        max_tokens=10,
        sleep=_Sleeper(),
    )
    response = await model.complete([], [])
    assert response.attempts == 2
    assert response.client_wait_ms >= 15
    assert response.latency_ms < 15


async def test_daily_limit_not_retried() -> None:
    error = openai.RateLimitError(
        "Rate limit exceeded: free-models-per-day",
        response=httpx2.Response(429, request=_REQUEST),
        body={"message": "free-models-per-day"},
    )
    sleeper = _Sleeper()
    model, client = _model([error], sleeper)
    with pytest.raises(LLMInfraError) as info:
        await model.complete([], [])
    assert info.value.kind == "daily_limit"
    assert info.value.attempts == 1
    assert info.value.status_code == 429
    assert len(client.completions.kwargs) == 1
    assert sleeper.delays == []


@pytest.mark.parametrize(("header", "expected"), [("7", 7.0), ("600", 60.0), ("soon", 5.0)])
async def test_retry_after_honoured_and_capped(header: str, expected: float) -> None:
    error = openai.RateLimitError(
        "slow down",
        response=httpx2.Response(429, request=_REQUEST, headers={"retry-after": header}),
        body=None,
    )
    sleeper = _Sleeper()
    model, _ = _model([error, _completion()], sleeper)
    await model.complete([], [])
    assert sleeper.delays == [expected]


@pytest.mark.parametrize(
    ("cls", "status", "kind"),
    [
        (openai.AuthenticationError, 401, "auth"),
        (openai.PermissionDeniedError, 403, "auth"),
        (openai.NotFoundError, 404, "not_found"),
        (openai.BadRequestError, 400, "bad_request"),
        (openai.UnprocessableEntityError, 422, "bad_request"),
    ],
)
async def test_non_retryable_status_kinds(
    cls: type[openai.APIStatusError], status: int, kind: str
) -> None:
    model, _ = _model([_status_error(cls, status)])
    with pytest.raises(LLMInfraError) as info:
        await model.complete([], [])
    assert (info.value.kind, info.value.status_code, info.value.attempts) == (kind, status, 1)


@pytest.mark.parametrize(
    ("make_error", "kind"),
    [
        (lambda: _status_error(openai.RateLimitError, 429), "rate_limited"),
        (lambda: _status_error(openai.InternalServerError, 500), "server"),
        (lambda: openai.APITimeoutError(request=_REQUEST), "timeout"),
        (lambda: openai.APIConnectionError(request=_REQUEST), "connection"),
    ],
)
async def test_exhausted_retryable_kinds(make_error: Any, kind: str) -> None:
    model, _ = _model([make_error() for _ in range(3)])
    with pytest.raises(LLMInfraError) as info:
        await model.complete([], [])
    assert info.value.kind == kind
    assert info.value.attempts == 3


async def test_empty_choices_and_no_usage_kinds() -> None:
    model, _ = _model([_completion(choices=[])] * 3)
    with pytest.raises(LLMInfraError) as info:
        await model.complete([], [])
    assert info.value.kind == "empty_choices"
    model, _ = _model([_completion(usage=None)])
    with pytest.raises(LLMInfraError) as info2:
        await model.complete([], [])
    assert (info2.value.kind, info2.value.attempts) == ("no_usage", 1)


_OPENROUTER_403 = "x/model is only available on agentic harnesses"


async def test_403_provider_message_from_openrouter_body() -> None:
    error = openai.PermissionDeniedError(
        "Error code: 403",
        response=httpx2.Response(403, request=_REQUEST),
        body={"error": {"message": _OPENROUTER_403, "code": 403, "metadata": {"a": 1}}},
    )
    model, _ = _model([error])
    with pytest.raises(LLMInfraError) as info:
        await model.complete([], [])
    assert info.value.kind == "auth"
    assert info.value.provider_message == _OPENROUTER_403
    assert f"— provider: {_OPENROUTER_403}" in str(info.value)


async def test_provider_message_from_inner_body_and_fallback() -> None:
    inner = openai.PermissionDeniedError(
        "Error code: 403",
        response=httpx2.Response(403, request=_REQUEST),
        body={"message": "inner msg", "code": 403},
    )
    model, _ = _model([inner])
    with pytest.raises(LLMInfraError) as info:
        await model.complete([], [])
    assert info.value.provider_message == "inner msg"
    model, _ = _model([_status_error(openai.BadRequestError, 400)])
    with pytest.raises(LLMInfraError) as info2:
        await model.complete([], [])
    assert info2.value.provider_message == "boom"


async def test_empty_choices_provider_message_after_retries() -> None:
    text = "Upstream error from Nvidia: Service temporarily overloaded"
    empty = _completion(choices=[], error={"message": text})
    model, _ = _model([empty, empty, empty])
    with pytest.raises(LLMInfraError) as info:
        await model.complete([], [])
    assert info.value.kind == "empty_choices"
    assert info.value.provider_message == text
    assert "— provider: Upstream error from Nvidia" in str(info.value)


async def test_provider_message_truncated() -> None:
    error = openai.PermissionDeniedError(
        "Error code: 403",
        response=httpx2.Response(403, request=_REQUEST),
        body={"error": {"message": "y" * 500}},
    )
    model, _ = _model([error])
    with pytest.raises(LLMInfraError) as info:
        await model.complete([], [])
    assert info.value.provider_message == "y" * 300
