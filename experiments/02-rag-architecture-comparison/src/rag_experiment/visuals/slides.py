"""The eleven carousel slides, told as a story in four chapters.

Wording is fixed here; every number comes from ``Numbers``. Techniques are shown by their
industry names (see ``NAMES``); the letters A-D are internal keys only and never drawn.
"""

import itertools
from collections.abc import Callable

from rag_experiment.visuals.cheatsheet import evidence_pill
from rag_experiment.visuals.cheatsheet import rows as cheat_rows
from rag_experiment.visuals.data import ARCHITECTURES, Numbers
from rag_experiment.visuals.draw import (
    HEIGHT,
    MARGIN,
    NAVY,
    ON_SERIES,
    REPO,
    SERIES,
    WIDTH,
    Canvas,
    LayoutError,
    shade,
    tint,
)
from rag_experiment.visuals.icons import (
    book_icon,
    check_icon,
    clock_icon,
    coin_icon,
    question_icon,
    technique_tile,
)
from rag_experiment.visuals.iso import Iso, draw_cuboid, draw_floor, draw_stack, draw_tile

TOTAL = 11
CONTENT_W = WIDTH - 2 * MARGIN
SLATE = "#2B3F5C"
DARK_CARD = "#16263F"

NAMES = {
    "A": "Semantic Search RAG",
    "B": "Hybrid Search RAG",
    "C": "Hybrid + Reranker RAG",
    "D": "Agentic RAG",
}
SHORT = {"A": "Semantic", "B": "Hybrid", "C": "Hybrid + Reranker", "D": "Agentic"}
PLAIN = {
    "A": "Finds passages that mean the same as your question",
    "B": "Meaning search + exact-keyword search, results merged",
    "C": "A second AI re-reads the top 30 finds and re-orders them",
    "D": "An AI agent plans searches, checks results, searches again",
}
RAG_DEFINITION = (
    "RAG = Retrieval-Augmented Generation: the AI first retrieves passages from your documents, "
    "then generates an answer from them."
)
USE_WHEN = {
    "A": "You need fast, cheap answers to everyday questions. Start here.",
    "B": "Users type exact codes, IDs or product names.",
    "C": "The right answer is found but ranked too low, and a few extra seconds are fine.",
    "D": (
        "People ask in their own words, a wrong ‘I don’t know’ is costly, and quality matters "
        "more than speed or cost."
    ),
}


# Agentic RAG uses the Hybrid Search retriever (#2) as its search tool, not the reranker.
BUILDS_ON = {"B": "Builds on #1", "C": "Builds on #2", "D": "Uses #2 as its tool"}


def fmt_time(seconds: float) -> str:
    return f"{seconds:.1f} s"


def fmt_cost(usd: float) -> str:
    return f"${usd:.2f}"


def watch_out(numbers: Numbers) -> dict[str, str]:
    return {
        "A": "Similar-looking passages crowding out the right one.",
        "B": "It can make everyday-language questions worse.",
        "C": "Catch-all reference text fooling the ranker; much slower on a laptop CPU.",
        "D": f"≈{numbers.get('costRatio')}× cost, slower, and it can over-reach on unanswerable "
        "questions.",
    }


# ---------------------------------------------------------------- page scaffolding


def _page(
    numbers: Numbers,
    font: str,
    n: int,
    kicker: str,
    dark: bool = False,
    band: str | None = None,
    band_text: str | None = None,
    footer: str | None = None,
) -> Canvas:
    """A canvas with the coloured top band (kicker + page number) and the footer."""
    numbers.slide = f"slide-{n:02d}"
    c = Canvas(font, dark=dark)
    fill = band or (DARK_CARD if dark else SLATE)
    text = band_text or ("#F4F6F8" if (dark or band is None) else "#1B1F24")
    c.rect(0, 0, WIDTH, 110, fc=fill, ec="none", z=0.8)
    c.text(MARGIN, 55, kicker, 11, "bold", text, va="center")
    c.text(WIDTH - MARGIN, 55, f"{n} / {TOTAL}", 11, "bold", text, ha="right", va="center")
    c.footer(text=footer)
    return c


def _title(
    c: Canvas, text: str, y: float = 142, size: float = 24, width: float = CONTENT_W
) -> float:
    """The slide title; returns the y just below it."""
    return c.paragraph(MARGIN, y, text, size, width, "bold", factor=1.24)


