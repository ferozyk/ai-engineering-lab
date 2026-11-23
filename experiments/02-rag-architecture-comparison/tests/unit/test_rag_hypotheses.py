"""Unit tests for the per-architecture hypothesis registry (A is unchanged, B is new)."""

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from ai_lab.benchmarking import PricingSnapshot, simulated_pricing
from rag_experiment.evaluation.answer_analysis import AnswerSummary, summarise_answers
from rag_experiment.evaluation.answer_run import AnswerRecord
from rag_experiment.evaluation.dataset import Question, QuestionConstraints
from rag_experiment.evaluation.hypotheses import (
    BASELINE_ANSWER_RUN,
    BASELINE_B_ANSWER_RUN,
    BASELINE_B_RETRIEVAL_RUN,
    BASELINE_RETRIEVAL_RUN,
    FROZEN_BASELINE,
    FROZEN_BASELINE_B,
    BaselineError,
    apply_answer_verdicts,
    apply_retrieval_verdicts,
    has_hypotheses,
    hb3_verdict,
    hc3_verdict,
    load_baseline,
    load_baseline_b,
)
from rag_experiment.evaluation.retrieval_metrics import (
    QuestionRetrieval,
    Verdict,
    summarize,
)

pytestmark = pytest.mark.unit

RESULTS = Path(__file__).resolve().parents[2] / "results"
RecordFactory = Callable[..., AnswerRecord]
HB1_GROUP = ("exact_identifier",) * 6 + ("schema",) * 5


def _rec(qid: str, category: str, hit1: bool, hit5: bool) -> QuestionRetrieval:
    hits = {1: float(hit1), 3: float(hit5), 5: float(hit5), 10: float(hit5)}
    return QuestionRetrieval(
        run_id="r",
        question_id=qid,
        category=category,
        paraphrase_of=None,
        retriever="hybrid",
        k=10,
        excluded=False,
        ranked=(),
        relevant_chunk_ids=("c",),
        n_relevant_sources=1,
        hit=hits,
        recall=dict(hits),
        precision=dict(hits),
        reciprocal_rank=1.0 if hit1 else 0.0,
        first_relevant_rank=1 if hit1 else None,
        embed_ms=1.0,
        search_ms=1.0,
    )


def _records(
    hb1_hits: int, hit5_total: int, n_group: int = 11, n_other: int = 23
) -> list[QuestionRetrieval]:
    """``n_group`` HB1-group questions (the first ``hb1_hits`` hit at 1) and ``n_other`` others;
    exactly ``hit5_total`` questions hit within the top 5 (group hits count)."""
    out: list[QuestionRetrieval] = []
    for i in range(n_group):
        out.append(_rec(f"G{i}", HB1_GROUP[i % 11], i < hb1_hits, i < hb1_hits))
    remaining = hit5_total - hb1_hits
    for i in range(n_other):
        out.append(_rec(f"O{i}", "semantic", False, i < remaining))
    return out


def _verdicts(
    records: list[QuestionRetrieval], retriever: str, set_name: str = "measured"
) -> tuple[Verdict, ...]:
    summary = summarize("r", set_name, records, [])
    return apply_retrieval_verdicts(summary, records, retriever, RESULTS).verdicts


def _by_name(verdicts: tuple[Verdict, ...]) -> dict[str, Verdict]:
    return {v.hypothesis: v for v in verdicts}


def test_hb1_boundary() -> None:
    low = _by_name(_verdicts(_records(7, 33), "hybrid"))["HB1"]
    high = _by_name(_verdicts(_records(8, 33), "hybrid"))["HB1"]
    assert low.verdict == "not supported" and "7/11" in low.evidence
    assert high.verdict == "supported" and "architecture A: 6/11" in high.evidence


def test_hb2_boundary() -> None:
    low = _by_name(_verdicts(_records(8, 30), "hybrid"))["HB2"]
    high = _by_name(_verdicts(_records(8, 31), "hybrid"))["HB2"]
    assert low.verdict == "not supported" and "30/34" in low.evidence
    assert high.verdict == "supported" and "architecture A: 32/34" in high.evidence


