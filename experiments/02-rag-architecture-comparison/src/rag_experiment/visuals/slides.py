"""The nine carousel slides. Wording follows the brief; numbers come from ``Numbers``."""

from dataclasses import dataclass

from rag_experiment.visuals.data import ARCHITECTURES, Numbers, VisualsDataError
from rag_experiment.visuals.draw import (
    HAIRLINE,
    HEIGHT,
    INK,
    MARGIN,
    MUTED,
    SERIES,
    WIDTH,
    Canvas,
    tint,
)

TOTAL = 9
CONTENT_W = WIDTH - 2 * MARGIN
PLAIN_NAMES = {
    "A": "Search by meaning",
    "B": "+ Keyword search",
    "C": "+ Second-opinion ranking",
    "D": "Agent that searches again",
}
TECH_NAMES = {
    "A": "dense vector retrieval",
    "B": "hybrid BM25 + vector search (RRF)",
    "C": "cross-encoder reranking",
    "D": "agentic RAG (LangGraph)",
}
HOW = {
    "A": "Find the 5 most similar passages, then let the AI answer from them.",
    "B": "Also search for exact words, then merge both result lists.",
    "C": "A second AI model re-reads the top 30 passages and re-orders them.",
    "D": "The AI plans its searches, checks whether it found enough, and searches again if not.",
}


def _open(slide: str, numbers: Numbers, font: str) -> Canvas:
    numbers.slide = slide
    return Canvas(font)


def _title(c: Canvas, text: str, y: float = 72, size: float = 22) -> float:
    return c.paragraph(MARGIN, y, text, size, CONTENT_W, "bold", factor=1.2)


def fmt_time(seconds: float) -> str:
    return f"{seconds:.1f} s"


def fmt_cost(usd: float) -> str:
    return f"${usd:.2f}"


def slide_cover(numbers: Numbers, font: str) -> Canvas:
    c = _open("slide-01", numbers, font)
    y = c.paragraph(
        MARGIN, 230, "We built the same AI assistant 4 ways.", 30, CONTENT_W, "bold", factor=1.2
    )
    y = c.paragraph(
        MARGIN,
        y + 30,
        "Which design actually gave better answers — and what did it cost?",
        14,
        CONTENT_W,
        color=MUTED,
        factor=1.35,
    )
    col = CONTENT_W / 4
    for i, x in enumerate(ARCHITECTURES):
        cx = MARGIN + col * i + col / 2
        c.badge(x, cx, 640, 50)
        c.paragraph(cx, 720, PLAIN_NAMES[x], 11, col - 24, "bold", ha="center", factor=1.3)
    c.line(MARGIN, 960, WIDTH - MARGIN, 960)
    c.paragraph(
        MARGIN,
        990,
        f"Same documents · same questions · same AI model · every question asked {numbers.get('repetitions')} times",
        11,
        CONTENT_W,
        color=MUTED,
    )
    c.footer(1, TOTAL)
    return c


def _icon_documents(c: Canvas, x: float, y: float) -> None:
    for i, dy in enumerate((28, 14, 0)):
        c.rect(
            x + 14 - i * 7 + 14,
            y + dy,
            80,
            70,
            fc="#FFFFFF" if i == 2 else BG_PAPER,
            ec=MUTED,
            lw=1.4,
            radius=6,
        )
    for k in range(3):
        c.line(x + 30, y + 22 + k * 16, x + 80, y + 22 + k * 16, color=MUTED, lw=1.4)


BG_PAPER = "#F1F2EE"


def _icon_questions(c: Canvas, x: float, y: float) -> None:
    c.rect(x + 8, y + 10, 104, 80, fc="#FFFFFF", ec=MUTED, lw=1.4, radius=14)
    c.text(x + 60, y + 52, "?", 22, "bold", MUTED, ha="center", va="center")
    c.arrow((x + 40, y + 90), (x + 28, y + 112), color=MUTED)


def _icon_grading(c: Canvas, x: float, y: float) -> None:
    c.rect(x + 8, y + 8, 104, 100, fc="#FFFFFF", ec=MUTED, lw=1.4, radius=10)
    c.line(x + 34, y + 62, x + 52, y + 82, color=INK, lw=3)
    c.line(x + 52, y + 82, x + 90, y + 34, color=INK, lw=3)