def _series_page(numbers: Numbers, font: str, n: int, kicker: str, key: str) -> Canvas:
    return _page(numbers, font, n, kicker, band=SERIES[key], band_text=ON_SERIES[key])


# ---------------------------------------------------------------- reusable pieces

BODY = 11.0
SMALL = 10.0
WHITE = "#FFFFFF"


def _dots(c: Canvas, x: float, cy: float, right: int, tries: int, key: str) -> float:
    """One circle per try: filled when answered right, hollow when not. Returns the end x."""
    for i in range(tries):
        cx = x + 13 + i * 32
        if i < right:
            c.dot(cx, cy, 12, SERIES[key], z=4)
        else:
            c.dot(cx, cy, 11, DARK_CARD if c.dark else WHITE, ec="#9AA3AF", z=4)
    return x + tries * 32


def _score_group(c: Canvas, key: str, x: float, cy: float, right: int, tries: int) -> float:
    """badge + short name + dots + n/3, left to right; returns the end x."""
    c.badge(key, x + 16, cy, 16)
    c.text(x + 42, cy, SHORT[key], 11, "bold", va="center")
    name_w = c.measure(SHORT[key], 11, "bold")
    end = _dots(c, x + 42 + name_w + 12, cy, right, tries, key)
    c.text(end + 8, cy, f"{right}/{tries}", 12, "bold", va="center")
    return end + 8 + c.measure(f"{right}/{tries}", 12, "bold")


def _pill(
    c: Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    kind: str,
    value: str,
    key: str,
    size: float = 10.5,
) -> None:
    """A small rounded stat pill: icon (clock or coin) + value."""
    c.rect(x, y, w, h, fc=DARK_CARD if c.dark else WHITE, ec=c.hair, lw=0.8, radius=h / 2, z=1.0)
    col = shade(SERIES[key], 0.68)
    icon = clock_icon if kind == "clock" else coin_icon
    icon(c, x + h * 0.55, y + h / 2, h * 0.27, col)
    c.text(x + h * 0.98, y + h / 2, value, size, "bold", va="center")


def _flow_strip(
    c: Canvas, key: str, steps: list[str], cy: float, loop_from: int | None = None
) -> None:
    """Small isometric step tiles joined by arrows, with a label under each."""
    n = len(steps)
    pitch = CONTENT_W / n
    tile_w = 76.0
    centres = [MARGIN + pitch * (i + 0.5) for i in range(n)]
    for i, (cx, label) in enumerate(zip(centres, steps, strict=True)):
        draw_tile(c, cx, cy, tile_w, SERIES[key], thick=9)
        c.text(cx, cy + 1, str(i + 1), 11, "bold", ha="center", va="center")
        for j, line in enumerate(c.wrap(label, 9.5, pitch - 8, "bold")):
            c.text(cx, cy + 40 + j * 29, line, 9.5, "bold", ha="center")
        if i + 1 < n:
            c.arrow(
                (cx + tile_w / 2 + 8, cy), (centres[i + 1] - tile_w / 2 - 8, cy), lw=1.6, scale=14
            )
    if loop_from is not None:
        x_a, x_b = centres[loop_from], centres[loop_from - 1]
        c.arrow((x_a, cy - 30), (x_b, cy - 30), color=SERIES["D"], rad=0.2, lw=2.0, scale=14)
        c.text(x_a + 34, cy - 62, "not enough: search again", 9.5, "bold", va="center")


# ---------------------------------------------------------------- slide 1: cover


