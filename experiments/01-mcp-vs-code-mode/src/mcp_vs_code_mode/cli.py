"""Command-line interface: plan, preflight, canary, run, dry-run and the analysis commands."""

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
from openai import AsyncOpenAI

from ai_lab.config import ConfigurationError, Settings, load_settings
from mcp_vs_code_mode.agent import ChatModel, OpenAIChatModel
from mcp_vs_code_mode.agent.fakes import OracleChatModel
from mcp_vs_code_mode.bench.analysis import Summary, load_tasks, summarise, write_summary
from mcp_vs_code_mode.bench.cells import (
    ScheduledTask,
    build_canary_schedule,
    build_schedule,
)
from mcp_vs_code_mode.bench.charts import render_all
from mcp_vs_code_mode.bench.config import BenchmarkConfig, load_config
from mcp_vs_code_mode.bench.limiter import (
    MinIntervalLimiter,
    RequestBudget,
    before_request_hook,
)
from mcp_vs_code_mode.bench.linkedin import render_linkedin
from mcp_vs_code_mode.bench.metadata import RunMetadata, git_state
from mcp_vs_code_mode.bench.openrouter import KeyInfo, OpenRouterClient, OpenRouterError
from mcp_vs_code_mode.bench.paths import RunPaths
from mcp_vs_code_mode.bench.plan import estimate_requests, format_plan
from mcp_vs_code_mode.bench.preflight import format_report, has_failures, run_preflight
from mcp_vs_code_mode.bench.pricing import (
    PricingError,
    PricingSnapshot,
    resolve_pricing,
    simulated_pricing,
)
from mcp_vs_code_mode.bench.records import TaskRow, load_rows
from mcp_vs_code_mode.bench.report import render_report
from mcp_vs_code_mode.bench.runner import ModelFactory, RunOutcome, run_benchmark
from mcp_vs_code_mode.scenarios import TaskSpec

_HTTP_TIMEOUT = 30.0
_CANARY_BAD_OUTCOMES = frozenset({"infra_error", "invalid_answer", "max_turns"})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-vs-code-mode", description="Experiment 01: MCP vs Code Mode benchmark runner."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="print the request budget estimate (no network)")
    pre = sub.add_parser("preflight", help="validate configuration, model, pricing and runtimes")
    pre.add_argument(
        "--live",
        action="store_true",
        help="also send exactly ONE model request to verify tool calling",
    )
    canary = sub.add_parser("canary", help="run one task per canary cell against the provider")
    canary.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    run = sub.add_parser("run", help="run the full benchmark")
    run.add_argument("--resume", metavar="RUN_ID", help="resume an interrupted run")
    run.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    run.add_argument("--allow-dirty", action="store_true", help="allow a dirty git tree")
    dry = sub.add_parser("dry-run", help="run the whole schedule offline against an oracle model")
    dry.add_argument("--iterations", type=int, default=None, help="override the iteration count")
    for name, text in (
        ("analyze", "compute the processed summary and print the hypothesis table"),
        ("charts", "render all charts (PNG and SVG) from the processed summary"),
        ("report", "write the Markdown report"),
        ("linkedin-assets", "render the two LinkedIn images"),
        ("publish", "analyze, charts, report and linkedin-assets in one go"),
    ):
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("run_id", metavar="RUN_ID")
    return parser


def _confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    return input(f"{question} [y/N] ").strip().lower() in {"y", "yes"}


def _remaining(key: KeyInfo | None) -> int | None:
    if key is None or key.free_model_daily_requests is None:
        return None
    return key.free_model_daily_requests.remaining


def _initial_used(config: BenchmarkConfig, key: KeyInfo | None) -> int:
    remaining = _remaining(key)
    if remaining is None:
        return 0
    return config.daily_request_cap - min(config.daily_request_cap, remaining)


def _chat_model_maker(
    settings: Settings, config: BenchmarkConfig, model_id: str, budget: RequestBudget
) -> Callable[[], ChatModel]:
    """Build a maker of chat models sharing one client, limiter and budget."""
    client = AsyncOpenAI(
        base_url=str(settings.openrouter_base_url),
        api_key=settings.require_openrouter_api_key(),
        timeout=config.request_timeout_seconds,
        max_retries=0,
    )
    hook = before_request_hook(MinIntervalLimiter(config.rate_limit_per_minute), budget)

    def make() -> ChatModel:
        return OpenAIChatModel(
            client=client,
            model=model_id,
            temperature=config.temperature,
            max_tokens=config.max_output_tokens,
            seed=config.llm_seed,
            before_request=hook,
        )

    return make


