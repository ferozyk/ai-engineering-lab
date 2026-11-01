"""The benchmark runner: executes a schedule, checkpointing every task to JSONL."""

import json
import secrets
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import ExitStack, suppress
from dataclasses import dataclass
from datetime import UTC, datetime

from mcp_vs_code_mode.agent import (
    ChatModel,
    CodeModeToolset,
    MCPToolset,
    TaskResult,
    Toolset,
    run_task,
)
from mcp_vs_code_mode.banking import (
    DATASET_VERSION,
    AuditLog,
    BankingService,
    Dataset,
    authenticate_token,
    generate_dataset,
    token_fingerprint,
)
from mcp_vs_code_mode.bench.cells import Cell, ScheduledTask
from mcp_vs_code_mode.bench.config import BenchmarkConfig
from mcp_vs_code_mode.bench.limiter import BudgetExhaustedError, RequestBudget
from mcp_vs_code_mode.bench.metadata import RunMetadata, collect_environment, git_state
from mcp_vs_code_mode.bench.openrouter import KeyInfo, OpenRouterError
from mcp_vs_code_mode.bench.paths import RunKind, RunPaths, new_run_id
from mcp_vs_code_mode.bench.pricing import PricingSnapshot, estimate_cost_usd
from mcp_vs_code_mode.bench.records import (
    LLMCallRow,
    TaskRow,
    ToolCallRow,
    append_row,
    load_rows,
)
from mcp_vs_code_mode.code_mode import CodeSandbox, SandboxLimits
from mcp_vs_code_mode.mcp_server import server_parameters
from mcp_vs_code_mode.scenarios import (
    AnswerA,
    AnswerB,
    TaskSpec,
    expected_answer_a,
    expected_answer_b,
    scenario_a_task,
    scenario_b_task,
)
from mcp_vs_code_mode.tools import ToolExecutor

ModelFactory = Callable[[ScheduledTask, TaskSpec], ChatModel]

_HALT_KINDS = frozenset({"daily_limit", "auth", "not_found", "bad_request", "no_usage"})
_MAX_CONSECUTIVE_INFRA = 3
_PRINCIPAL_ID = "rm-001"
_MB = 1024 * 1024


@dataclass
class RunOutcome:
    """Summary of a runner invocation."""

    run_id: str
    paths: RunPaths
    completed: int
    infra_errors: int
    halted: bool
    halt_reason: str | None
    requests_sent: int


def task_spec_for(cell: Cell) -> TaskSpec:
    """The task presented to the model for a cell."""
    if cell.scenario == "A":
        return scenario_a_task()
    assert cell.volume is not None
    return scenario_b_task(cell.volume)


def expected_for(dataset: Dataset, cell: Cell) -> AnswerA | AnswerB:
    """Ground truth for a cell, computed by plain Python."""
    if cell.scenario == "A":
        return expected_answer_a(dataset)
    assert cell.volume is not None
    return expected_answer_b(dataset, cell.volume)


def _new_metadata(
    *,
    run_id: str,
    kind: RunKind,
    config: BenchmarkConfig,
    schedule: Sequence[ScheduledTask],
    pricing: PricingSnapshot,
    model_id: str,
    dataset: Dataset,
) -> RunMetadata:
    sha, dirty = git_state()
    env = collect_environment()
    simulated = kind == "dry-run"
    return RunMetadata(
        run_id=run_id,
        kind=kind,
        simulated=simulated,
        experiment=config.experiment,
        experiment_version=config.experiment_version,
        git_sha=sha,
        git_dirty=dirty,
        started_at=datetime.now(UTC),
        hardware=env["hardware"],
        os=env["os"],
        python_version=env["python_version"],
        provider="simulated" if simulated else "openrouter",
        model_id="oracle (simulated)" if simulated else model_id,
        dataset_version=DATASET_VERSION,
        dataset_checksum=dataset.checksum(),
        config=config.model_dump(),
        iterations=config.iterations,
        tasks_planned=len(schedule),
        package_versions=env["package_versions"],
        pricing=pricing,
        max_turns=config.max_turns,
        rate_limit_per_minute=config.rate_limit_per_minute,
        daily_request_cap=config.daily_request_cap,
        order_seed=config.order_seed,
        llm_seed=config.llm_seed,
    )


def _write_metadata(paths: RunPaths, meta: RunMetadata) -> None:
    (paths.raw / "run_metadata.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")


