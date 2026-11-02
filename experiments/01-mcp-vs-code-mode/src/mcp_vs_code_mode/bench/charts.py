"""Static charts (PNG + SVG) generated from a processed ``Summary``.

Palette: MCP (raw tools) is blue with circle markers, MCP + aggregation tool is green with
triangle markers, Code Mode is orange with square markers. The green is below 3:1 contrast on
the surface, so direct end-of-line labels and distinct marker shapes are always drawn as well.
"""

import textwrap
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator

from mcp_vs_code_mode.agent.records import Mode
from mcp_vs_code_mode.bench.analysis import CellStats, Summary, mode_label

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
SPINE = "#c9c8c2"
MCP_COLOR = "#2a78d6"
AGG_COLOR = "#1baf7a"
CODE_COLOR = "#eb6834"
WATERMARK = "SIMULATED DATA — NOT A RESULT"
MODES: tuple[Mode, ...] = ("mcp", "mcp_agg", "code")
MODE_COLOR: dict[str, str] = {"mcp": MCP_COLOR, "mcp_agg": AGG_COLOR, "code": CODE_COLOR}
MODE_MARKER: dict[str, str] = {"mcp": "o", "mcp_agg": "^", "code": "s"}
LINE_WIDTH = 2.0
MARKER_SIZE = 8
BAND_ALPHA = 0.15
MIN_LABEL_GAP = 0.075  # minimum vertical gap between direct labels, in axes fraction
BAR_GROUP_WIDTH = 0.8  # total width of a group of bars, in x units
MINUS = "−"

_RC: dict[str, Any] = {
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": SPINE,
    "axes.labelcolor": TEXT_SECONDARY,
    "xtick.color": TEXT_SECONDARY,
    "ytick.color": TEXT_SECONDARY,
    "text.color": TEXT,
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": False,
    "svg.fonttype": "none",
}


def style_context() -> AbstractContextManager[None]:
    """The matplotlib rc context shared by every figure."""
    return plt.rc_context(cast("dict[Any, Any]", _RC))


# --------------------------------------------------------------------------- shared helpers


def title_prefix(summary: Summary) -> str:
    """``"SIMULATED — "`` for simulated runs, else an empty string."""
    return "SIMULATED — " if summary.simulated else ""


def add_watermark(fig: Figure, summary: Summary) -> None:
    """Diagonal watermark across the figure for simulated runs."""
    if not summary.simulated:
        return
    width_in = fig.get_figwidth()
    fig.text(
        0.5,
        0.5,
        WATERMARK,
        rotation=28,
        fontsize=3.2 * width_in,
        fontweight="bold",
        color="#7a7974",
        alpha=0.18,
        ha="center",
        va="center",
        zorder=100,
    )


def style_axes(ax: Axes) -> None:
    """Horizontal solid grid behind the data, light left/bottom spines."""
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, linestyle="-")
    ax.xaxis.grid(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(SPINE)
    ax.tick_params(axis="both", length=3, labelsize=9)


def thousands(ax: Axes) -> None:
    """Thousands separators on the y axis."""
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v:,.0f}"))


def volume_axis(ax: Axes, volumes: Sequence[int], *, label: bool = True) -> None:
    """Log x axis with ticks exactly at the benchmark volumes present in the data."""
    ticks = sorted(volumes) or [10, 200]
    ax.set_xscale("log")
    ax.set_xticks(ticks, labels=[str(v) for v in ticks])
    ax.minorticks_off()
    ax.set_xlim(ticks[0] * 0.7, ticks[-1] * 1.45)
    if label:
        ax.set_xlabel("Transactions per account (log scale)")


def n_label(cells: Sequence[CellStats | None]) -> str:
    """``n=10 per point`` (or a range when cells differ)."""
    counts = sorted({c.n_measured for c in cells if c is not None})
    if not counts:
        return "n=0 per point"
    if len(counts) == 1:
        return f"n={counts[0]} per point"
    return f"n={counts[0]}–{counts[-1]} per point"


SCENARIO_TITLES = {
    "A": "Single lookup (one account balance)",
    "B": "Chained task (4 accounts: balance, spend by category, large debits)",
    "C": "Unanticipated query (top merchants, weekend debits)",
}
# Subtitle variant: the full chained title nearly fills the figure width.
_SUBTITLE_TITLES = {**SCENARIO_TITLES, "B": "Chained task (4 accounts)"}


