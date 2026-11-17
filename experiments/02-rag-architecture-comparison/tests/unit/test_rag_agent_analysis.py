"""Unit tests for the agent summary, the HD verdicts, the report section and the comparison."""

import csv
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from ai_lab.benchmarking import PricingSnapshot, simulated_pricing
from rag_experiment.agent.records import AgentCall
from rag_experiment.answer_commands import coverage_context
from rag_experiment.config import ExperimentConfig
from rag_experiment.evaluation.answer_analysis import AnswerSummary, summarise_answers
from rag_experiment.evaluation.answer_report import agent_section, write_processed
from rag_experiment.evaluation.answer_run import AnswerRecord, load_records
from rag_experiment.evaluation.compare import run_compare
from rag_experiment.evaluation.coverage import CoverageContext, full_coverage
from rag_experiment.evaluation.hypotheses import (
    BASELINE_B_ANSWER_RUN,
    FROZEN_BASELINE_D,
    BaselineD,
    BaselineError,
    apply_answer_verdicts,
    hd1_verdict,
    hd2_verdict,
    hd3_verdict,
    load_baseline_d,
)
from rag_experiment.ingestion.chunker import Chunk

pytestmark = pytest.mark.unit

RESULTS = Path(__file__).resolve().parents[2] / "results"
RecordFactory = Callable[..., AnswerRecord]
PRICING: PricingSnapshot = simulated_pricing()
BASE = FROZEN_BASELINE_D


def _call(step: str) -> AgentCall:
    return AgentCall.model_validate(
        {
            "step": step,
            "latency_ms": 10.0,
            "attempts": 1,
            "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
            "finish_reason": "stop",
            "model_served": "m",
            "provider": "p",
            "request_id": "r",
        }
    )


def _agentic(make_record: RecordFactory, **overrides: object) -> AnswerRecord:
    base: dict[str, object] = {
        "calls": (_call("plan"), _call("judge"), _call("answer")),
        "model_calls": 3,
        "searches": 1,
        "queries": ("q",),
        "needs_retrieval": True,
        "judge_decisions": (True,),
        "agent_ms": 20.0,
        "sources_covered": 1,
        "n_sources": 1,
    }
    base.update(overrides)
    return make_record(**base)


def _run(
    make_record: RecordFactory,
    *,
    full: int = 9,
    correct: int = 80,
    refusals: int = 17,
    simulated: bool = False,
    multi: int = 12,
) -> list[AnswerRecord]:
    """``multi`` multi_endpoint attempts (``full`` of them fully covered), other answerable
    attempts up to 102 in total, and 18 unanswerable attempts (``refusals`` correct)."""
    records: list[AnswerRecord] = []
    answerable = 102
    for i in range(answerable):
        is_multi = i < multi
        records.append(
            _agentic(
                make_record,
                attempt_id=f"A{i}-r1",
                question_id=f"A{i}",
                category="multi_endpoint" if is_multi else "semantic",
                correct=i < correct,
                outcome="answered" if i < correct else "refused",
                false_refusal=i >= correct,
                sources_covered=2 if (not is_multi or i < full) else 1,
                n_sources=2 if is_multi else 1,
                simulated=simulated,
            )
        )
    for i in range(18):
        ok = i < refusals
        records.append(
            _agentic(
                make_record,
                attempt_id=f"U{i}-r1",
                question_id=f"U{i}",
                category="unanswerable",
                must_abstain=True,
                outcome="refused" if ok else "answered",
                correct=None,
                false_refusal=None,
                correct_refusal=ok,
                made_up_answer=not ok,
                sources_covered=0,
                n_sources=0,
                simulated=simulated,
            )
        )
    return records


def _summary(records: list[AnswerRecord], question_set: str = "measured") -> AnswerSummary:
    return summarise_answers(records, [], question_set=question_set, pricing=PRICING)


@pytest.fixture(scope="module")
def coverage(experiment_config: ExperimentConfig, chunks: list[Chunk]) -> CoverageContext:
    return coverage_context(experiment_config, chunks)


def test_the_agent_summary_counts_calls_searches_and_coverage(make_record: RecordFactory) -> None:
    records = [
        _agentic(make_record, attempt_id="Q1-r1", question_id="Q1", category="multi_endpoint",
                 sources_covered=2, n_sources=2, queries=("first", "second"), searches=2,
                 model_calls=4, judge_decisions=(False, True)),
        _agentic(make_record, attempt_id="Q1-r2", question_id="Q1", repetition=2,
                 category="multi_endpoint", sources_covered=1, n_sources=2, queries=("other",),
                 model_calls=5, searches=3, plan_parse_error="empty reply",
                 judge_parse_errors=2, needs_retrieval=False),
        _agentic(make_record, attempt_id="Q2-r1", question_id="Q2", model_calls=3),
    ]  # fmt: skip
    summary = _summary(records)
    agent = summary.agent
    assert agent is not None and agent.n_attempts == 3
    assert agent.model_calls.distribution == {"3": 1, "4": 1, "5": 1}
    assert agent.model_calls.mean == 4.0 and agent.model_calls.p50 == 4.0
    assert agent.model_calls.max == 5 and agent.searches.max == 3
    assert (agent.needs_retrieval_false, agent.plan_parse_errors) == (1, 1)
    assert agent.judge_parse_errors == 2
    assert agent.first_judge_enough.numerator == 2 and agent.first_judge_enough.denominator == 3
    assert agent.context_chunks_max == 1
    multi = agent.full_coverage_by_category["multi_endpoint"]
    assert (multi.numerator, multi.denominator) == (1, 2)
    assert agent.sources_covered_by_question["Q1"] == (2, 1)
    assert agent.n_sources_by_question["Q1"] == 2
    assert agent.multi_endpoint_queries == {"Q1": ("first", "second")}  # repetition 1 only
    assert [*summary.latency_ms] == ["embed", "search", "agent", "generation", "total"]
    assert summary.latency_ms["agent"].p50 == 20.0


