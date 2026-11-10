"""End-to-end retrieval evaluation with fake embeddings (no model, no network)."""

import json
from pathlib import Path

import pytest

from rag_experiment import cli
from rag_experiment.config import ExperimentConfig
from rag_experiment.evaluation.dataset import load_questions
from rag_experiment.evaluation.retrieval_metrics import RetrievalSummary
from rag_experiment.evaluation.retrieval_run import RetrievalRunMetadata

pytestmark = pytest.mark.integration


def test_evaluate_retrieval_dev_with_fake_embeddings(
    experiment_config: ExperimentConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    results = tmp_path / "results"
    monkeypatch.setattr(cli, "_results_root_base", lambda config: results)
    assert cli.main(["evaluate-retrieval", "--set", "dev", "--fake-embeddings"]) == 0
    out = capsys.readouterr().out
    assert "HA1:" in out and "HA3: pending" in out

    # Fake runs land in dry-run/, never in raw/, processed/ or reports/.
    assert not (results / "raw").exists()
    assert not (results / "processed").exists()
    assert not (results / "reports").exists()
    run_dirs = list((results / "dry-run" / "raw").iterdir())
    assert len(run_dirs) == 1
    run_id = run_dirs[0].name
    assert run_id.endswith("-retrieval-dev-dense-fake")
    raw = results / "dry-run" / "raw" / run_id
    processed = results / "dry-run" / "processed" / run_id
    report = results / "dry-run" / "reports" / run_id / "retrieval_report.md"

    questions = load_questions(experiment_config.questions_dev)
    lines = [json.loads(x) for x in (raw / "retrieval.jsonl").read_text("utf-8").splitlines()]
    assert len(lines) == len(questions) == 15
    unanswerable = {q.id for q in questions if q.category == "unanswerable"}
    assert {r["question_id"] for r in lines if r["excluded"]} == unanswerable
    assert all(len(r["ranked"]) == 10 for r in lines)

    metadata = RetrievalRunMetadata.model_validate_json(
        (raw / "run_metadata.json").read_text("utf-8")
    )
    assert metadata.simulated is True and metadata.deterministic is True
    assert metadata.question_set == "dev" and metadata.collection.startswith("lab-bank-")
    assert (raw / "ingest.json").is_file()

    summary = RetrievalSummary.model_validate_json(
        (processed / "retrieval_summary.json").read_text("utf-8")
    )
    assert summary.n_questions == 15 and summary.n_excluded == len(unanswerable)
    assert summary.overall.n == 15 - len(unanswerable)
    assert summary.deterministic and summary.nondeterministic_questions == ()
    csv_lines = (processed / "retrieval_by_question.csv").read_text("utf-8").splitlines()
    assert len(csv_lines) == 16
    text = report.read_text("utf-8")
    assert "Simulated run with fake embeddings" in text
    assert "not representative of a Qdrant server" in text
    assert "written by the author" in text