def group_label(scenario: str, volume: int | None, *, multiline: bool = False) -> str:
    """Reader-facing label for a scenario/volume group."""
    if scenario == "A" or volume is None:
        return "Single lookup"
    sep = "\n" if multiline else " · "
    name = "Unanticipated query" if scenario == "C" else "Chained"
    return f"{name}{sep}{volume} tx/account"


def subtitle_text(summary: Summary, scenario: str, cells: Sequence[CellStats | None]) -> str:
    """Subtitle line: scenario, model id, sample size and run id."""
    return (
        f"{_SUBTITLE_TITLES[scenario]} · {summary.model_id} · {n_label(cells)} · "
        f"run {summary.run_id}"
    )


def add_header(
    fig: Figure, summary: Summary, title: str, subtitle: str, *, top: float = 0.965
) -> None:
    """Title (13 pt) and subtitle (9.5 pt), left aligned at the figure's left margin."""
    fig.text(0.04, top, f"{title_prefix(summary)}{title}", fontsize=13, fontweight="bold", va="top")
    fig.text(0.04, top - 0.055, subtitle, fontsize=9.5, color=TEXT_SECONDARY, va="top")


def add_footnote(fig: Figure, text: str, *, wrap: int = 150) -> None:
    """Footnote (8 pt, secondary) at the bottom-left."""
    fig.text(
        0.04,
        0.015,
        textwrap.fill(text, wrap),
        fontsize=8,
        color=TEXT_SECONDARY,
        va="bottom",
    )


def no_data(ax: Axes, message: str = "No data") -> None:
    """Visible placeholder for an axes without data."""
    ax.text(
        0.5, 0.5, message, transform=ax.transAxes, ha="center", va="center",
        fontsize=12, color=TEXT_SECONDARY,
    )  # fmt: skip


def scenario_modes(summary: Summary, scenario: str) -> list[Mode]:
    """Modes that have a cell in ``scenario``, in canonical order."""
    present = {c.mode for c in summary.cells if c.scenario == scenario}
    return [m for m in MODES if m in present]


def mode_legend(
    ax: Axes,
    summary: Summary,
    modes: Sequence[str] | None = None,
    *,
    loc: Any = "best",
    **kwargs: Any,
) -> None:
    """Legend with a marker per mode (frameless)."""
    handles = [
        Line2D(
            [],
            [],
            color=MODE_COLOR[m],
            marker=MODE_MARKER[m],
            markersize=7,
            linewidth=LINE_WIDTH,
            label=mode_label(m, summary),
        )
        for m in (modes if modes is not None else scenario_modes(summary, "B"))
    ]
    ax.legend(handles=handles, loc=loc, frameon=False, fontsize=9, **kwargs)


def spread_positions(
    ys: Sequence[float], gap: float, low: float = 0.03, high: float = 0.97
) -> list[float]:
    """Push sorted label positions apart so neighbours are at least ``gap`` apart.

    Positions are axes fractions in the same order as ``ys`` (ascending). The group is centred
    on its original mean, then clamped into ``[low, high]``.
    """
    n = len(ys)
    if n == 0:
        return []
    out = list(ys)
    for _ in range(50):
        moved = False
        for i in range(1, n):
            deficit = gap - (out[i] - out[i - 1])
            if deficit > 1e-9:
                out[i - 1] -= deficit / 2
                out[i] += deficit / 2
                moved = True
        if not moved:
            break
    shift = 0.0
    if out[0] < low:
        shift = low - out[0]
    elif out[-1] > high:
        shift = high - out[-1]
    return [y + shift for y in out]


def end_labels(ax: Axes, items: Sequence[tuple[float, str]], summary: Summary) -> None:
    """Direct labels right of the axes for each (y data, mode); nudged apart if they would touch.

    Labels use the primary text colour next to a small marker in the series colour.
    """
    if not items:
        return
    placed: list[tuple[float, str]] = []
    for y_data, mode in items:
        _, y_disp = ax.transData.transform((ax.get_xlim()[0], y_data))
        _, y_axes = ax.transAxes.inverted().transform((0.0, y_disp))
        placed.append((float(y_axes), mode))
    placed.sort(key=lambda item: item[0])
    ys = spread_positions([y for y, _ in placed], MIN_LABEL_GAP)
    for y, (_, mode) in zip(ys, placed, strict=True):
        ax.plot(
            [1.02],
            [y],
            transform=ax.transAxes,
            marker=MODE_MARKER[mode],
            color=MODE_COLOR[mode],
            markersize=7,
            linestyle="none",
            clip_on=False,
        )
        ax.text(
            1.045,
            y,
            mode_label(mode, summary),
            transform=ax.transAxes,
            va="center",
            ha="left",
            fontsize=9,
            color=TEXT,
        )


