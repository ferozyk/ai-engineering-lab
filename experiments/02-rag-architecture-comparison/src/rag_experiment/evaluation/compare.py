"""Compare committed runs side by side. Reads processed summaries and raw records only.

No model, no request and no interpretation: the report is tables of numbers copied from the runs.
Output::

    processed/comparisons/<name>/comparison.json
    reports/comparisons/<name>/comparison.md
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from rag_experiment.evaluation.answer_analysis import AnswerSummary
from rag_experiment.evaluation.retrieval_metrics import (
    DIAGNOSTIC_TEXT,
    KS,
    RatioValue,
    RetrievalSummary,
    Verdict,
)

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class RetrievalRun:
    """A committed retrieval run: summary and first relevant rank per question."""

    run_id: str
    retriever: str
    summary: RetrievalSummary
    first_relevant_rank: dict[str, int | None]
    category: dict[str, str]
    excluded: frozenset[str]
    # Rerank runs only: 1-based position of the first relevant chunk in the candidate pool.
    pool_first_relevant_rank: dict[str, int | None] = field(default_factory=dict)


@dataclass(frozen=True)
class AnswerRun:
    """A committed answer run: its summary."""

    run_id: str
    retriever: str
    summary: AnswerSummary


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def load_retrieval_run(results_base: Path, run_id: str) -> RetrievalRun:
    """Load a committed retrieval run (not a dry run)."""
    meta = json.loads(_read(results_base / "raw" / run_id / "run_metadata.json"))
    summary = RetrievalSummary.model_validate_json(
        _read(results_base / "processed" / run_id / "retrieval_summary.json")
    )
    ranks: dict[str, int | None] = {}
    categories: dict[str, str] = {}
    excluded: set[str] = set()
    pool_ranks: dict[str, int | None] = {}
    for line in _read(results_base / "raw" / run_id / "retrieval.jsonl").splitlines():
        record = json.loads(line)
        ranks[record["question_id"]] = record["first_relevant_rank"]
        categories[record["question_id"]] = record["category"]
        if "pool_first_relevant_rank" in record:
            pool_ranks[record["question_id"]] = record["pool_first_relevant_rank"]
        if record["excluded"]:
            excluded.add(record["question_id"])
    return RetrievalRun(
        run_id, meta["retriever"], summary, ranks, categories, frozenset(excluded), pool_ranks
    )


def load_answer_run(results_base: Path, run_id: str) -> AnswerRun:
    """Load a committed answer run (not a dry run)."""
    meta = json.loads(_read(results_base / "raw" / run_id / "run_metadata.json"))
    summary = AnswerSummary.model_validate_json(
        _read(results_base / "processed" / run_id / "answer_summary.json")
    )
    return AnswerRun(run_id, meta["retriever"], summary)


# ------------------------------------------------------------------------------ formatting


def _ratio(value: RatioValue) -> str:
    if value.value is None:
        return "n/a"
    return f"{value.numerator}/{value.denominator} ({value.value:.3f})"


def _rank(value: int | None) -> str:
    return "not in top 10" if value is None else str(value)


def _pool_rank(value: int | None) -> str:
    return "not in candidates" if value is None else str(value)


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _verdict_lines(verdicts: Sequence[Verdict]) -> list[str]:
    if not verdicts:
        return [DIAGNOSTIC_TEXT]
    return _table(
        ["hypothesis", "criterion", "verdict", "evidence"],
        [[v.hypothesis, v.criterion, v.verdict, v.evidence] for v in verdicts],
    )


# ------------------------------------------------------------------------------ comparison


def build_comparison(
    retrieval: Sequence[RetrievalRun], answers: Sequence[AnswerRun]
) -> dict[str, object]:
    """The machine-readable comparison (every number is copied from a run)."""
    sets = {r.summary.question_set for r in retrieval} | {a.summary.question_set for a in answers}
    if len(sets) > 1:
        raise ValueError(f"runs use different question sets: {sorted(sets)}")
    categories = sorted({c for r in retrieval for c in r.summary.by_category})
    retrieval_rows: dict[str, dict[str, object]] = {}
    for r in retrieval:
        s = r.summary
        retrieval_rows[r.run_id] = {
            "retriever": r.retriever,
            "question_set": s.question_set,
            "n_answerable": s.overall.n,
            "hit": {str(k): s.overall.hit[k] for k in KS},
            "recall_at_5": s.overall.recall[5],
            "mrr": s.overall.mrr,
            "latency_total_p50_ms": s.latency_total_ms.p50,
            "latency_rerank_p50_ms": (
                None if s.latency_rerank_ms is None else s.latency_rerank_ms.p50
            ),
            "pool_hit": None if s.pool_hit is None else s.pool_hit.model_dump(),
            "hit_at_1_by_category": {c: s.by_category[c].hit[1] for c in s.by_category},
            "hit_at_5_by_category": {c: s.by_category[c].hit[5] for c in s.by_category},
            "verdicts": [v.model_dump() for v in s.verdicts],
        }
    answer_rows: dict[str, dict[str, object]] = {}
    for a in answers:
        s2 = a.summary
        g = s2.guardrails
        answer_rows[a.run_id] = {
            "retriever": a.retriever,
            "question_set": s2.question_set,
            "simulated": s2.simulated,
            "correct": s2.overall.answerable.model_dump(),
            "false_refusal": g.false_refusal.model_dump(),
            "correct_refusal": g.correct_refusal.model_dump(),
            "made_up_answer": g.made_up_answer.model_dump(),
            "with_invented_identifiers": s2.groundedness.with_invented.model_dump(),
            "citations_valid": s2.citations.citations_valid.model_dump(),
            "generation_p50_ms": s2.latency_ms["generation"].p50,
            "generation_p95_ms": s2.latency_ms["generation"].p95,
            "rerank_p50_ms": s2.latency_ms["rerank"].p50 if "rerank" in s2.latency_ms else None,
            "total_p50_ms": s2.latency_ms["total"].p50,
            "mean_total_tokens": s2.tokens["total"].mean,
            "estimated_cost_per_1000_questions_usd": s2.cost.per_1000_questions_usd,
            "cost_source": s2.cost.source,
            "verdicts": [v.model_dump() for v in s2.verdicts],
        }
    per_question: dict[str, dict[str, object]] = {}
    if retrieval:
        first = retrieval[0]
        for qid in first.first_relevant_rank:
            per_question[qid] = {
                "category": first.category[qid],
                "excluded": qid in first.excluded,
                "first_relevant_rank": {
                    r.run_id: r.first_relevant_rank.get(qid) for r in retrieval
                },
                "correct": {
                    a.run_id: f"{q.correct}/{q.attempts}"
                    for a in answers
                    for q in a.summary.per_question
                    if q.question_id == qid
                },
            }
            pools = {
                r.run_id: r.pool_first_relevant_rank.get(qid)
                for r in retrieval
                if r.pool_first_relevant_rank
            }
            if pools:
                per_question[qid]["pool_first_relevant_rank"] = pools
    return {
        "question_set": next(iter(sets)) if sets else None,
        "retrieval_runs": retrieval_rows,
        "answer_runs": answer_rows,
        "categories": categories,
        "per_question": per_question,
    }


def render_comparison(
    retrieval: Sequence[RetrievalRun], answers: Sequence[AnswerRun], name: str
) -> str:
    """Markdown report: numbers only, no interpretation."""
    out: list[str] = [f"# Comparison: {name}", ""]
    out += ["Generated from committed run summaries; no model was called.", ""]
    if retrieval:
        header = ["measure", *(f"{r.retriever} ({r.run_id})" for r in retrieval)]
        rows: list[list[str]] = [
            ["answerable questions", *(str(r.summary.overall.n) for r in retrieval)]
        ]
        for k in KS:
            rows.append([f"Hit@{k}", *(f"{r.summary.overall.hit[k]:.3f}" for r in retrieval)])
        rows.append(["Recall@5", *(f"{r.summary.overall.recall[5]:.3f}" for r in retrieval)])
        rows.append(["MRR", *(f"{r.summary.overall.mrr:.3f}" for r in retrieval)])
        rows.append(
            [
                "latency p50, retrieval total (ms)",
                *(f"{r.summary.latency_total_ms.p50:.2f}" for r in retrieval),
            ]
        )
        rows.append(
            [
                "latency p50, rerank (ms)",
                *(
                    "-"
                    if r.summary.latency_rerank_ms is None
                    else f"{r.summary.latency_rerank_ms.p50:.2f}"
                    for r in retrieval
                ),
            ]
        )
        rows.append(
            [
                "relevant chunk among candidates",
                *(
                    "-" if r.summary.pool_hit is None else _ratio(r.summary.pool_hit)
                    for r in retrieval
                ),
            ]
        )
        categories = sorted({c for r in retrieval for c in r.summary.by_category})
        for metric, k in (("Hit@1", 1), ("Hit@5", 5)):
            for c in categories:
                rows.append(
                    [
                        f"{metric} {c}",
                        *(
                            f"{r.summary.by_category[c].hit[k]:.3f} "
                            f"(n={r.summary.by_category[c].n})"
                            if c in r.summary.by_category
                            else "n/a"
                            for r in retrieval
                        ),
                    ]
                )
        out += ["## Retrieval", "", *_table(header, rows), ""]
    if answers:
        header = ["measure", *(f"{a.retriever} ({a.run_id})" for a in answers)]
        arows: list[list[str]] = []
        arows.append(
            ["correctness (answerable)", *(_ratio(a.summary.overall.answerable) for a in answers)]
        )
        arows.append(
            [
                "false refusal (answerable)",
                *(_ratio(a.summary.guardrails.false_refusal) for a in answers),
            ]
        )
        arows.append(
            [
                "correct refusal (unanswerable)",
                *(_ratio(a.summary.guardrails.correct_refusal) for a in answers),
            ]
        )
        arows.append(
            [
                "made-up answer (unanswerable)",
                *(_ratio(a.summary.guardrails.made_up_answer) for a in answers),
            ]
        )
        arows.append(
            [
                "answers with invented identifiers",
                *(_ratio(a.summary.groundedness.with_invented) for a in answers),
            ]
        )
        arows.append(
            ["citation validity", *(_ratio(a.summary.citations.citations_valid) for a in answers)]
        )
        arows.append(
            [
                "generation p50 (ms)",
                *(f"{a.summary.latency_ms['generation'].p50:.0f}" for a in answers),
            ]
        )
        arows.append(
            [
                "generation p95 (ms)",
                *(f"{a.summary.latency_ms['generation'].p95:.0f}" for a in answers),
            ]
        )
        arows.append(
            [
                "rerank p50 (ms)",
                *(
                    f"{a.summary.latency_ms['rerank'].p50:.0f}"
                    if "rerank" in a.summary.latency_ms
                    else "-"
                    for a in answers
                ),
            ]
        )
        arows.append(
            ["total p50 (ms)", *(f"{a.summary.latency_ms['total'].p50:.0f}" for a in answers)]
        )
        arows.append(
            ["mean total tokens", *(f"{a.summary.tokens['total'].mean:.0f}" for a in answers)]
        )
        arows.append(
            [
                "estimated cost per 1,000 questions (USD, estimated)",
                *(f"{a.summary.cost.per_1000_questions_usd:.4f}" for a in answers),
            ]
        )
        out += ["## Answers", "", *_table(header, arows), ""]
    if retrieval:
        first = retrieval[0]
        pooled = [r for r in retrieval if r.pool_first_relevant_rank]
        header = [
            "question",
            "category",
            *(f"first relevant rank: {r.retriever}" for r in retrieval),
            *(f"candidate rank: {r.retriever}" for r in pooled),
            *(f"correct: {a.retriever} ({a.run_id})" for a in answers),
        ]
        qrows: list[list[str]] = []
        for qid in first.first_relevant_rank:
            if qid in first.excluded:
                continue
            row = [qid, first.category[qid]]
            row += [_rank(r.first_relevant_rank.get(qid)) for r in retrieval]
            row += [_pool_rank(r.pool_first_relevant_rank.get(qid)) for r in pooled]
            for a in answers:
                match = [q for q in a.summary.per_question if q.question_id == qid]
                row.append(f"{match[0].correct}/{match[0].attempts}" if match else "n/a")
            qrows.append(row)
        out += ["## Per question", "", *_table(header, qrows), ""]
    out += ["## Verdicts", ""]
    for r in retrieval:
        out += [
            f"### Retrieval: {r.retriever} ({r.run_id})",
            "",
            *_verdict_lines(r.summary.verdicts),
            "",
        ]
    for a in answers:
        out += [
            f"### Answers: {a.retriever} ({a.run_id})",
            "",
            *_verdict_lines(a.summary.verdicts),
            "",
        ]
    return "\n".join(out)


def run_compare(
    results_base: Path,
    retrieval_ids: Sequence[str],
    answer_ids: Sequence[str],
    name: str | None,
) -> dict[str, Path]:
    """Load the runs, write the JSON and the Markdown report, return their paths."""
    name = name or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if not _NAME.match(name):
        raise ValueError(f"invalid comparison name {name!r}")
    retrieval = [load_retrieval_run(results_base, i) for i in retrieval_ids]
    answers = [load_answer_run(results_base, i) for i in answer_ids]
    data = build_comparison(retrieval, answers)
    json_path = results_base / "processed" / "comparisons" / name / "comparison.json"
    report_path = results_base / "reports" / "comparisons" / name / "comparison.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path.write_text(render_comparison(retrieval, answers, name) + "\n", encoding="utf-8")
    return {"json": json_path, "report": report_path}
