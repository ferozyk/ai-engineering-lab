"""LinkedIn images generated from a processed ``Summary`` (never typed by hand)."""

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

from mcp_vs_code_mode.bench.analysis import CellStats, Summary
from mcp_vs_code_mode.bench.charts import (
    SURFACE,
    TEXT,
    TEXT_SECONDARY,
    add_watermark,
    draw_volume_lines,
    mode_legend,
    style_context,
    title_prefix,
)

REPO_LINK = "github.com/ferozyk/ai-engineering-lab"
LANDSCAPE_NAME = "linkedin-landscape.png"
PORTRAIT_NAME = "linkedin-portrait.png"
_EQUAL_BELOW_PCT = 0.5  # |difference| below this rounds to 0% and is reported as "about the same"


def _largest_comparison(summary: Summary) -> tuple[int, float, int] | None:
    """Return ``(volume, tokens_reduction_pct, n)`` at the largest volume with data."""
    for volume in reversed(summary.volumes):
        comp = summary.comparison("B", volume)
        mcp, code = summary.cell("B", volume, "mcp"), summary.cell("B", volume, "code")
        if comp is not None and comp.tokens_reduction_pct is not None and mcp and code:
            return volume, comp.tokens_reduction_pct, min(mcp.n_measured, code.n_measured)
    return None


def takeaway(summary: Summary) -> str:
    """One sentence stating the measured token difference at the largest volume."""
    found = _largest_comparison(summary)
    if found is None:
        return "No measured token comparison is available for this run."
    volume, reduction, n = found
    prefix = f"At {volume} transactions per account, Code Mode used "
    suffix = f"tokens per task than MCP tool calling (mean of {n} runs)."
    if abs(reduction) < _EQUAL_BELOW_PCT:
        return f"{prefix}about the same number of {suffix.replace(' than', ' as')}"
    if reduction > 0:
        return f"{prefix}{reduction:.0f}% fewer {suffix}"
    return f"{prefix}{-reduction:.0f}% more {suffix}"


def _n_text(summary: Summary) -> str:
    counts = sorted({c.n_measured for c in summary.cells if c.volume is not None})
    if not counts:
        return "n=0 per point"
    return (
        f"n={counts[0]} per point" if len(counts) == 1 else f"n={counts[0]}–{counts[-1]} per point"
    )


def _scenario_a_sentence(summary: Summary) -> str:
    comp = summary.comparison("A", None)
    if comp is None or comp.tokens_reduction_pct is None:
        return "Scenario A (single lookup): no measured token comparison available"
    change = -comp.tokens_reduction_pct
    if abs(change) < _EQUAL_BELOW_PCT:
        return "Scenario A (single lookup): tokens differ by under 1%"
    direction = "more" if change > 0 else "fewer"
    return (
        f"Scenario A (single lookup): tokens differ by {abs(change):.1f}% (Code Mode {direction})"
    )


def _int(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.0f}"


def _sec(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f} s"


def _acc(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _save(fig: Figure, summary: Summary, path: Path) -> None:
    add_watermark(fig, summary)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=100, facecolor=SURFACE)  # no bbox_inches: keeps exact pixel size
    plt.close(fig)


def landscape(summary: Summary, out_dir: Path) -> Path:
    """1200 x 627 px: tokens and p50 latency against volume plus a data-derived takeaway."""
    path = out_dir / LANDSCAPE_NAME
    with style_context():
        fig = plt.figure(figsize=(12, 6.27), dpi=100)
        fig.text(
            0.04, 0.955, f"{title_prefix(summary)}MCP vs Code Mode: tokens and latency as tool "
            "chaining grows", fontsize=17, fontweight="bold", va="top",
        )  # fmt: skip
        fig.text(
            0.04, 0.885, "Mean total tokens and p50 latency per task, by transactions per account",
            fontsize=10.5, color=TEXT_SECONDARY, va="top",
        )  # fmt: skip
        left = fig.add_axes((0.08, 0.31, 0.31, 0.47))
        right = fig.add_axes((0.60, 0.31, 0.31, 0.47))
        if draw_volume_lines(left, summary, lambda c: c.tokens_mean, xlabel=True):
            left.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:,.0f}"))
            mode_legend(left)
        if draw_volume_lines(right, summary, lambda c: c.latency_p50_s, xlabel=True):
            mode_legend(right)
        left.set_title("Mean total tokens per task", loc="left", fontsize=11, color=TEXT)
        right.set_title("p50 latency per task (seconds)", loc="left", fontsize=11, color=TEXT)
        left.set_ylabel("Tokens")
        right.set_ylabel("Seconds")
        fig.text(
            0.04, 0.2, textwrap.fill(takeaway(summary), 82), fontsize=13.5, va="top",
            fontweight="bold",
        )  # fmt: skip
        fig.text(
            0.04, 0.035,
            f"{REPO_LINK}  ·  {summary.model_id}  ·  {_n_text(summary)}  ·  Scenario B  ·  "
            f"run {summary.run_id}",
            fontsize=9, color=TEXT_SECONDARY, va="bottom",
        )  # fmt: skip
        _save(fig, summary, path)
    return path


