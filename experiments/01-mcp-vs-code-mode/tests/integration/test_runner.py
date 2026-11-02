"""Integration tests for the benchmark runner (real MCP server, Monty and the oracle model)."""

import json
import secrets
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from mcp_vs_code_mode.agent import ChatModel, LLMInfraError, LLMResponse
from mcp_vs_code_mode.agent.fakes import OracleChatModel
from mcp_vs_code_mode.agent.llm import InfraErrorKind
from mcp_vs_code_mode.bench import paths as paths_module
from mcp_vs_code_mode.bench.cells import ScheduledTask, build_schedule
from mcp_vs_code_mode.bench.config import BenchmarkConfig, load_config
from mcp_vs_code_mode.bench.limiter import RequestBudget
from mcp_vs_code_mode.bench.metadata import RunMetadata
from mcp_vs_code_mode.bench.openrouter import FreeModelDailyRequests, KeyInfo
from mcp_vs_code_mode.bench.pricing import simulated_pricing
from mcp_vs_code_mode.bench.records import LLMCallRow, TaskRow, ToolCallRow, load_rows
from mcp_vs_code_mode.bench.runner import ModelFactory, RunOutcome, run_benchmark
from mcp_vs_code_mode.scenarios import TaskSpec

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

_TOKEN = "KNOWN-SECRET-SESSION-TOKEN-0123456789"


@pytest.fixture(autouse=True)
def _isolated_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths_module, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(secrets, "token_urlsafe", lambda nbytes=32: _TOKEN)


def _config() -> BenchmarkConfig:
    return load_config().with_overrides(iterations=1)


def _oracle(task: ScheduledTask, spec: TaskSpec) -> ChatModel:
    return OracleChatModel(spec, task.cell.mode)


class _Failing:
    def __init__(self, kind: InfraErrorKind) -> None:
        self._kind = kind

    async def complete(
        self, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]]
    ) -> LLMResponse:
        raise LLMInfraError("boom", kind=self._kind, attempts=3)


def _failing_factory(task_id: str, kind: InfraErrorKind) -> ModelFactory:
    def factory(task: ScheduledTask, spec: TaskSpec) -> ChatModel:
        if task.task_id == task_id:
            return _Failing(kind)
        return OracleChatModel(spec, task.cell.mode)

    return factory


async def _run(
    factory: ModelFactory = _oracle,
    *,
    budget: RequestBudget | None = None,
    key_info: Callable[[], Awaitable[KeyInfo]] | None = None,
    run_id: str | None = None,
    config: BenchmarkConfig | None = None,
) -> RunOutcome:
    cfg = config or _config()
    return await run_benchmark(
        kind="dry-run",
        config=cfg,
        schedule=build_schedule(cfg),
        model_factory=factory,
        pricing=simulated_pricing(),
        model_id="oracle",
        budget=budget or RequestBudget(10**6),
        key_info=key_info,
        run_id=run_id,
        progress=lambda line: None,
    )


async def test_dry_run_writes_all_files() -> None:
    outcome = await _run()
    raw = outcome.paths.raw
    assert not outcome.halted
    assert outcome.completed == 14

    tasks = load_rows(raw / "tasks.jsonl", TaskRow)
    llm = load_rows(raw / "llm_calls.jsonl", LLMCallRow)
    tools = load_rows(raw / "tool_calls.jsonl", ToolCallRow)
    assert len(tasks) == 14
    assert sum(1 for t in tasks if t.warmup) == 3
    assert all(t.outcome == "correct" and t.simulated for t in tasks)
    assert len(llm) == sum(t.model_calls for t in tasks)
    assert len(tools) == sum(t.tool_call_count for t in tasks)
    assert len(list((raw / "transcripts").glob("*.json"))) == 14
    transcript = json.loads((raw / "transcripts" / f"{tasks[0].task_id}.json").read_text())
    assert transcript["task_id"] == tasks[0].task_id
    assert transcript["messages"][0]["role"] == "system"
    assert (raw / "audit.jsonl").stat().st_size > 0

    raw_line = json.loads((raw / "tasks.jsonl").read_text().splitlines()[0])
    assert "transcript" not in raw_line
    assert "llm_calls" not in raw_line
    assert "tool_calls" not in raw_line
    assert raw_line["estimated_cost_usd"] > 0

    meta = RunMetadata.model_validate_json((raw / "run_metadata.json").read_text())
    assert meta.simulated
    assert meta.tasks_planned == 14
    assert meta.tasks_completed == 14
    assert meta.finished_at is not None
    assert meta.mcp_connect_ms > 0
    assert meta.mcp_agg_connect_ms is not None
    assert meta.mcp_agg_connect_ms > 0
    assert meta.sandbox_warmup_ms > 0
    assert meta.providers_served == ["simulated"]
    assert outcome.paths.raw.parent.parent.name == "dry-run"


