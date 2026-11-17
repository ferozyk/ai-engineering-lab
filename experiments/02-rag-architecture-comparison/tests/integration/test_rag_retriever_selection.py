"""The ``--retriever`` flag across commands, with fake embeddings (no model, no network)."""

import json
from pathlib import Path

import pytest

from rag_experiment import answer_commands, cli
from rag_experiment.config import ExperimentConfig
from rag_experiment.evaluation import compare
from rag_experiment.evaluation.answer_analysis import AnswerSummary
from rag_experiment.evaluation.answer_run import AnswerRunMetadata, RunPaths
from rag_experiment.evaluation.coverage import CoverageContext
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


# ----------------------------------------------------------------------- rerank (fake models)


def test_evaluate_rerank_records_pool_diagnostics_and_rerank_latency(
    results: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(
        ["evaluate-retrieval", "--set", "dev", "--retriever", "rerank", "--fake-embeddings"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "HC1: not applicable (development set)" in out and "HB1" not in out
    assert "candidates:" in out and "reranking latency:" in out
    raw = _only(results, "raw")
    assert raw.name.endswith("-retrieval-dev-rerank-fake")
    meta = json.loads((raw / "run_metadata.json").read_text("utf-8"))
    assert meta["retriever"] == "rerank"
    assert meta["rerank"]["revision"] == "fake" and meta["rerank"]["candidate_depth"] == 30
    rows = [json.loads(x) for x in (raw / "retrieval.jsonl").read_text("utf-8").splitlines()]
    assert all("rerank_ms" in r and "pool_first_relevant_rank" in r for r in rows)
    first = rows[0]["ranked"][0]
    assert first["component_ranks"]["hybrid"] >= 1 and "dense" in first["component_ranks"]
    summary = RetrievalSummary.model_validate_json(
        (results / "dry-run" / "processed" / raw.name / "retrieval_summary.json").read_text("utf-8")
    )
    assert summary.latency_rerank_ms is not None and summary.latency_rerank_ms.p50 > 0
    assert summary.pool_hit is not None and summary.pool_hit.denominator > 0
    total = summary.latency_total_ms.p50
    assert total >= summary.latency_rerank_ms.p50
    report = (results / "dry-run" / "reports" / raw.name / "retrieval_report.md").read_text("utf-8")
    assert "| reranking |" in report and "among the 30 candidates" in report
    csv_text = (
        results / "dry-run" / "processed" / raw.name / "retrieval_by_question.csv"
    ).read_text("utf-8")
    assert "rerank_ms" in csv_text.splitlines()[0]


def test_other_retrievers_keep_their_record_shape(
    results: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["evaluate-retrieval", "--set", "dev", "--fake-embeddings"]) == 0
    raw = _only(results, "raw")
    text = (raw / "retrieval.jsonl").read_text("utf-8")
    assert "rerank_ms" not in text and "pool_first_relevant_rank" not in text
    assert "rerank" not in (raw / "run_metadata.json").read_text("utf-8")
    summary_text = (
        results / "dry-run" / "processed" / raw.name / "retrieval_summary.json"
    ).read_text("utf-8")
    assert "rerank" not in summary_text and "pool_hit" not in summary_text
    report = (results / "dry-run" / "reports" / raw.name / "retrieval_report.md").read_text("utf-8")
    assert "rerank" not in report


def test_retrieve_command_with_rerank_shows_rerank_time(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.main(
        ["retrieve", "access token scopes", "--retriever", "rerank", "-k", "3", "--fake-embeddings"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "'hybrid':" in out and ", rerank " in out


def test_fake_answer_run_with_rerank_adds_a_rerank_stage(
    results: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli, "_settings", lambda config: pytest.fail("settings were read in a fake run")
    )
    assert cli.main(["run", "--set", "dev", "--retriever", "rerank", "--fake"]) == 0
    raw = _only(results, "raw")
    assert raw.name.endswith("-answers-dev-rerank-fake")
    paths = RunPaths(results / "dry-run", raw.name)
    summary = AnswerSummary.model_validate_json(
        (paths.processed / "answer_summary.json").read_text("utf-8")
    )
    assert list(summary.latency_ms) == ["embed", "search", "rerank", "generation", "total"]
    assert [v.hypothesis for v in summary.verdicts] == ["HC3"]
    assert summary.verdicts[0].verdict == "not applicable (simulated)"
    header = (paths.processed / "answers_by_attempt.csv").read_text("utf-8").splitlines()[0]
    assert "rerank_ms" in header
    first = json.loads(paths.answers.read_text("utf-8").splitlines()[0])
    assert first["rerank_ms"] > 0
    assert first["total_ms"] == pytest.approx(
        first["embed_ms"] + first["search_ms"] + first["rerank_ms"] + first["generation_ms"]
    )
    report = (paths.reports / "answer_report.md").read_text("utf-8")
    assert "| rerank |" in report
    meta = json.loads(paths.metadata.read_text("utf-8"))
    assert meta["rerank"]["model_id"] == "fake-word-overlap"


def test_retriever_choices_include_rerank() -> None:
    assert cli.RETRIEVERS == ("dense", "bm25", "hybrid", "rerank")


def test_compare_command_passes_source_coverage_for_answer_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_run_compare(
        base: Path, retrieval: object, answers: object, out: object, coverage: object = None
    ) -> dict[str, Path]:
        seen["coverage"] = coverage
        return {"json": base / "c.json", "report": base / "c.md"}

    monkeypatch.setattr(compare, "run_compare", fake_run_compare)
    assert cli.main(["compare", "--retrieval", "r1", "--answers", "a1", "--out", "x"]) == 0
    coverage = seen["coverage"]
    assert isinstance(coverage, CoverageContext)
    assert {"Q01", "Q128"} <= set(coverage.questions) and len(coverage.chunks) == 186

    assert cli.main(["compare", "--retrieval", "r1", "--out", "x"]) == 0
    assert seen["coverage"] is None
