"""Architecture A and B records and reports must survive the addition of reranking.

The committed run files are loaded into the current models, their summaries are rebuilt from the
raw records, and every file that is derived from them is rendered again and compared byte for byte
with the committed copy. Nothing here loads a model.
"""

import json
from pathlib import Path

import pytest

from rag_experiment.config import ExperimentConfig
from rag_experiment.evaluation import charts
from rag_experiment.evaluation.answer_analysis import AnswerSummary, summarise_answers
from rag_experiment.evaluation.answer_report import render_answer_report, write_processed
from rag_experiment.evaluation.answer_run import (
    AnswerRecord,
    AnswerRunMetadata,
    load_records,
    write_json,
)
from rag_experiment.evaluation.dataset import load_questions
from rag_experiment.evaluation.hypotheses import apply_answer_verdicts, apply_retrieval_verdicts
from rag_experiment.evaluation.retrieval_metrics import (
    QuestionRetrieval,
    RetrievalSummary,
    summarize,
)
from rag_experiment.evaluation.retrieval_run import (
    RetrievalRunMetadata,
    render_report,
    write_run,
)

pytestmark = pytest.mark.unit

RESULTS = Path(__file__).resolve().parents[2] / "results"
RETRIEVAL_RUNS = (
    "20261110T204546Z-retrieval-measured-dense",
    "20261113T232754Z-retrieval-measured-hybrid",
)
ANSWER_RUNS = (
    "20261110T221134Z-answers-measured-dense",
    "20261116T224508Z-answers-measured-hybrid",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _without_null_component_ranks(jsonl: str) -> list[dict[str, object]]:
    rows = [json.loads(line) for line in jsonl.splitlines()]
    for row in rows:
        for item in row["ranked"]:
            if item.get("component_ranks", 0) is None:
                del item["component_ranks"]
    return rows


@pytest.mark.parametrize("run_id", RETRIEVAL_RUNS)
def test_committed_retrieval_runs_rebuild_byte_for_byte(run_id: str, tmp_path: Path) -> None:
    raw, processed, reports = (RESULTS / d / run_id for d in ("raw", "processed", "reports"))
    metadata = RetrievalRunMetadata.model_validate_json(_text(raw / "run_metadata.json"))
    records = [
        QuestionRetrieval.model_validate_json(line)
        for line in _text(raw / "retrieval.jsonl").splitlines()
    ]
    committed = RetrievalSummary.model_validate_json(_text(processed / "retrieval_summary.json"))
    assert metadata.rerank is None
    assert committed.latency_rerank_ms is None and committed.pool_hit is None

    rebuilt = summarize(
        run_id, committed.question_set, records, list(committed.nondeterministic_questions)
    )
    rebuilt = apply_retrieval_verdicts(rebuilt, records, metadata.retriever, RESULTS)
    assert rebuilt == committed  # every metric, latency and verdict field

    ingest = json.loads(_text(raw / "ingest.json"))
    assert render_report(metadata, rebuilt, records, ingest) == _text(
        reports / "retrieval_report.md"
    )
    paths = write_run(tmp_path, metadata, records, rebuilt, ingest)
    assert _text(paths["metadata"]) == _text(raw / "run_metadata.json")
    # Architecture A was written before ``component_ranks`` existed; every other key is identical.
    assert _without_null_component_ranks(_text(paths["retrieval"])) == (
        _without_null_component_ranks(_text(raw / "retrieval.jsonl"))
    )
    assert _text(paths["summary"]) == _text(processed / "retrieval_summary.json")
    assert _text(paths["csv"]) == _text(processed / "retrieval_by_question.csv")
    assert _text(paths["report"]) == _text(reports / "retrieval_report.md")


@pytest.mark.parametrize("run_id", ANSWER_RUNS)
def test_committed_answer_runs_rebuild_byte_for_byte(
    run_id: str, experiment_config: ExperimentConfig, tmp_path: Path
) -> None:
    raw, processed, reports = (RESULTS / d / run_id for d in ("raw", "processed", "reports"))
    metadata = AnswerRunMetadata.model_validate_json(_text(raw / "run_metadata.json"))
    records = load_records(raw / "answers.jsonl")
    assert records and all(isinstance(r, AnswerRecord) for r in records)
    committed = AnswerSummary.model_validate_json(_text(processed / "answer_summary.json"))
    assert "rerank" not in committed.latency_ms

    questions = load_questions(experiment_config.questions_measured)
    rebuilt = summarise_answers(
        records, questions, question_set=metadata.question_set, pricing=metadata.pricing
    )
    rebuilt = apply_answer_verdicts(rebuilt, metadata.retriever, RESULTS)
    assert rebuilt == committed

    out = write_processed(tmp_path / "processed", rebuilt, records)
    assert _text(out["summary"]) == _text(processed / "answer_summary.json")
    assert _text(out["csv"]) == _text(processed / "answers_by_attempt.csv")
    assert "".join(
        json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n" for r in records
    ) == _text(raw / "answers.jsonl")
    write_json(tmp_path / "metadata.json", metadata)
    assert _text(tmp_path / "metadata.json") == _text(raw / "run_metadata.json")

    chart_dir = RESULTS / "charts" / run_id
    order = [
        "retrieval_hit_at_k.png",
        "ha3_correctness_by_context.png",
        "guardrails.png",
        "latency_by_stage.png",
        "tokens_per_question.png",
    ]
    names = charts.chart_names([chart_dir / n for n in order if (chart_dir / n).is_file()])
    assert render_answer_report(metadata, rebuilt, names) == _text(reports / "answer_report.md")
