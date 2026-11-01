"""Markdown benchmark report generated from a processed ``Summary``.

Only factual, computed content is generated. Interpretation sections are left as clearly
marked author placeholders.
"""

import os
from collections.abc import Sequence
from pathlib import Path

from mcp_vs_code_mode.bench.analysis import CellStats, Summary
from mcp_vs_code_mode.bench.paths import EXPERIMENT_DIR

RESEARCH_QUESTION = (
    "For an equivalent multi-step tool workflow, how do MCP-based tool calling and Code Mode "
    "differ in context overhead, token consumption, latency, reliability and security posture, "
    "and at what workflow shape and data volume does the difference become material?"
)
KNOWN_LIMITATIONS = (
    "Single model.",
    "Free-tier provider routing adds latency variance.",
    "stdio MCP transport only (no network hop).",
    "n=15 per cell makes p95 close to the sample maximum.",
    "Monty runs a Python subset.",
    "Synthetic data.",
    "Cost is estimated, not billed.",
)
AUTHOR_INTERPRETATION = (
    "> Author interpretation: _pending — to be written after reviewing the results._"
)
NA = "n/a"


def _int(value: float | None) -> str:
    return NA if value is None else f"{value:,.0f}"


def _one(value: float | None) -> str:
    return NA if value is None else f"{value:,.1f}"


def _pct(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return NA
    return f"{value:+,.1f}%" if signed else f"{value:,.1f}%"


def _ratio_pct(value: float | None) -> str:
    return NA if value is None else f"{value * 100:.1f}%"


def _sec(value: float | None) -> str:
    return NA if value is None else f"{value:,.2f} s"


def _usd(value: float | None) -> str:
    return NA if value is None else f"${value:,.4g}"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows]
    return lines


def _scope(volume: int | None) -> str:
    return "Scenario A" if volume is None else f"Scenario B, {volume} transactions per account"


def _executive_bullets(summary: Summary) -> list[str]:
    bullets: list[str] = []
    for comp in summary.comparisons:
        token_change = None if comp.tokens_reduction_pct is None else -comp.tokens_reduction_pct
        parts = [
            f"tokens: Code Mode {_pct(token_change, signed=True)} vs MCP",
            f"p50 latency: Code Mode {_pct(comp.latency_p50_change_pct, signed=True)} vs MCP",
            f"accuracy: MCP {_ratio_pct(comp.accuracy_mcp)}, "
            f"Code Mode {_ratio_pct(comp.accuracy_code)}",
        ]
        bullets.append(f"- **{_scope(comp.volume)}** — " + "; ".join(parts))
    return bullets


def _environment_rows(summary: Summary) -> list[list[str]]:
    meta = summary.metadata
    hardware = ", ".join(f"{k} {v}" for k, v in sorted(meta.hardware.items()))
    packages = ", ".join(f"{k} {v}" for k, v in sorted(meta.package_versions.items()))
    pricing = meta.pricing
    finished = meta.finished_at.isoformat() if meta.finished_at else "not finished"
    return [
        ["Experiment", f"{meta.experiment} {meta.experiment_version}"],
        ["Git commit", f"{meta.git_sha}{' (dirty working tree)' if meta.git_dirty else ''}"],
        ["Started", meta.started_at.isoformat()],
        ["Finished", finished],
        ["Hardware", hardware],
        ["Operating system", meta.os],
        ["Python", meta.python_version],
        ["Provider", meta.provider],
        ["Model id", meta.model_id],
        ["Dataset", f"{meta.dataset_version} (checksum {meta.dataset_checksum})"],
        ["Iterations per cell", str(meta.iterations)],
        ["Failed requests", str(meta.failed_requests)],
        ["Models served", ", ".join(meta.models_served) or NA],
        ["Providers served", ", ".join(meta.providers_served) or NA],
        ["Package versions", packages],
        [
            "Pricing snapshot",
            f"{pricing.source}; priced as {pricing.priced_model}; prompt "
            f"${pricing.prompt_usd_per_token * 1e6:,.4g} / completion "
            f"${pricing.completion_usd_per_token * 1e6:,.4g} per million tokens; "
            f"captured {pricing.captured_at:%Y-%m-%d}",
        ],
        ["MCP connect time", f"{meta.mcp_connect_ms:,.0f} ms (once per run)"],
        ["Sandbox warm-up time", f"{meta.sandbox_warmup_ms:,.0f} ms (once per run)"],
    ]


def _results_rows(cells: Sequence[CellStats]) -> list[list[str]]:
    return [
        [
            f"{c.cell}",
            str(c.n_measured),
            _ratio_pct(c.accuracy),
            _int(c.tokens_mean),
            _sec(c.latency_p50_s),
            _sec(c.latency_p95_s),
            _one(c.model_calls_mean),
            _usd(c.cost_usd_per_1k_tasks),
        ]
        for c in cells
    ]


_CHART_CAPTIONS = {
    "tokens_vs_volume": "Total tokens per task vs transactions per account",
    "latency_vs_volume": "Latency (p50, p95) vs transactions per account",
    "cost_vs_volume": "Estimated cost per 1,000 tasks vs transactions per account",
    "model_calls_vs_volume": "Model calls per task vs transactions per account",
    "scenario_a_parity": "Scenario A: tokens and latency",
    "latency_distribution": "Task latency distribution per cell",
    "accuracy_by_cell": "Accuracy by scenario and volume",
    "token_breakdown": "Input and output tokens per task",
}


