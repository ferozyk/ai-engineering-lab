"""Hypothesis verdicts per retrieval architecture, computed mechanically from frozen criteria.

``dense`` (architecture A) has HA1 and HA2 (retrieval) and HA3 and HA4 (answers); their logic
stays in ``retrieval_metrics`` and ``answer_analysis`` and is only dispatched from here.
``hybrid`` (architecture B) has HB1 and HB2 (retrieval) and HB3 (answers), defined in
``docs/evaluation-methodology.md`` section 8. ``rerank`` (architecture C) has HC1 and HC2
(retrieval) and HC3 (answers), defined in the same section. ``bm25`` is a diagnostic run with no
hypotheses.

Architecture B's criteria quote architecture A's measured values, and C's quote B's. They are read
from the committed files of the earlier architecture and checked against the numbers frozen in the
methodology; any mismatch is an error.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from rag_experiment.evaluation.answer_analysis import AnswerSummary
from rag_experiment.evaluation.retrieval_metrics import (
    QuestionRetrieval,
    RetrievalSummary,
    Verdict,
    compute_verdicts,
    hit5_ratio,
)

BASELINE_RETRIEVAL_RUN = "20261110T204546Z-retrieval-measured-dense"
BASELINE_ANSWER_RUN = "20261110T221134Z-answers-measured-dense"

HB1_CATEGORIES = ("exact_identifier", "schema")
HB1_MIN, HB1_DENOMINATOR = 8, 11
HB2_MIN, HB2_DENOMINATOR = 31, 34
HB3_MIN_RATE = 0.755

HB1_CRITERION = f"Hit@1 over exact_identifier + schema >= {HB1_MIN}/{HB1_DENOMINATOR}"
HB2_CRITERION = f"overall Hit@5 >= {HB2_MIN}/{HB2_DENOMINATOR}"
HB3_CRITERION = f"correctness over answerable attempts >= {HB3_MIN_RATE}"

BASELINE_B_RETRIEVAL_RUN = "20261113T232754Z-retrieval-measured-hybrid"
BASELINE_B_ANSWER_RUN = "20261116T224508Z-answers-measured-hybrid"

HC1_MIN_MRR, HC1_DENOMINATOR = 0.85, 34
HC2_MIN, HC2_DENOMINATOR = 32, 34
HC3_MIN, HC3_DENOMINATOR = 80, 102

HC1_CRITERION = f"MRR (top 10) over answerable questions >= {HC1_MIN_MRR:.2f}"
HC2_CRITERION = f"overall Hit@5 >= {HC2_MIN}/{HC2_DENOMINATOR}"
HC3_CRITERION = f"correct answerable attempts >= {HC3_MIN}/{HC3_DENOMINATOR}"

NOT_APPLICABLE_DEV = "not applicable (development set)"
NOT_APPLICABLE_SIMULATED = "not applicable (simulated)"
PENDING_ANSWERS = "pending (needs generation)"


class BaselineError(ValueError):
    """Architecture A's committed values are missing or differ from the frozen numbers."""


@dataclass(frozen=True)
class Baseline:
    """Architecture A's measured counts as ``(numerator, denominator)``."""

    hb1: tuple[int, int]
    hb2: tuple[int, int]
    hb3: tuple[int, int]


FROZEN_BASELINE = Baseline(hb1=(6, 11), hb2=(32, 34), hb3=(77, 102))