def slide_cover(numbers: Numbers, font: str) -> Canvas:
    c = _page(numbers, font, 1, "AN EXPERIMENT IN 4 CHAPTERS", dark=True)
    y = _title(c, "We gave 4 AI designs the same job. Only one clearly got better.", 160, 29)
    iso = Iso(WIDTH / 2, 0, 1.0)
    draw_floor(c, iso, WIDTH / 2, 880, 470, 190, 56, "#14253F", "#25395A", "#0B1626", 16)
    # the manual: a stack of pages, behind the towers
    stack = Iso(WIDTH / 2, 735, 1.0)
    stack_h = draw_stack(c, stack, -90, -70, 180, 140, 9, 8, "#F4F6F8")
    top = stack.project(0, 0, stack_h)
    label = f"Bank manual · {numbers.get('n_sections')} sections"
    c.text(top[0], y + 48, label, 12, "bold", ha="center")
    c.line(top[0], y + 90, top[0], top[1] - 52, color="#A9B4C2", lw=1.1)
    # four towers in front of it, heights proportional to right answers (no numbers: a teaser)
    correct = {x: int(numbers.get(f"{x}.correct")) for x in ARCHITECTURES}
    k = 170.0 / max(correct.values())
    step = 118.0
    piso = Iso(WIDTH / 2, 960, 1.0)
    for i, x in enumerate(ARCHITECTURES):
        u = (i - 1.5) * step * 0.5
        w = 62.0
        draw_cuboid(c, piso, u - w / 2, -u - w / 2, 0, w, w, correct[x] * k, SERIES[x])
        tp = piso.project(u, -u, correct[x] * k)
        c.badge(x, tp[0], tp[1], 17)
    c.text(MARGIN, 1176, "Swipe to see who won — and what it cost", 15, "bold")
    end = MARGIN + c.measure("Swipe to see who won — and what it cost", 15, "bold")
    c.arrow((end + 14, 1198), (end + 66, 1198), color="#F4F6F8", lw=2.4, scale=18)
    return c


# ---------------------------------------------------------------- slide 2: the job


def _step_card(
    c: Canvas, y: float, label: str, body: str, icon: Callable[[Canvas, float, float], None]
) -> float:
    inner_x = MARGIN + 180
    inner_w = WIDTH - MARGIN - 30 - inner_x
    lines = c.wrap(body, BODY + 1, inner_w)
    h = max(150.0, 78 + len(lines) * c.line_height(BODY + 1, 1.36))
    c.card(MARGIN, y, CONTENT_W, h, accent=SLATE)
    draw_tile(c, MARGIN + 98, y + h / 2 + 14, 124, "#8FA3BF", thick=12)
    icon(c, MARGIN + 98, y + h / 2 - 2)
    c.text(inner_x, y + 26, label, SMALL, "bold", c.muted)
    c.paragraph(inner_x, y + 62, body, BODY + 1, inner_w, factor=1.36)
    return y + h


def slide_job(numbers: Numbers, font: str) -> Canvas:
    c = _page(numbers, font, 2, "CHAPTER 1 · THE JOB")
    y = _title(c, "The job: answer questions from a bank’s manual")
    n_apis, n_sec = numbers.get("n_apis"), numbers.get("n_sections")
    n_ans, n_trick = numbers.get("n_answerable"), numbers.get("n_trick")
    reps, big_n = numbers.get("repetitions"), numbers.get("N")
    ink = SLATE
    steps: list[tuple[str, str, Callable[[Canvas, float, float], None]]] = [
        (
            "1 · THE MANUAL",
            f"A fictional bank’s API documentation — {n_apis} APIs, {n_sec} sections.",
            lambda cc, x, yy: book_icon(cc, x, yy, 74, ink),
        ),
        (
            "2 · THE EXAM",
            f"{n_ans} real questions, each asked {reps} times ({big_n} answers), plus "
            f"{n_trick} trick questions with no answer in the manual.",
            lambda cc, x, yy: question_icon(cc, x, yy, 74, ink),
        ),
        (
            "3 · THE GRADING",
            "Right or wrong? Says ‘I don’t know’ when it should? Makes anything up?",
            lambda cc, x, yy: check_icon(cc, x, yy, 66, ink),
        ),
    ]
    y += 30
    spans: list[tuple[float, float]] = []
    for label, body, icon in steps:
        bottom = _step_card(c, y, label, body, icon)
        spans.append((y, bottom))
        y = bottom + 30
    for (_, b0), (t1, _) in itertools.pairwise(spans):
        c.polyline(
            [(MARGIN + 98, b0 - 2), (MARGIN + 98, t1 + 2)],
            "#8FA3BF",
            2.4,
            dashed=True,
            z=1.1,
            round_caps=True,
        )
    lines = c.wrap(RAG_DEFINITION, BODY + 1, CONTENT_W - 70, "bold")
    h = len(lines) * c.line_height(BODY + 1, 1.36) + 48
    c.card(MARGIN, y, CONTENT_W, h, accent=SERIES["A"], fc=tint(SERIES["A"], 0.1))
    c.paragraph(MARGIN + 34, y + 24, RAG_DEFINITION, BODY + 1, CONTENT_W - 70, "bold", factor=1.36)
    return c


# ---------------------------------------------------------------- slide 3: contenders


