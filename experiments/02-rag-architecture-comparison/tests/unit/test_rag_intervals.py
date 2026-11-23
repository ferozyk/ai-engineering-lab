"""Wilson intervals appear in the stress-set reports and nowhere else."""

from collections.abc import Callable

import pytest

from ai_lab.benchmarking import simulated_pricing, wilson_interval
from rag_experiment.evaluation.answer_analysis import summarise_answers
from rag_experiment.evaluation.answer_run import AnswerRecord
from rag_experiment.evaluation.dataset import Question, QuestionConstraints
from rag_experiment.evaluation.intervals import (
    answer_interval_lines,
    rate_with_interval,
    retrieval_interval_lines,
)
from rag_experiment.evaluation.retrieval_metrics import QuestionRetrieval, RankedChunk, summarize

pytestmark = pytest.mark.unit

RecordFactory = Callable[..., AnswerRecord]
ZERO = {1: 0.0, 3: 0.0, 5: 0.0, 10: 0.0}


def _rec(qid: str, category: str, rank: int | None) -> QuestionRetrieval:
    hit = {k: 1.0 if rank is not None and rank <= k else 0.0 for k in ZERO}
    return QuestionRetrieval(
        run_id="r",
        question_id=qid,
        category=category,
        paraphrase_of=None,
        retriever="dense",
        k=10,
        excluded=False,
        ranked=(RankedChunk(rank=1, chunk_id="d:c", score=0.5, relevant=rank == 1),),
        relevant_chunk_ids=("d:c",),
        n_relevant_sources=1,
        hit=hit,
        recall=dict(hit),
        precision=dict(ZERO),
        reciprocal_rank=0.0 if rank is None else 1 / rank,
        first_relevant_rank=rank,
        embed_ms=1.0,
        search_ms=1.0,
    )


def test_rate_with_interval_text() -> None:
    low, high = wilson_interval(8, 20)
    assert rate_with_interval(8, 20) == f"8/20 = 0.400 [{low:.3f}, {high:.3f}]"
    assert rate_with_interval(0, 0) == "n/a (0)"


def test_retrieval_intervals_only_for_the_stress_set() -> None:
    records = [_rec("Q1", "version_lookalike", 1), _rec("Q2", "version_lookalike", None)]
    assert retrieval_interval_lines(summarize("r", "measured", records, [])) == []
    lines = retrieval_interval_lines(summarize("r", "stress", records, []))
    text = "\n".join(lines)
    assert "95% intervals (stress set)" in text and "Wilson" in text
    row = next(line for line in lines if line.startswith("| version_lookalike"))
    assert "1/2 = 0.500 [0.095, 0.905]" in row  # Hit@1 of 2 questions


def _questions() -> list[Question]:
    return [
        Question(
            id="Q1",
            question="?",
            category="semantic",
            expected_answer="",
            key_facts=("f",),
            relevant_sources=("d#/paths",),
            relevant_document_ids=("d",),
            constraints=QuestionConstraints(must_cite=True, must_abstain=False),
            paraphrase_of=None,
            notes="",
        )
    ]


def test_answer_intervals_only_for_the_stress_set(make_record: RecordFactory) -> None:
    records = [
        make_record(attempt_id=f"Q{i}-r1", question_id=f"Q{i}", correct=i < 3, simulated=False)
        for i in range(4)
    ]
    measured = summarise_answers(
        records, _questions(), question_set="measured", pricing=simulated_pricing()
    )
    assert answer_interval_lines(measured) == []
    stress = summarise_answers(
        records, _questions(), question_set="stress", pricing=simulated_pricing()
    )
    lines = answer_interval_lines(stress)
    assert any("95% intervals (stress set)" in line for line in lines)
    row = next(line for line in lines if line.startswith("| semantic"))
    assert row.startswith("| semantic | 3/4 = 0.750 [")
    assert "n/a (0)" in row  # no unanswerable attempts in the category
