"""The single-image summary."""

from rag_experiment.visuals.data import ARCHITECTURES, Numbers
from rag_experiment.visuals.draw import (
    MARGIN,
    MUTED,
    SERIES,
    WIDTH,
    Canvas,
    tint,
)
from rag_experiment.visuals.slides import CONTENT_W, fmt_cost, fmt_time

SHORT_HOW = {
    "A": "Search by meaning",
    "B": "+ exact-word search",
    "C": "+ second-opinion re-ranking",
    "D": "+ plans, checks, searches again",
}
BEST_FOR = {
    "A": "Fast, cheap answers to everyday questions",
    "B": "Exact codes, IDs and product names",
    "C": "Right answer found but ranked too low",
    "D": "Everyday wording, when quality matters most",
}


def build_infographic(numbers: Numbers, font: str) -> Canvas:
    g = numbers.get
    numbers.slide = "infographic"
    c = Canvas(font)
    y = c.paragraph(
        MARGIN,
        70,
        "Same AI assistant, 4 designs: what changed the answers?",
        22,
        CONTENT_W,
        "bold",
        factor=1.2,
    )
    y = c.paragraph(
        MARGIN,
        y + 14,
        f"{g('N')} graded answers per design · same documents, questions and AI model",
        10.5,
        CONTENT_W,
        color=MUTED,
    )
    n = g("N")
    bar_x, bar_w = MARGIN, 480.0
    time_x, cost_x = 800.0, 940.0
    head_y = y + 16
    c.text(bar_x, head_y, f"RIGHT ANSWERS (OUT OF {n})", 9, "bold", MUTED)
    c.text(time_x, head_y, "TIME", 9, "bold", MUTED, ha="center")
    c.text(cost_x, head_y, "EST. COST/1K", 9, "bold", MUTED, ha="center")
    c.line(MARGIN, head_y + 38, WIDTH - MARGIN, head_y + 38)
    pitch = 154.0
    first = head_y + 54
    for i, x in enumerate(ARCHITECTURES):
        top = first + i * pitch
        c.badge(x, MARGIN + 26, top + 26, 26)
        c.text(MARGIN + 70, top + 8, SHORT_HOW[x], 12, "bold")
        bar_y = top + 62
        c.rect(bar_x, bar_y, bar_w, 30, fc="#EDEEEA", ec="none")
        c.rect(bar_x, bar_y, bar_w * g(f"{x}.correct") / n, 30, fc=SERIES[x], ec="none")
        c.text(bar_x + bar_w + 14, bar_y + 15, f"{g(f'{x}.correct')}/{n}", 12, "bold", va="center")
        c.text(
            time_x,
            bar_y + 15,
            f"≈{fmt_time(g(f'{x}.time_s'))}",
            12,
            "bold",
            ha="center",
            va="center",
        )
        c.text(
            cost_x,
            bar_y + 15,
            fmt_cost(g(f"{x}.cost_per_1000")),
            12,
            "bold",
            ha="center",
            va="center",
        )
        c.text(MARGIN, top + 108, f"Best for: {BEST_FOR[x]}", 10, color=MUTED)
        c.line(MARGIN, top + 146, WIDTH - MARGIN, top + 146)
    box_top = first + 4 * pitch + 4
    box_h = 232.0
    c.rect(
        MARGIN,
        box_top,
        CONTENT_W,
        box_h,
        fc=tint(SERIES["D"], 0.1),
        ec=SERIES["D"],
        lw=2.4,
        radius=14,
    )
    c.paragraph(
        MARGIN + 28,
        box_top + 24,
        (
            f"Only the agent that searches again clearly improved answers (+{g('deltaD')} right vs A) "
            f"— at ≈{g('costRatio')}× the cost and ≈{g('timeRatio')}× the time. "
            "Start simple; add complexity only where you measure failures."
        ),
        12,
        CONTENT_W - 56,
        "bold",
        factor=1.35,
    )
    c.footer(1, 1)
    return c