def _real_model_factory(
    settings: Settings, config: BenchmarkConfig, model_id: str, budget: RequestBudget
) -> ModelFactory:
    make = _chat_model_maker(settings, config, model_id, budget)

    def factory(task: ScheduledTask, spec: TaskSpec) -> ChatModel:
        return make()

    return factory


def _print_outcome(outcome: RunOutcome) -> None:
    print(f"Run id: {outcome.run_id}")
    print(f"Output: {outcome.paths.raw}")
    print(
        f"Completed {outcome.completed} tasks; {outcome.infra_errors} infra errors; "
        f"{outcome.requests_sent} requests sent."
    )
    if outcome.halted:
        print(f"HALTED: {outcome.halt_reason}")
        print(f"Resume with: uv run mcp-vs-code-mode run --resume {outcome.run_id}")


def _cmd_plan() -> int:
    config = load_config()
    plan = estimate_requests(build_schedule(config), config)
    print(format_plan(plan, None, config.daily_request_cap))
    for label, count in plan.per_cell.items():
        print(f"  {label}: {count} tasks")
    return 0


async def _cmd_preflight(live: bool) -> int:
    settings = load_settings()
    config = load_config()
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
        factory: Callable[[], ChatModel] | None = None
        if live:
            model_id = settings.require_llm_model()
            factory = _chat_model_maker(
                settings, config, model_id, RequestBudget(config.daily_request_cap)
            )
        results = await run_preflight(
            settings=settings, config=config, http=http, live=live, chat_model_factory=factory
        )
    print(format_report(results))
    return 1 if has_failures(results) else 0


async def _prepare_real(
    settings: Settings, config: BenchmarkConfig, http: httpx.AsyncClient
) -> tuple[str, PricingSnapshot, KeyInfo, OpenRouterClient]:
    model_id = settings.require_llm_model()
    client = OpenRouterClient(
        base_url=str(settings.openrouter_base_url),
        api_key=settings.require_openrouter_api_key(),
        http=http,
    )
    models = await client.list_models()
    pricing = resolve_pricing(model_id, models, config)
    key = await client.key_info()
    return model_id, pricing, key, client


async def _cmd_canary(assume_yes: bool) -> int:
    settings = load_settings()
    config = load_config()
    schedule = build_canary_schedule(config)
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
        checks = await run_preflight(
            settings=settings, config=config, http=http, live=False, chat_model_factory=None
        )
        if has_failures(checks):
            print(format_report(checks))
            print("Preflight failed; fix the failures before the canary.")
            return 1
        model_id, pricing, key, client = await _prepare_real(settings, config, http)
        plan = estimate_requests(schedule, config)
        print("Canary cells: " + ", ".join(t.cell.label for t in schedule))
        print(format_plan(plan, _remaining(key), config.daily_request_cap))
        if not _confirm("Proceed?", assume_yes):
            print("Aborted.")
            return 1
        budget = RequestBudget(config.daily_request_cap, _initial_used(config, key))
        outcome = await run_benchmark(
            kind="canary",
            config=config,
            schedule=schedule,
            model_factory=_real_model_factory(settings, config, model_id, budget),
            pricing=pricing,
            model_id=model_id,
            budget=budget,
            key_info=client.key_info,
        )
    _print_outcome(outcome)
    rows = load_rows(outcome.paths.raw / "tasks.jsonl", TaskRow)
    print("\ntask                  outcome         tokens   calls")
    for row in rows:
        print(f"{row.task_id:<20}  {row.outcome:<14}  {row.total_tokens:>7,}  {row.model_calls:>5}")
    if outcome.halted or any(r.outcome in _CANARY_BAD_OUTCOMES for r in rows):
        print("Canary failed — stop and review before the full run.")
        return 1
    return 0