def any_truncated(summary: Summary) -> bool:
    """Whether any Scenario B cell has tasks cut off at the output limit."""
    return any(c.n_truncated > 0 for c in summary.cells if c.volume is not None)


def output_limit(summary: Summary) -> int | None:
    """Configured ``max_output_tokens`` of the run, when recorded."""
    value = summary.metadata.config.get("max_output_tokens")
    return int(value) if isinstance(value, int | float) else None


def truncation_footnote(summary: Summary) -> str:
    """Footnote sentence explaining hollow markers (empty when nothing was cut off)."""
    if not any_truncated(summary):
        return ""
    limit = output_limit(summary)
    where = f"the {limit:,}-token output limit" if limit is not None else "the output limit"
    return (
        f" Hollow marker: some or all tasks were cut off at {where} before answering; "
        "their tokens are included and are a lower bound."
    )


def cut_off_text(cell: CellStats) -> str:
    """Annotation text for a cell with truncated tasks."""
    return f"{cell.n_truncated}/{cell.n_measured} cut off at output limit"


def _mark_truncated(
    ax: Axes, cells: Sequence[CellStats], getter: Callable[[CellStats], float | None], mode: str
) -> None:
    """Hollow marker plus a small note on every point whose cell has truncated tasks."""
    color, marker = MODE_COLOR[mode], MODE_MARKER[mode]
    for cell in cells:
        value = getter(cell)
        if cell.n_truncated <= 0 or value is None or cell.volume is None:
            continue
        ax.plot(
            [cell.volume], [value], color=color, marker=marker, markersize=MARKER_SIZE,
            markerfacecolor="white", markeredgecolor=color, markeredgewidth=1.8,
            linestyle="none", zorder=4,
        )  # fmt: skip
        frac = float(
            ax.transAxes.inverted().transform(ax.transData.transform((cell.volume, value)))[1]
        )
        if mode in ("mcp", "mcp_agg"):
            near_edge = frac > 0.8  # no room above: put the note left of the point instead
            offset, va = ((-10, 0), "center") if near_edge else ((-8, 9), "bottom")
        else:
            near_edge = frac < 0.2  # no room below: put the note above
            offset, va = ((-8, 9), "bottom") if near_edge else ((-8, -9), "top")
        ax.annotate(
            cut_off_text(cell), xy=(cell.volume, value), xytext=offset,
            textcoords="offset points", ha="right", va=va, fontsize=7.5, color=TEXT_SECONDARY,
            zorder=6,
        )  # fmt: skip


def _series(summary: Summary, mode: str) -> list[CellStats]:
    cells = [summary.cell("B", v, mode) for v in summary.volumes]
    return [c for c in cells if c is not None]


def _points(
    cells: Sequence[CellStats], getter: Callable[[CellStats], float | None]
) -> tuple[list[int], list[float]]:
    xs: list[int] = []
    ys: list[float] = []
    for cell in cells:
        value = getter(cell)
        if value is not None and cell.volume is not None:
            xs.append(cell.volume)
            ys.append(value)
    return xs, ys


def draw_volume_lines(
    ax: Axes,
    summary: Summary,
    getter: Callable[[CellStats], float | None],
    *,
    band: tuple[Callable[[CellStats], float | None], Callable[[CellStats], float | None]]
    | None = None,
    hollow: Callable[[CellStats], float | None] | None = None,
    integer_ticks: bool = False,
    xlabel: bool = True,
) -> bool:
    """Draw one line per mode against volume. Returns ``False`` if there is nothing to plot."""
    style_axes(ax)
    volume_axis(ax, summary.volumes, label=xlabel)
    any_data = False
    end_points: list[tuple[float, str]] = []
    for mode in scenario_modes(summary, "B"):
        cells = _series(summary, mode)
        xs, ys = _points(cells, getter)
        if not xs:
            continue
        any_data = True
        color, marker = MODE_COLOR[mode], MODE_MARKER[mode]
        if band is not None:
            bx, lows = _points(cells, band[0])
            hx, highs = _points(cells, band[1])
            if bx == hx and bx:
                ax.fill_between(bx, lows, highs, color=color, alpha=BAND_ALPHA, linewidth=0)
        ax.plot(
            xs,
            ys,
            color=color,
            marker=marker,
            linewidth=LINE_WIDTH,
            markersize=MARKER_SIZE,
            zorder=3,
            label=mode_label(mode, summary),
        )
        if hollow is not None:
            px, py = _points(cells, hollow)
            if px:
                # Secondary statistic (e.g. p95): a short horizontal tick, so hollow
                # markers stay reserved for "cut off at the output limit".
                ax.plot(
                    px, py, color=color, marker="_", markersize=MARKER_SIZE * 2,
                    markeredgewidth=2.4, linestyle="none", zorder=3,
                )  # fmt: skip
        end_points.append((ys[-1], mode))
    if not any_data:
        no_data(ax)
        return False
    ax.set_ylim(bottom=0)
    ax.margins(y=0.08)
    ax.set_ylim(bottom=0)
    if integer_ticks:
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.figure.canvas.draw()
    for mode in scenario_modes(summary, "B"):
        _mark_truncated(ax, _series(summary, mode), getter, mode)
    end_labels(ax, end_points, summary)
    return True


