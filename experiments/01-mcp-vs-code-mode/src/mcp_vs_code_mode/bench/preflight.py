"""Preflight checks run before any real benchmark traffic."""

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import httpx

from ai_lab.config import ConfigurationError, Settings
from mcp_vs_code_mode.agent import (
    ChatModel,
    CodeModeToolset,
    LLMInfraError,
    MCPToolset,
    TaskResult,
    run_task,
)
from mcp_vs_code_mode.agent.fakes import OracleChatModel
from mcp_vs_code_mode.agent.records import Mode
from mcp_vs_code_mode.banking import (
    AuditLog,
    BankingService,
    authenticate_token,
    generate_dataset,
    token_fingerprint,
)
from mcp_vs_code_mode.bench.cells import all_cells, build_schedule
from mcp_vs_code_mode.bench.config import BenchmarkConfig
from mcp_vs_code_mode.bench.metadata import git_state
from mcp_vs_code_mode.bench.openrouter import (
    ModelInfo,
    OpenRouterClient,
    OpenRouterError,
)
from mcp_vs_code_mode.bench.paths import RESULTS_DIR
from mcp_vs_code_mode.bench.plan import estimate_requests
from mcp_vs_code_mode.bench.pricing import PricingError, resolve_pricing
from mcp_vs_code_mode.bench.runner import expected_for, task_spec_for
from mcp_vs_code_mode.code_mode import CodeSandbox, SandboxLimits
from mcp_vs_code_mode.mcp_server import server_parameters
from mcp_vs_code_mode.tools import AGGREGATION_TOOL_SPECS, TOOL_SPECS, ToolExecutor