def slide_contenders(numbers: Numbers, font: str) -> Canvas:
    c = _page(numbers, font, 3, "CHAPTER 2 · THE CONTENDERS")
    y = _title(c, "Four ways to build the same assistant") + 26
    h, gap = 196.0, 18.0
    for i, x in enumerate(ARCHITECTURES):
        top = y + i * (h + gap)
        c.card(MARGIN, top, CONTENT_W, h, accent=SERIES[x])
        technique_tile(c, x, MARGIN + 120, top + h / 2 - 4, 190)
        c.badge(x, MARGIN + 52, top + 38, 22)
        tx = MARGIN + 244
        tw = WIDTH - MARGIN - 28 - tx
        ty = c.paragraph(tx, top + 30, NAMES[x], 16, tw, "bold", factor=1.2)
        c.paragraph(tx, ty + 8, PLAIN[x], BODY, tw, color=c.muted, factor=1.34)
        if i > 0:
            label = BUILDS_ON[x]
            pw = c.measure(label, SMALL, "bold") + 36
            px, py = WIDTH - MARGIN - 24 - pw, top + h - 54
            c.rect(px, py, pw, 36, fc=tint(SERIES[x], 0.16), ec="none", radius=18)
            c.text(px + pw / 2, py + 18, label, SMALL, "bold", ha="center", va="center")
    c.text(
        WIDTH / 2,
        y + 4 * (h + gap) - 4,
        "Same manual, same questions, same AI model for all four.",
        SMALL,
        color=c.muted,
        ha="center",
    )
    return c


# ---------------------------------------------------------------- slides 4-7: report cards

HEADLINES = {
    "A": "The strong, simple baseline.",
    "B": "Sharper on exact terms, clumsier on everyday words.",
    "C": "A second opinion that got distracted.",
    "D": "Plans, checks, and digs again.",
}
ORDER_N = {"A": 1, "B": 2, "C": 3, "D": 4}


def _how_steps(key: str) -> list[str]:
    return {
        "A": ["Your question", "Find the 5 closest passages", "AI writes the answer"],
        "B": [
            "Your question",
            "Meaning + keyword search",
            "Merge the two lists",
            "AI writes the answer",
        ],
        "C": [
            "Your question",
            "Hybrid search: 30 candidates",
            "A second AI re-orders them",
            "AI writes the answer",
        ],
        "D": ["Plan the searches", "Search", "Enough found?", "Write the answer"],
    }[key]


def _score_card(c: Canvas, numbers: Numbers, key: str, y: float, h: float) -> None:
    right, total = int(numbers.get(f"{key}.correct")), int(numbers.get(f"{key}.attempts"))
    pct = numbers.get(f"{key}.pct")
    c.card(MARGIN, y, CONTENT_W, h, accent=SERIES[key])
    x0 = MARGIN + 36
    base = y + 90
    big = f"{right} / {total}"
    c.text(x0, base, big, 36, "bold", va="baseline")
    c.text(x0 + c.measure(big, 36, "bold") + 14, base, "right", 15, "bold", c.muted, va="baseline")
    c.text(WIDTH - MARGIN - 32, base, f"{pct}%", 30, "bold", ha="right", va="baseline")
    bar_w, bar_y = CONTENT_W - 68, y + h - 34
    c.rect(x0, bar_y, bar_w, 22, fc=tint(SERIES[key], 0.16), ec="none", radius=11)
    c.rect(
        x0, bar_y, max(22.0, bar_w * right / total), 22, fc=SERIES[key], ec="none", radius=11, z=1.3
    )


def _stat_tiles(c: Canvas, numbers: Numbers, key: str, y: float, h: float) -> None:
    gap = 18.0
    w = (CONTENT_W - 2 * gap) / 3
    col = shade(SERIES[key], 0.68)
    fr = int(numbers.get(f"{key}.false_refusal"))
    tiles = [
        ("clock", f"≈ {fmt_time(numbers.get(f'{key}.time_s'))}", "per answer (typical)"),
        ("coin", fmt_cost(numbers.get(f"{key}.cost_per_1000")), "per 1,000 answers (est.)"),
        ("q", str(fr), "wrong ‘I don’t know’"),
    ]
    for i, (kind, value, label) in enumerate(tiles):
        x = MARGIN + i * (w + gap)
        c.card(x, y, w, h, radius=14)
        cx, cy = x + 36, y + 36
        if kind == "clock":
            clock_icon(c, cx, cy, 16, col)
        elif kind == "coin":
            coin_icon(c, cx, cy, 16, col)
        else:
            c.dot(cx, cy, 16, WHITE, ec=col)
            c.text(cx, cy, "?", 11, "bold", col, ha="center", va="center")
        c.text(x + 66, y + 12, value, 16, "bold")
        c.text(x + 20, y + 62, label, 9.5, color=c.muted)