# --------------------------------------------------------------------------- figure plumbing


def _new_figure(
    summary: Summary, title: str, subtitle: str, footnote: str, *, top_margin: float = 0.82
) -> tuple[Figure, Axes]:
    fig = plt.figure(figsize=(10, 6))
    ax = fig.add_axes((0.09, 0.17, 0.78, top_margin - 0.17))
    add_header(fig, summary, title, subtitle)
    add_footnote(fig, footnote)
    return fig, ax


def _save(fig: Figure, summary: Summary, out_dir: Path, stem: str) -> list[Path]:
    add_watermark(fig, summary)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for suffix in ("png", "svg"):
        path = out_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=200, bbox_inches="tight")
        written.append(path)
    plt.close(fig)
    return written


def _all_b_cells(summary: Summary) -> list[CellStats | None]:
    return [summary.cell("B", v, m) for v in summary.volumes for m in scenario_modes(summary, "B")]


def _annotate_gaps(ax: Axes, summary: Summary) -> None:
    """Annotate Code Mode's token change against each other mode, between the lines."""
    modes = scenario_modes(summary, "B")
    others = [m for m in modes if m != "code"]
    for volume in summary.volumes:
        code = summary.cell("B", volume, "code")
        if code is None or code.tokens_mean is None:
            continue
        for other in others:
            comp = summary.comparison("B", volume, other, "code")
            base = summary.cell("B", volume, other)
            if (
                comp is None
                or comp.tokens_reduction_pct is None
                or base is None
                or base.tokens_mean is None
            ):
                continue
            change = -comp.tokens_reduction_pct
            text = f"{MINUS if change < 0 else '+'}{abs(change):.0f}%"
            if len(others) > 1:
                text += " vs " + ("MCP" if other == "mcp" else "agg. tool")
            ax.plot(
                [volume, volume],
                [code.tokens_mean, base.tokens_mean],
                color=TEXT_SECONDARY,
                linewidth=0.8,
                zorder=2,
            )
            first = volume == summary.volumes[0]
            if first and len(others) > 1:
                # Narrow gaps at the smallest volume: anchor each label at its own marker.
                anchor = base.tokens_mean if other == "mcp" else code.tokens_mean
                offset, align = ((9, -9) if other == "mcp" else (9, -15)), "left"
            else:
                anchor = (base.tokens_mean + code.tokens_mean) / 2
                offset, align = (-7, 0), "right"
            ax.annotate(
                text,
                xy=(volume, anchor),
                xytext=offset,
                textcoords="offset points",
                ha=align,
                va="center",
                fontsize=9,
                color=TEXT_SECONDARY,
                bbox={"boxstyle": "round,pad=0.2", "fc": SURFACE, "ec": "none", "alpha": 0.9},
                zorder=5,
            )


# --------------------------------------------------------------------------- charts


def tokens_vs_volume(summary: Summary, out_dir: Path) -> list[Path]:
    """Mean total tokens per task against volume, with min-max bands."""
    fig, ax = _new_figure(
        summary,
        "Total tokens per task vs transactions per account",
        subtitle_text(summary, "B", _all_b_cells(summary)),
        "Measured (provider-reported usage). Line = mean per cell; band = min to max; "
        "labels between the lines = Code Mode tokens relative to the other mode (mean)."
        + truncation_footnote(summary),
    )
    if draw_volume_lines(
        ax, summary, lambda c: c.tokens_mean, band=(lambda c: c.tokens_min, lambda c: c.tokens_max)
    ):
        thousands(ax)
        _annotate_gaps(ax, summary)
        mode_legend(ax, summary)
    ax.set_ylabel("Mean total tokens per task")
    return _save(fig, summary, out_dir, "tokens_vs_volume")


