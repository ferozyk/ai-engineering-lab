"""The one-image summary: a cheat sheet of the four RAG patterns with measured numbers and the
strength of evidence behind each "use when" line."""

from rag_experiment.visuals.cheatsheet import HINT, MEASURED, NOT_SHOWN, evidence_pill, rows
from rag_experiment.visuals.data import ARCHITECTURES, Numbers
from rag_experiment.visuals.draw import MARGIN, SERIES, WIDTH, Canvas
from rag_experiment.visuals.slides import NAMES, fmt_cost, fmt_time

CONTENT_W = WIDTH - 2 * MARGIN
SHORT_PLAIN = {
    "A": "Finds passages that mean the same as your question",
    "B": "Meaning search + exact-keyword search, merged",
    "C": "A second AI re-orders the top 30 finds",
    "D": "An AI agent plans, searches, checks, searches again",
}
CARD_H = 240.0
GAP = 10.0
TEXT = 9.5


def _stats_line(c: Canvas, x: float, y: float, parts: list[tuple[str, str]]) -> None:
    """``value label`` pairs on one line: value bold, label muted, separated by gaps."""
    for value, label in parts:
        c.text(x, y, value, 11, "bold")
        x += c.measure(value, 11, "bold") + 8
        c.text(x, y + 4, label, TEXT, color=c.muted)
        x += c.measure(label, TEXT) + 30


def build_infographic(numbers: Numbers, font: str) -> Canvas:
    numbers.slide = "infographic"
    c = Canvas(font, dark=True)
    n = numbers.get("N")

    # header
    c.text(MARGIN, 34, "EXPERIMENT 02 · 4 RAG PATTERNS · ONE TEST", 9.5, "bold", "#7FD3B5")
    y = c.paragraph(MARGIN, 68, "Which RAG pattern should you use?", 18, CONTENT_W, "bold")
    y = c.paragraph(
        MARGIN,
        y + 4,
        f"Measured on one small, clean manual: {numbers.get('n_sections')} sections, "
        f"{numbers.get('n_answerable')} questions, {numbers.get('repetitions')} tries each. "
        "Every ‘use when’ is tagged with how strong our evidence is.",
        TEXT,
        CONTENT_W,
        color=c.muted,
        factor=1.3,
    )
    lx: float = MARGIN
    ly = y + 24
    for label in (MEASURED, HINT, NOT_SHOWN):
        lx += evidence_pill(c, lx, ly, label) + 10

    # cards
    table = rows(numbers)
    top = ly + 34
    left_x = MARGIN + 76
    right = WIDTH - MARGIN - 28
    col_w = (right - left_x - 28) / 2
    watch_x = left_x + col_w + 28
    for i, x in enumerate(ARCHITECTURES):
        cy = top + i * (CARD_H + GAP)
        row = table[x]
        c.card(MARGIN, cy, CONTENT_W, CARD_H, accent=SERIES[x], radius=14)
        c.badge(x, MARGIN + 40, cy + 36, 20)
        c.text(left_x, cy + 14, NAMES[x], 12, "bold")
        c.text(left_x, cy + 50, SHORT_PLAIN[x], TEXT, color=c.muted)
        _stats_line(
            c,
            left_x,
            cy + 82,
            [
                (f"{numbers.get(f'{x}.correct')}/{n}", "right"),
                (fmt_time(numbers.get(f"{x}.time_s")), "per answer"),
                (fmt_cost(numbers.get(f"{x}.cost_per_1000")), "per 1k answers (est.)"),
            ],
        )
        c.line(left_x, cy + 122, right, cy + 122)
        c.text(left_x, cy + 132, "USE WHEN", TEXT, "bold", c.muted)
        evidence_pill(
            c, left_x + c.measure("USE WHEN", TEXT, "bold") + 12, cy + 144, row.evidence, 9.5
        )
        c.paragraph(left_x, cy + 166, row.use_when, TEXT, col_w, factor=1.25)
        c.text(watch_x, cy + 132, "WATCH OUT FOR", TEXT, "bold", c.muted)
        c.paragraph(watch_x, cy + 166, row.watch_out, TEXT, col_w, factor=1.25)
    c.footer()
    return c
