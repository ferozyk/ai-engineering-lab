"""Chat model protocol and the OpenAI-compatible implementation (with retries)."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal, Protocol

import openai
from openai import AsyncOpenAI

from mcp_vs_code_mode.agent.records import LLMResponse, LLMToolCall, Usage

InfraErrorKind = Literal[
    "rate_limited",
    "daily_limit",
    "server",
    "timeout",
    "connection",
    "bad_request",
    "auth",
    "not_found",
    "empty_choices",
    "no_usage",
    "other",
]


class LLMInfraError(Exception):
    """Provider failure after retries (counts as infra_error).

    ``attempts`` is the number of requests sent in the failing call. Messages never contain
    headers or keys.
    """

    def __init__(
        self,
        message: str,
        *,
        kind: InfraErrorKind = "other",
        status_code: int | None = None,
        attempts: int = 0,
    ) -> None:
        super().__init__(message)
        self.kind: InfraErrorKind = kind
        self.status_code = status_code
        self.attempts = attempts


class ChatModel(Protocol):
    """Anything that can answer a chat turn with optional tool calls."""

    async def complete(
        self, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]]
    ) -> LLMResponse:
        """Return the model's next message."""
        ...


_MAX_RETRY_AFTER_SECS = 60.0


class _EmptyChoicesError(Exception):
    """Provider returned HTTP 200 without choices (treated as retryable)."""


def _status(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    return status if isinstance(status, int) else None


def _describe(exc: Exception) -> str:
    status = _status(exc)
    suffix = f" (status {status})" if status is not None else ""
    return f"{type(exc).__name__}{suffix}"


def _is_daily_limit(exc: openai.RateLimitError) -> bool:
    text = f"{exc} {getattr(exc, 'body', None)}".lower()
    return "per-day" in text or "per day" in text


def _retry_after(exc: openai.APIStatusError) -> float | None:
    raw = exc.response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return min(max(value, 0.0), _MAX_RETRY_AFTER_SECS)


def _non_retryable_kind(status: int | None) -> InfraErrorKind:
    if status in (401, 403):
        return "auth"
    if status == 404:
        return "not_found"
    if status is not None and 400 <= status < 500:
        return "bad_request"
    return "other"


class OpenAIChatModel:
    """Chat Completions client with bounded retries. The model id is a parameter."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
        temperature: float,
        max_tokens: int,
        seed: int | None = None,
        max_attempts: int = 3,
        backoff_seconds: Sequence[float] = (5.0, 20.0),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        before_request: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._seed = seed
        self._max_attempts = max_attempts
        self._backoff = tuple(backoff_seconds)
        self._sleep = sleep
        self._before_request = before_request

    async def complete(
        self, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]]
    ) -> LLMResponse:
        """Call the provider, retrying transient failures."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": list(messages),
            "tools": list(tools),
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if self._seed is not None:
            kwargs["seed"] = self._seed
        entered = time.perf_counter()
        last_error = "no attempts made"
        last_kind: InfraErrorKind = "other"
        last_status: int | None = None
        for attempt in range(1, self._max_attempts + 1):
            if self._before_request is not None:
                await self._before_request()
            started = time.perf_counter()
            override: float | None = None
            try:
                response = await self._client.chat.completions.create(**kwargs)
                latency_ms = (time.perf_counter() - started) * 1000
                if not response.choices:
                    error = (response.model_extra or {}).get("error")
                    raise _EmptyChoicesError(f"Provider returned no choices; error={error!r}")
            except _EmptyChoicesError as exc:
                last_error, last_kind, last_status = str(exc), "empty_choices", None
            except openai.RateLimitError as exc:
                if _is_daily_limit(exc):
                    raise LLMInfraError(
                        f"Daily request limit reached: {_describe(exc)}",
                        kind="daily_limit",
                        status_code=_status(exc),
                        attempts=attempt,
                    ) from exc
                last_error, last_kind, last_status = _describe(exc), "rate_limited", _status(exc)
                override = _retry_after(exc)
            except openai.InternalServerError as exc:
                last_error, last_kind, last_status = _describe(exc), "server", _status(exc)
            except openai.APITimeoutError as exc:
                last_error, last_kind, last_status = _describe(exc), "timeout", None
            except openai.APIConnectionError as exc:
                last_error, last_kind, last_status = _describe(exc), "connection", None
            except openai.APIError as exc:
                status = _status(exc)
                raise LLMInfraError(
                    f"Non-retryable provider error: {_describe(exc)}",
                    kind=_non_retryable_kind(status),
                    status_code=status,
                    attempts=attempt,
                ) from exc
            else:
                total_ms = (time.perf_counter() - entered) * 1000
                return self._to_response(
                    response, latency_ms, attempt, max(0.0, total_ms - latency_ms)
                )
            if attempt < self._max_attempts:
                if override is not None:
                    delay = override
                elif self._backoff:
                    delay = self._backoff[min(attempt - 1, len(self._backoff) - 1)]
                else:
                    delay = 0.0
                await self._sleep(delay)
        raise LLMInfraError(
            f"Provider failed after {self._max_attempts} attempts: {last_error}",
            kind=last_kind,
            status_code=last_status,
            attempts=self._max_attempts,
        )

    @staticmethod
    def _to_response(
        response: Any, latency_ms: float, attempts: int, client_wait_ms: float
    ) -> LLMResponse:
        raw_usage = response.usage
        if raw_usage is None:
            raise LLMInfraError("Provider returned no usage", kind="no_usage", attempts=attempts)
        completion_details = raw_usage.completion_tokens_details
        prompt_details = raw_usage.prompt_tokens_details
        usage = Usage(
            prompt_tokens=raw_usage.prompt_tokens,
            completion_tokens=raw_usage.completion_tokens,
            total_tokens=raw_usage.total_tokens,
            reasoning_tokens=completion_details.reasoning_tokens if completion_details else None,
            cached_tokens=prompt_details.cached_tokens if prompt_details else None,
        )
        choice = response.choices[0]
        message = choice.message
        tool_calls = tuple(
            LLMToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
            for tc in (message.tool_calls or [])
            if tc.type == "function"
        )
        assistant: dict[str, Any] = {"role": "assistant", "content": message.content}
        if tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in tool_calls
            ]
        extra = message.model_extra or {}
        if "reasoning_details" in extra:
            assistant["reasoning_details"] = extra["reasoning_details"]
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage=usage,
            latency_ms=latency_ms,
            attempts=attempts,
            client_wait_ms=client_wait_ms,
            provider=(response.model_extra or {}).get("provider"),
            model=response.model,
            request_id=response.id,
            assistant_message=assistant,
        )
