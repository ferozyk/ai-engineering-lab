"""Pydantic records for one LLM call: token usage, tool calls and the response."""

from typing import Any

from pydantic import BaseModel


class Usage(BaseModel, frozen=True):
    """Token usage reported by the provider for one LLM call."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None


class LLMToolCall(BaseModel, frozen=True):
    """A tool call requested by the model; ``arguments`` is the raw JSON string."""

    id: str
    name: str
    arguments: str


class LLMResponse(BaseModel, frozen=True):
    """One model response plus the measurements taken around the call."""

    content: str | None
    tool_calls: tuple[LLMToolCall, ...]
    finish_reason: str | None
    usage: Usage
    latency_ms: float
    attempts: int
    client_wait_ms: float
    provider: str | None = None
    model: str | None = None
    request_id: str | None = None
    assistant_message: dict[str, Any]
    simulated: bool = False
