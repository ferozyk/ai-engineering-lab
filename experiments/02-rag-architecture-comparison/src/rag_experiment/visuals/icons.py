"""Icons drawn from simple shapes (no font glyphs, no images)."""

import math

from matplotlib.patches import Circle

from rag_experiment.visuals.draw import SERIES, Canvas, shade, tint
from rag_experiment.visuals.iso import draw_tile

PX_TO_PT = 72 / 200


def icon_color(key: str) -> str:
    """The technique colour darkened enough to read on its own light tile."""
    return shade(SERIES[key], 0.68)


def _lw(s: float, k: float = 0.045) -> float:
    return max(1.6, s * k * PX_TO_PT * 2.78)


def ring(
    c: Canvas, cx: float, cy: float, r: float, color: str, lw: float, fc: str = "none"
) -> None:
    c.ax.add_patch(Circle((cx, cy), r, fc=fc, ec=color, lw=lw, zorder=5))


def magnifier(c: Canvas, cx: float, cy: float, s: float, color: str) -> None:
    """A magnifying glass inside a box of size s centred on (cx, cy)."""
    lw = _lw(s)
    rx, ry, r = cx - 0.12 * s, cy - 0.12 * s, 0.3 * s
    ring(c, rx, ry, r, color, lw, fc="#FFFFFF")
    ex, ey = rx + r * math.cos(math.pi / 4), ry + r * math.sin(math.pi / 4)
    c.polyline([(ex, ey), (cx + 0.42 * s, cy + 0.42 * s)], color, lw * 1.7, z=5, round_caps=True)


def bubble(
    c: Canvas, cx: float, cy: float, w: float, h: float, color: str, lines: bool = True
) -> None:
    lw = _lw(w)
    c.rect(
        cx - w / 2,
        cy - h / 2,
        w,
        h,
        fc=tint(color, 0.2, "#FFFFFF"),
        ec=color,
        lw=lw,
        radius=h * 0.3,
        z=4,
    )
    c.poly(
        [
            (cx - w * 0.3, cy + h / 2 - 1),
            (cx - w * 0.18, cy + h / 2 - 1),
            (cx - w * 0.38, cy + h / 2 + h * 0.32),
        ],
        fc=tint(color, 0.2, "#FFFFFF"),
        ec=color,
        lw=lw,
        z=4,
    )
    for i, frac in enumerate((0.6, 0.4) if lines else ()):
        y = cy - h * 0.12 + i * h * 0.26
        c.polyline(
            [(cx - w * 0.3, y), (cx - w * 0.3 + w * frac, y)], color, lw, z=5, round_caps=True
        )


def hash_tag(c: Canvas, cx: float, cy: float, s: float, color: str) -> None:
    lw = _lw(s, 0.07)
    g, h = s * 0.14, s * 0.5
    for dx in (-g, g):
        c.polyline(
            [(cx + dx + 0.06 * s, cy - h / 2), (cx + dx - 0.06 * s, cy + h / 2)],
            color,
            lw,
            z=5,
            round_caps=True,
        )
    for dy in (-g * 0.9, g * 0.9):
        c.polyline([(cx - h / 2, cy + dy), (cx + h / 2, cy + dy)], color, lw, z=5, round_caps=True)


def triangle(c: Canvas, cx: float, cy: float, s: float, color: str, up: bool) -> None:
    k = -1 if up else 1
    c.poly(
        [(cx - s / 2, cy + k * s * 0.3), (cx + s / 2, cy + k * s * 0.3), (cx, cy - k * s * 0.45)],
        fc=color,
        z=5,
    )


def ranked_list(c: Canvas, cx: float, cy: float, s: float, color: str) -> None:
    lw = _lw(s, 0.07)
    for i, frac in enumerate((0.55, 0.42, 0.3)):
        y = cy - 0.24 * s + i * 0.2 * s
        c.polyline(
            [(cx - 0.42 * s, y), (cx - 0.42 * s + frac * s, y)], color, lw, z=5, round_caps=True
        )
    triangle(c, cx + 0.34 * s, cy - 0.18 * s, 0.17 * s, color, up=True)
    triangle(c, cx + 0.34 * s, cy + 0.2 * s, 0.17 * s, color, up=False)


