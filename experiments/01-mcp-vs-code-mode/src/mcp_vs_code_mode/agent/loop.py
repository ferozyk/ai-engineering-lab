"""The shared agent loop: identical for MCP mode and Code Mode."""

import time
from typing import Any

from mcp_vs_code_mode.agent.llm import ChatModel, LLMInfraError
from mcp_vs_code_mode.agent.prompts import build_system_prompt
from mcp_vs_code_mode.agent.records import (
    LLMCallRecord,
    TaskOutcome,
    TaskResult,
    ToolCallRecord,
)
from mcp_vs_code_mode.agent.toolsets import Toolset
from mcp_vs_code_mode.scenarios.definitions import AnswerA, AnswerB, AnswerC, TaskSpec
from mcp_vs_code_mode.scenarios.scoring import (
    score_answer_a,
    score_answer_b,
    score_answer_c,
)

MAX_TURNS = 8


async def run_task(
    *,
    task_id: str,
    task: TaskSpec,
    expected: AnswerA | AnswerB | AnswerC,
    model: ChatModel,
    toolset: Toolset,
    max_turns: int = MAX_TURNS,
) -> TaskResult:
    """Run one task to completion and return measurements and the scored outcome."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt(toolset)},
        {"role": "user", "content": task.user_prompt},
    ]
    tools = toolset.tool_definitions()
    llm_records: list[LLMCallRecord] = []
    tool_records: list[ToolCallRecord] = []
    outcome: TaskOutcome = "max_turns"
    partial = 0.0
    field_errors: tuple[str, ...] = ()
    final_text: str | None = None
    error: str | None = None
    infra_kind: str | None = None
    infra_attempts = 0
    start = time.perf_counter()

    for turn in range(1, max_turns + 1):
        try:
            response = await model.complete(messages, tools)
        except LLMInfraError as exc:
            outcome, error = "infra_error", str(exc)
            infra_kind, infra_attempts = exc.kind, exc.attempts
            break
        llm_records.append(
            LLMCallRecord(
                turn=turn,
                latency_ms=response.latency_ms,
                usage=response.usage,
                finish_reason=response.finish_reason,
                tool_call_count=len(response.tool_calls),
                attempts=response.attempts,
                client_wait_ms=response.client_wait_ms,
                provider=response.provider,
                model=response.model,
                request_id=response.request_id,
                simulated=response.simulated,
            )
        )
        messages.append(response.assistant_message)
        if response.tool_calls:
            for call in response.tool_calls:
                result = await toolset.call(call.name, call.arguments)
                tool_records.append(
                    ToolCallRecord(
                        turn=turn,
                        name=call.name,
                        arguments=call.arguments,
                        duration_ms=result.duration_ms,
                        is_error=result.is_error,
                        error_type=result.error_type,
                        result_chars=len(result.content),
                        host_calls=result.host_calls,
                    )
                )
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result.content}
                )
            continue
        final_text = response.content or ""
        if task.scenario == "A":
            assert isinstance(expected, AnswerA)
            score = score_answer_a(expected, final_text)
        elif task.scenario == "B":
            assert isinstance(expected, AnswerB)
            score = score_answer_b(expected, final_text)
        else:
            assert isinstance(expected, AnswerC)
            score = score_answer_c(expected, final_text)
        outcome, partial, field_errors = score.outcome, score.partial_score, score.field_errors
        break

    wall_ms = (time.perf_counter() - start) * 1000
    client_wait_ms = sum(r.client_wait_ms for r in llm_records)
    latency_ms = wall_ms - client_wait_ms
    llm_ms = sum(r.latency_ms for r in llm_records)
    tool_ms = sum(r.duration_ms for r in tool_records)
    return TaskResult(
        task_id=task_id,
        mode=toolset.mode,
        scenario=task.scenario,
        volume=task.volume,
        outcome=outcome,
        partial_score=partial,
        field_errors=field_errors,
        final_text=final_text,
        error=error,
        infra_error_kind=infra_kind,
        infra_attempts=infra_attempts,
        llm_calls=tuple(llm_records),
        tool_calls=tuple(tool_records),
        input_tokens=sum(r.usage.prompt_tokens for r in llm_records),
        output_tokens=sum(r.usage.completion_tokens for r in llm_records),
        reasoning_tokens=sum(r.usage.reasoning_tokens or 0 for r in llm_records),
        total_tokens=sum(r.usage.total_tokens for r in llm_records),
        peak_prompt_tokens=max((r.usage.prompt_tokens for r in llm_records), default=0),
        model_calls=len(llm_records),
        tool_call_count=len(tool_records),
        tool_errors=sum(1 for r in tool_records if r.is_error),
        wall_ms=wall_ms,
        client_wait_ms=client_wait_ms,
        latency_ms=latency_ms,
        llm_ms=llm_ms,
        tool_ms=tool_ms,
        overhead_ms=latency_ms - llm_ms - tool_ms,
        transcript=tuple(messages),
    )