def _sample_size(summary: Summary) -> str:
    """Sample size per Scenario B cell: ``10`` or a range when cells differ."""
    counts = sorted({c.n_measured for c in summary.cells if c.volume is not None})
    if not counts:
        return "0"
    return str(counts[0]) if len(counts) == 1 else f"{counts[0]}–{counts[-1]}"


def latency_vs_volume(summary: Summary, out_dir: Path) -> list[Path]:
    """p50 latency (line) and p95 (tick marks) against volume."""
    fig, ax = _new_figure(
        summary,
        "Task latency vs transactions per account",
        subtitle_text(summary, "B", _all_b_cells(summary)),
        "Measured wall-clock latency; excludes client-side throttling. Line = p50; "
        f"horizontal ticks = p95 (with n={_sample_size(summary)}, close to the sample maximum)."
        + truncation_footnote(summary),
    )
    if draw_volume_lines(ax, summary, lambda c: c.latency_p50_s, hollow=lambda c: c.latency_p95_s):
        mode_legend(ax, summary)
    ax.set_ylabel("Latency per task (seconds)")
    return _save(fig, summary, out_dir, "latency_vs_volume")


def cost_vs_volume(summary: Summary, out_dir: Path) -> list[Path]:
    """Estimated USD per 1,000 tasks against volume."""
    fig, ax = _new_figure(
        summary,
        "Estimated cost per 1,000 tasks vs transactions per account",
        subtitle_text(summary, "B", _all_b_cells(summary)),
        f"Estimated, not billed. {summary.metadata.pricing.note}." + truncation_footnote(summary),
    )
    if draw_volume_lines(ax, summary, lambda c: c.cost_usd_per_1k_tasks):
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"${v:,.4g}"))
        mode_legend(ax, summary)
    ax.set_ylabel("Estimated cost per 1,000 tasks (USD)")
    return _save(fig, summary, out_dir, "cost_vs_volume")


def model_calls_vs_volume(summary: Summary, out_dir: Path) -> list[Path]:
    """Mean model calls (round trips) per task against volume."""
    fig, ax = _new_figure(
        summary,
        "Model calls per task vs transactions per account",
        subtitle_text(summary, "B", _all_b_cells(summary)),
        "Measured. Each model call is one request to the provider within a task.",
    )
    if draw_volume_lines(ax, summary, lambda c: c.model_calls_mean, integer_ticks=True):
        mode_legend(ax, summary)
    ax.set_ylabel("Mean model calls per task")
    return _save(fig, summary, out_dir, "model_calls_vs_volume")


def _bar_positions(count: int, width: float = BAR_GROUP_WIDTH) -> tuple[list[float], float]:
    """Offsets of ``count`` bars centred on a group position, and the width of each bar."""
    bar = width / max(count, 1)
    return [(i - (count - 1) / 2) * bar for i in range(count)], bar * 0.95


def _bar_panel(
    ax: Axes,
    summary: Summary,
    values: dict[str, float | None],
    formatter: Callable[[float], str],
    ylabel: str,
    title: str,
) -> None:
    style_axes(ax)
    ax.set_title(title, loc="left", fontsize=10.5, color=TEXT)
    present = [v for v in values.values() if v is not None]
    if not present:
        no_data(ax)
        return
    modes = list(values)
    for index, mode in enumerate(modes):
        value = values[mode]
        if value is None:
            continue
        ax.bar(index, value, width=0.55, color=MODE_COLOR[mode], zorder=3)
        ax.annotate(
            formatter(value),
            xy=(index, value),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=10,
            color=TEXT,
        )
    ax.set_xticks(
        range(len(modes)),
        labels=[textwrap.fill(mode_label(m, summary), 14) for m in modes],
        fontsize=8.5,
    )
    ax.set_xlim(-0.6, len(modes) - 0.4)
    ax.set_ylim(0, max(present) * 1.18)
    ax.set_ylabel(ylabel)


def _seconds_label(value: float) -> str:
    """Seconds with 2 decimals; sub-100 ms values are shown in milliseconds to stay legible."""
    return f"{value:.2f} s" if value >= 0.1 else f"{value * 1000:.1f} ms"


def _mode_patches(summary: Summary, modes: Sequence[str]) -> list[Patch]:
    return [Patch(facecolor=MODE_COLOR[m], label=mode_label(m, summary)) for m in modes]


