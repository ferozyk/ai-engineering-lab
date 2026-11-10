"""Unit tests for the answer summary: verdict boundaries, applicability, percentiles, cost."""

from collections.abc import Callable

import pytest

from ai_lab.benchmarking import PricingSnapshot, simulated_pricing
from ai_lab.llm import Usage
from rag_experiment.evaluation.answer_analysis import AnswerSummary, summarise_answers
from rag_experiment.evaluation.answer_run import AnswerRecord
from rag_experiment.evaluation.dataset import Question, QuestionConstraints

pytestmark = pytest.mark.unit

RecordFactory = Callable[..., AnswerRecord]
PRICING = PricingSnapshot(
    source="same_model",
    priced_model="test/model",
    prompt_usd_per_token=1e-6,
    completion_usd_per_token=3e-6,
    captured_at=simulated_pricing().captured_at,
    note="test price",
)


def _questions() -> list[Question]:
    def q(qid: str, abstain: bool) -> Question:
        return Question(
            id=qid,
            question="?",
            category="unanswerable" if abstain else "semantic",
            expected_answer="",
            key_facts=() if abstain else ("f",),
            relevant_sources=() if abstain else ("d#/paths",),
            relevant_document_ids=() if abstain else ("d",),
            constraints=QuestionConstraints(must_cite=not abstain, must_abstain=abstain),
            paraphrase_of=None,
            notes="",
        )

    return [q("Q1", False), q("Q2", False), q("Q3", True)]


def _summary(records: list[AnswerRecord], question_set: str = "measured") -> AnswerSummary:
    return summarise_answers(records, _questions(), question_set=question_set, pricing=PRICING)


def _answerable(
    make_record: RecordFactory, n: int, *, hit: bool, correct: int, prefix: str = "H"
) -> list[AnswerRecord]:
    """``n`` answerable attempts, the first ``correct`` of them correct."""
    return [
        make_record(
            attempt_id=f"{prefix}{i}-r1",
            question_id=f"{prefix}{i}",
            context_hit=hit,
            correct=i < correct,
            outcome="answered" if i < correct else "refused",
            false_refusal=i >= correct,
        )
        for i in range(n)
    ]


def _refusals(make_record: RecordFactory, n: int, correct: int) -> list[AnswerRecord]:
    return [
        make_record(
            attempt_id=f"U{i}-r1",
            question_id=f"U{i}",
            category="unanswerable",
            must_abstain=True,
            context_hit=False,
            outcome="refused" if i < correct else "answered",
            correct=None,
            false_refusal=None,
            correct_refusal=i < correct,
            made_up_answer=i >= correct,
            citations_valid=None,
            cites_relevant=None,
        )
        for i in range(n)
    ]


def _verdict(summary: AnswerSummary, name: str) -> tuple[str, str]:
    v = next(v for v in summary.verdicts if v.hypothesis == name)
    return v.verdict, v.evidence


def test_ha3_boundaries(make_record: RecordFactory) -> None:
    # hit 8/10 = 0.80 (supported side); miss 1/5 = 0.20 (supported side)
    records = _answerable(make_record, 10, hit=True, correct=8) + _answerable(
        make_record, 5, hit=False, correct=1, prefix="M"
    )
    assert _verdict(_summary(records), "HA3")[0] == "supported"
    # hit 7/10 = 0.70 fails the hit half
    records = _answerable(make_record, 10, hit=True, correct=7) + _answerable(
        make_record, 5, hit=False, correct=0, prefix="M"
    )
    assert _verdict(_summary(records), "HA3")[0] == "not supported"
    # miss 2/5 = 0.40 fails the miss half
    records = _answerable(make_record, 10, hit=True, correct=10) + _answerable(
        make_record, 5, hit=False, correct=2, prefix="M"
    )
    assert _verdict(_summary(records), "HA3")[0] == "not supported"


def test_ha3_miss_half_not_testable_below_three(make_record: RecordFactory) -> None:
    records = _answerable(make_record, 10, hit=True, correct=9) + _answerable(
        make_record, 2, hit=False, correct=2, prefix="M"
    )
    verdict, evidence = _verdict(_summary(records), "HA3")
    assert verdict == "supported"
    assert "miss half not testable (n<3)" in evidence
    # a failing hit half is still a failure
    records = _answerable(make_record, 10, hit=True, correct=5)
    assert _verdict(_summary(records), "HA3")[0] == "not supported"


def test_ha3_not_testable_without_hits(make_record: RecordFactory) -> None:
    records = _answerable(make_record, 4, hit=False, correct=0, prefix="M")
    assert _verdict(_summary(records), "HA3")[0] == "not testable"


def test_ha4_boundaries(make_record: RecordFactory) -> None:
    assert _verdict(_summary(_refusals(make_record, 5, 4)), "HA4")[0] == "supported"  # 0.80
    assert _verdict(_summary(_refusals(make_record, 6, 4)), "HA4")[0] == "not supported"  # 0.67
    assert _verdict(_summary(_answerable(make_record, 3, hit=True, correct=3)), "HA4")[0] == (
        "not testable"
    )


def test_applicability_rules(make_record: RecordFactory) -> None:
    records = _answerable(make_record, 5, hit=True, correct=5) + _refusals(make_record, 3, 3)
    assert _verdict(_summary(records, "dev"), "HA3")[0] == "not applicable (development set)"
    assert _verdict(_summary(records, "dev"), "HA4")[0] == "not applicable (development set)"
    simulated = [r.model_copy(update={"simulated": True}) for r in records]
    assert _verdict(_summary(simulated, "measured"), "HA3")[0] == "not applicable (simulated)"
    assert _verdict(_summary(simulated, "dev"), "HA4")[0] == "not applicable (simulated)"
    assert _summary(simulated).simulated is True