def test_a_plain_summary_has_no_agent_section_and_no_agent_key(make_record: RecordFactory) -> None:
    summary = summarise_answers([make_record()], [], question_set="measured", pricing=PRICING)
    assert summary.agent is None and "agent" not in summary.latency_ms
    assert "agent" not in json.loads(summary.model_dump_json())


@pytest.mark.parametrize(
    ("full", "verdict"), [(8, "not supported"), (9, "supported"), (12, "supported")]
)
def test_hd1_boundary(
    full: int, verdict: str, make_record: RecordFactory, coverage: CoverageContext
) -> None:
    result = apply_answer_verdicts(
        _summary(_run(make_record, full=full)), "agentic", RESULTS, coverage
    )
    hd1 = result.verdicts[0]
    assert hd1.hypothesis == "HD1" and hd1.verdict == verdict
    assert f"full source coverage {full}/12" in hd1.evidence
    assert "architecture B: 3/12" in hd1.evidence


@pytest.mark.parametrize(("correct", "verdict"), [(79, "not supported"), (80, "supported")])
def test_hd2_boundary(
    correct: int, verdict: str, make_record: RecordFactory, coverage: CoverageContext
) -> None:
    result = apply_answer_verdicts(
        _summary(_run(make_record, correct=correct)), "agentic", RESULTS, coverage
    )
    hd2 = result.verdicts[1]
    assert hd2.hypothesis == "HD2" and hd2.verdict == verdict
    assert f"correct {correct}/102" in hd2.evidence and "architecture B: 78/102" in hd2.evidence


@pytest.mark.parametrize(("refusals", "verdict"), [(16, "not supported"), (17, "supported")])
def test_hd3_boundary(
    refusals: int, verdict: str, make_record: RecordFactory, coverage: CoverageContext
) -> None:
    result = apply_answer_verdicts(
        _summary(_run(make_record, refusals=refusals)), "agentic", RESULTS, coverage
    )
    hd3 = result.verdicts[2]
    assert hd3.hypothesis == "HD3" and hd3.verdict == verdict
    assert "architecture B: 18/18" in hd3.evidence


def test_other_denominators_are_not_testable(
    make_record: RecordFactory, coverage: CoverageContext
) -> None:
    few = apply_answer_verdicts(
        _summary(_run(make_record, full=5, multi=8)), "agentic", RESULTS, coverage
    )
    assert few.verdicts[0].verdict == "not testable" and "expected 12" in few.verdicts[0].evidence
    assert hd1_verdict((12, 11), None, BASE).verdict == "not testable"
    assert hd2_verdict((90, 101), None, BASE).verdict == "not testable"
    assert hd3_verdict((17, 17), None, BASE).verdict == "not testable"
    none = apply_answer_verdicts(_summary(_run(make_record, multi=0)), "agentic", RESULTS, coverage)
    assert none.verdicts[0].verdict == "not testable"


def test_applicability_rules_are_unchanged(
    make_record: RecordFactory, coverage: CoverageContext
) -> None:
    simulated = apply_answer_verdicts(
        _summary(_run(make_record, simulated=True)), "agentic", RESULTS, coverage
    )
    assert {v.verdict for v in simulated.verdicts} == {"not applicable (simulated)"}
    dev = apply_answer_verdicts(_summary(_run(make_record), "dev"), "agentic", RESULTS, coverage)
    assert {v.verdict for v in dev.verdicts} == {"not applicable (development set)"}
    assert [v.hypothesis for v in dev.verdicts] == ["HD1", "HD2", "HD3"]
    with pytest.raises(BaselineError, match="coverage"):
        apply_answer_verdicts(_summary(_run(make_record)), "agentic", RESULTS)