CheckStatus = Literal["pass", "warn", "fail"]
_CONTEXT_MARGIN = 1.3
_REQUIRED_DAILY_LIMIT = 1000
_MB = 1024 * 1024


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one check; ``detail`` is a single line."""

    name: str
    status: CheckStatus
    detail: str


def _one_line(text: str) -> str:
    return " ".join(text.split())


async def _projected_peak_prompt(config: BenchmarkConfig) -> int:
    """Peak prompt tokens from an offline oracle run of the largest scenario B over MCP."""
    from mcp_vs_code_mode.bench.cells import Cell

    cell = Cell("B", max(config.volumes), "mcp")
    spec = task_spec_for(cell)
    token = secrets.token_urlsafe(24)
    params = server_parameters(
        token=token, trusted={token_fingerprint(token): "rm-001"}, audit_log=None
    )
    async with MCPToolset.open(params, call_timeout=config.mcp_call_timeout_seconds) as toolset:
        result = await run_task(
            task_id="preflight-context",
            task=spec,
            expected=expected_for(generate_dataset(), cell),
            model=OracleChatModel(spec, "mcp"),
            toolset=toolset,
            max_turns=config.max_turns,
        )
    return result.peak_prompt_tokens


async def _mcp_tool_names(config: BenchmarkConfig, *, aggregation: bool = False) -> list[str]:
    token = secrets.token_urlsafe(24)
    params = server_parameters(
        token=token,
        trusted={token_fingerprint(token): "rm-001"},
        audit_log=None,
        aggregation=aggregation,
    )
    mode: Mode = "mcp_agg" if aggregation else "mcp"
    async with MCPToolset.open(
        params, mode=mode, call_timeout=config.mcp_call_timeout_seconds
    ) as toolset:
        return [str(d["function"]["name"]) for d in toolset.tool_definitions()]


async def _sandbox_result(config: BenchmarkConfig) -> TaskResult:
    from mcp_vs_code_mode.bench.cells import Cell

    dataset = generate_dataset()
    token = secrets.token_urlsafe(24)
    trusted = {token_fingerprint(token): "rm-001"}
    executor = ToolExecutor(
        BankingService(dataset, AuditLog()), authenticate_token(token, trusted), "code_mode"
    )
    limits = SandboxLimits(
        max_duration_secs=config.sandbox.max_duration_secs,
        max_memory_bytes=config.sandbox.max_memory_mb * _MB,
        max_host_calls=config.sandbox.max_host_calls,
    )
    cell = Cell("B", min(config.volumes), "code")
    spec = task_spec_for(cell)
    with CodeSandbox(executor, limits) as sandbox:
        return await run_task(
            task_id="preflight-sandbox",
            task=spec,
            expected=expected_for(dataset, cell),
            model=OracleChatModel(spec, "code"),
            toolset=CodeModeToolset(sandbox),
            max_turns=config.max_turns,
        )


def _check_model_facts(
    model_id: str, models: list[ModelInfo], config: BenchmarkConfig
) -> tuple[list[CheckResult], ModelInfo | None]:
    results: list[CheckResult] = []
    info = next((m for m in models if m.id == model_id), None)
    if info is None:
        results.append(
            CheckResult("model_listed", "fail", f"{model_id} is not in the provider's model list")
        )
    else:
        results.append(
            CheckResult("model_listed", "pass", f"{model_id} found ({len(models)} models listed)")
        )
        if "tools" in info.supported_parameters:
            results.append(CheckResult("tool_calling", "pass", "model advertises tool support"))
        else:
            results.append(
                CheckResult("tool_calling", "fail", "'tools' not in supported_parameters")
            )
    try:
        snapshot = resolve_pricing(model_id, models, config)
        results.append(CheckResult("pricing", "pass", snapshot.note))
    except PricingError as exc:
        results.append(CheckResult("pricing", "fail", _one_line(str(exc))))
    return results, info


async def run_preflight(
    *,
    settings: Settings,
    config: BenchmarkConfig,
    http: httpx.AsyncClient,
    live: bool,
    chat_model_factory: Callable[[], ChatModel] | None,
) -> list[CheckResult]:
    """Run all checks in order and return their results."""
    results: list[CheckResult] = []
    api_key: str | None = None
    model_id: str | None = None
    try:
        api_key = settings.require_openrouter_api_key()
        model_id = settings.require_llm_model()
        results.append(CheckResult("config", "pass", "OPENROUTER_API_KEY and LLM_MODEL are set"))
    except ConfigurationError as exc:
        results.append(CheckResult("config", "fail", _one_line(str(exc))))

    client: OpenRouterClient | None = None
    model_info: ModelInfo | None = None
    pricing_result: CheckResult | None = None
    if api_key is not None and model_id is not None:
        client = OpenRouterClient(
            base_url=str(settings.openrouter_base_url), api_key=api_key, http=http
        )
        try:
            models = await client.list_models()
        except OpenRouterError as exc:
            results.append(CheckResult("model_listed", "fail", _one_line(str(exc))))
        else:
            facts, model_info = _check_model_facts(model_id, models, config)
            results.extend(facts[:-1])
            pricing_result = facts[-1]

    # context_window
    try:
        projected = await _projected_peak_prompt(config)
    except Exception as exc:  # report, never crash the preflight
        results.append(CheckResult("context_window", "fail", f"offline oracle run failed: {exc}"))
    else:
        known = [
            v
            for v in (
                model_info.context_length if model_info else None,
                model_info.top_provider_context_length if model_info else None,
            )
            if v is not None
        ]
        label = "estimate (chars/4 from an offline oracle run)"
        if model_info is None:
            results.append(
                CheckResult(
                    "context_window",
                    "warn",
                    f"projected peak prompt {projected:,} tokens, {label}; model unknown",
                )
            )
        elif not known:
            results.append(
                CheckResult(
                    "context_window",
                    "warn",
                    f"model context length unknown; projected peak prompt {projected:,} "
                    f"tokens, {label}",
                )
            )
        else:
            effective = min(known)
            needed = projected * _CONTEXT_MARGIN
            status: CheckStatus = "pass" if effective >= needed else "fail"
            results.append(
                CheckResult(
                    "context_window",
                    status,
                    f"effective context {effective:,} vs projected peak prompt {projected:,} "
                    f"x {_CONTEXT_MARGIN} = {needed:,.0f} tokens; projection is an {label}",
                )
            )

    # max_output
    cap = model_info.top_provider_max_completion_tokens if model_info else None
    if cap is not None and cap < config.max_output_tokens:
        results.append(
            CheckResult(
                "max_output",
                "warn",
                f"provider max completion {cap:,} < configured max_output_tokens "
                f"{config.max_output_tokens:,}",
            )
        )
    else:
        results.append(
            CheckResult(
                "max_output",
                "pass",
                "provider limit not below configured max_output_tokens"
                if cap is not None
                else "provider max completion tokens not reported",
            )
        )

    if pricing_result is not None:
        results.append(pricing_result)

    # key_tier
    if client is not None:
        plan = estimate_requests(build_schedule(config), config)
        try:
            key = await client.key_info()
        except OpenRouterError as exc:
            results.append(CheckResult("key_tier", "fail", _one_line(str(exc))))
        else:
            daily = key.free_model_daily_requests
            if daily is None:
                results.append(
                    CheckResult("key_tier", "warn", "key info does not report free-model counters")
                )
            elif daily.limit < _REQUIRED_DAILY_LIMIT:
                results.append(
                    CheckResult(
                        "key_tier",
                        "fail",
                        f"account allows {daily.limit} free requests/day; the benchmark plan "
                        f"needs about {plan.oracle_requests}",
                    )
                )
            elif daily.remaining < plan.oracle_requests:
                results.append(
                    CheckResult(
                        "key_tier",
                        "warn",
                        f"{daily.remaining} requests remaining today, plan needs about "
                        f"{plan.oracle_requests}; run will need --resume on another day",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        "key_tier",
                        "pass",
                        f"{daily.remaining}/{daily.limit} free requests remaining today",
                    )
                )

    # mcp_server
    try:
        names = await _mcp_tool_names(config)
        expected_names = [spec.name for spec in TOOL_SPECS]
        if names == expected_names:
            results.append(CheckResult("mcp_server", "pass", f"lists {len(names)} tools: {names}"))
        else:
            results.append(CheckResult("mcp_server", "fail", f"unexpected tools: {names}"))
    except Exception as exc:
        results.append(CheckResult("mcp_server", "fail", f"server did not start: {exc}"))

    # mcp_agg_server
    if "mcp_agg" in config.modes:
        try:
            names = await _mcp_tool_names(config, aggregation=True)
            expected_names = [spec.name for spec in AGGREGATION_TOOL_SPECS]
            if names == expected_names:
                results.append(
                    CheckResult("mcp_agg_server", "pass", f"lists {len(names)} tools: {names}")
                )
            else:
                results.append(CheckResult("mcp_agg_server", "fail", f"unexpected tools: {names}"))
        except Exception as exc:
            results.append(CheckResult("mcp_agg_server", "fail", f"server did not start: {exc}"))

    # sandbox
    try:
        sandbox_result = await _sandbox_result(config)
        if sandbox_result.outcome == "correct":
            results.append(CheckResult("sandbox", "pass", "oracle script matches ground truth"))
        else:
            results.append(
                CheckResult("sandbox", "fail", f"oracle outcome {sandbox_result.outcome}")
            )
    except Exception as exc:
        results.append(CheckResult("sandbox", "fail", f"sandbox run failed: {exc}"))

    # ground_truth
    try:
        dataset = generate_dataset()
        cells = all_cells(config)
        for cell in cells:
            expected_for(dataset, cell)
        results.append(CheckResult("ground_truth", "pass", f"computed for {len(cells)} cells"))
    except Exception as exc:
        results.append(CheckResult("ground_truth", "fail", f"ground truth failed: {exc}"))

    # output_dir
    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        probe = RESULTS_DIR / f".preflight-{secrets.token_hex(4)}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        results.append(CheckResult("output_dir", "pass", f"{RESULTS_DIR} is writable"))
    except OSError as exc:
        results.append(CheckResult("output_dir", "fail", f"cannot write results: {exc}"))

    # git_clean
    sha, dirty = git_state()
    if dirty:
        results.append(
            CheckResult(
                "git_clean",
                "warn",
                "working tree has uncommitted changes; commit before the real run so "
                "results map to a commit",
            )
        )
    else:
        results.append(CheckResult("git_clean", "pass", f"clean at {sha[:10]}"))

    if live:
        results.append(await _live_tool_call(chat_model_factory))
    return results


async def _live_tool_call(chat_model_factory: Callable[[], ChatModel] | None) -> CheckResult:
    import json

    if chat_model_factory is None:
        return CheckResult("live_tool_call", "fail", "no chat model available")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "ping",
                "description": "Echo a message.",
                "parameters": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            },
        }
    ]
    messages = [
        {"role": "system", "content": "You are a test."},
        {"role": "user", "content": "Call the ping tool with message set to 'ok'."},
    ]
    started = time.perf_counter()
    try:
        response = await chat_model_factory().complete(messages, tools)
    except LLMInfraError as exc:
        detail = f"provider error kind={exc.kind} status={exc.status_code}"
        if exc.provider_message:
            detail += f": {exc.provider_message}"
        return CheckResult("live_tool_call", "fail", detail)
    elapsed = time.perf_counter() - started
    for call in response.tool_calls:
        if call.name != "ping":
            continue
        try:
            args = json.loads(call.arguments)
        except ValueError:
            break
        if isinstance(args, dict) and "message" in args:
            return CheckResult(
                "live_tool_call",
                "pass",
                f"well-formed tool call; prompt={response.usage.prompt_tokens} "
                f"completion={response.usage.completion_tokens} latency={elapsed:.1f}s",
            )
    return CheckResult("live_tool_call", "fail", "response had no well-formed ping tool call")


def format_report(results: list[CheckResult]) -> str:
    """Render results as a table."""
    width = max((len(r.name) for r in results), default=4)
    lines = [f"{'check'.ljust(width)}  status  detail", f"{'-' * width}  ------  ------"]
    lines.extend(f"{r.name.ljust(width)}  {r.status.upper():<6}  {r.detail}" for r in results)
    failed = sum(1 for r in results if r.status == "fail")
    warned = sum(1 for r in results if r.status == "warn")
    lines.append(f"\n{len(results)} checks: {failed} failed, {warned} warnings")
    return "\n".join(lines)


def has_failures(results: list[CheckResult]) -> bool:
    """True if any check failed."""
    return any(r.status == "fail" for r in results)