def _report_card(numbers: Numbers, font: str, n: int, key: str) -> Canvas:
    c = _series_page(numbers, font, n, f"CHAPTER 3 · REPORT CARD {ORDER_N[key]} OF 4", key)
    technique_tile(c, key, MARGIN + 80, 212, 156)
    c.badge(key, MARGIN + 18, 150, 20)
    tx = MARGIN + 180
    y = c.paragraph(tx, 140, NAMES[key], 22, WIDTH - MARGIN - tx, "bold", factor=1.15)
    c.paragraph(tx, y + 4, PLAIN[key], BODY, WIDTH - MARGIN - tx, color=c.muted, factor=1.34)
    c.text(MARGIN, 304, HEADLINES[key], 13, "bold")
    _flow_strip(c, key, _how_steps(key), 430, loop_from=2 if key == "D" else None)
    _score_card(c, numbers, key, 544, 140)
    _stat_tiles(c, numbers, key, 698, 96)
    return c


MOMENT_TOP = 810.0
MOMENT_H = 436.0
IN_X = MARGIN + 36
IN_W = CONTENT_W - 72


def _moment_card(
    c: Canvas, key: str, content_end: float, heading: str = "MOMENT THAT MATTERED"
) -> None:
    """The card behind a moment (drawn after its content so it fits it)."""
    c.card(
        MARGIN,
        MOMENT_TOP,
        CONTENT_W,
        min(MOMENT_H, content_end + 30 - MOMENT_TOP),
        accent=SERIES[key],
    )
    c.text(IN_X, MOMENT_TOP + 20, heading, SMALL, "bold", c.muted)


def _quote(c: Canvas, text: str, y: float) -> float:
    return c.paragraph(IN_X, y, f"“{text}”", BODY, IN_W, "bold", factor=1.3)


def _caption(c: Canvas, y: float, text: str) -> float:
    return c.paragraph(IN_X, y, text, BODY, IN_W, factor=1.36)


def _all_or(right: int, tries: int) -> str:
    wrong = tries - right
    return f"all {tries} times" if wrong == tries else f"{wrong} of {tries} times"


def _transition(
    c: Canvas, cy: float, left: tuple[str, int, int], right: tuple[str, int, int]
) -> None:
    end = _score_group(c, left[0], IN_X, cy, left[1], left[2])
    c.arrow((end + 22, cy), (end + 62, cy), color=c.muted, lw=2.0, scale=16)
    _score_group(c, right[0], end + 84, cy, right[1], right[2])


def _tuple(numbers: Numbers, q: str, key: str) -> tuple[str, int, int]:
    return key, numbers.get(f"{q}.{key}.right"), numbers.get(f"{q}.{key}.tries")


def slide_report_a(numbers: Numbers, font: str) -> Canvas:
    c = _report_card(numbers, font, 4, "A")
    y = _quote(c, numbers.get("q104.text"), MOMENT_TOP + 52)
    _score_group(c, "A", IN_X, y + 36, numbers.get("q104.A.right"), numbers.get("q104.A.tries"))
    end = _caption(
        c,
        y + 78,
        "Worded in everyday language, the question never matched the manual’s terms — "
        f"it missed {_all_or(numbers.get('q104.A.right'), numbers.get('q104.A.tries'))}.",
    )
    _moment_card(c, "A", end)
    return c


def slide_report_b(numbers: Numbers, font: str) -> Canvas:
    c = _report_card(numbers, font, 5, "B")
    y = MOMENT_TOP + 52
    for q in ("q125", "q108"):
        y = _quote(c, numbers.get(f"{q}.text"), y)
        _transition(c, y + 30, _tuple(numbers, q, "A"), _tuple(numbers, q, "B"))
        y += 68
    net = numbers.get("deltaB")
    end = _caption(
        c,
        y + 4,
        "Won when the question used the manual’s own words; lost when it did not. "
        f"Net: {net:+d} right.",
    )
    _moment_card(c, "B", end, "MOMENTS THAT MATTERED")
    return c