def slide_test(numbers: Numbers, font: str) -> Canvas:
    c = _open("slide-02", numbers, font)
    _title(c, "The test")
    text_x = MARGIN + 170
    text_w = WIDTH - MARGIN - text_x
    blocks = [
        _icon_documents,
        _icon_questions,
        _icon_grading,
    ]
    texts = [
        f"A fictional bank’s API documentation: {numbers.get('n_apis')} APIs, {numbers.get('n_sections')} sections.",
        (
            f"{numbers.get('n_answerable')} real questions, each asked {numbers.get('repetitions')} times: "
            f"{numbers.get('N')} answers to grade. Plus {numbers.get('n_trick')} trick questions "
            "that have no answer in the docs."
        ),
        "Graded automatically:\nIs the answer right?\nDoes it admit ‘I don’t know’ when it should?\nDoes it make anything up?",
    ]
    y = 190
    for icon, text in zip(blocks, texts, strict=True):
        icon(c, MARGIN, y)
        c.paragraph(text_x, y + 4, text, 12, text_w, factor=1.45)
        y += 270
        c.line(MARGIN, y - 50, WIDTH - MARGIN, y - 50)
    c.paragraph(
        MARGIN,
        1130,
        "Synthetic data. A small test: results show direction, not universal truth.",
        11,
        CONTENT_W,
        color=MUTED,
    )
    c.footer(2, TOTAL)
    return c


@dataclass(frozen=True)
class Stage:
    """One column of a tiny flow diagram: one or two stacked boxes, each maybe new."""

    labels: tuple[tuple[str, bool], ...]
    weight: float = 1.0


FLOWS: dict[str, tuple[Stage, ...]] = {
    "A": (
        Stage((("Question", False),)),
        Stage((("Find similar passages", True),)),
        Stage((("AI answers", False),)),
    ),
    "B": (
        Stage((("Question", False),)),
        Stage((("Meaning search", False), ("Keyword search", True)), 1.5),
        Stage((("Merge", True),)),
        Stage((("AI answers", False),)),
    ),
    "C": (
        Stage((("Question", False),)),
        Stage((("Search", False),)),
        Stage((("Re-rank top 30", True),)),
        Stage((("AI answers", False),)),
    ),
    "D": (
        Stage((("Question", False),)),
        Stage((("Plan", True),)),
        Stage((("Search", False),)),
        Stage((("Enough?", True),)),
        Stage((("AI answers", False),)),
    ),
}


def _flow(c: Canvas, x: str, top: float) -> float:
    """Draw the flow diagram; returns the y below it."""
    stages = FLOWS[x]
    gap = 44.0
    avail = CONTENT_W - gap * (len(stages) - 1)
    unit = avail / sum(s.weight for s in stages)
    cy = top + 70
    left = float(MARGIN)
    centers: list[tuple[float, float, float]] = []
    prev_right = None
    for stage in stages:
        w = unit * stage.weight
        n = len(stage.labels)
        h = 96.0 if n == 1 else 62.0
        spacing = 12.0
        total = n * h + (n - 1) * spacing
        for k, (label, new) in enumerate(stage.labels):
            by = cy - total / 2 + k * (h + spacing)
            c.rect(
                left,
                by,
                w,
                h,
                fc=tint(SERIES[x], 0.22) if new else "#FFFFFF",
                ec=SERIES[x] if new else MUTED,
                lw=2.4 if new else 1.2,
                radius=10,
            )
            lines = c.wrap(label, 10.5, w - 20)
            pitch = c.line_height(10.5, 1.25)
            for i, line in enumerate(lines):
                c.text(
                    left + w / 2,
                    by + h / 2 - len(lines) * pitch / 2 + i * pitch,
                    line,
                    10.5,
                    "bold" if new else "normal",
                    ha="center",
                )
        if prev_right is not None:
            c.arrow((prev_right + 6, cy), (left - 4, cy))
        centers.append((left, w, total))
        prev_right = left + w
        left += w + gap
    bottom = cy + 50
    if x == "D":
        search_left, search_w, _ = centers[2]
        enough_left, enough_w, _ = centers[3]
        start = (enough_left + enough_w / 2, bottom - 2)
        end = (search_left + search_w / 2, bottom - 2)
        c.arrow(start, end, rad=-0.55)
        c.text(
            (start[0] + end[0]) / 2, bottom + 64, "no: search again", 9, color=MUTED, ha="center"
        )
        bottom += 84
    return bottom