def scenario_a_parity(summary: Summary, out_dir: Path) -> list[Path]:
    """Scenario A: mean tokens and p50 latency for every mode (two separate panels)."""
    modes = scenario_modes(summary, "A")
    cells = [summary.cell("A", None, m) for m in modes]
    fig = plt.figure(figsize=(10, 6))
    left = fig.add_axes((0.09, 0.17, 0.36, 0.60))
    right = fig.add_axes((0.57, 0.17, 0.36, 0.60))
    add_header(
        fig, summary, "Simple lookup: tokens and latency per task",
        subtitle_text(summary, "A", cells),
    )  # fmt: skip
    add_footnote(
        fig,
        "Measured. Each panel has its own y axis. Latency is p50 wall-clock time and excludes "
        "client-side throttling.",
    )
    _bar_panel(
        left,
        summary,
        {m: (c.tokens_mean if c else None) for m, c in zip(modes, cells, strict=True)},
        lambda v: f"{v:,.0f}",
        "Mean total tokens per task",
        "Tokens",
    )
    thousands(left)
    _bar_panel(
        right,
        summary,
        {m: (c.latency_p50_s if c else None) for m, c in zip(modes, cells, strict=True)},
        _seconds_label,
        "p50 latency per task (seconds)",
        "Latency",
    )
    fig.legend(
        handles=_mode_patches(summary, modes), loc="upper right", bbox_to_anchor=(0.96, 0.985),
        frameon=False, fontsize=9, ncols=len(modes),
    )  # fmt: skip
    return _save(fig, summary, out_dir, "scenario_a_parity")


def _groups(summary: Summary) -> list[tuple[str, str, int | None]]:
    groups: list[tuple[str, str, int | None]] = [
        ("A", group_label("A", None, multiline=True), None)
    ]
    groups.extend(("B", group_label("B", v, multiline=True), v) for v in summary.volumes)
    groups.extend(("C", group_label("C", v, multiline=True), v) for v in summary.c_volumes)
    return groups


def _group_modes(summary: Summary, scenario: str, volume: int | None) -> list[Mode]:
    """Modes that have a cell in one scenario/volume group."""
    return [m for m in MODES if summary.cell(scenario, volume, m) is not None]


def _scope_text(summary: Summary) -> str:
    """``Single lookup and chained task`` plus the unanticipated query when it is in the run."""
    if summary.c_volumes:
        return "Single lookup, chained task and unanticipated query"
    return "Single lookup and chained task"


def latency_distribution(summary: Summary, tasks: pd.DataFrame, out_dir: Path) -> list[Path]:
    """Box plots of task latency per cell, grouped by scenario and volume."""
    cells = [
        summary.cell(s, v, m) for s, _, v in _groups(summary) for m in _group_modes(summary, s, v)
    ]
    fig, ax = _new_figure(
        summary,
        "Task latency distribution per cell",
        f"{_scope_text(summary)} · {summary.model_id} · {n_label(cells)} · run {summary.run_id}",
        "Measured. Box = interquartile range, line = median, whiskers = 1.5 x IQR; outliers "
        "not drawn. Latency excludes client-side throttling.",
    )
    style_axes(ax)
    drawn = False
    groups = _groups(summary)
    for index, (scenario, _, volume) in enumerate(groups):
        modes = _group_modes(summary, scenario, volume)
        shifts, bar = _bar_positions(len(modes))
        for mode, shift in zip(modes, shifts, strict=True):
            label = f"{scenario}{volume if volume is not None else ''}:{mode}"
            if tasks.empty:
                continue
            subset = tasks[(tasks["cell"] == label) & (tasks["outcome"] != "infra_error")]
            if subset.empty:
                continue
            values = (subset["latency_ms"] / 1000).to_numpy(dtype=float)
            box = ax.boxplot(
                [values], positions=[index + shift], widths=bar * 0.9, patch_artist=True,
                showfliers=False, manage_ticks=False,
                medianprops={"color": TEXT, "linewidth": 1.6},
                whiskerprops={"color": MODE_COLOR[mode], "linewidth": 1.2},
                capprops={"color": MODE_COLOR[mode], "linewidth": 1.2},
                boxprops={"edgecolor": MODE_COLOR[mode], "linewidth": 1.4},
            )  # fmt: skip
            box["boxes"][0].set_facecolor(MODE_COLOR[mode])
            box["boxes"][0].set_alpha(0.35)
            drawn = True
    if drawn:
        ax.set_xticks(range(len(groups)), labels=[g[1] for g in groups])
        ax.set_xlim(-0.6, len(groups) - 0.4)
        ax.set_ylim(bottom=0)
        ax.set_xlabel("Task type · transactions per account")
        ax.set_ylabel("Latency per task (seconds)")
        ax.legend(
            handles=_mode_patches(summary, summary.modes),
            loc="upper left", frameon=False, fontsize=9,
        )  # fmt: skip
    else:
        no_data(ax)
    return _save(fig, summary, out_dir, "latency_distribution")


