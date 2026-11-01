"""Static charts (PNG + SVG) generated from a processed ``Summary``.

Palette: MCP is blue with circle markers, Code Mode is orange with square markers. The marker
shape is a second encoding so the modes stay distinguishable without colour.
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

from mcp_vs_code_mode.bench.analysis import CellStats, Summary

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
SPINE = "#c9c8c2"
MCP_COLOR = "#2a78d6"
CODE_COLOR = "#eb6834"
WATERMARK = "SIMULATED DATA — NOT A RESULT"
MODES: tuple[str, ...] = ("mcp", "code")
MODE_LABEL = {"mcp": "MCP", "code": "Code Mode"}
MODE_COLOR = {"mcp": MCP_COLOR, "code": CODE_COLOR}
MODE_MARKER = {"mcp": "o", "code": "s"}
VOLUME_TICKS = (10, 50, 200)
LINE_WIDTH = 2.0
MARKER_SIZE = 8
BAND_ALPHA = 0.15
MIN_LABEL_GAP = 0.075  # minimum vertical gap between direct labels, in axes fraction
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


def volume_axis(ax: Axes, *, label: bool = True) -> None:
    """Log x axis with ticks exactly at the benchmark volumes."""
    ax.set_xscale("log")
    ax.set_xticks(list(VOLUME_TICKS), labels=[str(v) for v in VOLUME_TICKS])
    ax.minorticks_off()
    ax.set_xlim(7.0, 290.0)
    if label:
        ax.set_xlabel("Transactions per account (log scale)")


def n_label(cells: Sequence[CellStats | None]) -> str:
    """``n=15 per point`` (or a range when cells differ)."""
    counts = sorted({c.n_measured for c in cells if c is not None})
    if not counts:
        return "n=0 per point"
    if len(counts) == 1:
        return f"n={counts[0]} per point"
    return f"n={counts[0]}–{counts[-1]} per point"


def subtitle_text(summary: Summary, scenario: str, cells: Sequence[CellStats | None]) -> str:
    """Subtitle line: scenario, model id, sample size and run id."""
    return f"Scenario {scenario} · {summary.model_id} · {n_label(cells)} · run {summary.run_id}"


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


def mode_legend(ax: Axes, *, loc: Any = "upper left", **kwargs: Any) -> None:
    """Legend with a marker per mode (frameless)."""
    handles = [
        Line2D(
            [],
            [],
            color=MODE_COLOR[m],
            marker=MODE_MARKER[m],
            markersize=7,
            linewidth=LINE_WIDTH,
            label=MODE_LABEL[m],
        )
        for m in MODES
    ]
    ax.legend(handles=handles, loc=loc, frameon=False, fontsize=9, **kwargs)


def end_labels(ax: Axes, items: Sequence[tuple[float, str]]) -> None:
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
    ys = [y for y, _ in placed]
    for i in range(1, len(ys)):
        if ys[i] - ys[i - 1] < MIN_LABEL_GAP:
            middle = (ys[i] + ys[i - 1]) / 2
            ys[i - 1], ys[i] = middle - MIN_LABEL_GAP / 2, middle + MIN_LABEL_GAP / 2
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
            MODE_LABEL[mode],
            transform=ax.transAxes,
            va="center",
            ha="left",
            fontsize=9,
            color=TEXT,
        )


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
    volume_axis(ax, label=xlabel)
    any_data = False
    end_points: list[tuple[float, str]] = []
    for mode in MODES:
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
            label=MODE_LABEL[mode],
        )
        if hollow is not None:
            px, py = _points(cells, hollow)
            if px:
                ax.plot(
                    px, py, color=color, marker=marker, markersize=MARKER_SIZE,
                    markerfacecolor=SURFACE, markeredgewidth=1.6, linestyle=":",
                    linewidth=1.0, zorder=3,
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
    end_labels(ax, end_points)
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
    return [summary.cell("B", v, m) for v in summary.volumes for m in MODES]


def _annotate_gaps(ax: Axes, summary: Summary) -> None:
    """Annotate the token change between the lines at each volume."""
    for volume in summary.volumes:
        comp = summary.comparison("B", volume)
        mcp, code = summary.cell("B", volume, "mcp"), summary.cell("B", volume, "code")
        if (
            comp is None
            or comp.tokens_reduction_pct is None
            or mcp is None
            or code is None
            or mcp.tokens_mean is None
            or code.tokens_mean is None
        ):
            continue
        change = -comp.tokens_reduction_pct
        text = f"{MINUS if change < 0 else '+'}{abs(change):.0f}%"
        ax.plot(
            [volume, volume],
            [code.tokens_mean, mcp.tokens_mean],
            color=TEXT_SECONDARY,
            linewidth=0.8,
            zorder=2,
        )
        ax.annotate(
            text,
            xy=(volume, (mcp.tokens_mean + code.tokens_mean) / 2),
            xytext=(-7, 0),
            textcoords="offset points",
            ha="right",
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
        "labels between the lines = Code Mode tokens relative to MCP (mean).",
    )
    if draw_volume_lines(
        ax, summary, lambda c: c.tokens_mean, band=(lambda c: c.tokens_min, lambda c: c.tokens_max)
    ):
        thousands(ax)
        _annotate_gaps(ax, summary)
        mode_legend(ax)
    ax.set_ylabel("Mean total tokens per task")
    return _save(fig, summary, out_dir, "tokens_vs_volume")


def latency_vs_volume(summary: Summary, out_dir: Path) -> list[Path]:
    """p50 latency (filled) and p95 (hollow) against volume."""
    fig, ax = _new_figure(
        summary,
        "Task latency vs transactions per account",
        subtitle_text(summary, "B", _all_b_cells(summary)),
        "Measured wall-clock latency; excludes client-side throttling. Filled markers = p50, "
        "hollow markers = p95. p95 with n=15 is close to the sample maximum.",
    )
    if draw_volume_lines(ax, summary, lambda c: c.latency_p50_s, hollow=lambda c: c.latency_p95_s):
        mode_legend(ax)
    ax.set_ylabel("Latency per task (seconds)")
    return _save(fig, summary, out_dir, "latency_vs_volume")


def cost_vs_volume(summary: Summary, out_dir: Path) -> list[Path]:
    """Estimated USD per 1,000 tasks against volume."""
    fig, ax = _new_figure(
        summary,
        "Estimated cost per 1,000 tasks vs transactions per account",
        subtitle_text(summary, "B", _all_b_cells(summary)),
        f"Estimated, not billed. {summary.metadata.pricing.note}.",
    )
    if draw_volume_lines(ax, summary, lambda c: c.cost_usd_per_1k_tasks):
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"${v:,.4g}"))
        mode_legend(ax)
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
        mode_legend(ax)
    ax.set_ylabel("Mean model calls per task")
    return _save(fig, summary, out_dir, "model_calls_vs_volume")


def _bar_panel(
    ax: Axes,
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
    for index, mode in enumerate(MODES):
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
    ax.set_xticks(range(len(MODES)), labels=[MODE_LABEL[m] for m in MODES])
    ax.set_xlim(-0.6, len(MODES) - 0.4)
    ax.set_ylim(0, max(present) * 1.18)
    ax.set_ylabel(ylabel)


def _seconds_label(value: float) -> str:
    """Seconds with 2 decimals; sub-100 ms values are shown in milliseconds to stay legible."""
    return f"{value:.2f} s" if value >= 0.1 else f"{value * 1000:.1f} ms"


def _mode_patches() -> list[Patch]:
    return [Patch(facecolor=MODE_COLOR[m], label=MODE_LABEL[m]) for m in MODES]


def scenario_a_parity(summary: Summary, out_dir: Path) -> list[Path]:
    """Scenario A: mean tokens and p50 latency, MCP vs Code Mode (two separate panels)."""
    cells = [summary.cell("A", None, m) for m in MODES]
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
        {m: (c.tokens_mean if c else None) for m, c in zip(MODES, cells, strict=True)},
        lambda v: f"{v:,.0f}",
        "Mean total tokens per task",
        "Tokens",
    )
    thousands(left)
    _bar_panel(
        right,
        {m: (c.latency_p50_s if c else None) for m, c in zip(MODES, cells, strict=True)},
        _seconds_label,
        "p50 latency per task (seconds)",
        "Latency",
    )
    fig.legend(
        handles=_mode_patches(), loc="upper right", bbox_to_anchor=(0.96, 0.985),
        frameon=False, fontsize=9, ncols=2,
    )  # fmt: skip
    return _save(fig, summary, out_dir, "scenario_a_parity")


def _groups(summary: Summary) -> list[tuple[str, str, int | None]]:
    groups: list[tuple[str, str, int | None]] = [("A", "Scenario A", None)]
    groups.extend(("B", f"B · {v}", v) for v in summary.volumes)
    return groups


def latency_distribution(summary: Summary, tasks: pd.DataFrame, out_dir: Path) -> list[Path]:
    """Box plots of task latency per cell, grouped by scenario and volume."""
    cells = [summary.cell(s, v, m) for s, _, v in _groups(summary) for m in MODES]
    fig, ax = _new_figure(
        summary,
        "Task latency distribution per cell",
        f"Scenarios A and B · {summary.model_id} · {n_label(cells)} · run {summary.run_id}",
        "Measured. Box = interquartile range, line = median, whiskers = 1.5 x IQR; outliers "
        "not drawn. Latency excludes client-side throttling.",
    )
    style_axes(ax)
    offsets = {"mcp": -0.19, "code": 0.19}
    drawn = False
    groups = _groups(summary)
    for index, (scenario, _, volume) in enumerate(groups):
        for mode in MODES:
            label = f"{scenario}{volume if volume is not None else ''}:{mode}"
            if tasks.empty:
                continue
            subset = tasks[(tasks["cell"] == label) & (tasks["outcome"] != "infra_error")]
            if subset.empty:
                continue
            values = (subset["latency_ms"] / 1000).to_numpy(dtype=float)
            box = ax.boxplot(
                [values], positions=[index + offsets[mode]], widths=0.32, patch_artist=True,
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
        ax.set_xlabel("Scenario · transactions per account")
        ax.set_ylabel("Latency per task (seconds)")
        ax.legend(handles=_mode_patches(), loc="upper left", frameon=False, fontsize=9)
    else:
        no_data(ax)
    return _save(fig, summary, out_dir, "latency_distribution")


def accuracy_by_cell(summary: Summary, out_dir: Path) -> list[Path]:
    """Grouped bars: accuracy (% correct of measured tasks) per scenario/volume and mode."""
    groups = _groups(summary)
    cells = [summary.cell(s, v, m) for s, _, v in groups for m in MODES]
    fig, ax = _new_figure(
        summary,
        "Accuracy by scenario and volume",
        f"Scenarios A and B · {summary.model_id} · {n_label(cells)} · run {summary.run_id}",
        "Measured. Accuracy = correct answers / measured tasks (tasks with an infrastructure "
        "error are excluded and reported separately).",
    )
    style_axes(ax)
    width = 0.36
    drawn = False
    for index, (scenario, _, volume) in enumerate(groups):
        for mode, shift in zip(MODES, (-width / 2, width / 2), strict=True):
            cell = summary.cell(scenario, volume, mode)
            if cell is None or cell.accuracy is None:
                continue
            drawn = True
            value = cell.accuracy * 100
            ax.bar(index + shift, value, width=width * 0.95, color=MODE_COLOR[mode], zorder=3)
            ax.annotate(
                f"{value:.1f}%", xy=(index + shift, value), xytext=(0, 4),
                textcoords="offset points", ha="center", va="bottom", fontsize=9, color=TEXT,
            )  # fmt: skip
    if drawn:
        ax.set_xticks(range(len(groups)), labels=[g[1] for g in groups])
        ax.set_xlim(-0.6, len(groups) - 0.4)
        ax.set_ylim(0, 125)
        ax.set_yticks([0, 20, 40, 60, 80, 100])
        ax.set_xlabel("Scenario · transactions per account")
        ax.set_ylabel("Accuracy (% of measured tasks correct)")
        ax.legend(handles=_mode_patches(), loc="upper left", frameon=False, fontsize=9, ncols=2)
    else:
        no_data(ax)
    return _save(fig, summary, out_dir, "accuracy_by_cell")


def token_breakdown(summary: Summary, out_dir: Path) -> list[Path]:
    """Mean input vs output tokens per task for Scenario A and the largest Scenario B volume."""
    volumes = summary.volumes
    largest = volumes[-1] if volumes else None
    panels: list[tuple[str, str, int | None]] = [("A", "Scenario A", None)]
    if largest is not None:
        panels.append(("B", f"Scenario B · {largest} transactions per account", largest))
    cells = [summary.cell(s, v, m) for s, _, v in panels for m in MODES]
    fig = plt.figure(figsize=(10, 6))
    axes = [fig.add_axes((0.09 + 0.47 * i, 0.17, 0.36, 0.60)) for i in range(len(panels))]
    add_header(
        fig, summary, "Input and output tokens per task",
        f"{' and '.join(p[1] for p in panels)} · {summary.model_id} · {n_label(cells)} · "
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
        width = 0.36
        values: list[float] = []
        for index, kind in enumerate(("input", "output")):
            for mode, shift in zip(MODES, (-width / 2, width / 2), strict=True):
                cell = summary.cell(scenario, volume, mode)
                value = None
                if cell is not None:
                    value = cell.input_tokens_mean if kind == "input" else cell.output_tokens_mean
                if value is None:
                    continue
                values.append(value)
                ax.bar(index + shift, value, width=width * 0.95, color=MODE_COLOR[mode], zorder=3)
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
        handles=_mode_patches(), loc="upper right", bbox_to_anchor=(0.96, 0.985),
        frameon=False, fontsize=9, ncols=2,
    )  # fmt: skip
    return _save(fig, summary, out_dir, "token_breakdown")


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
    return written
