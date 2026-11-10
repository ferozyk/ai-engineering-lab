"""Unit tests for the run plan, record helpers, charts and the report."""

from collections.abc import Callable
from pathlib import Path

import matplotlib.image as mpimg
import pytest

from ai_lab.benchmarking import simulated_pricing
from rag_experiment.evaluation import charts
from rag_experiment.evaluation.answer_analysis import AnswerSummary, summarise_answers
from rag_experiment.evaluation.answer_report import BANNER, LIMITATIONS
from rag_experiment.evaluation.answer_run import (
    AnswerRecord,
    PlannedAttempt,
    completed_attempts,
    latest_by_attempt,
    make_answer_run_id,
    plan_attempts,
)
from rag_experiment.evaluation.dataset import Question, QuestionConstraints
from rag_experiment.evaluation.retrieval_metrics import RetrievalSummary

pytestmark = pytest.mark.unit

RecordFactory = Callable[..., AnswerRecord]
EXP_ROOT = Path(__file__).resolve().parents[2]


def _question(qid: str) -> Question:
    return Question(
        id=qid,
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


def test_plan_is_repetition_major_and_seeded() -> None:
    questions = [_question(f"Q{i}") for i in range(1, 7)]
    plan = plan_attempts(questions, 3, 42)
    assert len(plan) == 18
    assert [p.repetition for p in plan] == [1] * 6 + [2] * 6 + [3] * 6
    for rep in (1, 2, 3):
        ids = [p.question.id for p in plan if p.repetition == rep]
        assert sorted(ids) == [q.id for q in questions]
    assert plan == plan_attempts(questions, 3, 42)
    assert [p.attempt_id for p in plan] != [p.attempt_id for p in plan_attempts(questions, 3, 43)]
    first = PlannedAttempt(questions[0], 2)
    assert first.attempt_id == "Q1-r2"


def test_run_ids() -> None:
    assert make_answer_run_id("dev", "dense", fake=False).endswith("Z-answers-dev-dense")
    assert make_answer_run_id("dev", "dense", fake=True).endswith("-answers-dev-dense-fake")
    both = make_answer_run_id("dev", "dense", fake=True, canary=True)
    assert both.endswith("-answers-dev-dense-canary-fake")


def test_latest_wins_and_completed_excludes_infra_errors(make_record: RecordFactory) -> None:
    failed = make_record(attempt_id="A-r1", outcome="infra_error")
    fixed = make_record(attempt_id="A-r1")
    only_failed = make_record(attempt_id="B-r1", outcome="infra_error")
    done = make_record(attempt_id="C-r1")
    records = [failed, only_failed, fixed, done]
    assert latest_by_attempt(records)["A-r1"] is fixed
    assert completed_attempts(records) == {"A-r1", "C-r1"}
    assert (
        completed_attempts([fixed, make_record(attempt_id="A-r1", outcome="infra_error")]) == set()
    )


def _summary(records: list[AnswerRecord]) -> AnswerSummary:
    return summarise_answers(
        records, [_question("Q01")], question_set="dev", pricing=simulated_pricing()
    )


def _retrieval_summary() -> RetrievalSummary:
    path = next((EXP_ROOT / "results" / "processed").glob("*retrieval-dev-dense")) / (
        "retrieval_summary.json"
    )
    return RetrievalSummary.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("simulated", [False, True])
def test_charts_are_written_as_png_and_svg(
    tmp_path: Path, make_record: RecordFactory, simulated: bool
) -> None:
    records = [
        make_record(attempt_id="Q01-r1", simulated=simulated),
        make_record(attempt_id="Q01-r2", repetition=2, context_hit=False, simulated=simulated),
        make_record(
            attempt_id="U1-r1",
            question_id="U1",
            category="unanswerable",
            must_abstain=True,
            outcome="refused",
            correct=None,
            false_refusal=None,
            correct_refusal=True,
            made_up_answer=False,
            simulated=simulated,
        ),
    ]
    ctx = charts.ChartContext(
        run_id="run-1", model_id="test/model", simulated=simulated, n_attempts=3
    )
    paths = charts.render_all(_summary(records), _retrieval_summary(), ctx, tmp_path, "note")
    names = sorted(p.name for p in paths)
    expected = {
        "retrieval_hit_at_k",
        "ha3_correctness_by_context",
        "guardrails",
        "latency_by_stage",
        "tokens_per_question",
    }
    assert names == sorted(f"{n}.{ext}" for n in expected for ext in ("png", "svg"))
    assert all(p.stat().st_size > 1000 for p in paths)
    assert mpimg.imread(tmp_path / "guardrails.png").shape[:2] == (1000, 1600)
    svg = (tmp_path / "guardrails.svg").read_text(encoding="utf-8")
    assert ("SIMULATED" in svg) is simulated


def test_charts_skip_retrieval_chart_without_a_summary(
    tmp_path: Path, make_record: RecordFactory
) -> None:
    ctx = charts.ChartContext(run_id="r", model_id="m", simulated=False, n_attempts=1)
    paths = charts.render_all(_summary([make_record()]), None, ctx, tmp_path)
    assert "retrieval_hit_at_k.png" not in {p.name for p in paths}
    assert len(paths) == 8


def test_limitations_match_the_methodology_document() -> None:
    text = (EXP_ROOT / "docs" / "evaluation-methodology.md").read_text(encoding="utf-8")
    section = text.split("## 9. Limitations", 1)[1]
    for item in LIMITATIONS:
        assert f"- {item}" in section
    assert "SIMULATED" in BANNER