def loop_arrow(c: Canvas, cx: float, cy: float, s: float, color: str) -> None:
    lw = _lw(s, 0.05)
    r = 0.42 * s
    start, end = math.radians(-60), math.radians(235)
    pts = [
        (cx + r * math.cos(a), cy + r * math.sin(a))
        for a in (start + (end - start) * i / 40 for i in range(41))
    ]
    c.polyline(pts, color, lw, z=5, round_caps=True)
    tx, ty = pts[-1]
    ang = end + math.pi / 2
    h = 0.14 * s
    c.poly(
        [
            (tx + h * math.cos(ang), ty + h * math.sin(ang)),
            (tx + h * 0.9 * math.cos(ang + 2.4), ty + h * 0.9 * math.sin(ang + 2.4)),
            (tx + h * 0.9 * math.cos(ang - 2.4), ty + h * 0.9 * math.sin(ang - 2.4)),
        ],
        fc=color,
        z=5,
    )


def technique_icon(c: Canvas, key: str, cx: float, cy: float, s: float) -> None:
    """The icon for technique ``key`` ("A".."D" internally; shown as 1-4) in a box of size s."""
    col = icon_color(key)
    if key == "A":
        bubble(c, cx - 0.1 * s, cy - 0.14 * s, 0.64 * s, 0.4 * s, col)
        magnifier(c, cx + 0.14 * s, cy + 0.14 * s, 0.62 * s, col)
    elif key == "B":
        hash_tag(c, cx + 0.22 * s, cy - 0.22 * s, 0.5 * s, col)
        magnifier(c, cx - 0.04 * s, cy + 0.08 * s, 0.78 * s, col)
    elif key == "C":
        ranked_list(c, cx - 0.05 * s, cy - 0.12 * s, 0.9 * s, col)
        magnifier(c, cx + 0.2 * s, cy + 0.22 * s, 0.46 * s, col)
    else:
        loop_arrow(c, cx, cy, 0.9 * s, col)
        magnifier(c, cx + 0.02 * s, cy + 0.02 * s, 0.5 * s, col)


def technique_tile(c: Canvas, key: str, cx: float, cy: float, width: float) -> None:
    """An isometric tile in the technique colour with its icon standing on it."""
    draw_tile(c, cx, cy + width * 0.12, width, SERIES[key], thick=width * 0.09)
    technique_icon(c, key, cx, cy - width * 0.02, width * 0.46)


def clock_icon(c: Canvas, cx: float, cy: float, r: float, color: str) -> None:
    lw = _lw(r * 2, 0.07)
    ring(c, cx, cy, r, color, lw)
    c.polyline(
        [(cx, cy - r * 0.6), (cx, cy), (cx + r * 0.45, cy + r * 0.2)],
        color,
        lw,
        z=5,
        round_caps=True,
    )


def coin_icon(c: Canvas, cx: float, cy: float, r: float, color: str) -> None:
    lw = _lw(r * 2, 0.07)
    ring(c, cx, cy, r, color, lw)
    ring(c, cx, cy, r * 0.55, color, lw * 0.7)


def check_icon(c: Canvas, cx: float, cy: float, s: float, color: str) -> None:
    lw = _lw(s, 0.09)
    c.polyline(
        [(cx - 0.3 * s, cy), (cx - 0.08 * s, cy + 0.24 * s), (cx + 0.34 * s, cy - 0.26 * s)],
        color,
        lw,
        z=5,
        round_caps=True,
    )


def book_icon(c: Canvas, cx: float, cy: float, s: float, color: str) -> None:
    """A document page with a folded corner and text lines."""
    lw = _lw(s, 0.06)
    w, h, f = 0.62 * s, 0.82 * s, 0.2 * s
    x0, y0 = cx - w / 2, cy - h / 2
    c.poly(
        [(x0, y0), (x0 + w - f, y0), (x0 + w, y0 + f), (x0 + w, y0 + h), (x0, y0 + h)],
        fc=tint(color, 0.12, "#FFFFFF"),
        ec=color,
        lw=lw,
        z=4,
    )
    c.polyline([(x0 + w - f, y0), (x0 + w - f, y0 + f), (x0 + w, y0 + f)], color, lw, z=5)
    for k, frac in enumerate((0.7, 0.7, 0.45)):
        y = y0 + h * (0.42 + 0.17 * k)
        c.polyline(
            [(x0 + w * 0.15, y), (x0 + w * (0.15 + 0.7 * frac), y)], color, lw, z=5, round_caps=True
        )


def question_icon(c: Canvas, cx: float, cy: float, s: float, color: str) -> None:
    bubble(c, cx, cy - 0.05 * s, 0.9 * s, 0.62 * s, color, lines=False)
    c.text(
        cx, cy - 0.04 * s, "?", max(9.5, 0.4 * s / 2.78), "bold", color, ha="center", va="center"
    )