def test_wrong_denominator_is_not_testable_and_dev_is_not_applicable() -> None:
    short = _by_name(_verdicts(_records(8, 31, n_group=10, n_other=23), "hybrid"))
    assert short["HB1"].verdict == "not testable" and short["HB2"].verdict == "not testable"
    dev = _by_name(_verdicts(_records(8, 31), "hybrid", set_name="dev"))
    assert dev["HB1"].verdict == "not applicable (development set)"
    assert dev["HB2"].verdict == "not applicable (development set)"
    assert dev["HB3"].verdict.startswith("pending")


def test_hybrid_retrieval_lists_hb1_hb2_and_pending_hb3() -> None:
    verdicts = _verdicts(_records(8, 31), "hybrid")
    assert [v.hypothesis for v in verdicts] == ["HB1", "HB2", "HB3"]
    assert verdicts[2].verdict.startswith("pending")


def test_hb3_boundary_uses_the_rate_with_tolerance() -> None:
    base = FROZEN_BASELINE
    assert hb3_verdict(754, 1000, None, base).verdict == "not supported"
    assert hb3_verdict(755, 1000, None, base).verdict == "supported"
    assert hb3_verdict(77, 102, None, base).verdict == "not supported"  # 0.7549...
    assert hb3_verdict(0, 0, None, base).verdict == "not testable"
    assert "architecture A: 77/102" in hb3_verdict(80, 102, None, base).evidence
    assert hb3_verdict(80, 102, "not applicable (simulated)", base).verdict == (
        "not applicable (simulated)"
    )


def test_baseline_matches_the_committed_architecture_a_runs() -> None:
    assert load_baseline(RESULTS) == FROZEN_BASELINE


def test_baseline_mismatch_fails_loudly(tmp_path: Path) -> None:
    raw = tmp_path / "raw" / BASELINE_RETRIEVAL_RUN
    shutil.copytree(RESULTS / "raw" / BASELINE_RETRIEVAL_RUN, raw)
    shutil.copytree(
        RESULTS / "processed" / BASELINE_ANSWER_RUN, tmp_path / "processed" / BASELINE_ANSWER_RUN
    )
    assert load_baseline(tmp_path) == FROZEN_BASELINE
    path = raw / "retrieval.jsonl"
    lines = [json.loads(x) for x in path.read_text("utf-8").splitlines()]
    flipped = next(r for r in lines if not r["excluded"] and r["hit"]["1"] == 1.0)
    flipped["hit"]["1"] = 0.0
    flipped["hit"]["5"] = 0.0
    path.write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
    with pytest.raises(BaselineError, match="differs from the frozen"):
        load_baseline(tmp_path)
    with pytest.raises(BaselineError, match="missing"):
        load_baseline(tmp_path / "nowhere")


def test_registry_dispatch() -> None:
    assert has_hypotheses("dense") and has_hypotheses("hybrid") and not has_hypotheses("bm25")
    records = _records(8, 31)
    summary = summarize("r", "measured", records, [])
    assert apply_retrieval_verdicts(summary, records, "dense", RESULTS) is summary
    assert [v.hypothesis for v in summary.verdicts] == ["HA1", "HA2", "HA3", "HA4"]
    assert apply_retrieval_verdicts(summary, records, "bm25", RESULTS).verdicts == ()


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

    return [q("Q1", False), q("Q2", False)]


PRICING = PricingSnapshot(
    source="same_model",
    priced_model="test/model",
    prompt_usd_per_token=1e-6,
    completion_usd_per_token=3e-6,
    captured_at=simulated_pricing().captured_at,
    note="test price",
)


def _answers(
    make_record: RecordFactory, correct: int, total: int, simulated: bool
) -> AnswerSummary:
    records = [
        make_record(
            attempt_id=f"Q{i}-r1",
            question_id=f"Q{i}",
            correct=i < correct,
            outcome="answered" if i < correct else "refused",
            false_refusal=i >= correct,
            simulated=simulated,
        )
        for i in range(total)
    ]
    return summarise_answers(records, _questions(), question_set="measured", pricing=PRICING)


