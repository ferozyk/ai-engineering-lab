"""Derive every number shown on the shared visuals from committed result files.

``Numbers`` is a registry: each value is stored with its source file and derivation, and the
renderers read values only through ``Numbers.get``, so ``numbers.json`` lists exactly what appears
on a slide.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from rag_experiment.evaluation.answer_run import AnswerRecord, latest_by_attempt

ARCHITECTURES = ("A", "B", "C", "D")
COMPARISON_PATH = "results/processed/comparisons/a-b-c-d/comparison.json"
Scalar = int | float | str


class VisualsDataError(ValueError):
    """A value the visuals need is missing or inconsistent."""


def round_half_up(value: float, digits: int = 0) -> float:
    """Ordinary rounding (2.5 -> 3), not Python's round-half-to-even."""
    quantum = Decimal(1).scaleb(-digits)
    return float(Decimal(repr(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def percent(numerator: int, denominator: int) -> int:
    """Whole-number percentage, rounded half up."""
    if denominator <= 0:
        raise VisualsDataError("percentage over an empty denominator")
    return int(round_half_up(100 * numerator / denominator))


def dig(data: Mapping[str, Any], path: str, source: str) -> Any:
    """Follow a dotted path through nested mappings; a missing key is a clear error."""
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            raise VisualsDataError(f"{source}: missing '{path}' (stopped at '{part}')")
        node = node[part]
    return node


@dataclass(frozen=True)
class NumberEntry:
    """One displayed number with where it comes from."""

    value: Scalar
    source: str
    derivation: str


@dataclass
class Numbers:
    """Registry of displayed numbers; ``slide`` names the page currently being drawn."""

    entries: dict[str, NumberEntry] = field(default_factory=dict)
    used: dict[str, set[str]] = field(default_factory=dict)
    slide: str = ""

    def add(self, key: str, value: Scalar, source: str, derivation: str) -> None:
        self.entries[key] = NumberEntry(value, source, derivation)

    def get(self, key: str) -> Any:
        if key not in self.entries:
            raise VisualsDataError(f"no such number: {key}")
        self.used.setdefault(key, set()).add(self.slide)
        return self.entries[key].value

    def used_entries(self) -> dict[str, dict[str, Any]]:
        return {
            key: {
                "value": self.entries[key].value,
                "source": self.entries[key].source,
                "derivation": self.entries[key].derivation,
                "slides": sorted(self.used[key]),
            }
            for key in sorted(self.used)
        }


@dataclass(frozen=True)
class RunInputs:
    """The committed files of one answer run, already parsed."""

    run_id: str
    summary: Mapping[str, Any]
    comparison: Mapping[str, Any]
    metadata: Mapping[str, Any]
    records: Sequence[AnswerRecord]


@dataclass(frozen=True)
class Setup:
    """Facts shared by the four runs and the dataset."""

    chunk_count: int
    n_apis: int
    n_answerable_questions: int
    n_trick_questions: int
    question_text: Mapping[str, str]
    q120_pool_rank: int
    q120_final_rank: int


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualsDataError(f"cannot read {path}: {exc}") from exc


def check_same_setup(runs: Mapping[str, RunInputs]) -> tuple[str, str]:
    """All four runs must share the model and the question set; returns ``(model, checksum)``."""
    models = {
        k: str(dig(r.metadata, "model_id", f"{r.run_id}/run_metadata.json"))
        for k, r in runs.items()
    }
    sums = {
        k: str(dig(r.metadata, "question_set_checksum", f"{r.run_id}/run_metadata.json"))
        for k, r in runs.items()
    }
    if len(set(models.values())) != 1:
        raise VisualsDataError(f"runs used different models: {models}")
    if len(set(sums.values())) != 1:
        raise VisualsDataError(f"runs used different question sets: {sums}")
    return next(iter(models.values())), next(iter(sums.values()))


def _fraction(summary: Mapping[str, Any], path: str, run: str) -> tuple[int, int]:
    node = dig(summary, path, f"{run}/answer_summary.json")
    return int(dig(node, "numerator", path)), int(dig(node, "denominator", path))


def _attempts(records: Sequence[AnswerRecord], question_id: str) -> list[AnswerRecord]:
    found = [r for r in latest_by_attempt(records).values() if r.question_id == question_id]
    if not found:
        raise VisualsDataError(f"no records for question {question_id}")
    return sorted(found, key=lambda r: r.repetition)


def _add_arch(numbers: Numbers, x: str, run: RunInputs) -> None:
    summ = f"results/processed/{run.run_id}/answer_summary.json"
    cn, cd = _fraction(run.summary, "overall.answerable", run.run_id)
    fn, fd = _fraction(run.summary, "overall.false_refusals", run.run_id)
    rn, rd = _fraction(run.summary, "overall.correct_refusals", run.run_id)
    mn, md = _fraction(run.summary, "guardrails.made_up_answer", run.run_id)
    p50 = float(dig(run.summary, "latency_ms.total.p50", summ))
    cost = float(dig(run.summary, "cost.per_1000_questions_usd", summ))
    cmp_correct = dig(run.comparison, "correct", COMPARISON_PATH)
    if (int(cmp_correct["numerator"]), int(cmp_correct["denominator"])) != (cn, cd):
        raise VisualsDataError(f"{run.run_id}: comparison.json disagrees with answer_summary.json")
    calls = float(dig(run.comparison, "model_calls_mean", COMPARISON_PATH))
    full = dig(run.comparison, "multi_endpoint_full_coverage", COMPARISON_PATH)
    numbers.add(f"{x}.correct", cn, summ, "overall.answerable.numerator")
    numbers.add(f"{x}.attempts", cd, summ, "overall.answerable.denominator")
    numbers.add(f"{x}.pct", percent(cn, cd), summ, "round-half-up(100 * numerator / denominator)")
    numbers.add(f"{x}.false_refusal", fn, summ, "overall.false_refusals.numerator")
    numbers.add(f"{x}.false_refusal_of", fd, summ, "overall.false_refusals.denominator")
    numbers.add(f"{x}.correct_refusal", rn, summ, "overall.correct_refusals.numerator")
    numbers.add(f"{x}.trick_attempts", rd, summ, "overall.correct_refusals.denominator")
    numbers.add(f"{x}.made_up", mn, summ, "guardrails.made_up_answer.numerator")
    numbers.add(f"{x}.made_up_of", md, summ, "guardrails.made_up_answer.denominator")
    numbers.add(
        f"{x}.time_s", round_half_up(p50 / 1000, 1), summ, "latency_ms.total.p50 / 1000, 1 decimal"
    )
    numbers.add(
        f"{x}.cost_per_1000",
        round_half_up(cost, 2),
        summ,
        "cost.per_1000_questions_usd, 2 decimals (estimated)",
    )
    numbers.add(
        f"{x}.calls_mean",
        round_half_up(calls, 2),
        COMPARISON_PATH,
        f"answer_runs.{run.run_id}.model_calls_mean, 2 decimals",
    )
    numbers.add(
        f"{x}.multi_step_full",
        int(full["numerator"]),
        COMPARISON_PATH,
        f"answer_runs.{run.run_id}.multi_endpoint_full_coverage.numerator",
    )
    numbers.add(
        f"{x}.multi_step_of",
        int(full["denominator"]),
        COMPARISON_PATH,
        f"answer_runs.{run.run_id}.multi_endpoint_full_coverage.denominator",
    )
    numbers.add(f"{x}._p50_raw", p50, summ, "latency_ms.total.p50 (ms, unrounded; used for ratios)")
    numbers.add(
        f"{x}._cost_raw", cost, summ, "cost.per_1000_questions_usd (unrounded; used for ratios)"
    )


def build_numbers(runs: Mapping[str, RunInputs], setup: Setup) -> Numbers:
    """All numbers of the visuals, with their sources."""
    if tuple(runs) != ARCHITECTURES:
        raise VisualsDataError(f"expected runs {ARCHITECTURES}, got {tuple(runs)}")
    check_same_setup(runs)
    numbers = Numbers()
    for x, run in runs.items():
        _add_arch(numbers, x, run)
    raw = {
        x: (
            float(numbers.entries[f"{x}._p50_raw"].value),
            float(numbers.entries[f"{x}._cost_raw"].value),
        )
        for x in runs
    }
    c = {x: int(numbers.entries[f"{x}.correct"].value) for x in runs}
    attempts = int(numbers.entries["A.attempts"].value)
    metadata_src = f"results/raw/{runs['A'].run_id}/run_metadata.json"
    n_attempts = int(dig(runs["A"].summary, "n_scored", "answer_summary.json"))
    reps = int(dig(runs["A"].metadata, "run.repetitions", metadata_src))
    numbers.add("N", attempts, "answer_summary.json", "overall.answerable.denominator")
    numbers.add(
        "n_attempts", n_attempts, "answer_summary.json", "n_scored (answerable + trick attempts)"
    )
    numbers.add("repetitions", reps, metadata_src, "run.repetitions")
    numbers.add(
        "n_sections",
        setup.chunk_count,
        "results/raw/*-retrieval-measured-dense/ingest.json",
        "index_build.chunks",
    )
    numbers.add(
        "n_apis", setup.n_apis, "datasets/corpus/*.yaml", "count of API specification files"
    )
    numbers.add(
        "n_answerable",
        setup.n_answerable_questions,
        "datasets/evaluation/questions-measured.jsonl",
        "questions with must_abstain = false",
    )
    numbers.add(
        "n_trick",
        setup.n_trick_questions,
        "datasets/evaluation/questions-measured.jsonl",
        "questions with must_abstain = true",
    )
    if setup.n_answerable_questions * reps != attempts:
        raise VisualsDataError("answerable questions x repetitions does not match the attempts")
    numbers.add("deltaB", c["B"] - c["A"], "derived", "correct B - correct A")
    numbers.add("deltaC", c["C"] - c["B"], "derived", "correct C - correct B")
    numbers.add("deltaD", c["D"] - c["A"], "derived", "correct D - correct A")
    numbers.add(
        "slowC",
        int(round_half_up(raw["C"][0] / raw["A"][0])),
        "derived",
        "round(total p50 C / total p50 A)",
    )
    numbers.add(
        "timeRatio",
        int(round_half_up(raw["D"][0] / raw["A"][0])),
        "derived",
        "round(total p50 D / total p50 A)",
    )
    numbers.add(
        "costRatio",
        round_half_up(raw["D"][1] / raw["A"][1], 1),
        "derived",
        "round(cost D / cost A, 1)",
    )
    _add_examples(numbers, runs, setup)
    _add_gains(numbers, runs)
    return numbers


MOMENT_QUESTIONS = ("Q104", "Q125", "Q108", "Q120")


def _add_examples(numbers: Numbers, runs: Mapping[str, RunInputs], setup: Setup) -> None:
    """Per-question scores of the "moments that mattered", straight from the answer records."""
    for qid in MOMENT_QUESTIONS:
        key = qid.lower()
        text = setup.question_text.get(qid)
        if text is None:
            raise VisualsDataError(f"question {qid} not found")
        numbers.add(
            f"{key}.text",
            text.replace("`", ""),
            "datasets/evaluation/questions-measured.jsonl",
            f"{qid}.question, backticks removed",
        )
        for x, run in runs.items():
            rows = _attempts(run.records, qid)
            src = f"results/raw/{run.run_id}/answers.jsonl"
            numbers.add(
                f"{key}.{x}.right",
                sum(1 for r in rows if r.correct),
                src,
                f"{qid} attempts with correct = true",
            )
            numbers.add(f"{key}.{x}.tries", len(rows), src, f"{qid} attempts")
    d_first = _attempts(runs["D"].records, "Q104")[0]
    if len(d_first.queries) != 2:
        raise VisualsDataError(f"expected 2 agent queries for Q104, got {len(d_first.queries)}")
    d_src = f"results/raw/{runs['D'].run_id}/answers.jsonl"
    numbers.add("q104.D.query1", d_first.queries[0], d_src, "Q104-r1 queries[0]")
    numbers.add("q104.D.query2", d_first.queries[1], d_src, "Q104-r1 queries[1]")
    numbers.add(
        "q120.pool_rank",
        setup.q120_pool_rank,
        COMPARISON_PATH,
        "per_question.Q120.pool_first_relevant_rank (rerank retrieval run): rank of the right "
        "passage among the candidates handed to the reranker",
    )
    numbers.add(
        "q120.final_rank",
        setup.q120_final_rank,
        COMPARISON_PATH,
        "per_question.Q120.first_relevant_rank (rerank retrieval run): rank after reranking",
    )


def _correct_by_question(run: RunInputs) -> tuple[dict[str, int], dict[str, str]]:
    counts: dict[str, int] = {}
    categories: dict[str, str] = {}
    for r in latest_by_attempt(run.records).values():
        if r.must_abstain or r.outcome == "infra_error":
            continue
        counts[r.question_id] = counts.get(r.question_id, 0) + (1 if r.correct else 0)
        categories[r.question_id] = r.category
    return counts, categories


def _add_gains(numbers: Numbers, runs: Mapping[str, RunInputs]) -> None:
    """Where D's extra right answers over B came from, and the false-refusal range of A-C."""
    b, cat = _correct_by_question(runs["B"])
    d, _ = _correct_by_question(runs["D"])
    gains = sorted(q for q in d if d[q] > b.get(q, 0))
    by_cat: dict[str, int] = {}
    for q in gains:
        by_cat[cat[q]] = by_cat.get(cat[q], 0) + 1
    extra = set(by_cat) - {"semantic", "comparison"}
    if extra:
        raise VisualsDataError(f"D's gains over B include other categories: {sorted(extra)}")
    src = "results/raw/<run>/answers.jsonl (B and D)"
    how = "questions where D has more correct attempts than B"
    numbers.add("gain.questions", len(gains), src, how)
    numbers.add("gain.semantic", by_cat.get("semantic", 0), src, how + ", category semantic")
    numbers.add("gain.comparison", by_cat.get("comparison", 0), src, how + ", category comparison")
    for x in ("B", "D"):
        total = sum(n for q, n in (b if x == "B" else d).items() if cat[q] == "multi_endpoint")
        numbers.add(
            f"{x}.multi_correct", total, src, "correct attempts on multi_endpoint questions"
        )
    frs = [int(numbers.entries[f"{x}.false_refusal"].value) for x in ("A", "B", "C")]
    numbers.add("frMin", min(frs), "answer_summary.json", "min false refusals over A-C")
    numbers.add("frMax", max(frs), "answer_summary.json", "max false refusals over A-C")
