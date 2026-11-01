"""Unit tests for the shared agent loop using scripted models and a fake toolset."""

import json

import pytest

from mcp_vs_code_mode.agent import LLMInfraError, ToolOutcome, run_task
from mcp_vs_code_mode.agent.fakes import (
    ScriptedChatModel,
    build_response,
    scripted_text,
    scripted_tool_call,
)
from mcp_vs_code_mode.agent.records import LLMToolCall, Mode, Usage
from mcp_vs_code_mode.scenarios import AnswerA, scenario_a_task

pytestmark = [pytest.mark.unit, pytest.mark.anyio]

_EXPECTED = AnswerA(account_id="ACC-0050-1", available_balance=100.0, currency="GBP")
_CORRECT = json.dumps(_EXPECTED.model_dump())


class FakeToolset:
    mode: Mode = "mcp"

    def __init__(self, outcomes: dict[str, ToolOutcome] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._outcomes = outcomes or {}

    def tool_definitions(self) -> list[dict[str, object]]:
        return []

    def prompt_section(self) -> str:
        return "fake section"

    async def call(self, name: str, arguments: str) -> ToolOutcome:
        self.calls.append((name, arguments))
        return self._outcomes.get(name, ToolOutcome("{}", False, None, 0.0, None))


async def _run(responses: list, toolset: FakeToolset | None = None, max_turns: int = 8):  # type: ignore[no-untyped-def,type-arg]
    return await run_task(
        task_id="t1",
        task=scenario_a_task(),
        expected=_EXPECTED,
        model=ScriptedChatModel(responses),
        toolset=toolset or FakeToolset(),
        max_turns=max_turns,
    )


async def test_tool_call_then_correct_answer() -> None:
    toolset = FakeToolset({"get_balance": ToolOutcome('{"x":1}', False, None, 0.0, None)})
    result = await _run(
        [
            scripted_tool_call("get_balance", {"account_id": "ACC-0050-1"}, "c1"),
            scripted_text(_CORRECT),
        ],
        toolset,
    )
    assert result.outcome == "correct"
    assert result.partial_score == 1.0
    assert result.model_calls == 2
    assert result.tool_call_count == 1
    tool_message = result.transcript[-2]
    assert tool_message == {"role": "tool", "tool_call_id": "c1", "content": '{"x":1}'}
    assert result.transcript[0]["role"] == "system"
    assert "fake section" in result.transcript[0]["content"]
    assert result.overhead_ms >= 0


async def test_parallel_tool_calls_in_one_turn() -> None:
    calls = [LLMToolCall(id=f"c{i}", name="get_balance", arguments="{}") for i in range(3)]
    toolset = FakeToolset()
    result = await _run(
        [build_response(content=None, tool_calls=calls, prompt_tokens=10), scripted_text(_CORRECT)],
        toolset,
    )
    assert [c[0] for c in toolset.calls] == ["get_balance"] * 3
    assert [m["tool_call_id"] for m in result.transcript if m["role"] == "tool"] == [
        "c0",
        "c1",
        "c2",
    ]
    assert {t.turn for t in result.tool_calls} == {1}
    assert result.llm_calls[0].tool_call_count == 3


async def test_usage_totals_and_peak() -> None:
    first = build_response(
        content=None,
        tool_calls=[LLMToolCall(id="c1", name="t", arguments="{}")],
        prompt_tokens=100,
        completion_tokens=7,
    )
    second = scripted_text(_CORRECT, prompt_tokens=250).model_copy(
        update={
            "usage": Usage(
                prompt_tokens=250, completion_tokens=11, total_tokens=261, reasoning_tokens=4
            )
        }
    )
    result = await _run([first, second])
    assert result.input_tokens == 350
    assert result.output_tokens == 18
    assert result.total_tokens == 107 + 261
    assert result.reasoning_tokens == 4
    assert result.peak_prompt_tokens == 250


async def test_max_turns() -> None:
    looping = [scripted_tool_call("t", {}, f"c{i}") for i in range(3)]
    result = await _run(looping, max_turns=3)
    assert result.outcome == "max_turns"
    assert result.model_calls == 3
    assert result.final_text is None


async def test_infra_error_keeps_prior_records() -> None:
    result = await _run([scripted_tool_call("t", {}, "c1"), LLMInfraError("provider down")])
    assert result.outcome == "infra_error"
    assert result.error == "provider down"
    assert result.model_calls == 1
    assert result.tool_call_count == 1


async def test_invalid_final_json() -> None:
    result = await _run([scripted_text("I think it is 100")])
    assert result.outcome == "invalid_answer"
    assert result.partial_score == 0.0


async def test_incorrect_answer_and_tool_errors_counted() -> None:
    wrong = json.dumps({**_EXPECTED.model_dump(), "available_balance": 1.0})
    toolset = FakeToolset({"t": ToolOutcome("{}", True, "access_denied", 1.0, None)})
    result = await _run([scripted_tool_call("t", {}, "c1"), scripted_text(wrong)], toolset)
    assert result.outcome == "incorrect"
    assert result.tool_errors == 1
    assert result.field_errors


async def test_infra_error_kind_and_attempts_propagate() -> None:
    result = await _run([LLMInfraError("quota", kind="daily_limit", status_code=429, attempts=1)])
    assert result.infra_error_kind == "daily_limit"
    assert result.infra_attempts == 1
    ok = await _run([scripted_text(_CORRECT)])
    assert ok.infra_error_kind is None
    assert ok.infra_attempts == 0


async def test_client_wait_excluded_from_latency() -> None:
    waited = scripted_text(_CORRECT).model_copy(update={"client_wait_ms": 5000.0})
    result = await _run([waited])
    assert result.client_wait_ms == 5000.0
    assert result.latency_ms < 5000
    assert result.wall_ms >= result.latency_ms
    assert result.llm_calls[0].client_wait_ms == 5000.0