def test_answer_verdicts_per_retriever(make_record: RecordFactory) -> None:
    summary = _answers(make_record, 8, 10, False)
    hybrid = apply_answer_verdicts(summary, "hybrid", RESULTS)
    assert [v.hypothesis for v in hybrid.verdicts] == ["HB3"]
    assert hybrid.verdicts[0].verdict == "supported"  # 8/10 = 0.800 >= 0.755
    assert "correct 8/10" in hybrid.verdicts[0].evidence
    assert apply_answer_verdicts(summary, "dense", RESULTS) is summary
    assert [v.hypothesis for v in summary.verdicts] == ["HA3", "HA4"]
    assert apply_answer_verdicts(summary, "bm25", RESULTS).verdicts == ()
    simulated = apply_answer_verdicts(_answers(make_record, 8, 10, True), "hybrid", RESULTS)
    assert simulated.verdicts[0].verdict == "not applicable (simulated)"


# ----------------------------------------------------------------------- architecture C


def _rec_c(qid: str, rr: float, hit5: bool, *, excluded: bool = False) -> QuestionRetrieval:
    hits = {1: float(rr == 1.0), 3: float(hit5), 5: float(hit5), 10: float(rr > 0)}
    return QuestionRetrieval(
        run_id="r",
        question_id=qid,
        category="semantic",
        paraphrase_of=None,
        retriever="rerank",
        k=10,
        excluded=excluded,
        ranked=(),
        relevant_chunk_ids=("c",),
        n_relevant_sources=1,
        hit=hits,
        recall=dict(hits),
        precision=dict(hits),
        reciprocal_rank=rr,
        first_relevant_rank=None if rr == 0 else round(1 / rr),
        embed_ms=1.0,
        search_ms=1.0,
        rerank_ms=1.0,
    )


def _records_c(mrr_total: float, hit5_total: int, n: int = 34) -> list[QuestionRetrieval]:
    """``n`` answerable questions whose reciprocal ranks sum to ``mrr_total``; the first
    ``hit5_total`` hit within the top 5."""
    out = []
    remaining = mrr_total
    for i in range(n):
        rr = min(1.0, max(0.0, remaining))
        remaining -= rr
        out.append(_rec_c(f"C{i}", rr, i < hit5_total))
    return out


def test_hc1_boundary() -> None:
    below = _by_name(_verdicts(_records_c(34 * 0.85 - 0.01, 32), "rerank"))["HC1"]
    exact = _by_name(_verdicts(_records_c(34 * 0.85, 32), "rerank"))["HC1"]
    assert below.verdict == "not supported"
    assert exact.verdict == "supported"
    assert "architecture B: 0.782" in exact.evidence and exact.evidence.startswith("MRR = 0.850")


def test_hc2_boundary() -> None:
    low = _by_name(_verdicts(_records_c(30.0, 31), "rerank"))["HC2"]
    high = _by_name(_verdicts(_records_c(30.0, 32), "rerank"))["HC2"]
    assert low.verdict == "not supported" and "31/34" in low.evidence
    assert high.verdict == "supported" and "architecture B: 30/34" in high.evidence


def test_hc_wrong_denominator_and_dev_set() -> None:
    short = _by_name(_verdicts(_records_c(30.0, 32, n=33), "rerank"))
    assert short["HC1"].verdict == "not testable" and short["HC2"].verdict == "not testable"
    dev = _by_name(_verdicts(_records_c(30.0, 32), "rerank", set_name="dev"))
    assert dev["HC1"].verdict == dev["HC2"].verdict == "not applicable (development set)"
    assert dev["HC3"].verdict.startswith("pending")


def test_rerank_retrieval_registry_and_other_retrievers_unchanged() -> None:
    assert has_hypotheses("rerank") and has_hypotheses("hybrid") and has_hypotheses("dense")
    assert not has_hypotheses("bm25")
    verdicts = _verdicts(_records_c(30.0, 32), "rerank")
    assert [v.hypothesis for v in verdicts] == ["HC1", "HC2", "HC3"]
    assert [v.hypothesis for v in _verdicts(_records(8, 31), "hybrid")] == ["HB1", "HB2", "HB3"]
    assert [v.hypothesis for v in _verdicts(_records(8, 31), "dense")] == [
        "HA1",
        "HA2",
        "HA3",
        "HA4",
    ]
    assert _verdicts(_records(8, 31), "bm25") == ()