def _chart_section(chart_paths: Sequence[Path], out_path: Path) -> list[str]:
    lines: list[str] = []
    pngs = {p.stem: p for p in chart_paths if p.suffix == ".png"}
    for stem, caption in _CHART_CAPTIONS.items():
        png = pngs.get(stem)
        if png is None:
            continue
        rel = Path(os.path.relpath(png, out_path.parent)).as_posix()
        lines += [f"![{caption}]({rel})", "", f"*{caption}.*", ""]
    return lines or ["No charts were generated.", ""]


def _run_limitations(summary: Summary) -> list[str]:
    meta = summary.metadata
    infra_tasks = sum(c.n_infra_error for c in summary.cells)
    items = [
        f"Infrastructure errors (latest record per task): {infra_tasks}; "
        f"infrastructure-error records over the whole run: {meta.infra_errors}. "
        "These tasks are excluded from token, latency and accuracy statistics.",
        f"Failed or retried provider requests: {meta.failed_requests}.",
        f"Records superseded by a later attempt: {summary.superseded_records}; "
        f"warm-up tasks excluded: {summary.excluded_warmup_tasks}.",
        f"Providers served: {len(meta.providers_served)} "
        f"({', '.join(meta.providers_served) or NA}).",
    ]
    if meta.halted:
        items.append(f"The run was halted: {meta.halt_reason}")
    else:
        items.append("The run was not halted.")
    if summary.simulated:
        items.append(
            "This is a simulated run against a scripted oracle model. No model requests were "
            "made and none of the numbers are measurements of any model."
        )
    return items


def _methodology_link(out_path: Path) -> str:
    target = EXPERIMENT_DIR / "benchmarks" / "methodology.md"
    return Path(os.path.relpath(target, out_path.parent)).as_posix()


def render_report(summary: Summary, chart_paths: Sequence[Path], out_path: Path) -> None:
    """Write the Markdown report for ``summary`` to ``out_path``."""
    meta = summary.metadata
    prefix = "SIMULATED — " if summary.simulated else ""
    lines: list[str] = [f"# {prefix}Benchmark report — MCP vs Code Mode ({summary.run_id})", ""]
    if summary.simulated:
        lines += [
            "> **SIMULATED DATA — NOT A RESULT.** Generated from a dry run against a scripted "
            "oracle model to verify the pipeline.",
            "",
        ]

    lines += ["## Executive summary", ""]
    lines += _executive_bullets(summary) or ["No comparisons are available."]
    lines += [
        "",
        "Percentages compare Code Mode with MCP; negative token change means fewer tokens.",
    ]
    lines += ["", AUTHOR_INTERPRETATION, ""]

    lines += ["## Research question", "", RESEARCH_QUESTION, ""]

    cfg = meta.config
    lines += [
        "## Experimental setup",
        "",
        "- Scenario A: single balance lookup. Scenario B: chained aggregation at "
        f"{', '.join(str(v) for v in summary.volumes)} transactions per account.",
        f"- Cells: {len(summary.cells)} (scenario x volume x mode).",
        f"- Iterations per cell: {meta.iterations}; warm-up tasks per mode: "
        f"{cfg.get('warmup_tasks_per_mode', NA)} (excluded from statistics).",
        f"- Maximum model turns per task: {meta.max_turns}.",
        f"- Temperature: {cfg.get('temperature', NA)}.",
        f"- Rate limit: {meta.rate_limit_per_minute} requests per minute; daily request cap "
        f"{meta.daily_request_cap}.",
        f"- Tasks planned: {meta.tasks_planned}; completed: {meta.tasks_completed}.",
        "",
    ]

    lines += ["## Environment", ""]
    lines += [*_table(["Field", "Value"], _environment_rows(summary)), ""]

    lines += [
        "## Methodology",
        "",
        f"Full methodology: [benchmarks/methodology.md]({_methodology_link(out_path)}).",
        "",
        "- Same model, temperature, turn limit, dataset and principal in both modes.",
        "- Cells run interleaved in a seeded shuffled order each iteration.",
        "- Ground truth is computed by plain Python; a task is correct only if every value "
        "matches.",
        "- Token and latency statistics include all tasks with outcome other than `infra_error`; "
        "accuracy uses the same denominator.",
        "- Percentiles use linear interpolation. Latency excludes client-side throttling.",
        "",
    ]

    lines += ["## Results table", ""]
    lines += _table(
        [
            "Cell",
            "n",
            "Accuracy",
            "Mean tokens",
            "p50 latency",
            "p95 latency",
            "Mean model calls",
            "Cost per 1k tasks (est.)",
        ],
        _results_rows(summary.cells),
    )
    lines += ["", f"Cost is estimated, not billed. {meta.pricing.note}.", ""]

    lines += ["## Graphical comparisons", ""]
    lines += _chart_section(chart_paths, out_path)

    lines += ["## Key observations", ""]
    lines += _table(
        ["ID", "Statement", "Verdict", "Evidence"],
        [[h.id, h.statement, h.verdict, h.evidence] for h in summary.hypotheses],
    )
    lines += ["", "> Author interpretation pending.", ""]

    lines += ["## Engineering trade-offs", "", "> Author section — pending.", ""]

    lines += ["## Limitations", ""]
    lines += [f"- {item}" for item in KNOWN_LIMITATIONS]
    lines += [f"- {item}" for item in _run_limitations(summary)]
    lines += [""]

    lines += ["## Conclusion", "", "> Author section — pending.", ""]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
