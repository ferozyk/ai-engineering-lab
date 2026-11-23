"""The "which RAG pattern when" cheat sheet, with the strength of evidence behind each row.

Experiment 02 tested every pattern on one small, clean corpus. Each "use when" line is therefore
labelled by what this experiment actually showed for it:

- MEASURED: the experiment's results support it directly.
- HINT ONLY: a small-sample signal (a few questions), not a measured improvement in answers.
- NOT SHOWN HERE: the usual reason to choose the pattern, which this corpus did not reproduce.

The "watch out for" lines are all measured findings of this experiment.
"""

from dataclasses import dataclass

from rag_experiment.visuals.data import Numbers
from rag_experiment.visuals.draw import Canvas

MEASURED = "MEASURED"
HINT = "HINT ONLY"
NOT_SHOWN = "NOT SHOWN HERE"

EVIDENCE_MEANING = {
    MEASURED: "our results support it",
    HINT: "a small-sample signal",
    NOT_SHOWN: "the usual reason to pick it; not seen in this test",
}


@dataclass(frozen=True)
class Row:
    use_when: str
    evidence: str
    watch_out: str


def rows(numbers: Numbers) -> dict[str, Row]:
    """One row per technique; numbers in the text are read from ``numbers``."""
    made_up = int(numbers.get("D.made_up"))
    once = "once" if made_up == 1 else f"{made_up} times"
    return {
        "A": Row(
            "Small, tidy documents and fast, cheap answers. Start here.",
            MEASURED,
            "Questions worded far from the documents' own terms.",
        ),
        "B": Row(
            "Users type exact codes, IDs or product names.",
            HINT,
            "Made everyday-language questions worse here.",
        ),
        "C": Row(
            "Right passage found but ranked too low; seconds don't matter.",
            NOT_SHOWN,
            f"Fooled by catch-all text; ≈{numbers.get('slowC')}× slower than Semantic.",
        ),
        "D": Row(
            "Users ask in their own words; a wrong ‘I don’t know’ hurts.",
            MEASURED,
            f"≈{numbers.get('costRatio')}× cost, ≈{numbers.get('timeRatio')}× time; "
            f"{once} answered a trick question.",
        ),
    }


def evidence_pill(c: Canvas, x: float, cy: float, label: str, size: float = 9.5) -> float:
    """A small rounded label; returns its width. Text carries the meaning, colour supports it."""
    w = c.measure(label, size, "bold") + 26
    h = size * 2.78 * 1.55
    y = cy - h / 2
    if label == MEASURED:
        c.rect(x, y, w, h, fc="#1E8E6A", ec="none", radius=h / 2, z=1.6)
        color = "#FFFFFF"
    elif label == HINT:
        c.rect(x, y, w, h, fc="none", ec="#E6A100", lw=1.6, radius=h / 2, z=1.6)
        color = "#F2B84B" if c.dark else "#8A5A00"
    else:
        c.rect(x, y, w, h, fc="none", ec=c.muted, lw=1.2, radius=h / 2, z=1.6)
        color = c.muted
    c.text(x + 13, cy, label, size, "bold", color, va="center")
    return w