def test_hc3_boundary_is_a_count() -> None:
    base = FROZEN_BASELINE_B
    assert hc3_verdict(79, 102, None, base).verdict == "not supported"
    assert hc3_verdict(80, 102, None, base).verdict == "supported"
    assert "architecture B: 78/102" in hc3_verdict(80, 102, None, base).evidence
    odd = hc3_verdict(80, 101, None, base)
    assert odd.verdict == "not testable" and "expected 102" in odd.evidence
    assert hc3_verdict(0, 0, None, base).verdict == "not testable"
    assert hc3_verdict(80, 102, "not applicable (simulated)", base).verdict.startswith("not app")


def test_load_baseline_b_reads_the_committed_files() -> None:
    base = load_baseline_b(RESULTS)
    assert base == FROZEN_BASELINE_B or (
        base.hc2 == (30, 34)
        and base.hc3 == (78, 102)
        and abs(base.mrr - 0.7823529411764706) < 1e-12
    )
    assert round(base.mrr, 3) == 0.782


def test_load_baseline_b_detects_a_changed_record(tmp_path: Path) -> None:
    raw = tmp_path / "raw" / BASELINE_B_RETRIEVAL_RUN
    processed = tmp_path / "processed" / BASELINE_B_ANSWER_RUN
    raw.mkdir(parents=True)
    processed.mkdir(parents=True)
    lines = (RESULTS / "raw" / BASELINE_B_RETRIEVAL_RUN / "retrieval.jsonl").read_text("utf-8")
    shutil.copy(
        RESULTS / "processed" / BASELINE_B_ANSWER_RUN / "answer_summary.json",
        processed / "answer_summary.json",
    )
    (raw / "retrieval.jsonl").write_text(lines, encoding="utf-8")
    assert load_baseline_b(tmp_path).hc3 == (78, 102)
    changed = [json.loads(x) for x in lines.splitlines()]
    target = next(r for r in changed if not r["excluded"] and r["reciprocal_rank"] == 1.0)
    target["reciprocal_rank"] = 0.5
    (raw / "retrieval.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in changed), encoding="utf-8"
    )
    with pytest.raises(BaselineError, match="differs"):
        load_baseline_b(tmp_path)
    with pytest.raises(BaselineError, match="missing"):
        load_baseline_b(tmp_path / "nowhere")


# ------------------------------------------------------------------- registry by question set


@pytest.mark.parametrize("retriever", ["dense", "bm25", "hybrid", "rerank"])
def test_stress_retrieval_has_one_not_preregistered_row(retriever: str) -> None:
    verdicts = _verdicts(_records(8, 33), retriever, "stress")
    assert [(v.hypothesis, v.verdict) for v in verdicts] == [("stress", "not pre-registered yet")]
    assert not has_hypotheses(retriever, "stress")


@pytest.mark.parametrize("retriever", ["dense", "bm25", "hybrid", "rerank", "agentic"])
def test_stress_answers_have_one_not_preregistered_row(
    make_record: RecordFactory, retriever: str
) -> None:
    summary = summarise_answers(
        [make_record()],
        _questions(),
        question_set="stress",
        pricing=simulated_pricing(),
    )
    result = apply_answer_verdicts(summary, retriever, RESULTS)
    assert [(v.hypothesis, v.verdict) for v in result.verdicts] == [
        ("stress", "not pre-registered yet")
    ]


def test_registry_for_the_measured_and_dev_sets_is_unchanged() -> None:
    for question_set in ("measured", "dev"):
        assert has_hypotheses("dense", question_set) and has_hypotheses("hybrid", question_set)
        assert has_hypotheses("rerank", question_set) and not has_hypotheses("bm25", question_set)
    assert has_hypotheses("hybrid")  # the default set is "measured"