def _chip(c: Canvas, x: float, y: float, w: float, h: float, value: str, label: str) -> None:
    c.rect(x, y, w, h, fc="#FFFFFF", ec=HAIRLINE, lw=1.2, radius=10)
    c.text(x + 18, y + 14, value, 20, "bold")
    c.paragraph(x + 18, y + 14 + c.line_height(20) + 6, label, 10, w - 36, color=MUTED, factor=1.25)


def _changed_texts(x: str, numbers: Numbers) -> tuple[str, str]:
    g = numbers.get
    if x == "A":
        if g("A.made_up") != 0 or g("A.correct_refusal") != g("A.trick_attempts"):
            raise VisualsDataError("slide copy for A assumes no made-up answers and all refusals")
        return (
            f"A strong, cheap starting point: right {g('A.pct')}% of the time.",
            f"Never made anything up, and declined every trick question, in all {g('A.correct_refusal')} tries.",
        )
    if x == "B":
        return (
            "Better when questions use the documentation’s exact terms.",
            "Worse when people use everyday words — the extra keyword matches crowded out good results. "
            f"Net: {g('deltaB'):+d} right vs A.",
        )
    if x == "C":
        delta = g("deltaC")
        net = "no change in right answers vs B" if delta == 0 else f"{delta:+d} right vs B"
        return (
            "Recovered several everyday-wording questions B missed.",
            "But a one-paragraph permissions list that mentions everything often looked more relevant "
            f"than the real answer. Net: {net}, and {g('slowC')}× slower than A.",
        )
    fr_b, fr_d = g("B.false_refusal"), g("D.false_refusal")
    if fr_d >= fr_b:
        raise VisualsDataError("slide copy for D assumes wrong ‘I don’t know’ answers fell")
    made_up = g("D.made_up")
    once = {
        0: "It never answered a trick question it should have declined.",
        1: "Once, it answered a trick question it should have declined.",
    }.get(made_up, f"{made_up} times, it answered a trick question it should have declined.")
    return (
        f"Most right answers, and wrong ‘I don’t know’ fell to {fr_d} (the other designs: {g('frMin')}–{g('frMax')}).",
        f"Costs ≈{g('costRatio')}× more and takes ≈{g('timeRatio')}× longer than A. {once}",
    )


def slide_pattern(x: str, numbers: Numbers, font: str, page: int) -> Canvas:
    g = numbers.get
    c = _open(f"slide-{page:02d}", numbers, font)
    c.badge(x, MARGIN + 38, 112, 38)
    head = c.paragraph(
        MARGIN + 100, 80, f"Pattern {x}: {PLAIN_NAMES[x]}", 22, CONTENT_W - 100, "bold", factor=1.2
    )
    y = max(180.0, head + 18)
    c.text(MARGIN, y, "HOW IT WORKS", 10, "bold", MUTED)
    y = c.paragraph(MARGIN, y + 40, HOW[x], 12, CONTENT_W, factor=1.4)
    y = _flow(c, x, y + 8)
    y += 30
    c.text(MARGIN, y, f"{g(f'{x}.correct')}/{g('N')} right", 32, "bold")
    c.text(WIDTH - MARGIN, y, f"{g(f'{x}.pct')}%", 32, "bold", ha="right")
    y += 110
    frac = g(f"{x}.correct") / g("N")
    c.rect(MARGIN, y, CONTENT_W, 16, fc=HAIRLINE, ec="none", radius=8)
    c.rect(MARGIN, y, CONTENT_W * frac, 16, fc=SERIES[x], ec="none", radius=8)
    y += 44
    gap = 20.0
    w = (CONTENT_W - 2 * gap) / 3
    chips = [
        (f"≈ {fmt_time(g(f'{x}.time_s'))}", "Time per question (typical)"),
        (fmt_cost(g(f"{x}.cost_per_1000")), "Estimated cost per 1,000 questions"),
        (
            f"{g(f'{x}.false_refusal')} of {g(f'{x}.false_refusal_of')}",
            "Wrong ‘I don’t know’ answers",
        ),
    ]
    for i, (value, label) in enumerate(chips):
        _chip(c, MARGIN + i * (w + gap), y, w, 168, value, label)
    y += 168 + 28
    c.text(MARGIN, y, "WHAT CHANGED", 10, "bold", MUTED)
    y += 40
    for bullet in _changed_texts(x, numbers):
        c.dot(MARGIN + 7, y + 17, 6, SERIES[x])
        y = c.paragraph(MARGIN + 28, y, bullet, 12, CONTENT_W - 28, factor=1.35) + 12
    c.text(MARGIN, HEIGHT - 132, f"Technical name: {TECH_NAMES[x]}", 9, color=MUTED)
    c.footer(page, TOTAL)
    return c


