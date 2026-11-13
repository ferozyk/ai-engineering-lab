"""The ``--retriever`` flag across commands, with fake embeddings (no model, no network)."""

import json
from pathlib import Path

import pytest

from rag_experiment import answer_commands, cli
from rag_experiment.config import ExperimentConfig
from rag_experiment.evaluation.answer_analysis import AnswerSummary
from rag_experiment.evaluation.answer_run import AnswerRunMetadata, RunPaths
from rag_experiment.evaluation.hypotheses import BASELINE_RETRIEVAL_RUN
from rag_experiment.evaluation.retrieval_metrics import QuestionRetrieval, RetrievalSummary
from rag_experiment.evaluation.retrieval_run import RetrievalRunMetadata

pytestmark = pytest.mark.integration

EXP_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "results"
    monkeypatch.setattr(cli, "_results_root_base", lambda config: root)
    return root


def _only(root: Path, kind: str) -> Path:
    (path,) = list((root / "dry-run" / kind).iterdir()) if (root / "dry-run").exists() else []
    return path


def test_committed_architecture_a_records_still_parse() -> None:
    path = EXP_ROOT / "results" / "raw" / BASELINE_RETRIEVAL_RUN / "retrieval.jsonl"
    records = [
        QuestionRetrieval.model_validate_json(line) for line in path.read_text("utf-8").splitlines()
    ]
    assert len(records) == 40
    assert all(c.component_ranks is None for r in records for c in r.ranked)


def test_evaluate_bm25_needs_no_embedding_model(
    results: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["evaluate-retrieval", "--set", "dev", "--retriever", "bm25"]) == 0
    out = capsys.readouterr().out
    assert "diagnostic run: no pre-registered hypotheses" in out and "HA1" not in out
    (raw,) = list((results / "raw").iterdir())
    assert raw.name.endswith("-retrieval-dev-bm25")
    meta = RetrievalRunMetadata.model_validate_json((raw / "run_metadata.json").read_text("utf-8"))
    assert meta.retriever == "bm25" and meta.embedding.model_id == "none"
    assert meta.collection.startswith("none")
    summary = RetrievalSummary.model_validate_json(
        (results / "processed" / raw.name / "retrieval_summary.json").read_text("utf-8")
    )
    assert summary.verdicts == () and summary.latency_embed_ms.p95 == 0.0
    report = (results / "reports" / raw.name / "retrieval_report.md").read_text("utf-8")
    assert "diagnostic run: no pre-registered hypotheses" in report
    assert "BM25 over an in-memory index" in report


def test_evaluate_hybrid_records_component_ranks(
    results: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(
        ["evaluate-retrieval", "--set", "dev", "--retriever", "hybrid", "--fake-embeddings"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "HB1: not applicable (development set)" in out and "HA1" not in out
    raw = _only(results, "raw")
    assert raw.name.endswith("-retrieval-dev-hybrid-fake")
    lines = [json.loads(x) for x in (raw / "retrieval.jsonl").read_text("utf-8").splitlines()]
    first = lines[0]["ranked"][0]
    assert set(first["component_ranks"]) <= {"dense", "bm25"} and first["component_ranks"]
    assert all(r["retriever"] == "hybrid" for r in lines)


def test_dense_output_is_unchanged(results: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["evaluate-retrieval", "--set", "dev", "--fake-embeddings"]) == 0
    out = capsys.readouterr().out
    assert "HA1 group Hit@5:" in out and "HA3: pending" in out


@pytest.mark.parametrize(("retriever", "expected"), [("hybrid", ["HB3"]), ("bm25", [])])
def test_fake_answer_run_per_retriever(
    results: Path,
    monkeypatch: pytest.MonkeyPatch,
    experiment_config: ExperimentConfig,
    retriever: str,
    expected: list[str],
) -> None:
    monkeypatch.setattr(
        cli, "_settings", lambda config: pytest.fail("settings were read in a fake run")
    )
    assert cli.main(["run", "--set", "dev", "--retriever", retriever, "--fake"]) == 0
    raw = _only(results, "raw")
    assert raw.name.endswith(f"-answers-dev-{retriever}-fake")
    paths = RunPaths(results / "dry-run", raw.name)
    meta = AnswerRunMetadata.model_validate_json(paths.metadata.read_text("utf-8"))
    assert meta.retriever == retriever and meta.simulated
    summary = AnswerSummary.model_validate_json(
        (paths.processed / "answer_summary.json").read_text("utf-8")
    )
    assert [v.hypothesis for v in summary.verdicts] == expected
    for v in summary.verdicts:
        assert v.verdict == "not applicable (simulated)"
    report = (paths.reports / "answer_report.md").read_text("utf-8")
    if not expected:
        assert "diagnostic run: no pre-registered hypotheses" in report


def test_retrieve_command_with_bm25(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["retrieve", "--question-id", "Q01", "--retriever", "bm25", "-k", "3"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("1 · ") and "embed 0.0 ms" in out


def test_retrieve_command_with_hybrid_shows_component_ranks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.main(
        ["retrieve", "access token scopes", "--retriever", "hybrid", "-k", "3", "--fake-embeddings"]
    )
    assert code == 0
    assert "ranks {" in capsys.readouterr().out


def test_find_retrieval_run_filters_by_retriever(tmp_path: Path) -> None:
    for name in (
        "20260101T000000Z-retrieval-measured-dense",
        "20260102T000000Z-retrieval-measured-hybrid",
        "20260103T000000Z-retrieval-measured-bm25",
    ):
        (tmp_path / "raw" / name).mkdir(parents=True)
        (tmp_path / "raw" / name / "retrieval.jsonl").write_text("", encoding="utf-8")
    find = answer_commands.find_retrieval_run
    assert find(tmp_path, "measured") == "20260101T000000Z-retrieval-measured-dense"
    assert find(tmp_path, "measured", "hybrid") == "20260102T000000Z-retrieval-measured-hybrid"
    assert find(tmp_path, "dev", "hybrid") is None