def slide_report_c(numbers: Numbers, font: str) -> Canvas:
    c = _report_card(numbers, font, 6, "C")
    y = _quote(c, numbers.get("q120.text"), MOMENT_TOP + 52)
    _transition(c, y + 34, _tuple(numbers, "q120", "B"), _tuple(numbers, "q120", "C"))
    pool, final = numbers.get("q120.pool_rank"), numbers.get("q120.final_rank")
    delta = numbers.get("deltaC")
    net = "no change in the total" if delta == 0 else f"{delta:+d} right in total"
    end = _caption(
        c,
        y + 76,
        f"The right passage was #{pool} among the 30 candidates; the reranker pushed it down to "
        f"#{final}. Over the whole exam: {net}, and ≈{numbers.get('slowC')}× slower than "
        "Semantic Search RAG.",
    )
    _moment_card(c, "C", end)
    return c


def slide_report_d(numbers: Numbers, font: str) -> Canvas:
    c = _report_card(numbers, font, 7, "D")
    y = _quote(c, numbers.get("q104.text"), MOMENT_TOP + 52)
    cy = y + 30
    for row, key_x in enumerate(ARCHITECTURES):
        t = _tuple(numbers, "q104", key_x)
        _score_group(c, key_x, IN_X, cy + row * 37, t[1], t[2])
    right_d, tries_d = numbers.get("q104.D.right"), numbers.get("q104.D.tries")
    outcome = "every time" if right_d == tries_d else f"{right_d} of {tries_d} times"
    end = _caption(
        c,
        cy + 3 * 37 + 32,
        f"It split the question into two searches — ‘{numbers.get('q104.D.query1')}’ and "
        f"‘{numbers.get('q104.D.query2')}’ — and got it right {outcome}.",
    )
    _moment_card(c, "D", end)
    return c


# ---------------------------------------------------------------- slides 8-11


def slide_break(numbers: Numbers, font: str) -> Canvas:
    c = _page(numbers, font, 8, "CHAPTER 4 · THE RESULTS", dark=True)
    y = c.paragraph(
        MARGIN,
        236,
        "Three designs scored almost the same. One pulled ahead.",
        31,
        CONTENT_W,
        "bold",
        factor=1.24,
    )
    vals = [numbers.get(f"{x}.correct") for x in ARCHITECTURES]
    y = (
        c.paragraph(
            MARGIN,
            y + 22,
            f"{vals[0]}, {vals[1]}, {vals[2]} and {vals[3]} right answers out of "
            f"{numbers.get('N')}.",
            14,
            CONTENT_W,
            color=c.muted,
            factor=1.3,
        )
        + 50
    )
    gap = 16.0
    w = (CONTENT_W - 3 * gap) / 4
    for i, x in enumerate(ARCHITECTURES):
        tx = MARGIN + i * (w + gap)
        c.card(tx, y, w, 440, radius=14, accent=SERIES[x])
        c.badge(x, tx + 38, y + 36, 17)
        technique_tile(c, x, tx + w / 2 + 4, y + 140, 170)
        c.text(tx + w / 2 + 4, y + 210, str(vals[i]), 34, "bold", ha="center")
        c.text(tx + w / 2 + 4, y + 326, "right answers", 9.5, color=c.muted, ha="center")
        for j, line in enumerate(c.wrap(SHORT[x], SMALL, w - 30, "bold")):
            c.text(tx + w / 2 + 4, y + 358 + j * 30, line, SMALL, "bold", ha="center")
    return c


def podium(
    c: Canvas,
    numbers: Numbers,
    base_y: float,
    max_h: float,
    spacing: float,
    tower_w: float,
    value_size: float = 20,
    floor_half_h: float = 80,
) -> list[float]:
    """Four isometric towers, heights proportional to right answers (base at zero).

    Returns each tower's centre x. The exact ``right/N`` is printed above every tower.
    """
    values = {x: int(numbers.get(f"{x}.correct")) for x in ARCHITECTURES}
    n = int(numbers.get("N"))
    scale = max_h / max(values.values())
    step = spacing / (2 * 0.8660254)
    iso = Iso(WIDTH / 2, base_y, 1.0)
    draw_floor(
        c,
        iso,
        WIDTH / 2,
        base_y,
        (WIDTH - 2 * MARGIN) / 2,
        floor_half_h,
        50,
        "#EEF0F3",
        "#CBD2DB",
        "#C3CAD4",
        14,
    )
    centres: list[float] = []
    for i, x in enumerate(ARCHITECTURES):
        u = (i - 1.5) * step
        h = values[x] * scale
        draw_cuboid(c, iso, u - tower_w / 2, -u - tower_w / 2, 0, tower_w, tower_w, h, SERIES[x])
        tx, ty = iso.project(u, -u, h)
        topv = iso.project(u - tower_w / 2, -u - tower_w / 2, h)
        c.badge(x, tx, ty, 16)
        c.text(tx, topv[1] - 10, f"{values[x]}/{n}", value_size, "bold", ha="center", va="bottom")
        centres.append(tx)
    return centres