def _bar_panel(
    c: Canvas,
    top: float,
    title: str,
    values: dict[str, float],
    labels: dict[str, str],
    scale_max: float,
) -> None:
    c.text(MARGIN, top, title, 12, "bold")
    x0 = MARGIN + 86
    max_len = 640.0
    row = 58.0
    first = top + 78
    c.line(x0, first - 28, x0, first - 28 + 4 * row - 6)
    for i, x in enumerate(ARCHITECTURES):
        cy = first + i * row
        c.badge(x, MARGIN + 24, cy, 20)
        length = max_len * values[x] / scale_max
        c.rect(x0, cy - 17, length, 34, fc=SERIES[x], ec="none")
        c.text(x0 + length + 14, cy, labels[x], 12, "bold", va="center")


def slide_side_by_side(numbers: Numbers, font: str) -> Canvas:
    g = numbers.get
    c = _open("slide-07", numbers, font)
    _title(c, "Side by side")
    n = g("N")
    _bar_panel(
        c,
        170,
        f"Right answers (out of {n})",
        {x: float(g(f"{x}.correct")) for x in ARCHITECTURES},
        {x: str(g(f"{x}.correct")) for x in ARCHITECTURES},
        float(n),
    )
    times = {x: float(g(f"{x}.time_s")) for x in ARCHITECTURES}
    _bar_panel(
        c,
        470,
        "Time per question (seconds, typical)",
        times,
        {x: fmt_time(times[x]) for x in ARCHITECTURES},
        max(times.values()),
    )
    costs = {x: float(g(f"{x}.cost_per_1000")) for x in ARCHITECTURES}
    _bar_panel(
        c,
        770,
        "Estimated cost per 1,000 questions (USD)",
        costs,
        {x: fmt_cost(costs[x]) for x in ARCHITECTURES},
        max(costs.values()),
    )
    c.line(MARGIN, 1085, WIDTH - MARGIN, 1085)
    c.paragraph(
        MARGIN,
        1112,
        "Only the agent moved answer quality clearly. B and C changed which questions were right, not how many.",
        12,
        CONTENT_W,
        "bold",
        factor=1.35,
    )
    c.footer(7, TOTAL)
    return c


def _card(c: Canvas, top: float, height: float) -> None:
    c.rect(MARGIN, top, CONTENT_W, height, fc="#FFFFFF", ec=HAIRLINE, lw=1.4, radius=14)


