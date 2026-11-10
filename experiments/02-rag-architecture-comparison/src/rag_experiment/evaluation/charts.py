"""Static charts (PNG and SVG) drawn from the processed summaries only.

Colours follow one fixed order: blue is the main series, grey marks the neutral or "context miss"
series. Green and red are never used. Simulated runs carry a visible banner on every chart.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from rag_experiment.evaluation.answer_analysis import AnswerSummary
from rag_experiment.evaluation.retrieval_metrics import KS, RetrievalSummary

BLUE = "#2a78d6"
GREY = "#8a8a8a"
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
SERIES = (BLUE, "#eb6834", "#7a4fd0", GREY)
MARKERS = ("o", "s", "^", "D")
BANNER = "SIMULATED: fake model, not a measurement"
FIG_SIZE = (8.0, 5.0)  # inches; at 200 dpi this is 1600 x 1000 pixels
DPI = 200

_RC: dict[str, Any] = {
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID,
    "axes.labelcolor": TEXT_SECONDARY,
    "xtick.color": TEXT_SECONDARY,
    "ytick.color": TEXT_SECONDARY,
    "text.color": TEXT,
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
}


@dataclass(frozen=True)
class ChartContext:
    """What the footnote and banner say."""

    run_id: str
    model_id: str
    simulated: bool
    n_attempts: int


def _figure(
    title: str, subtitle: str | None, ctx: ChartContext, note: str = "", left: float = 0.11
) -> tuple[Figure, Axes]:
    fig = plt.figure(figsize=FIG_SIZE, dpi=DPI)
    ax = fig.add_axes((left, 0.22, 0.95 - left, 0.56))
    if ctx.simulated:
        fig.text(
            0.04,
            0.955,
            BANNER,
            fontsize=8.5,
            fontweight="bold",
            color=TEXT,
            ha="left",
            va="center",
            bbox={"boxstyle": "round,pad=0.3", "fc": "#f1e3b8", "ec": GREY},
        )
    fig.text(0.04, 0.895, title, fontsize=14, fontweight="bold", ha="left", va="center")
    if subtitle:
        fig.text(0.04, 0.845, subtitle, fontsize=9.5, color=TEXT_SECONDARY, ha="left", va="center")
    foot = (
        f"Run {ctx.run_id} | model {ctx.model_id} | n = {ctx.n_attempts} attempts | "
        "Qdrant local mode, CPU"
    )
    if note:
        foot = f"{note}\n{foot}"
    fig.text(0.04, 0.06, foot, fontsize=7, color=TEXT_SECONDARY, ha="left", va="center")
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def _save(fig: Figure, directory: Path, name: str) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / f"{name}.png", directory / f"{name}.svg"]
    for path in paths:
        fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return paths


def _percent(value: float, _: int) -> str:
    return f"{value:.0%}"


def chart_retrieval_hit_at_k(
    retrieval: RetrievalSummary, ctx: ChartContext, directory: Path, source_note: str
) -> list[Path]:
    """Hit@K for the whole set and the three largest category groups."""
    fig, ax = _figure(
        "Retrieval Hit@K (dense retrieval)",
        "Share of answerable questions with a relevant chunk in the top K",
        ctx,
        source_note,
    )
    groups = [("overall", retrieval.overall)]
    largest = sorted(retrieval.by_category.items(), key=lambda item: (-item[1].n, item[0]))[:3]
    groups.extend(largest)
    for index, (name, metrics) in enumerate(groups):
        values = [metrics.hit[k] for k in KS]
        ax.plot(
            KS,
            values,
            color=SERIES[index],
            marker=MARKERS[index],
            linewidth=2,
            markersize=7,
            label=f"{name} (n = {metrics.n})",
        )
    ax.set_xticks(list(KS))
    ax.set_xlabel("K (number of retrieved chunks)")
    ax.set_ylabel("Hit@K (share of questions)")
    ax.set_ylim(0, 1.05)
    ax.yaxis.set_major_formatter(FuncFormatter(_percent))
    ax.legend(frameon=False, loc="lower right", fontsize=8.5)
    return _save(fig, directory, "retrieval_hit_at_k")


def chart_ha3(summary: AnswerSummary, ctx: ChartContext, directory: Path) -> list[Path]:
    """Correctness of answerable attempts, split by whether the context had a relevant chunk."""
    fig, ax = _figure(
        "Answer correctness by context quality",
        "Answerable questions only; correct = every key fact present in the answer text",
        ctx,
    )
    groups = [("context hit", summary.ha3_hit, BLUE), ("context miss", summary.ha3_miss, GREY)]
    for index, (label, ratio, colour) in enumerate(groups):
        value = ratio.value or 0.0
        ax.bar(index, value, width=0.5, color=colour, label=label)
        text = (
            "no attempts"
            if ratio.value is None
            else f"{ratio.numerator}/{ratio.denominator} = {ratio.value:.0%}"
        )
        ax.text(index, value + 0.02, text, ha="center", va="bottom", fontsize=9)
    ax.axhline(0.80, color=TEXT_SECONDARY, linestyle="--", linewidth=1)
    ax.text(1.42, 0.80, "0.80 (hit threshold)", fontsize=8, va="bottom", ha="right")
    ax.axhline(0.20, color=TEXT_SECONDARY, linestyle=":", linewidth=1)
    ax.text(1.42, 0.20, "0.20 (miss threshold)", fontsize=8, va="bottom", ha="right")
    ax.set_xticks([0, 1])
    ax.set_xticklabels([f"{label}\n(n = {ratio.denominator})" for label, ratio, _ in groups])
    ax.set_xlim(-0.6, 1.5)
    ax.set_ylim(0, 1.1)
    ax.set_xlabel("Top-5 context contained a relevant chunk? (attempts)")
    ax.set_ylabel("Share of attempts that were correct")
    ax.yaxis.set_major_formatter(FuncFormatter(_percent))
    return _save(fig, directory, "ha3_correctness_by_context")


def chart_guardrails(summary: AnswerSummary, ctx: ChartContext, directory: Path) -> list[Path]:
    """Refusal behaviour on unanswerable and answerable questions."""
    fig, ax = _figure(
        "Guardrail behaviour",
        "Refusal is the model's structured 'insufficient_context' flag",
        ctx,
        left=0.27,
    )
    g = summary.guardrails
    rows = [
        ("False refusal\n(answerable questions)", g.false_refusal),
        ("Made-up answer\n(unanswerable questions)", g.made_up_answer),
        ("Correct refusal\n(unanswerable questions)", g.correct_refusal),
    ]
    for index, (_, ratio) in enumerate(rows):
        value = ratio.value or 0.0
        ax.barh(index, value, height=0.5, color=BLUE)
        text = (
            "no attempts"
            if ratio.value is None
            else f"{ratio.numerator}/{ratio.denominator} = {ratio.value:.0%}"
        )
        ax.text(value + 0.02, index, text, va="center", fontsize=9)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([label for label, _ in rows])
    ax.set_xlim(0, 1.3)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xlabel("Share of attempts")
    ax.xaxis.set_major_formatter(FuncFormatter(_percent))
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    return _save(fig, directory, "guardrails")


def chart_latency(summary: AnswerSummary, ctx: ChartContext, directory: Path) -> list[Path]:
    """p50 per stage as bars, p95 as a tick."""
    fig, ax = _figure(
        "Latency by stage",
        "Bars show p50, ticks show p95; client-side throttling excluded",
        ctx,
    )
    stages = ("embed", "search", "generation")
    labels = ("Query embedding", "Vector search", "Generation")
    p50 = [summary.latency_ms[s].p50 for s in stages]
    p95 = [summary.latency_ms[s].p95 for s in stages]
    use_log = all(v > 0 for v in p50 + p95)
    ax.bar(range(3), p50, width=0.5, color=BLUE, label="p50")
    ax.scatter(range(3), p95, marker="_", s=900, color=TEXT, linewidths=2, label="p95", zorder=3)
    for index, (a, b) in enumerate(zip(p50, p95, strict=True)):
        ax.annotate(
            f"p50 {a:,.2f} / p95 {b:,.2f}",
            (index, max(a, b)),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    if use_log:
        ax.set_yscale("log")
    ax.set_xticks(range(3))
    ax.set_xticklabels(labels)
    ax.set_xlabel("Pipeline stage")
    ax.set_ylabel("Latency (ms, log scale)" if use_log else "Latency (ms)")
    if not use_log:
        ax.set_ylim(0, max(p95 + p50 + [1e-9]) * 1.3)
    ax.legend(frameon=False, loc="upper right", fontsize=8.5)
    return _save(fig, directory, "latency_by_stage")


def chart_tokens(summary: AnswerSummary, ctx: ChartContext, directory: Path) -> list[Path]:
    """Total tokens per attempt, one box per category."""
    fig, ax = _figure(
        "Tokens per attempt by question category",
        "Total tokens as reported by the provider (prompt + completion)",
        ctx,
        left=0.27,
    )
    categories = [c for c, values in summary.tokens_by_category.items() if values]
    data = [list(summary.tokens_by_category[c]) for c in categories]
    if data:
        ax.boxplot(
            data,
            orientation="horizontal",
            patch_artist=True,
            boxprops={"facecolor": BLUE, "alpha": 0.35, "edgecolor": BLUE},
            medianprops={"color": TEXT, "linewidth": 1.5},
            whiskerprops={"color": GREY},
            capprops={"color": GREY},
            flierprops={"markeredgecolor": GREY, "markersize": 4},
            tick_labels=[f"{c} (n = {len(v)})" for c, v in zip(categories, data, strict=True)],
        )
    ax.invert_yaxis()
    ax.set_xlabel("Total tokens per attempt (tokens)")
    ax.set_ylabel("Question category (attempts)")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    return _save(fig, directory, "tokens_per_question")


def render_all(
    summary: AnswerSummary,
    retrieval: RetrievalSummary | None,
    ctx: ChartContext,
    directory: Path,
    retrieval_note: str = "",
) -> list[Path]:
    """Draw every chart; the retrieval chart is skipped when no retrieval summary is given."""
    paths: list[Path] = []
    with plt.rc_context(cast(Any, _RC)):
        if retrieval is not None:
            paths += chart_retrieval_hit_at_k(retrieval, ctx, directory, retrieval_note)
        paths += chart_ha3(summary, ctx, directory)
        paths += chart_guardrails(summary, ctx, directory)
        paths += chart_latency(summary, ctx, directory)
        paths += chart_tokens(summary, ctx, directory)
    return paths


def chart_names(paths: Sequence[Path]) -> list[str]:
    """The PNG file names among ``paths`` (for linking from the report)."""
    return [p.name for p in paths if p.suffix == ".png"]
