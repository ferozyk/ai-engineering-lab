"""Small drawing toolkit: a 1080 x 1350 pixel canvas on matplotlib with measured text wrapping."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from matplotlib import font_manager
from matplotlib.artist import Artist
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle

WIDTH = 1080
HEIGHT = 1350
DPI = 200
PX_PER_PT = DPI / 72
MARGIN = 64
MIN_MARGIN = 48
MIN_TEXT_PT = 9.0

BG = "#FAFAF7"
INK = "#1B1F24"
MUTED = "#5B6470"
HAIRLINE = "#D9DDE3"
SERIES = {"A": "#0072B2", "B": "#E69F00", "C": "#CC79A7", "D": "#009E73"}
FONT_CANDIDATES = ("Avenir Next", "Helvetica Neue", "Helvetica", "Arial")
FALLBACK_FONT = "DejaVu Sans"
REPO = "github.com/ferozyk/ai-engineering-lab"


class LayoutError(RuntimeError):
    """Text that overflows the margins, is too small, or overlaps other text."""


def resolve_font() -> str:
    """The first available system sans font, else DejaVu Sans."""
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in FONT_CANDIDATES:
        if name in available:
            return name
    return FALLBACK_FONT


def wrap_words(text: str, max_px: float, measure: Callable[[str], float]) -> list[str]:
    """Greedy word wrap by measured pixel width (a single over-long word keeps its own line)."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        words: list[str] = []
        for word in paragraph.split():
            if words and words[-1] == "+":  # keep a leading plus with the word it belongs to
                words[-1] = f"+ {word}"
            else:
                words.append(word)
        for word in words:
            trial = f"{current} {word}" if current else word
            if current and measure(trial) > max_px:
                lines.append(current)
                current = word
            else:
                current = trial
        lines.append(current)
    return lines


def tint(color: str, amount: float = 0.18) -> str:
    """The colour mixed towards the background (a light fill for a coloured outline)."""
    bg = [int(BG[i : i + 2], 16) for i in (1, 3, 5)]
    fg = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(b + (f - b) * amount) for b, f in zip(bg, fg, strict=True)]
    return "#" + "".join(f"{v:02X}" for v in mixed)


@dataclass(frozen=True)
class Placed:
    """A drawn text, kept for layout checks."""

    text: str
    size_pt: float
    artist: Artist