def accuracy_by_cell(summary: Summary, out_dir: Path) -> list[Path]:
    """Grouped bars: accuracy (% correct of measured tasks) per scenario/volume and mode."""
    groups = _groups(summary)
    cells = [summary.cell(s, v, m) for s, _, v in groups for m in _group_modes(summary, s, v)]
    fig, ax = _new_figure(
        summary,
        "Accuracy by scenario and volume",
        f"{_scope_text(summary)} · {summary.model_id} · {n_label(cells)} · run {summary.run_id}",
        "Measured. Accuracy = correct answers / measured tasks (tasks with an infrastructure "
        "error are excluded and reported separately)."
        + (
            " Tasks cut off at the output limit count as incorrect."
            if any_truncated(summary)
            else ""
        ),
    )
    style_axes(ax)
    drawn = False
    for index, (scenario, _, volume) in enumerate(groups):
        modes = _group_modes(summary, scenario, volume)
        shifts, width = _bar_positions(len(modes))
        for mode, shift in zip(modes, shifts, strict=True):
            cell = summary.cell(scenario, volume, mode)
            if cell is None or cell.accuracy is None:
                continue
            drawn = True
            value = cell.accuracy * 100
            ax.bar(index + shift, value, width=width, color=MODE_COLOR[mode], zorder=3)
            ax.annotate(
                f"{value:.1f}%", xy=(index + shift, value), xytext=(0, 4),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=9 if len(modes) < 3 else 7.5, color=TEXT,
            )  # fmt: skip
            if cell.n_truncated > 0:
                ax.annotate(
                    f"{cell.n_truncated} cut off", xy=(index + shift, value), xytext=(0, 16),
                    textcoords="offset points", ha="center", va="bottom", fontsize=7.5,
                    color=TEXT_SECONDARY,
                )  # fmt: skip
    if drawn:
        ax.set_xticks(range(len(groups)), labels=[g[1] for g in groups])
        ax.set_xlim(-0.6, len(groups) - 0.4)
        ax.set_ylim(0, 125)
        ax.set_yticks([0, 20, 40, 60, 80, 100])
        ax.set_xlabel("Task type · transactions per account")
        ax.set_ylabel("Accuracy (% of measured tasks correct)")
        ax.legend(
            handles=_mode_patches(summary, summary.modes),
            loc="upper left", frameon=False, fontsize=9, ncols=len(summary.modes),
        )  # fmt: skip
    else:
        no_data(ax)
    return _save(fig, summary, out_dir, "accuracy_by_cell")


def token_breakdown(summary: Summary, out_dir: Path) -> list[Path]:
    """Mean input vs output tokens per task for Scenario A and the largest Scenario B volume."""
    volumes = summary.volumes
    largest = volumes[-1] if volumes else None
    panels: list[tuple[str, str, int | None]] = [("A", group_label("A", None), None)]
    if largest is not None:
        panels.append(("B", group_label("B", largest), largest))
    cells = [summary.cell(s, v, m) for s, _, v in panels for m in _group_modes(summary, s, v)]
    subtitle_scope = "Single lookup and chained task"
    if largest is not None:
        subtitle_scope += f" ({largest} tx/account)"
    fig = plt.figure(figsize=(10, 6))
    axes = [fig.add_axes((0.09 + 0.47 * i, 0.17, 0.36, 0.60)) for i in range(len(panels))]
    add_header(
        fig, summary, "Input and output tokens per task",
        f"{subtitle_scope} · {summary.model_id} · {n_label(cells)} · "
        f"run {summary.run_id}",
    )  # fmt: skip
    add_footnote(
        fig,
        "Measured (provider-reported usage). Output tokens include reasoning tokens when the "
        "provider reports them. Each panel has its own y axis.",
    )
    for ax, (scenario, name, volume) in zip(axes, panels, strict=True):
        style_axes(ax)
        ax.set_title(name, loc="left", fontsize=10.5, color=TEXT)
        modes = _group_modes(summary, scenario, volume)
        shifts, width = _bar_positions(len(modes))
        values: list[float] = []
        for index, kind in enumerate(("input", "output")):
            for mode, shift in zip(modes, shifts, strict=True):
                cell = summary.cell(scenario, volume, mode)
                value = None
                if cell is not None:
                    value = cell.input_tokens_mean if kind == "input" else cell.output_tokens_mean
                if value is None:
                    continue
                values.append(value)
                ax.bar(index + shift, value, width=width, color=MODE_COLOR[mode], zorder=3)
                ax.annotate(
                    f"{value:,.0f}", xy=(index + shift, value), xytext=(0, 4),
                    textcoords="offset points", ha="center", va="bottom", fontsize=9, color=TEXT,
                )  # fmt: skip
        if values:
            ax.set_xticks([0, 1], labels=["Input tokens", "Output tokens"])
            ax.set_xlim(-0.6, 1.6)
            ax.set_ylim(0, max(values) * 1.18)
            ax.set_ylabel("Mean tokens per task")
            thousands(ax)
        else:
            no_data(ax)
    fig.legend(
        handles=_mode_patches(summary, summary.modes), loc="upper right",
        bbox_to_anchor=(0.96, 0.985), frameon=False, fontsize=8.5, ncols=len(summary.modes),
    )  # fmt: skip
    return _save(fig, summary, out_dir, "token_breakdown")