def slide_podium(numbers: Numbers, font: str) -> Canvas:
    c = _page(numbers, font, 9, "CHAPTER 4 · THE RESULTS")
    y = _title(c, "Right answers, side by side")
    c.text(
        MARGIN,
        y + 6,
        f"Out of {numbers.get('N')} graded answers to questions that have an answer.",
        BODY,
        color=c.muted,
    )
    base_y = 790.0
    centres = podium(c, numbers, base_y, 360, 232, 84, 20, 84)
    for x, cx in zip(ARCHITECTURES, centres, strict=True):
        ty = base_y + 118
        lines = c.wrap(SHORT[x], 11.5, 200, "bold")
        for j, line in enumerate(lines):
            c.text(cx, ty + j * 34, line, 11.5, "bold", ha="center")
        py = ty + 40 + 34 * (len(lines) - 1)
        _pill(c, cx - 64, py + 6, 128, 40, "clock", fmt_time(numbers.get(f"{x}.time_s")), x)
        _pill(c, cx - 64, py + 54, 128, 40, "coin", fmt_cost(numbers.get(f"{x}.cost_per_1000")), x)
    c.text(
        MARGIN,
        1166,
        "Bars start at zero. Time is per answer (typical); cost is per 1,000 answers.",
        SMALL,
        color=c.muted,
    )
    c.text(
        MARGIN,
        1200,
        "Cost is an estimate at list price; the runs used a free tier.",
        SMALL,
        color=c.muted,
    )
    return c


def _paired_bar(
    c: Canvas, x: float, y: float, w: float, label: str, vals: tuple[int, int], of: int
) -> float:
    c.text(x, y, label, SMALL, "bold")
    y += 38
    for key, v in zip(("B", "D"), vals, strict=True):
        c.text(x, y + 13, SHORT[key], SMALL, color=c.muted, va="center")
        bx = x + 104
        bw = w - 104 - 70
        c.rect(bx, y, bw, 24, fc=tint(SERIES[key], 0.15), ec="none", radius=12)
        c.rect(bx, y, max(24.0, bw * v / of), 24, fc=SERIES[key], ec="none", radius=12, z=1.3)
        c.text(bx + bw + 12, y + 12, f"{v}/{of}", 11.5, "bold", va="center")
        y += 36
    return y


def slide_insights(numbers: Numbers, font: str) -> Canvas:
    c = _page(numbers, font, 10, "CHAPTER 4 · THE RESULTS")
    y = _title(c, "What actually made the difference") + 28
    x, w = IN_X, IN_W
    # insight 1
    body1 = (
        "Hybrid and Reranker re-ordered results, but the AI answered about as well whenever a "
        "relevant passage was in front of it."
    )
    h1 = 72 + len(c.wrap(body1, BODY, w)) * c.line_height(BODY, 1.36) + 22
    c.card(MARGIN, y, CONTENT_W, h1, accent=SERIES["B"])
    c.text(x, y + 22, "Better ranking ≠ better answers", 14, "bold")
    c.paragraph(x, y + 74, body1, BODY, w, factor=1.36)
    y += h1 + 22
    # insight 2
    q, sem = numbers.get("gain.questions"), numbers.get("gain.semantic")
    cmp_ = numbers.get("gain.comparison")
    lead = (
        f"{q} questions it answered better than Hybrid: {sem} in everyday language, {cmp_} "
        "comparing two parts of the manual."
    )
    tail = (
        "On multi-step questions it gathered complete information far more often, but got the "
        "same ones right."
    )
    n12 = int(numbers.get("D.multi_step_of"))
    top2 = y
    c.text(x, y + 22, "Agentic RAG won on everyday wording", 14, "bold")
    yy = c.paragraph(x, y + 74, lead, BODY, w, "bold", factor=1.36)
    yy = c.paragraph(x, yy + 10, tail, BODY, w, factor=1.36)
    yy = _paired_bar(
        c,
        x,
        yy + 18,
        w,
        "Gathered complete information",
        (numbers.get("B.multi_step_full"), numbers.get("D.multi_step_full")),
        n12,
    )
    yy = _paired_bar(
        c,
        x,
        yy + 10,
        w,
        "Got the answer right",
        (numbers.get("B.multi_correct"), numbers.get("D.multi_correct")),
        n12,
    )
    c.card(MARGIN, top2, CONTENT_W, yy + 14 - top2, accent=SERIES["D"])
    y = yy + 14 + 22
    # price tag
    made = int(numbers.get("D.made_up"))
    once = "Once" if made == 1 else f"{made} times"
    strip = (
        f"Agentic RAG: ≈{numbers.get('costRatio')}× the cost, ≈{numbers.get('timeRatio')}× the "
        f"time of Semantic Search RAG. {once}, it answered a trick question it should have "
        "declined."
    )
    h3 = len(c.wrap(strip, BODY, w, "bold")) * c.line_height(BODY, 1.36) + 44
    c.card(MARGIN, y, CONTENT_W, h3, fc="#FFF4D6", accent="#E69F00")
    c.paragraph(x, y + 22, strip, BODY, w, "bold", factor=1.36)
    return c