def test_the_baseline_is_computed_from_b_and_checked(
    coverage: CoverageContext, tmp_path: Path
) -> None:
    assert load_baseline_d(RESULTS, coverage) == BaselineD(hd1=(3, 12), hd2=(78, 102), hd3=(18, 18))
    records = load_records(RESULTS / "raw" / BASELINE_B_ANSWER_RUN / "answers.jsonl")
    assert full_coverage(records, coverage) == (3, 12)  # the one definition used for B and D
    copy = tmp_path / "results"
    for part in ("raw", "processed"):
        shutil.copytree(RESULTS / part / BASELINE_B_ANSWER_RUN, copy / part / BASELINE_B_ANSWER_RUN)
    answers = copy / "raw" / BASELINE_B_ANSWER_RUN / "answers.jsonl"
    lines = answers.read_text("utf-8").splitlines()
    multi = next(
        i for i, line in enumerate(lines) if json.loads(line)["category"] == "multi_endpoint"
    )
    del lines[multi]
    answers.write_text("\n".join(lines) + "\n", "utf-8")
    with pytest.raises(BaselineError, match="differs from the frozen values"):
        load_baseline_d(copy, coverage)
    with pytest.raises(BaselineError, match="missing"):
        load_baseline_d(tmp_path / "nowhere", coverage)


def test_the_report_section_and_csv_exist_for_agentic_runs_only(
    make_record: RecordFactory, tmp_path: Path
) -> None:
    records = [
        _agentic(make_record, attempt_id="Q128-r1", question_id="Q128", category="multi_endpoint",
                 queries=("find `customer`", "then accounts"), sources_covered=1, n_sources=2),
    ]  # fmt: skip
    summary = _summary(records)
    assert summary.agent is not None
    text = "\n".join(agent_section(summary.agent))
    assert "## Agent behaviour" in text and "| 5 | 0 |" in text and "| 1 | 1 |" in text
    assert "| multi_endpoint | 0/1 attempts |" in text
    assert "- Q128: `` find `customer` ``, `then accounts`" in text
    out = write_processed(tmp_path / "agentic", summary, records)
    header = next(csv.reader(out["csv"].open(encoding="utf-8")))
    assert {"agent_ms", "model_calls", "searches", "sources_covered", "n_sources"} <= set(header)
    plain = [make_record()]
    plain_out = write_processed(tmp_path / "plain", _summary(plain), plain)
    plain_header = next(csv.reader(plain_out["csv"].open(encoding="utf-8")))
    assert not {"agent_ms", "model_calls", "searches", "sources_covered"} & set(plain_header)


def _write_answer_run(base: Path, run_id: str, retriever: str, records: list[AnswerRecord]) -> None:
    summary = _summary(records)
    raw = base / "raw" / run_id
    raw.mkdir(parents=True)
    (raw / "run_metadata.json").write_text(json.dumps({"retriever": retriever}), "utf-8")
    (raw / "answers.jsonl").write_text(
        "".join(json.dumps(r.model_dump(mode="json")) + "\n" for r in records), "utf-8"
    )
    processed = base / "processed" / run_id
    processed.mkdir(parents=True)
    (processed / "answer_summary.json").write_text(summary.model_dump_json(), "utf-8")


def test_compare_adds_the_agent_columns_for_every_answer_run(
    make_record: RecordFactory,
    coverage: CoverageContext,
    chunks: list[Chunk],
    experiment_config: ExperimentConfig,
    tmp_path: Path,
) -> None:
    from rag_experiment.evaluation.relevance import relevant_chunk_ids

    question = next(q for q in coverage.questions.values() if q.category == "multi_endpoint")
    ids = sorted(relevant_chunk_ids(question.sources, chunks))
    covering = {"context_chunk_ids": tuple(ids), "category": "multi_endpoint"}
    part = {"context_chunk_ids": ids[:1], "category": "multi_endpoint"}
    ident = {"question_id": question.id, "attempt_id": f"{question.id}-r1"}
    _write_answer_run(
        tmp_path, "plain-run", "hybrid", [make_record(**ident, **covering), make_record(
            question_id=question.id, attempt_id=f"{question.id}-r2", repetition=2, **part)]
    )  # fmt: skip
    _write_answer_run(
        tmp_path,
        "agent-run",
        "agentic",
        [_agentic(make_record, **ident, **covering, sources_covered=2, n_sources=2, model_calls=4)],
    )
    paths = run_compare(tmp_path, [], ["plain-run", "agent-run"], "cmp", coverage)
    report = paths["report"].read_text("utf-8")
    assert "| model calls per attempt (mean / max) | 1.00 / 1 | 4.00 / 4 |" in report
    assert "| searches per attempt (mean) | 1.00 | 1.00 |" in report
    assert "| agent p50 (ms) | - | 20 |" in report
    assert "| full source coverage, multi_endpoint | 1/2 attempts | 1/1 attempts |" in report
    data = json.loads(paths["json"].read_text("utf-8"))
    assert data["answer_runs"]["agent-run"]["model_calls_max"] == 4
    assert data["answer_runs"]["plain-run"]["multi_endpoint_full_coverage"] == {
        "numerator": 1,
        "denominator": 2,
    }
    # without a coverage context the column is a dash, never a guess
    unknown = run_compare(tmp_path, [], ["plain-run"], "cmp2")["report"].read_text("utf-8")
    assert "| full source coverage, multi_endpoint | - |" in unknown