def unanticipated_query(summary: Summary, out_dir: Path) -> list[Path]:
    """Scenario C at its largest volume: mean tokens, p50 latency and accuracy per mode."""
    volume = summary.c_volumes[-1]
    modes = _group_modes(summary, "C", volume)
    cells = [summary.cell("C", volume, m) for m in modes]
    fig = plt.figure(figsize=(10, 6))
    axes = [fig.add_axes((0.07 + 0.32 * i, 0.17, 0.25, 0.60)) for i in range(3)]
    add_header(
        fig, summary, "Unanticipated query: tokens, latency and accuracy",
        subtitle_text(summary, "C", cells) + f" · {volume} tx/account",
    )  # fmt: skip
    add_footnote(
        fig,
        "Measured. The aggregation tool cannot answer this question directly (no per-merchant "
        "totals, no weekday information); Code Mode has no aggregation tool either. Each panel "
        "has its own y axis; latency is p50 wall-clock time excluding client-side throttling.",
    )
    getters: list[tuple[str, Callable[[CellStats], float | None], Callable[[float], str], str]] = [
        ("Mean tokens per task", lambda c: c.tokens_mean, lambda v: f"{v:,.0f}", "Tokens"),
        ("p50 latency (seconds)", lambda c: c.latency_p50_s, _seconds_label, "Latency"),
        (
            "Accuracy (% of measured tasks correct)",
            lambda c: None if c.accuracy is None else c.accuracy * 100,
            lambda v: f"{v:.1f}%",
            "Accuracy",
        ),
    ]
    for ax, (ylabel, getter, formatter, title) in zip(axes, getters, strict=True):
        values: dict[str, float | None] = {
            m: (getter(c) if c is not None else None) for m, c in zip(modes, cells, strict=True)
        }
        _bar_panel(ax, summary, values, formatter, ylabel, title)
        if title == "Tokens":
            thousands(ax)
        if title == "Accuracy":
            ax.set_ylim(0, 118)
            ax.set_yticks([0, 20, 40, 60, 80, 100])
    return _save(fig, summary, out_dir, "unanticipated_query")


UNANTICIPATED_STEM = "unanticipated_query"
CHART_STEMS = (
    "tokens_vs_volume",
    "latency_vs_volume",
    "cost_vs_volume",
    "model_calls_vs_volume",
    "scenario_a_parity",
    "latency_distribution",
    "accuracy_by_cell",
    "token_breakdown",
)


def render_all(summary: Summary, tasks_df: pd.DataFrame, out_dir: Path) -> list[Path]:
    """Render every chart as PNG and SVG into ``out_dir``; returns the written paths."""
    with style_context():
        written: list[Path] = []
        written += tokens_vs_volume(summary, out_dir)
        written += latency_vs_volume(summary, out_dir)
        written += cost_vs_volume(summary, out_dir)
        written += model_calls_vs_volume(summary, out_dir)
        written += scenario_a_parity(summary, out_dir)
        written += latency_distribution(summary, tasks_df, out_dir)
        written += accuracy_by_cell(summary, out_dir)
        written += token_breakdown(summary, out_dir)
        if summary.c_volumes:
            written += unanticipated_query(summary, out_dir)
    return written
