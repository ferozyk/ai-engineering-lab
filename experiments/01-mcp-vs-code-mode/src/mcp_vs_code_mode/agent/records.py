"""Pydantic records for LLM calls, tool calls and task results.

Latency excludes client-side throttling and retry back-off: ``client_wait_ms`` records that
time separately and ``TaskResult.latency_ms`` is ``wall_ms - client_wait_ms``.
"""

from typing import Any, Literal

from pydantic import BaseModel

from mcp_vs_code_mode.scenarios.definitions import ScenarioId

Mode = Literal["mcp", "code"]
TaskOutcome = Literal["correct", "incorrect", "invalid_answer", "max_turns", "infra_error"]


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


class LLMCallRecord(BaseModel, frozen=True):
    """Per-call measurement kept in the task result."""

    turn: int
    latency_ms: float
    usage: Usage
    finish_reason: str | None
    tool_call_count: int
    attempts: int
    client_wait_ms: float
    provider: str | None
    model: str | None
    request_id: str | None
    simulated: bool


class ToolCallRecord(BaseModel, frozen=True):
    """Per-tool-call measurement. ``host_calls`` is set only in code mode."""

    turn: int
    name: str
    arguments: str
    duration_ms: float
    is_error: bool
    error_type: str | None
    result_chars: int
    host_calls: int | None


class TaskResult(BaseModel, frozen=True):
    """Outcome and measurements for one task run."""

    task_id: str
    mode: Mode
    scenario: ScenarioId
    volume: int | None
    outcome: TaskOutcome
    partial_score: float
    field_errors: tuple[str, ...]
    final_text: str | None
    error: str | None
    infra_error_kind: str | None
    infra_attempts: int
    llm_calls: tuple[LLMCallRecord, ...]
    tool_calls: tuple[ToolCallRecord, ...]
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    peak_prompt_tokens: int
    model_calls: int
    tool_call_count: int
    tool_errors: int
    wall_ms: float
    client_wait_ms: float
    latency_ms: float
    llm_ms: float
    tool_ms: float
    overhead_ms: float
    transcript: tuple[dict[str, Any], ...]
