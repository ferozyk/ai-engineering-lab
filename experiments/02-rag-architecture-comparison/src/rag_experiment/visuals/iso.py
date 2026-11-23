"""Isometric drawing: 2D polygons in a 30 degree isometric projection (no perspective).

Heights are drawn in the same unit as the footprint, so a tower's on-screen height is exactly
``value * scale`` and bars of different values can be compared by eye (base at zero).
"""

import itertools
import math
from dataclasses import dataclass

from rag_experiment.visuals.draw import Canvas, shade, tint

COS30 = math.sqrt(3) / 2
SIN30 = 0.5
Point = tuple[float, float]


@dataclass(frozen=True)
class Iso:
    """A projection: world (x right-down, y left-down, z up) to page pixels."""

    ox: float
    oy: float
    scale: float = 1.0

    def project(self, x: float, y: float, z: float = 0.0) -> Point:
        return (
            self.ox + (x - y) * COS30 * self.scale,
            self.oy + (x + y) * SIN30 * self.scale - z * self.scale,
        )


def cuboid_faces(
    iso: Iso, x: float, y: float, z: float, w: float, d: float, h: float
) -> dict[str, list[Point]]:
    """The three visible faces (top, left, right) of a box with its back corner at (x, y, z)."""
    p = iso.project
    return {
        "top": [p(x, y, z + h), p(x + w, y, z + h), p(x + w, y + d, z + h), p(x, y + d, z + h)],
        "left": [p(x, y + d, z), p(x + w, y + d, z), p(x + w, y + d, z + h), p(x, y + d, z + h)],
        "right": [p(x + w, y, z), p(x + w, y + d, z), p(x + w, y + d, z + h), p(x + w, y, z + h)],
    }


def draw_cuboid(
    c: Canvas,
    iso: Iso,
    x: float,
    y: float,
    z: float,
    w: float,
    d: float,
    h: float,
    color: str,
    shadow: bool = True,
    top_color: str | None = None,
    z_order: float = 2.0,
) -> dict[str, list[Point]]:
    """Draw one box: lighter top, base-colour left face, darker right face, soft shadow."""
    faces = cuboid_faces(iso, x, y, z, w, d, h)
    if shadow:
        reach = min(0.45 * h * iso.scale, 46.0)
        foot = cuboid_faces(iso, x, y, z, w, d, 0.0)["top"]
        cast = [(px + reach, py + reach * 0.42) for px, py in foot]
        hull = [foot[0], foot[1], cast[1], cast[2], cast[3], foot[3]]
        c.poly(hull, fc="#000000", alpha=0.14, z=z_order - 0.5)
    top = top_color or tint(color, 0.55, "#FFFFFF")
    for name, fill in (("left", color), ("right", shade(color, 0.72)), ("top", top)):
        c.poly(faces[name], fc=fill, ec=fill, lw=0.5, z=z_order)
    return faces


def draw_tile(
    c: Canvas, cx: float, cy: float, width: float, color: str, thick: float = 12.0
) -> None:
    """A flat isometric slab whose top rhombus is centred on (cx, cy)."""
    hw = width / 2
    hh = hw * math.tan(math.radians(30))
    top = [(cx, cy - hh), (cx + hw, cy), (cx, cy + hh), (cx - hw, cy)]
    shadow = [(px + 8, py + thick + 6) for px, py in top]
    c.poly(shadow, fc="#000000", alpha=0.12, z=1.4)
    left = [top[3], top[2], (top[2][0], top[2][1] + thick), (top[3][0], top[3][1] + thick)]
    right = [top[2], top[1], (top[1][0], top[1][1] + thick), (top[2][0], top[2][1] + thick)]
    c.poly(left, fc=color, ec=color, lw=0.5, z=1.6)
    c.poly(right, fc=shade(color, 0.72), ec=shade(color, 0.72), lw=0.5, z=1.6)
    c.poly(top, fc=tint(color, 0.3, "#FFFFFF"), ec=tint(color, 0.3, "#FFFFFF"), lw=0.5, z=1.8)


def clip_to_convex(p: Point, q: Point, poly: list[Point]) -> tuple[Point, Point] | None:
    """Cyrus-Beck clip of a segment to a convex polygon; ``None`` when fully outside."""
    area = sum(
        poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
        for i in range(len(poly))
    )
    sign = 1.0 if area > 0 else -1.0
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        nx, ny = sign * (b[1] - a[1]), -sign * (b[0] - a[0])  # outward normal
        num = nx * (p[0] - a[0]) + ny * (p[1] - a[1])
        den = nx * dx + ny * dy
        if abs(den) < 1e-12:
            if num > 0:
                return None
            continue
        t = -num / den
        if den < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return (p[0] + t0 * dx, p[1] + t0 * dy), (p[0] + t1 * dx, p[1] + t1 * dy)


def floor_polygon(cx: float, cy: float, half_w: float, half_h: float) -> list[Point]:
    """A flat-ended isometric stage: a hexagon whose slanted sides are at 30 degrees."""
    run = half_h / math.tan(math.radians(30))
    return [
        (cx - half_w, cy),
        (cx - half_w + run, cy - half_h),
        (cx + half_w - run, cy - half_h),
        (cx + half_w, cy),
        (cx + half_w - run, cy + half_h),
        (cx - half_w + run, cy + half_h),
    ]


def draw_floor(
    c: Canvas,
    iso: Iso,
    cx: float,
    cy: float,
    half_w: float,
    half_h: float,
    step: float,
    top: str,
    grid: str,
    side: str,
    thick: float = 14.0,
) -> None:
    """A slab with a faint isometric grid on top (the stage the towers stand on)."""
    hexa = floor_polygon(cx, cy, half_w, half_h)
    lower = [hexa[0], hexa[5], hexa[4], hexa[3]]
    for a, b in itertools.pairwise(lower):
        c.poly([a, b, (b[0], b[1] + thick), (a[0], a[1] + thick)], fc=side, ec=side, lw=0.5, z=0.3)
    c.poly(hexa, fc=top, ec=top, lw=0.5, z=0.35)
    extent = (half_w + half_h) * 1.2
    n = int(extent / step)
    centre = iso.project(0, 0, 0)
    for i in range(-n, n + 1):
        v = i * step
        for a, b in (
            (iso.project(v, -extent), iso.project(v, extent)),
            (iso.project(-extent, v), iso.project(extent, v)),
        ):
            seg = clip_to_convex(
                (a[0] - centre[0] + cx, a[1] - centre[1] + cy),
                (b[0] - centre[0] + cx, b[1] - centre[1] + cy),
                hexa,
            )
            if seg:
                c.line(seg[0][0], seg[0][1], seg[1][0], seg[1][1], color=grid, lw=0.7, z=0.4)


def draw_stack(
    c: Canvas,
    iso: Iso,
    x: float,
    y: float,
    w: float,
    d: float,
    pages: int,
    page_h: float,
    cover: str,
) -> float:
    """A stack of document pages; returns the world height of the stack."""
    z = 0.0
    for i in range(pages):
        jitter = ((i * 7) % 5 - 2) * 2.5
        last = i == pages - 1
        color = cover if last else ("#E9ECF0" if i % 2 == 0 else "#DDE2E8")
        draw_cuboid(
            c,
            iso,
            x + jitter,
            y - jitter * 0.6,
            z,
            w,
            d,
            page_h,
            color,
            shadow=(i == 0),
            top_color=None if last else "#FFFFFF",
            z_order=2.0 + i * 0.01,
        )
        z += page_h
    return z