def slide_examples(numbers: Numbers, font: str) -> Canvas:
    g = numbers.get
    c = _open("slide-08", numbers, font)
    title_end = _title(c, "What actually made the difference", size=22)
    inner = MARGIN + 28
    inner_w = CONTENT_W - 56
    # Card 1: everyday wording
    top = title_end + 26
    _card(c, top, 410)
    c.text(inner, top + 26, "EVERYDAY WORDING", 10, "bold", MUTED)
    y = c.paragraph(inner, top + 70, f"“{g('q104.text')}”", 12, inner_w, "bold", factor=1.4)
    y += 22
    col = inner_w / 4
    for i, x in enumerate(ARCHITECTURES):
        cx = inner + col * i
        c.badge(x, cx + 26, y + 26, 26)
        c.text(
            cx + 62,
            y + 26,
            f"{g(f'q104.{x}.right')}/{g(f'q104.{x}.tries')} right",
            12,
            "bold",
            va="center",
        )
    y += 90
    c.paragraph(
        inner,
        y,
        f"The agent rephrased it into two searches: ‘{g('q104.D.query1')}’ and ‘{g('q104.D.query2')}’.",
        11,
        inner_w,
        color=MUTED,
        factor=1.4,
    )
    # Card 2: where the agent's extra right answers came from
    top = top + 410 + 30
    _card(c, top, 360)
    c.text(inner, top + 26, "WHERE THE AGENT’S EXTRA RIGHT ANSWERS CAME FROM", 10, "bold", MUTED)
    y = c.paragraph(
        inner,
        top + 70,
        (
            f"{g('gain.questions')} questions it answered better than B: {g('gain.semantic')} "
            f"worded in everyday language, {g('gain.comparison')} comparing two parts of the docs."
        ),
        12,
        inner_w,
        "bold",
        factor=1.4,
    )
    c.paragraph(
        inner,
        y + 24,
        (
            "On multi-step questions it gathered complete information far more often "
            f"({g('D.multi_step_full')}/{g('D.multi_step_of')} tries vs "
            f"{g('B.multi_step_full')}/{g('B.multi_step_of')} for B), but it got the same ones "
            f"right as B ({g('D.multi_correct')}/{g('D.multi_step_of')} vs "
            f"{g('B.multi_correct')}/{g('B.multi_step_of')})."
        ),
        12,
        inner_w,
        factor=1.4,
    )
    c.footer(8, TOTAL)
    return c


USE_WHEN = {
    "A": "You need fast, cheap answers to everyday questions. Start here.",
    "B": "Users type exact codes, IDs or product names.",
    "C": "The right answer is found but ranked too low, and a few extra seconds are fine.",
    "D": "People ask in their own words, a wrong ‘I don’t know’ is costly, and quality matters more than speed or cost.",
}


def _watch_out(numbers: Numbers) -> dict[str, str]:
    return {
        "A": "Similar-looking passages crowding out the right one.",
        "B": "It can make everyday-language questions worse.",
        "C": "Catch-all reference text fooling the ranker; much slower on a laptop CPU.",
        "D": f"≈{numbers.get('costRatio')}× cost, slower, and it can over-reach on unanswerable questions.",
    }


def slide_cheat_sheet(numbers: Numbers, font: str) -> Canvas:
    c = _open("slide-09", numbers, font)
    _title(c, "Which pattern when?")
    watch = _watch_out(numbers)
    pitch = 195.0
    left_x = MARGIN + 100
    col_w = 400.0
    right_x = left_x + col_w + 30
    for i, x in enumerate(ARCHITECTURES):
        y = 160 + i * pitch
        c.line(MARGIN, y, WIDTH - MARGIN, y)
        c.badge(x, MARGIN + 34, y + 62, 34)
        c.text(left_x, y + 24, "USE WHEN", 10, "bold", MUTED)
        c.paragraph(left_x, y + 62, USE_WHEN[x], 11, col_w, factor=1.35)
        c.text(right_x, y + 24, "WATCH OUT FOR", 10, "bold", MUTED)
        c.paragraph(right_x, y + 62, watch[x], 11, WIDTH - MARGIN - right_x, factor=1.35)
    rule = "Start simple. Measure where it fails. Add one piece only when the failures point to it."
    rule_lines = c.wrap(rule, 14, CONTENT_W - 60, "bold")
    box_top = 160 + 4 * pitch + 96
    box_h = len(rule_lines) * c.line_height(14, 1.3) + 52
    c.rect(
        MARGIN,
        box_top,
        CONTENT_W,
        box_h,
        fc=tint(SERIES["D"], 0.12),
        ec=SERIES["D"],
        lw=2.4,
        radius=14,
    )
    c.paragraph(
        MARGIN + 30,
        box_top + 28,
        rule,
        14,
        CONTENT_W - 60,
        "bold",
        factor=1.3,
    )
    c.footer(9, TOTAL, extra="Full code, data and method: github.com/ferozyk/ai-engineering-lab")
    return c


def build_slides(numbers: Numbers, font: str) -> list[Canvas]:
    """All nine slides in order."""
    slides = [
        slide_cover(numbers, font),
        slide_test(numbers, font),
        *(slide_pattern(x, numbers, font, 3 + i) for i, x in enumerate(ARCHITECTURES)),
        slide_side_by_side(numbers, font),
        slide_examples(numbers, font),
        slide_cheat_sheet(numbers, font),
    ]
    return slides
