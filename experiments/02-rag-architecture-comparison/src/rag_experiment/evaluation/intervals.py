"""95% Wilson intervals for the per-category rates of the stress set.

The stress set has about 20 questions per category, so a single rate carries a wide margin of
error. The reports of the stress set show it next to every rate. Reports of the clean-corpus sets
are unchanged.
"""

from typing import TYPE_CHECKING

from ai_lab.benchmarking import wilson_interval
from rag_experiment.evaluation.retrieval_metrics import KS, RetrievalSummary

if TYPE_CHECKING:  # answer_analysis imports the run metadata, which imports the retrieval report
    from rag_experiment.evaluation.answer_analysis import AnswerSummary

STRESS_SET = "stress"
_NOTE = (
    "95% Wilson score intervals. With about 20 questions per category the intervals are wide: "
    "read them before comparing two rates."
)


def rate_with_interval(numerator: int, denominator: int) -> str:
    """``k/n = 0.xxx [low, high]``, or ``n/a (0)`` when nothing was asked."""
    if denominator == 0:
        return "n/a (0)"
    low, high = wilson_interval(numerator, denominator)
    return f"{numerator}/{denominator} = {numerator / denominator:.3f} [{low:.3f}, {high:.3f}]"


def retrieval_interval_lines(summary: RetrievalSummary) -> list[str]:
    """The Hit@K intervals per category, or nothing for a set other than the stress set."""
    if summary.question_set != STRESS_SET:
        return []
    header = ["group", "n"] + [f"Hit@{k}" for k in KS]
    lines = [
        "## Hit@K with 95% intervals (stress set)",
        "",
        _NOTE,
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    for name, group in [("overall", summary.overall), *summary.by_category.items()]:
        cells = [name, str(group.n)]
        cells += [rate_with_interval(round(group.hit[k] * group.n), group.n) for k in KS]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def answer_interval_lines(summary: "AnswerSummary") -> list[str]:
    """The answer-rate intervals per category, or nothing for a set other than the stress set."""
    if summary.question_set != STRESS_SET:
        return []
    lines = [
        "## Rates with 95% intervals (stress set)",
        "",
        _NOTE,
        "",
        "| group | correctness (answerable) | false refusal (answerable) "
        "| correct refusal (unanswerable) |",
        "|---|---|---|---|",
    ]
    for name, group in [("overall", summary.overall), *summary.by_category.items()]:
        cells = [
            rate_with_interval(r.numerator, r.denominator)
            for r in (group.answerable, group.false_refusals, group.correct_refusals)
        ]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines.append("")
    return lines