def slide_finale(numbers: Numbers, font: str) -> Canvas:
    c = _page(
        numbers,
        font,
        11,
        "CHAPTER 4 · THE VERDICT",
        dark=True,
        footer="Full code, data and method: " + REPO,
    )
    y = _title(c, "Which one should you use?") + 12
    table = cheat_rows(numbers)
    name_x = MARGIN + 82
    use_x = MARGIN + 262
    use_w = 340.0
    watch_x = use_x + use_w + 24
    watch_w = WIDTH - MARGIN - 24 - watch_x
    for x in ARCHITECTURES:
        row = table[x]
        pitch = c.line_height(SMALL, 1.34)
        use_lines = len(c.wrap(row.use_when, SMALL, use_w))
        watch_lines = len(c.wrap(row.watch_out, SMALL, watch_w))
        h = max(124.0, 94 + use_lines * pitch + 12, 50 + watch_lines * pitch + 12)
        c.card(MARGIN, y, CONTENT_W, h, accent=SERIES[x], radius=14)
        c.badge(x, MARGIN + 44, y + 40, 22)
        for j, line in enumerate(c.wrap(NAMES[x], 12, use_x - name_x - 16, "bold")):
            c.text(name_x, y + 22 + j * 36, line, 12, "bold")
        c.text(use_x, y + 12, "USE WHEN", 9.5, "bold", c.muted)
        evidence_pill(c, use_x, y + 65, row.evidence)
        c.paragraph(use_x, y + 94, row.use_when, SMALL, use_w, factor=1.34)
        c.text(watch_x, y + 12, "WATCH OUT FOR", 9.5, "bold", c.muted)
        c.paragraph(watch_x, y + 50, row.watch_out, SMALL, watch_w, factor=1.34)
        y += h + 8
    rule = "Start simple. Measure where it fails. Add one piece only when the failures point to it."
    lines = c.wrap(rule, 12, CONTENT_W - 64, "bold")
    h = len(lines) * c.line_height(12, 1.3) + 40
    y += 6
    if y + h > HEIGHT - 96:
        raise LayoutError(f"slide-11: closing banner ends at {y + h:.0f}px, into the footer")
    c.rect(MARGIN, y, CONTENT_W, h, fc="#E9FBF4", ec=SERIES["D"], lw=3.0, radius=14)
    c.paragraph(MARGIN + 32, y + 20, rule, 12, CONTENT_W - 64, "bold", color=NAVY, factor=1.3)
    return c


def build_slides(numbers: Numbers, font: str) -> list[Canvas]:
    """All eleven slides in order."""
    return [
        slide_cover(numbers, font),
        slide_job(numbers, font),
        slide_contenders(numbers, font),
        slide_report_a(numbers, font),
        slide_report_b(numbers, font),
        slide_report_c(numbers, font),
        slide_report_d(numbers, font),
        slide_break(numbers, font),
        slide_podium(numbers, font),
        slide_insights(numbers, font),
        slide_finale(numbers, font),
    ]