async def _cmd_run(resume: str | None, assume_yes: bool, allow_dirty: bool) -> int:
    sha, dirty = git_state()
    if dirty and not allow_dirty:
        print(
            "Working tree has uncommitted changes. Commit first so results map to a commit, "
            "or pass --allow-dirty."
        )
        return 1
    settings = load_settings()
    config = load_config()
    schedule = build_schedule(config)
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
        model_id, pricing, key, client = await _prepare_real(settings, config, http)
        if resume is not None:
            paths = RunPaths.find(resume)
            meta = RunMetadata.model_validate_json(
                (paths.raw / "run_metadata.json").read_text(encoding="utf-8")
            )
            pricing = meta.pricing
            model_id = meta.model_id
        print(f"Commit: {sha[:10]}{' (dirty)' if dirty else ''}")
        print(
            format_plan(
                estimate_requests(schedule, config), _remaining(key), config.daily_request_cap
            )
        )
        if not _confirm("Proceed?", assume_yes):
            print("Aborted.")
            return 1
        budget = RequestBudget(config.daily_request_cap, _initial_used(config, key))
        outcome = await run_benchmark(
            kind="full",
            config=config,
            schedule=schedule,
            model_factory=_real_model_factory(settings, config, model_id, budget),
            pricing=pricing,
            model_id=model_id,
            budget=budget,
            key_info=client.key_info,
            run_id=resume,
        )
    _print_outcome(outcome)
    return 1 if outcome.halted else 0


async def _cmd_dry_run(iterations: int | None) -> int:
    config = load_config().with_overrides(iterations=iterations)
    schedule = build_schedule(config)

    def factory(task: ScheduledTask, spec: TaskSpec) -> ChatModel:
        return OracleChatModel(spec, task.cell.mode)

    outcome = await run_benchmark(
        kind="dry-run",
        config=config,
        schedule=schedule,
        model_factory=factory,
        pricing=simulated_pricing(),
        model_id="oracle",
        budget=RequestBudget(10**9),
        key_info=None,
    )
    _print_outcome(outcome)
    print("SIMULATED: no model requests were made; nothing here is a measurement.")
    print()
    _publish(outcome.run_id)
    return 0


def _print_hypotheses(summary: Summary) -> None:
    print(f"{'ID':<4} {'Verdict':<14} Evidence")
    for hyp in summary.hypotheses:
        print(f"{hyp.id:<4} {hyp.verdict:<14} {hyp.evidence}")


def _analyze(run_id: str) -> tuple[RunPaths, Summary]:
    paths = RunPaths.find(run_id)
    summary = summarise(paths)
    write_summary(summary, paths)
    print(f"Summary: {paths.processed / 'summary.json'}")
    print(f"Cells:   {paths.processed / 'cells.csv'}")
    print(f"Compare: {paths.processed / 'comparisons.csv'}")
    _print_hypotheses(summary)
    return paths, summary


def _load_summary(run_id: str) -> tuple[RunPaths, Summary]:
    paths = RunPaths.find(run_id)
    path = paths.processed / "summary.json"
    if not path.exists():
        raise FileNotFoundError(f"No summary for run {run_id!r}; run 'analyze {run_id}' first")
    return paths, Summary.model_validate_json(path.read_text(encoding="utf-8"))


def _charts(paths: RunPaths, summary: Summary) -> list[Path]:
    written = render_all(summary, load_tasks(paths), paths.charts)
    for path in written:
        print(f"Chart:   {path}")
    return written


def _report(paths: RunPaths, summary: Summary, charts: list[Path]) -> Path:
    out = paths.reports / "report.md"
    render_report(summary, charts, out)
    print(f"Report:  {out}")
    return out


def _existing_charts(paths: RunPaths) -> list[Path]:
    return sorted(paths.charts.glob("*.png")) if paths.charts.is_dir() else []


def _linkedin(paths: RunPaths, summary: Summary) -> None:
    for path in render_linkedin(summary, paths.linkedin):
        print(f"LinkedIn: {path}")


def _publish(run_id: str) -> None:
    paths, summary = _analyze(run_id)
    charts = _charts(paths, summary)
    _report(paths, summary, charts)
    _linkedin(paths, summary)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            return _cmd_plan()
        if args.command == "preflight":
            return asyncio.run(_cmd_preflight(args.live))
        if args.command == "canary":
            return asyncio.run(_cmd_canary(args.yes))
        if args.command == "run":
            return asyncio.run(_cmd_run(args.resume, args.yes, args.allow_dirty))
        if args.command == "analyze":
            _analyze(args.run_id)
            return 0
        if args.command == "charts":
            paths, summary = _load_summary(args.run_id)
            _charts(paths, summary)
            return 0
        if args.command == "report":
            paths, summary = _load_summary(args.run_id)
            _report(paths, summary, _existing_charts(paths))
            return 0
        if args.command == "linkedin-assets":
            paths, summary = _load_summary(args.run_id)
            _linkedin(paths, summary)
            return 0
        if args.command == "publish":
            _publish(args.run_id)
            return 0
        return asyncio.run(_cmd_dry_run(args.iterations))
    except (ConfigurationError, PricingError, OpenRouterError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