def load_baseline(results_dir: Path) -> Baseline:
    """Read A's committed run files and check them against :data:`FROZEN_BASELINE`."""
    retrieval = results_dir / "raw" / BASELINE_RETRIEVAL_RUN / "retrieval.jsonl"
    answers = results_dir / "processed" / BASELINE_ANSWER_RUN / "answer_summary.json"
    try:
        lines = retrieval.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines if line.strip()]
        summary = json.loads(answers.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BaselineError(f"architecture A baseline file missing: {exc}") from exc
    scored = [r for r in records if not r["excluded"]]
    group = [r for r in scored if r["category"] in HB1_CATEGORIES]
    ratio = summary["overall"]["answerable"]
    found = Baseline(
        hb1=(sum(1 for r in group if r["hit"]["1"] == 1.0), len(group)),
        hb2=(sum(1 for r in scored if r["hit"]["5"] == 1.0), len(scored)),
        hb3=(int(ratio["numerator"]), int(ratio["denominator"])),
    )
    if found != FROZEN_BASELINE:
        raise BaselineError(
            f"architecture A baseline {found} differs from the frozen values {FROZEN_BASELINE}"
        )
    return found


@dataclass(frozen=True)
class BaselineB:
    """Architecture B's measured MRR and counts."""

    mrr: float
    hc2: tuple[int, int]
    hc3: tuple[int, int]


FROZEN_BASELINE_B_MRR = 0.7823529411764706
FROZEN_BASELINE_B = BaselineB(mrr=FROZEN_BASELINE_B_MRR, hc2=(30, 34), hc3=(78, 102))


def load_baseline_b(results_dir: Path) -> BaselineB:
    """Read B's committed run files and check them against the numbers frozen in the methodology."""
    retrieval = results_dir / "raw" / BASELINE_B_RETRIEVAL_RUN / "retrieval.jsonl"
    answers = results_dir / "processed" / BASELINE_B_ANSWER_RUN / "answer_summary.json"
    try:
        lines = retrieval.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines if line.strip()]
        summary = json.loads(answers.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BaselineError(f"architecture B baseline file missing: {exc}") from exc
    scored = [r for r in records if not r["excluded"]]
    if not scored:
        raise BaselineError("architecture B baseline has no answerable questions")
    ratio = summary["overall"]["answerable"]
    mrr = sum(r["reciprocal_rank"] for r in scored) / len(scored)
    found = BaselineB(
        mrr=mrr,
        hc2=(sum(1 for r in scored if r["hit"]["5"] == 1.0), len(scored)),
        hc3=(int(ratio["numerator"]), int(ratio["denominator"])),
    )
    if (
        round(found.mrr, 3) != 0.782
        or abs(found.mrr - FROZEN_BASELINE_B_MRR) > 1e-12
        or found.hc2 != FROZEN_BASELINE_B.hc2
        or found.hc3 != FROZEN_BASELINE_B.hc3
    ):
        raise BaselineError(
            f"architecture B baseline {found} differs from the frozen values {FROZEN_BASELINE_B}"
        )
    return found


def _pair(value: tuple[int, int]) -> str:
    return f"{value[0]}/{value[1]}"


def _rate(num: int, den: int) -> str:
    return f"{num / den:.3f}" if den else "n/a"


def _hb1(records: Sequence[QuestionRetrieval], frozen: bool, base: Baseline) -> Verdict:
    group = [r for r in records if not r.excluded and r.category in HB1_CATEGORIES]
    hits = sum(1 for r in group if r.hit[1] == 1.0)
    evidence = (
        f"Hit@1 = {hits}/{len(group)} = {_rate(hits, len(group))}; "
        f"architecture A: {_pair(base.hb1)}"
    )
    if not frozen:
        verdict = NOT_APPLICABLE_DEV
    elif len(group) != HB1_DENOMINATOR:
        verdict = "not testable"
        evidence += f"; expected {HB1_DENOMINATOR} questions in the group"
    else:
        verdict = "supported" if hits >= HB1_MIN else "not supported"
    return Verdict(hypothesis="HB1", criterion=HB1_CRITERION, verdict=verdict, evidence=evidence)


def _hb2(records: Sequence[QuestionRetrieval], frozen: bool, base: Baseline) -> Verdict:
    scored = [r for r in records if not r.excluded]
    hits = sum(1 for r in scored if r.hit[5] == 1.0)
    evidence = (
        f"Hit@5 = {hits}/{len(scored)} = {_rate(hits, len(scored))}; "
        f"architecture A: {_pair(base.hb2)}"
    )
    if not frozen:
        verdict = NOT_APPLICABLE_DEV
    elif len(scored) != HB2_DENOMINATOR:
        verdict = "not testable"
        evidence += f"; expected {HB2_DENOMINATOR} answerable questions"
    else:
        verdict = "supported" if hits >= HB2_MIN else "not supported"
    return Verdict(hypothesis="HB2", criterion=HB2_CRITERION, verdict=verdict, evidence=evidence)


def _hc1(records: Sequence[QuestionRetrieval], frozen: bool, base: BaselineB) -> Verdict:
    scored = [r for r in records if not r.excluded]
    mrr = sum(r.reciprocal_rank for r in scored) / len(scored) if scored else 0.0
    evidence = f"MRR = {mrr:.3f}; architecture B: {base.mrr:.3f}"
    if not frozen:
        verdict = NOT_APPLICABLE_DEV
    elif len(scored) != HC1_DENOMINATOR:
        verdict = "not testable"
        evidence += f"; expected {HC1_DENOMINATOR} answerable questions, found {len(scored)}"
    else:
        verdict = "supported" if mrr >= HC1_MIN_MRR - 1e-9 else "not supported"
    return Verdict(hypothesis="HC1", criterion=HC1_CRITERION, verdict=verdict, evidence=evidence)


def _hc2(records: Sequence[QuestionRetrieval], frozen: bool, base: BaselineB) -> Verdict:
    scored = [r for r in records if not r.excluded]
    hits = sum(1 for r in scored if r.hit[5] == 1.0)
    evidence = (
        f"Hit@5 = {hits}/{len(scored)} = {_rate(hits, len(scored))}; "
        f"architecture B: {_pair(base.hc2)}"
    )
    if not frozen:
        verdict = NOT_APPLICABLE_DEV
    elif len(scored) != HC2_DENOMINATOR:
        verdict = "not testable"
        evidence += f"; expected {HC2_DENOMINATOR} answerable questions"
    else:
        verdict = "supported" if hits >= HC2_MIN else "not supported"
    return Verdict(hypothesis="HC2", criterion=HC2_CRITERION, verdict=verdict, evidence=evidence)


def hc3_verdict(
    numerator: int, denominator: int, applicability: str | None, base: BaselineB
) -> Verdict:
    """HC3 from the correct/answerable attempt counts of an answer run (compared as a count)."""
    evidence = (
        f"correct {numerator}/{denominator} = {_rate(numerator, denominator)}; "
        f"architecture B: {_pair(base.hc3)}"
    )
    if applicability is not None:
        verdict = applicability
    elif denominator != HC3_DENOMINATOR:
        verdict = "not testable"
        evidence += f"; expected {HC3_DENOMINATOR} answerable attempts"
    else:
        verdict = "supported" if numerator >= HC3_MIN else "not supported"
    return Verdict(hypothesis="HC3", criterion=HC3_CRITERION, verdict=verdict, evidence=evidence)


def hb3_verdict(
    numerator: int, denominator: int, applicability: str | None, base: Baseline
) -> Verdict:
    """HB3 from the correct/answerable attempt counts of an answer run."""
    evidence = (
        f"correct {numerator}/{denominator} = {_rate(numerator, denominator)}; "
        f"architecture A: {_pair(base.hb3)}"
    )
    if applicability is not None:
        verdict = applicability
    elif denominator == 0:
        verdict = "not testable"
    elif numerator / denominator >= HB3_MIN_RATE - 1e-9:
        verdict = "supported"
    else:
        verdict = "not supported"
    return Verdict(hypothesis="HB3", criterion=HB3_CRITERION, verdict=verdict, evidence=evidence)


def _dense_retrieval(
    records: Sequence[QuestionRetrieval], frozen: bool, _results_dir: Path
) -> tuple[Verdict, ...]:
    return compute_verdicts(
        hit5_ratio(records, ("semantic", "endpoint_discovery")),
        hit5_ratio(records, ("exact_identifier",)),
        frozen,
    )


def _hybrid_retrieval(
    records: Sequence[QuestionRetrieval], frozen: bool, results_dir: Path
) -> tuple[Verdict, ...]:
    base = load_baseline(results_dir)
    pending = Verdict(
        hypothesis="HB3", criterion=HB3_CRITERION, verdict=PENDING_ANSWERS, evidence=""
    )
    return (_hb1(records, frozen, base), _hb2(records, frozen, base), pending)


def _rerank_retrieval(
    records: Sequence[QuestionRetrieval], frozen: bool, results_dir: Path
) -> tuple[Verdict, ...]:
    base = load_baseline_b(results_dir)
    pending = Verdict(
        hypothesis="HC3", criterion=HC3_CRITERION, verdict=PENDING_ANSWERS, evidence=""
    )
    return (_hc1(records, frozen, base), _hc2(records, frozen, base), pending)


# Registry: retriever name -> retrieval-time verdicts. A retriever absent here has none.
_RETRIEVAL: dict[str, Callable[[Sequence[QuestionRetrieval], bool, Path], tuple[Verdict, ...]]] = {
    "dense": _dense_retrieval,
    "hybrid": _hybrid_retrieval,
    "rerank": _rerank_retrieval,
}


_ANSWER_HYPOTHESES = frozenset({"hybrid", "rerank"})


def has_hypotheses(retriever: str) -> bool:
    """Whether the retriever has pre-registered hypotheses."""
    return retriever in _RETRIEVAL


def apply_retrieval_verdicts(
    summary: RetrievalSummary,
    records: Sequence[QuestionRetrieval],
    retriever: str,
    results_dir: Path,
) -> RetrievalSummary:
    """The summary with the retriever's own verdicts. Dense summaries are returned unchanged."""
    if retriever == "dense":
        return summary
    compute = _RETRIEVAL.get(retriever)
    verdicts = (
        () if compute is None else compute(records, summary.question_set == "measured", results_dir)
    )
    return summary.model_copy(update={"verdicts": verdicts})


def apply_answer_verdicts(
    summary: AnswerSummary, retriever: str, results_dir: Path
) -> AnswerSummary:
    """The answer summary with the retriever's own verdicts (dense: unchanged)."""
    if retriever == "dense":
        return summary
    if retriever not in _ANSWER_HYPOTHESES:
        return summary.model_copy(update={"verdicts": ()})
    applicability: str | None = None
    if summary.simulated:
        applicability = NOT_APPLICABLE_SIMULATED
    elif summary.question_set != "measured":
        applicability = NOT_APPLICABLE_DEV
    ratio = summary.overall.answerable
    if retriever == "rerank":
        verdict = hc3_verdict(
            ratio.numerator, ratio.denominator, applicability, load_baseline_b(results_dir)
        )
    else:
        verdict = hb3_verdict(
            ratio.numerator, ratio.denominator, applicability, load_baseline(results_dir)
        )
    return summary.model_copy(update={"verdicts": (verdict,)})
