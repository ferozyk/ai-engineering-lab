"""Small drawing toolkit: a 1080 x 1350 pixel canvas on matplotlib with measured text wrapping."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from matplotlib import font_manager
from matplotlib.artist import Artist
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

WIDTH = 1080
HEIGHT = 1350
DPI = 200
PX_PER_PT = DPI / 72
MARGIN = 64
MIN_MARGIN = 48
MIN_TEXT_PT = 9.5

BG = "#FAFAF7"
INK = "#1B1F24"
MUTED = "#5B6470"
HAIRLINE = "#D9DDE3"
NAVY = "#0F1B2D"
LIGHT_INK = "#F4F6F8"
LIGHT_MUTED = "#A9B4C2"
DARK_HAIRLINE = "#2A3B55"
SERIES = {"A": "#0072B2", "B": "#E69F00", "C": "#CC79A7", "D": "#009E73"}
# Text on a technique colour: white on the blue, dark ink on the three lighter colours (contrast).
ON_SERIES = {"A": "#FFFFFF", "B": INK, "C": INK, "D": INK}
ORDER = {"A": 1, "B": 2, "C": 3, "D": 4}
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


def tint(color: str, amount: float = 0.18, bg_color: str = BG) -> str:
    """The colour mixed towards the background (a light fill for a coloured outline)."""
    bg = [int(bg_color[i : i + 2], 16) for i in (1, 3, 5)]
    fg = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(b + (f - b) * amount) for b, f in zip(bg, fg, strict=True)]
    return "#" + "".join(f"{v:02X}" for v in mixed)


def shade(color: str, factor: float) -> str:
    """The colour scaled towards black (factor < 1 darkens)."""
    parts = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{min(255, round(v * factor)):02X}" for v in parts)


@dataclass(frozen=True)
class Placed:
    """A drawn text, kept for layout checks."""

    text: str
    size_pt: float
    artist: Artist


class Canvas:
    """One page. Coordinates are pixels with the origin at the top left."""

    def __init__(self, font: str, dark: bool = False) -> None:
        self.font = font
        self.dark = dark
        self.bg = NAVY if dark else BG
        self.ink = LIGHT_INK if dark else INK
        self.muted = LIGHT_MUTED if dark else MUTED
        self.hair = DARK_HAIRLINE if dark else HAIRLINE
        self.fig = Figure(figsize=(WIDTH / DPI, HEIGHT / DPI), dpi=DPI, facecolor=self.bg)
        self._agg = FigureCanvasAgg(self.fig)
        self.ax = self.fig.add_axes((0, 0, 1, 1))
        self.ax.set_xlim(0, WIDTH)
        self.ax.set_ylim(HEIGHT, 0)
        self.ax.axis("off")
        self.renderer = self._agg.get_renderer()  # type: ignore[no-untyped-call]
        self.placed: list[Placed] = []
        # Layout problems found while drawing (e.g. a block pushed into the footer).
        self.problems: list[str] = []

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
        color: str | None = None,
        ha: str = "left",
        va: str = "top",
    ) -> None:
        artist = self.ax.text(
            x,
            y,
            text,
            fontproperties=self.props(size, weight),
            color=color or self.ink,
            ha=ha,
            va=va,
            zorder=6,
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
        color: str | None = None,
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
        ec: str | None = None,
        lw: float = 1.0,
        radius: float = 0.0,
        alpha: float = 1.0,
        z: float = 1.0,
    ) -> None:
        edge = ec or self.hair
        if radius > 0:
            patch: Rectangle | FancyBboxPatch = FancyBboxPatch(
                (x + radius, y + radius),
                w - 2 * radius,
                h - 2 * radius,
                boxstyle=f"round,pad={radius},rounding_size={radius}",
                fc=fc,
                ec=edge,
                lw=lw,
                alpha=alpha,
                zorder=z,
            )
        else:
            patch = Rectangle((x, y), w, h, fc=fc, ec=edge, lw=lw, alpha=alpha, zorder=z)
        self.ax.add_patch(patch)

    def card(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        accent: str | None = None,
        fc: str | None = None,
        radius: float = 16.0,
    ) -> None:
        """A rounded card with a soft shadow and an optional coloured left accent bar."""
        fill = fc or ("#16263F" if self.dark else "#FFFFFF")
        self.rect(x + 3, y + 7, w, h, fc="#000000", ec="none", radius=radius, alpha=0.07, z=0.5)
        self.rect(x, y, w, h, fc=fill, ec=self.hair, lw=0.8, radius=radius, z=1.0)
        if accent:
            self.rect(x, y + radius, 7, h - 2 * radius, fc=accent, ec="none", z=1.2)

    def poly(
        self,
        points: list[tuple[float, float]],
        fc: str = "none",
        ec: str = "none",
        lw: float = 0.8,
        alpha: float = 1.0,
        z: float = 2.0,
    ) -> Polygon:
        patch = Polygon(points, closed=True, fc=fc, ec=ec, lw=lw, alpha=alpha, zorder=z)
        patch.set_joinstyle("round")
        self.ax.add_patch(patch)
        return patch

    def line(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        color: str | None = None,
        lw: float = 1.0,
        dashed: bool = False,
        z: float = 2.0,
    ) -> None:
        self.polyline([(x0, y0), (x1, y1)], color, lw, dashed, z)

    def polyline(
        self,
        points: list[tuple[float, float]],
        color: str | None = None,
        lw: float = 1.0,
        dashed: bool = False,
        z: float = 2.0,
        round_caps: bool = False,
    ) -> None:
        self.ax.plot(
            [p[0] for p in points],
            [p[1] for p in points],
            color=color or self.hair,
            lw=lw,
            solid_capstyle="round" if round_caps else "butt",
            linestyle=(0, (1.5, 3.2)) if dashed else "-",
            dash_capstyle="round",
            zorder=z,
        )

    def badge(self, key: str, cx: float, cy: float, r: float) -> None:
        """A circle in the technique's colour with its order number (1-4)."""
        self.ax.add_patch(Circle((cx, cy), r, fc=SERIES[key], ec="none", zorder=4))
        self.text(
            cx,
            cy + r * 0.04,
            str(ORDER[key]),
            max(9.5, r * 0.62),
            "bold",
            ON_SERIES[key],
            ha="center",
            va="center",
        )

    def dot(
        self, cx: float, cy: float, r: float, color: str, ec: str = "none", z: float = 3.0
    ) -> None:
        self.ax.add_patch(Circle((cx, cy), r, fc=color, ec=ec, lw=1.6, zorder=z))

    def arrow(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        color: str | None = None,
        rad: float = 0.0,
        lw: float = 1.4,
        scale: float = 16.0,
    ) -> None:
        self.ax.add_patch(
            FancyArrowPatch(
                start,
                end,
                arrowstyle="-|>",
                mutation_scale=scale,
                color=color or self.muted,
                lw=lw,
                connectionstyle=f"arc3,rad={rad}",
                shrinkA=0,
                shrinkB=0,
                zorder=3,
            )
        )

    def footer(self, extra: str | None = None, text: str | None = None) -> None:
        y = HEIGHT - 62
        self.line(MARGIN, y - 20, WIDTH - MARGIN, y - 20)
        self.text(MARGIN, y, text or f"Experiment 02 \u00b7 {REPO}", 9.5, color=self.muted)
        if extra:
            self.text(WIDTH - MARGIN, y, extra, 9.5, color=self.muted, ha="right")

    def extents(self) -> list[tuple[Placed, float, float, float, float]]:
        """Each text's box as (placed, x0, y0, x1, y1) in top-left pixel coordinates."""
        boxes = []
        for placed in self.placed:
            bb = placed.artist.get_window_extent(self.renderer)
            boxes.append((placed, bb.x0, HEIGHT - bb.y1, bb.x1, HEIGHT - bb.y0))
        return boxes

    def check(self) -> list[str]:
        """Problems found: too small, outside the side margins or the page, overlapping."""
        problems: list[str] = list(self.problems)
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
        self.fig.savefig(path, dpi=DPI, facecolor=self.bg)