def _hero(summary: Summary) -> tuple[str, str]:
    found = _largest_comparison(summary)
    if found is None:
        return "n/a", "No measured token comparison is available for this run"
    volume, reduction, _ = found
    where = f"Code Mode at {volume} transactions/account"
    if abs(reduction) < _EQUAL_BELOW_PCT:
        return "0%", f"difference in tokens per task with {where}"
    if reduction > 0:
        return f"{reduction:.0f}%", f"fewer tokens per task with {where}"
    return f"{-reduction:.0f}%", f"more tokens per task with {where}"


def _table_rows(summary: Summary) -> list[list[str]]:
    rows: list[list[str]] = []
    groups: list[tuple[str, int | None]] = [("Scenario A", None)]
    groups.extend((f"B · {v}", v) for v in summary.volumes)
    for label, volume in groups:
        scenario = "A" if volume is None else "B"
        mcp: CellStats | None = summary.cell(scenario, volume, "mcp")
        code: CellStats | None = summary.cell(scenario, volume, "code")
        rows.append(
            [
                label,
                _int(mcp.tokens_mean if mcp else None),
                _int(code.tokens_mean if code else None),
                _sec(mcp.latency_p50_s if mcp else None),
                _sec(code.latency_p50_s if code else None),
                _acc(mcp.accuracy if mcp else None),
                _acc(code.accuracy if code else None),
            ]
        )
    return rows


def portrait(summary: Summary, out_dir: Path) -> Path:
    """1080 x 1350 px summary card: hero number, results table, tokens chart, footer."""
    path = out_dir / PORTRAIT_NAME
    with style_context():
        fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
        fig.text(
            0.06, 0.965, textwrap.fill(
                f"{title_prefix(summary)}MCP vs Code Mode: tokens and latency as tool "
                "chaining grows",
                38,
            ), fontsize=27, fontweight="bold", va="top", linespacing=1.25,
        )  # fmt: skip
        fig.text(
            0.06, 0.885, f"{summary.model_id}  ·  {_n_text(summary)}  ·  run {summary.run_id}",
            fontsize=11.5, color=TEXT_SECONDARY, va="top",
        )  # fmt: skip
        number, caption = _hero(summary)
        fig.text(0.5, 0.835, number, fontsize=100, fontweight="bold", ha="center", va="top")
        fig.text(
            0.5, 0.715, textwrap.fill(caption, 50), fontsize=16, color=TEXT_SECONDARY,
            ha="center", va="top",
        )  # fmt: skip
        _draw_table(fig, summary)
        ax = fig.add_axes((0.11, 0.15, 0.72, 0.25))
        if draw_volume_lines(ax, summary, lambda c: c.tokens_mean):
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:,.0f}"))
            mode_legend(ax)
        ax.set_title("Mean total tokens per task", loc="left", fontsize=12, color=TEXT)
        ax.set_ylabel("Tokens")
        fig.text(
            0.06, 0.085, textwrap.fill(_scenario_a_sentence(summary), 70), fontsize=13.5,
            fontweight="bold", va="top",
        )  # fmt: skip
        fig.text(0.06, 0.03, REPO_LINK, fontsize=12, color=TEXT_SECONDARY, va="bottom")
        _save(fig, summary, path)
    return path


def _draw_table(fig: Figure, summary: Summary) -> None:
    """Compact results table drawn from text so column alignment is exact."""
    header = [
        "",
        "Tokens\nMCP",
        "Tokens\nCode",
        "p50 s\nMCP",
        "p50 s\nCode",
        "Acc.\nMCP",
        "Acc.\nCode",
    ]
    columns = [0.06, 0.27, 0.40, 0.53, 0.66, 0.79, 0.90]  # right edges for numeric columns
    top = 0.64
    for i, (x, text) in enumerate(zip(columns, header, strict=True)):
        fig.text(
            x, top, text, fontsize=10.5, color=TEXT_SECONDARY, va="top",
            ha="left" if i == 0 else "right", fontweight="bold", linespacing=1.2,
        )  # fmt: skip
    line_y = top - 0.036
    fig.add_artist(Line2D([0.06, 0.94], [line_y, line_y], color=TEXT_SECONDARY, linewidth=0.8))
    row_y = line_y - 0.012
    for row in _table_rows(summary):
        for i, (x, text) in enumerate(zip(columns, row, strict=True)):
            fig.text(
                x, row_y, text, fontsize=12, va="top", ha="left" if i == 0 else "right",
                color=TEXT,
            )  # fmt: skip
        row_y -= 0.032


def render_linkedin(summary: Summary, out_dir: Path) -> list[Path]:
    """Write both LinkedIn PNGs into ``out_dir`` and return their paths."""
    return [landscape(summary, out_dir), portrait(summary, out_dir)]