class Canvas:
    """One page. Coordinates are pixels with the origin at the top left."""

    def __init__(self, font: str) -> None:
        self.font = font
        self.fig = Figure(figsize=(WIDTH / DPI, HEIGHT / DPI), dpi=DPI, facecolor=BG)
        self._agg = FigureCanvasAgg(self.fig)
        self.ax = self.fig.add_axes((0, 0, 1, 1))
        self.ax.set_xlim(0, WIDTH)
        self.ax.set_ylim(HEIGHT, 0)
        self.ax.axis("off")
        self.renderer = self._agg.get_renderer()  # type: ignore[no-untyped-call]
        self.placed: list[Placed] = []

    def props(self, size: float, weight: str = "normal") -> FontProperties:
        return FontProperties(family=self.font, weight=weight, size=size)

    def measure(self, text: str, size: float, weight: str = "normal") -> float:
        width, _, _ = self.renderer.get_text_width_height_descent(
            text, self.props(size, weight), ismath=False
        )
        return float(width)

    def wrap(self, text: str, size: float, max_px: float, weight: str = "normal") -> list[str]:
        return wrap_words(text, max_px, lambda s: self.measure(s, size, weight))

    def line_height(self, size: float, factor: float = 1.32) -> float:
        return size * PX_PER_PT * factor

    def text(
        self,
        x: float,
        y: float,
        text: str,
        size: float,
        weight: str = "normal",
        color: str = INK,
        ha: str = "left",
        va: str = "top",
    ) -> None:
        artist = self.ax.text(
            x, y, text, fontproperties=self.props(size, weight), color=color, ha=ha, va=va
        )
        self.placed.append(Placed(text, size, artist))

    def paragraph(
        self,
        x: float,
        y: float,
        text: str,
        size: float,
        max_px: float,
        weight: str = "normal",
        color: str = INK,
        ha: str = "left",
        factor: float = 1.32,
    ) -> float:
        """Wrapped text; returns the y just below the last line."""
        pitch = self.line_height(size, factor)
        for i, line in enumerate(self.wrap(text, size, max_px, weight)):
            self.text(x, y + i * pitch, line, size, weight, color, ha)
            y_end = y + (i + 1) * pitch
        return y_end

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fc: str = "none",
        ec: str = HAIRLINE,
        lw: float = 1.0,
        radius: float = 0.0,
    ) -> None:
        if radius > 0:
            patch: Rectangle | FancyBboxPatch = FancyBboxPatch(
                (x + radius, y + radius),
                w - 2 * radius,
                h - 2 * radius,
                boxstyle=f"round,pad={radius},rounding_size={radius}",
                fc=fc,
                ec=ec,
                lw=lw,
            )
        else:
            patch = Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw)
        self.ax.add_patch(patch)

    def line(
        self, x0: float, y0: float, x1: float, y1: float, color: str = HAIRLINE, lw: float = 1.0
    ) -> None:
        self.ax.plot([x0, x1], [y0, y1], color=color, lw=lw, solid_capstyle="butt")

    def badge(self, letter: str, cx: float, cy: float, r: float) -> None:
        """A circle in the pattern's colour with its white letter."""
        self.ax.add_patch(Circle((cx, cy), r, fc=SERIES[letter], ec="none"))
        self.text(cx, cy + r * 0.04, letter, r * 0.47, "bold", "#FFFFFF", ha="center", va="center")

    def dot(self, cx: float, cy: float, r: float, color: str) -> None:
        self.ax.add_patch(Circle((cx, cy), r, fc=color, ec="none"))

    def arrow(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        color: str = MUTED,
        rad: float = 0.0,
        lw: float = 1.4,
    ) -> None:
        self.ax.add_patch(
            FancyArrowPatch(
                start,
                end,
                arrowstyle="-|>",
                mutation_scale=16,
                color=color,
                lw=lw,
                connectionstyle=f"arc3,rad={rad}",
                shrinkA=0,
                shrinkB=0,
            )
        )

    def footer(self, page: int, total: int, extra: str | None = None) -> None:
        y = HEIGHT - 62
        self.line(MARGIN, y - 20, WIDTH - MARGIN, y - 20)
        self.text(MARGIN, y, f"Experiment 02 · {REPO}", 9, color=MUTED)
        self.text(WIDTH - MARGIN, y, f"{page} / {total}", 9, color=MUTED, ha="right")
        if extra:
            self.text(MARGIN, y - 62, extra, 9, color=MUTED)

    def extents(self) -> list[tuple[Placed, float, float, float, float]]:
        """Each text's box as (placed, x0, y0, x1, y1) in top-left pixel coordinates."""
        boxes = []
        for placed in self.placed:
            bb = placed.artist.get_window_extent(self.renderer)
            boxes.append((placed, bb.x0, HEIGHT - bb.y1, bb.x1, HEIGHT - bb.y0))
        return boxes

    def check(self) -> list[str]:
        """Problems found: too small, outside the side margins or the page, overlapping."""
        problems: list[str] = []
        boxes = self.extents()
        for placed, x0, y0, x1, y1 in boxes:
            if placed.size_pt < MIN_TEXT_PT - 1e-6:
                problems.append(f"too small ({placed.size_pt} pt): {placed.text!r}")
            if x0 < MIN_MARGIN - 1 or x1 > WIDTH - MIN_MARGIN + 1 or y0 < 0 or y1 > HEIGHT:
                problems.append(
                    f"outside margins ({x0:.0f}-{x1:.0f}, {y0:.0f}-{y1:.0f}): {placed.text!r}"
                )
        for i, (a, ax0, ay0, ax1, ay1) in enumerate(boxes):
            for b, bx0, by0, bx1, by1 in boxes[i + 1 :]:
                if min(ax1, bx1) - max(ax0, bx0) > 3 and min(ay1, by1) - max(ay0, by0) > 14:
                    problems.append(f"overlap: {a.text!r} / {b.text!r}")
        return problems

    def save_png(self, path: Path) -> None:
        self.fig.savefig(path, dpi=DPI, facecolor=BG)