def _record_task(
    *,
    paths: RunPaths,
    run_id: str,
    scheduled: ScheduledTask,
    result: TaskResult,
    started_at: datetime,
    pricing: PricingSnapshot,
    simulated: bool,
) -> None:
    row = TaskRow(
        run_id=run_id,
        iteration=scheduled.iteration,
        warmup=scheduled.warmup,
        order_index=scheduled.order_index,
        cell=scheduled.cell.label,
        started_at=started_at,
        simulated=simulated,
        estimated_cost_usd=estimate_cost_usd(result.input_tokens, result.output_tokens, pricing),
        **result.model_dump(
            exclude={"transcript", "llm_calls", "tool_calls"},
        ),
    )
    for call in result.llm_calls:
        append_row(
            paths.raw / "llm_calls.jsonl",
            LLMCallRow(
                task_id=result.task_id,
                turn=call.turn,
                latency_ms=call.latency_ms,
                prompt_tokens=call.usage.prompt_tokens,
                completion_tokens=call.usage.completion_tokens,
                total_tokens=call.usage.total_tokens,
                reasoning_tokens=call.usage.reasoning_tokens,
                cached_tokens=call.usage.cached_tokens,
                finish_reason=call.finish_reason,
                tool_call_count=call.tool_call_count,
                attempts=call.attempts,
                client_wait_ms=call.client_wait_ms,
                provider=call.provider,
                model=call.model,
                request_id=call.request_id,
                simulated=call.simulated,
            ),
        )
    for tool in result.tool_calls:
        append_row(
            paths.raw / "tool_calls.jsonl",
            ToolCallRow(task_id=result.task_id, mode=result.mode, **tool.model_dump()),
        )
    transcript = {"task_id": result.task_id, "messages": list(result.transcript)}
    (paths.raw / "transcripts" / f"{result.task_id}.json").write_text(
        json.dumps(transcript, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    append_row(paths.raw / "tasks.jsonl", row)


def _latest_task_rows(paths: RunPaths) -> dict[str, TaskRow]:
    latest: dict[str, TaskRow] = {}
    for row in load_rows(paths.raw / "tasks.jsonl", TaskRow):
        latest[row.task_id] = row
    return latest


def _progress_line(
    position: int, total: int, scheduled: ScheduledTask, result: TaskResult, requests: str
) -> str:
    outcome = f"warmup:{result.outcome}" if scheduled.warmup else result.outcome
    return (
        f"[{position:>3}/{total}] {scheduled.task_id}  {outcome}  "
        f"tokens={result.total_tokens:,}  latency={result.latency_ms / 1000:.1f}s  "
        f"calls={result.model_calls}  requests={requests}"
    )


async def run_benchmark(
    *,
    kind: RunKind,
    config: BenchmarkConfig,
    schedule: Sequence[ScheduledTask],
    model_factory: ModelFactory,
    pricing: PricingSnapshot,
    model_id: str,
    budget: RequestBudget,
    key_info: Callable[[], Awaitable[KeyInfo]] | None,
    run_id: str | None = None,
    progress: Callable[[str], None] = print,
) -> RunOutcome:
    """Execute ``schedule``, appending results as they complete.

    Pass ``run_id`` to resume: tasks that already have a non-``infra_error`` record are skipped.
    """
    resumed = run_id is not None
    if run_id is None:
        paths = RunPaths.for_run(new_run_id(kind), kind)
    else:
        paths = RunPaths.find(run_id)
        kind = paths.kind
    paths.ensure()
    simulated = kind == "dry-run"
    dataset = generate_dataset()

    meta_path = paths.raw / "run_metadata.json"
    if resumed and meta_path.exists():
        meta = RunMetadata.model_validate_json(meta_path.read_text(encoding="utf-8"))
        meta.halted, meta.halt_reason, meta.finished_at = False, None, None
    else:
        meta = _new_metadata(
            run_id=paths.run_id,
            kind=kind,
            config=config,
            schedule=schedule,
            pricing=pricing,
            model_id=model_id,
            dataset=dataset,
        )
    if key_info is not None and meta.free_model_daily_requests_before is None:
        with suppress(OpenRouterError):
            meta.free_model_daily_requests_before = (await key_info()).free_model_daily_requests
    _write_metadata(paths, meta)

    done = {tid for tid, row in _latest_task_rows(paths).items() if row.outcome != "infra_error"}
    pending = [task for task in schedule if task.task_id not in done]
    expected = {cell: expected_for(dataset, cell) for cell in {t.cell for t in schedule}}
    total = len(schedule)

    # Credentials: a fresh random token, shared in memory only. Never written anywhere.
    token = secrets.token_urlsafe(32)
    trusted = {token_fingerprint(token): _PRINCIPAL_ID}
    audit_path = paths.raw / "audit.jsonl"
    params = server_parameters(token=token, trusted=trusted, audit_log=audit_path)
    principal = authenticate_token(token, trusted)
    executor = ToolExecutor(BankingService(dataset, AuditLog(audit_path)), principal, "code_mode")
    limits = SandboxLimits(
        max_duration_secs=config.sandbox.max_duration_secs,
        max_memory_bytes=config.sandbox.max_memory_mb * _MB,
        max_host_calls=config.sandbox.max_host_calls,
    )

    requests_before = budget.used
    halted, halt_reason = False, None
    consecutive_infra = 0
    attempted_done = 0

    with ExitStack() as stack:
        connect_started = time.perf_counter()
        async with MCPToolset.open(
            params, call_timeout=config.mcp_call_timeout_seconds
        ) as mcp_toolset:
            meta.mcp_connect_ms = (time.perf_counter() - connect_started) * 1000
            sandbox_started = time.perf_counter()
            sandbox = stack.enter_context(CodeSandbox(executor, limits))
            meta.sandbox_warmup_ms = (time.perf_counter() - sandbox_started) * 1000
            code_toolset = CodeModeToolset(sandbox)
            toolsets: dict[str, Toolset] = {"mcp": mcp_toolset, "code": code_toolset}

            for scheduled in pending:
                if budget.remaining < config.max_turns:
                    halted = True
                    halt_reason = (
                        "daily request cap reached; resume tomorrow with: "
                        f"run --resume {paths.run_id}"
                    )
                    break
                spec = task_spec_for(scheduled.cell)
                started_at = datetime.now(UTC)
                try:
                    result = await run_task(
                        task_id=scheduled.task_id,
                        task=spec,
                        expected=expected[scheduled.cell],
                        model=model_factory(scheduled, spec),
                        toolset=toolsets[scheduled.cell.mode],
                        max_turns=config.max_turns,
                    )
                except BudgetExhaustedError:
                    halted = True
                    halt_reason = (
                        "daily request cap reached mid-task; resume tomorrow with: "
                        f"run --resume {paths.run_id}"
                    )
                    break
                _record_task(
                    paths=paths,
                    run_id=paths.run_id,
                    scheduled=scheduled,
                    result=result,
                    started_at=started_at,
                    pricing=pricing,
                    simulated=simulated,
                )
                attempted_done += 1
                position = scheduled.order_index + 1
                progress(
                    _progress_line(
                        position,
                        total,
                        scheduled,
                        result,
                        f"{budget.used}/{config.daily_request_cap}",
                    )
                )
                if result.outcome != "infra_error":
                    consecutive_infra = 0
                    continue
                consecutive_infra += 1
                kind_name = result.infra_error_kind or "other"
                if kind_name in _HALT_KINDS:
                    halted, halt_reason = (
                        True,
                        f"infrastructure error '{kind_name}': {result.error}",
                    )
                    break
                if kind_name == "rate_limited" and key_info is not None:
                    try:
                        info = await key_info()
                    except OpenRouterError:
                        info = None
                    daily = info.free_model_daily_requests if info is not None else None
                    if daily is not None and daily.remaining == 0:
                        halted = True
                        halt_reason = (
                            "provider daily limit reached (0 free requests remaining); "
                            f"resume tomorrow with: run --resume {paths.run_id}"
                        )
                        break
                if consecutive_infra >= _MAX_CONSECUTIVE_INFRA:
                    halted = True
                    halt_reason = (
                        f"{_MAX_CONSECUTIVE_INFRA} consecutive infrastructure errors "
                        f"(last: '{kind_name}')"
                    )
                    break

    rows = list(_latest_task_rows(paths).values())
    all_rows = load_rows(paths.raw / "tasks.jsonl", TaskRow)
    calls = load_rows(paths.raw / "llm_calls.jsonl", LLMCallRow)
    meta.models_served = sorted({c.model for c in calls if c.model})
    meta.providers_served = sorted({c.provider for c in calls if c.provider})
    meta.requests_sent += budget.used - requests_before
    meta.failed_requests = sum(c.attempts - 1 for c in calls) + sum(
        r.infra_attempts for r in all_rows
    )
    meta.infra_errors = sum(1 for r in all_rows if r.outcome == "infra_error")
    meta.tasks_completed = sum(1 for r in rows if r.outcome != "infra_error")
    if key_info is not None:
        with suppress(OpenRouterError):
            meta.free_model_daily_requests_after = (await key_info()).free_model_daily_requests
    meta.halted, meta.halt_reason = halted, halt_reason
    meta.finished_at = datetime.now(UTC)
    _write_metadata(paths, meta)
    if halted:
        progress(f"HALTED: {halt_reason}")
    return RunOutcome(
        run_id=paths.run_id,
        paths=paths,
        completed=meta.tasks_completed,
        infra_errors=meta.infra_errors,
        halted=halted,
        halt_reason=halt_reason,
        requests_sent=meta.requests_sent,
    )