async def test_token_never_written() -> None:
    outcome = await _run()
    needle = _TOKEN.encode()
    files = [p for p in outcome.paths.raw.parent.rglob("*") if p.is_file()]
    assert files
    assert not [p for p in files if needle in p.read_bytes()]


async def test_resume_reattempts_only_infra_errors() -> None:
    first = await _run(_failing_factory("01-B10-code", "server"))
    assert first.infra_errors == 1
    assert not first.halted
    rows = load_rows(first.paths.raw / "tasks.jsonl", TaskRow)
    assert len(rows) == 14
    assert [r.task_id for r in rows if r.outcome == "infra_error"] == ["01-B10-code"]

    second = await _run(run_id=first.run_id)
    rows = load_rows(second.paths.raw / "tasks.jsonl", TaskRow)
    assert len(rows) == 15
    assert rows[-1].task_id == "01-B10-code"
    assert rows[-1].outcome == "correct"
    assert second.completed == 14
    meta = RunMetadata.model_validate_json((second.paths.raw / "run_metadata.json").read_text())
    assert meta.tasks_completed == 14
    assert meta.infra_errors == 1


async def test_halt_on_daily_limit() -> None:
    outcome = await _run(_failing_factory("01-A-mcp", "daily_limit"))
    assert outcome.halted
    assert outcome.halt_reason is not None
    assert "daily_limit" in outcome.halt_reason
    rows = load_rows(outcome.paths.raw / "tasks.jsonl", TaskRow)
    assert rows[-1].task_id == "01-A-mcp"
    assert len(rows) < 15


async def test_halt_when_budget_below_max_turns() -> None:
    outcome = await _run(budget=RequestBudget(cap=5))
    assert outcome.halted
    assert outcome.halt_reason is not None
    assert "--resume" in outcome.halt_reason
    assert load_rows(outcome.paths.raw / "tasks.jsonl", TaskRow) == []


async def test_rate_limited_with_zero_remaining_halts() -> None:
    async def key_info() -> KeyInfo:
        return KeyInfo(
            free_model_daily_requests=FreeModelDailyRequests(used=1000, limit=1000, remaining=0)
        )

    outcome = await _run(_failing_factory("01-A-mcp", "rate_limited"), key_info=key_info)
    assert outcome.halted
    assert outcome.halt_reason is not None
    assert "daily limit" in outcome.halt_reason
    meta = RunMetadata.model_validate_json((outcome.paths.raw / "run_metadata.json").read_text())
    assert meta.free_model_daily_requests_before is not None
    assert meta.free_model_daily_requests_after is not None


async def test_rate_limited_with_remaining_continues() -> None:
    async def key_info() -> KeyInfo:
        return KeyInfo(
            free_model_daily_requests=FreeModelDailyRequests(used=1, limit=1000, remaining=999)
        )

    outcome = await _run(_failing_factory("01-A-mcp", "rate_limited"), key_info=key_info)
    assert not outcome.halted
    assert outcome.infra_errors == 1


async def test_three_consecutive_infra_errors_halt() -> None:
    def factory(task: ScheduledTask, spec: TaskSpec) -> ChatModel:
        if not task.warmup:
            return _Failing("server")
        return OracleChatModel(spec, task.cell.mode)

    outcome = await _run(factory)
    assert outcome.halted
    assert outcome.infra_errors == 3


async def test_every_scheduled_cell_is_answered_correctly_by_the_oracle() -> None:
    """Real MCP servers (raw and aggregation) and Monty: all 11 cells end 'correct'."""
    outcome = await _run()
    rows = load_rows(outcome.paths.raw / "tasks.jsonl", TaskRow)
    measured = {r.cell: r.outcome for r in rows if not r.warmup}
    assert set(measured) == {
        "A:mcp", "A:mcp_agg", "A:code", "B10:mcp", "B10:mcp_agg", "B10:code",
        "B100:mcp", "B100:mcp_agg", "B100:code", "C100:mcp_agg", "C100:code",
    }  # fmt: skip
    assert set(measured.values()) == {"correct"}
    tools = load_rows(outcome.paths.raw / "tool_calls.jsonl", ToolCallRow)
    assert any(t.mode == "mcp_agg" and t.name == "summarise_spending" for t in tools)
    assert not [t for t in tools if t.mode in ("mcp", "code") and t.name == "summarise_spending"]
    audit = (outcome.paths.raw / "audit.jsonl").read_text().splitlines()
    channels = {json.loads(line)["channel"] for line in audit}
    assert channels == {"mcp", "mcp_agg", "code_mode"}