def test_infra_errors_are_counted_but_excluded(make_record: RecordFactory) -> None:
    records = [
        *_answerable(make_record, 4, hit=True, correct=4),
        make_record(
            attempt_id="E-r1",
            question_id="E",
            outcome="infra_error",
            correct=None,
            false_refusal=None,
            citations_valid=None,
            cites_relevant=None,
            attempts=3,
            error_kind="server",
            usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        ),
    ]
    summary = _summary(records)
    assert (summary.n_attempts, summary.n_scored, summary.n_infra_errors) == (5, 4, 1)
    assert summary.overall.answerable.denominator == 4
    assert summary.requests.sent == 4 + 3 and summary.requests.failed == 3


def test_latest_record_per_attempt_wins_and_requests_use_all_records(
    make_record: RecordFactory,
) -> None:
    failed = make_record(
        outcome="infra_error", correct=None, false_refusal=None, attempts=3, error_kind="server"
    )
    retried = make_record(attempts=2)
    summary = _summary([failed, retried])
    assert (summary.n_attempts, summary.n_scored, summary.n_infra_errors) == (1, 1, 0)
    assert summary.requests.sent == 5 and summary.requests.failed == 3 + 1
    assert summary.requests.retried == 1 and summary.requests.infra_error_attempts == 1


def test_percentiles_tokens_and_cost(make_record: RecordFactory) -> None:
    records = [
        make_record(
            attempt_id=f"A{i}-r1",
            question_id=f"A{i}",
            generation_ms=float(g),
            embed_ms=1.0,
            search_ms=1.0,
            total_ms=float(g) + 2.0,
            usage=Usage(
                prompt_tokens=100 * (i + 1),
                completion_tokens=10,
                total_tokens=100 * (i + 1) + 10,
                reasoning_tokens=5,
            ),
        )
        for i, g in enumerate([100, 200, 300, 400, 500])
    ]
    summary = _summary(records)
    gen = summary.latency_ms["generation"]
    assert (gen.n, gen.p50, gen.p95) == (5, 300.0, 480.0)
    assert summary.latency_ms["total"].p50 == 302.0
    prompt = summary.tokens["prompt"]
    assert (prompt.mean, prompt.p50, prompt.p95) == (300.0, 300.0, 480.0)
    assert summary.tokens["reasoning"].mean == 5.0
    expected = sum(100 * (i + 1) * 1e-6 + 10 * 3e-6 for i in range(5))
    assert summary.cost.run_total_usd == pytest.approx(expected)
    assert summary.cost.per_1000_questions_usd == pytest.approx(expected / 5 * 1000)
    assert "Estimated" in summary.cost.note and summary.cost.source == "same_model"
    assert summary.tokens_by_category["semantic"] == (110, 210, 310, 410, 510)


def test_reasoning_stats_absent_when_not_reported(make_record: RecordFactory) -> None:
    assert "reasoning" not in _summary([make_record()]).tokens


def test_guardrails_groundedness_and_citations(make_record: RecordFactory) -> None:
    records = [
        make_record(
            attempt_id="Q1-r1",
            unsupported_identifiers=("name:x", "name:y"),
            invented_identifiers=("name:y",),
        ),
        make_record(
            attempt_id="Q1-r2",
            unsupported_identifiers=("name:x",),
            citations_valid=False,
            cites_relevant=False,
        ),
        make_record(attempt_id="Q1-r3"),
        make_record(
            attempt_id="Q2-r1",
            question_id="Q2",
            outcome="invalid_answer",
            correct=False,
            false_refusal=False,
            citations_valid=None,
            cites_relevant=None,
        ),
        *_refusals(make_record, 2, 1),
    ]
    summary = _summary(records)
    g = summary.guardrails
    assert (g.correct_refusal.numerator, g.correct_refusal.denominator) == (1, 2)
    assert (g.made_up_answer.numerator, g.made_up_answer.denominator) == (1, 2)
    assert g.false_refusal.numerator == 0 and g.false_refusal.denominator == 4
    gr = summary.groundedness
    assert gr.with_unsupported.numerator == 2 and gr.with_unsupported.denominator == 5
    assert gr.with_invented.numerator == 1
    assert gr.top_unsupported[0] == ("name:x", 2)
    cit = summary.citations
    assert (cit.citations_valid.numerator, cit.citations_valid.denominator) == (2, 3)
    assert cit.cites_relevant.numerator == 2


def test_per_question_agreement(make_record: RecordFactory) -> None:
    records = [
        make_record(attempt_id="Q1-r1", question_id="Q1"),
        make_record(
            attempt_id="Q1-r2",
            question_id="Q1",
            repetition=2,
            outcome="refused",
            correct=False,
            false_refusal=True,
        ),
        make_record(attempt_id="Q2-r1", question_id="Q2"),
        make_record(attempt_id="Q2-r2", question_id="Q2", repetition=2),
    ]
    by_id = {q.question_id: q for q in _summary(records).per_question}
    assert by_id["Q1"].correct == 1 and by_id["Q1"].repetitions_agree is False
    assert by_id["Q2"].correct == 2 and by_id["Q2"].repetitions_agree is True


def test_empty_records_are_rejected() -> None:
    with pytest.raises(ValueError, match="no answer records"):
        _summary([])
