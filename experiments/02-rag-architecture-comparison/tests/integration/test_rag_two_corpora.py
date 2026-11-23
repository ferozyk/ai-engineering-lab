"""Question sets bound to corpora, end to end with the fake embedder and the fake chat model."""

import shutil
from pathlib import Path

import pytest

from rag_experiment import cli
from rag_experiment.config import ExperimentConfig
from rag_experiment.corpus import corpus_checksum
from rag_experiment.evaluation.answer_run import AnswerRunMetadata
from rag_experiment.evaluation.retrieval_metrics import RetrievalSummary
from rag_experiment.evaluation.retrieval_run import RetrievalRunMetadata
from rag_experiment.retrieval.store import collection_name

pytestmark = pytest.mark.integration


def _only(folder: Path) -> Path:
    runs = list(folder.iterdir())
    assert len(runs) == 1
    return runs[0]


def test_stress_set_is_missing_until_it_is_written(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["evaluate-retrieval", "--set", "stress", "--fake-embeddings"]) == 2
    assert "stress question set not written yet" in capsys.readouterr().err
    assert cli.main(["run", "--set", "stress", "--fake"]) == 2
    assert "stress question set not written yet" in capsys.readouterr().err


def test_evaluate_retrieval_on_the_stress_set_uses_the_large_corpus(
    stress_config_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = stress_config_file.parent.parent
    args = ["--config", str(stress_config_file)]
    command = ["evaluate-retrieval", "--set", "stress", "--retriever", "hybrid"]
    code = cli.main([*args, *command, "--fake-embeddings"])
    assert code == 0
    assert "stress: not pre-registered yet" in capsys.readouterr().out

    run = _only(root / "results" / "dry-run" / "raw")
    assert run.name.endswith("-retrieval-stress-hybrid-fake")
    metadata = RetrievalRunMetadata.model_validate_json(
        (run / "run_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata.corpus == "large" and metadata.question_set == "stress"
    assert metadata.experiment_version == "0.2.0"
    assert metadata.question_set_version == "0.1.0"
    assert metadata.corpus_checksum[:8] in metadata.collection
    summary = RetrievalSummary.model_validate_json(
        (
            root / "results" / "dry-run" / "processed" / run.name / "retrieval_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary.n_questions == 5 and summary.n_excluded == 1  # the near_miss is excluded
    assert {v.verdict for v in summary.verdicts} == {"not pre-registered yet"}
    report = (
        root / "results" / "dry-run" / "reports" / run.name / "retrieval_report.md"
    ).read_text(encoding="utf-8")
    assert "Corpus: large, version 1.0.0" in report
    assert "95% intervals (stress set)" in report
    assert "(1 unanswerable, excluded" in report


def test_agentic_fake_run_searches_the_large_corpus(stress_config_file: Path) -> None:
    root = stress_config_file.parent.parent
    command = ["run", "--set", "stress", "--retriever", "agentic", "--fake"]
    code = cli.main(["--config", str(stress_config_file), *command])
    assert code == 0
    run = _only(root / "results" / "dry-run" / "raw")
    assert run.name.endswith("-answers-stress-agentic-fake")
    metadata = AnswerRunMetadata.model_validate_json(
        (run / "run_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata.corpus == "large" and metadata.question_set == "stress"
    assert metadata.retriever == "agentic" and metadata.simulated
    answers = (run / "answers.jsonl").read_text(encoding="utf-8")
    assert "cards-api-v1" in answers  # the agent collected chunks of a generated spec
    report = (root / "results" / "dry-run" / "reports" / run.name / "answer_report.md").read_text(
        encoding="utf-8"
    )
    assert "Corpus: large" in report and "95% intervals (stress set)" in report
    assert "not pre-registered yet" in report


def test_clean_runs_record_the_clean_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    results = tmp_path / "results"
    monkeypatch.setattr(cli, "_results_root_base", lambda config: results)
    assert cli.main(["evaluate-retrieval", "--set", "dev", "--fake-embeddings"]) == 0
    capsys.readouterr()
    run = _only(results / "dry-run" / "raw")
    metadata = RetrievalRunMetadata.model_validate_json(
        (run / "run_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata.corpus == "clean" and metadata.question_set == "dev"
    report = (results / "dry-run" / "reports" / run.name / "retrieval_report.md").read_text("utf-8")
    assert "Corpus: clean, version 1.0.0" in report
    assert "95% intervals" not in report  # only the stress set reports intervals


def test_each_corpus_gets_its_own_collection(experiment_config: ExperimentConfig) -> None:
    from rag_experiment.corpus import load_corpus

    clean = load_corpus(experiment_config.corpora["clean"], "clean")
    large = load_corpus(experiment_config.corpora["large"], "large")
    names = [
        collection_name(
            experiment_config.index, c, experiment_config.chunking, "BAAI/bge-m3", "rev"
        )
        for c in (clean, large)
    ]
    assert names[0] != names[1]
    assert clean.checksum[:8] in names[0] and large.checksum[:8] in names[1]


def test_indexing_the_large_corpus_with_fake_embeddings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["index", "--corpus", "large", "--fake-embeddings"]) == 0
    out = capsys.readouterr().out
    assert "chunks: 2" in out and "cc01ee53" in out  # collection carries the large checksum


def test_retrieve_and_chunks_accept_a_corpus(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(
        ["retrieve", "--corpus", "large", "--fake-embeddings", "-k", "3", "ERR-CRD-007 frozen card"]
    )
    assert code == 0
    assert "-api-v" in capsys.readouterr().out
    assert cli.main(["chunks", "--corpus", "large", "--document", "cards-api-v2"]) == 0
    out = capsys.readouterr().out
    assert "[cards-api-v2]" in out or "cards-api-v2:" in out
    assert cli.main(["show-chunk", "--corpus", "large", "cards-api-v2:listCards:operation"]) == 0
    assert "listCards" in capsys.readouterr().out
    # the clean corpus does not contain generated documents
    assert cli.main(["show-chunk", "cards-api-v2:listCards:operation"]) == 2


def test_a_question_of_another_corpus_is_refused(
    stress_config_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["--config", str(stress_config_file), "retrieve", "--question-id", "Q201"]
    assert cli.main([*args, "--fake-embeddings"]) == 2
    assert "pass --corpus large" in capsys.readouterr().err
    assert cli.main([*args, "--corpus", "large", "--fake-embeddings"]) == 0


def test_validate_dataset_checks_the_stress_fixture(
    stress_config_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--config", str(stress_config_file), "validate-dataset"]) == 0
    out = capsys.readouterr().out
    assert "questions (stress): 5" in out and "no problems found" in out


def test_generate_corpus_check_passes_and_detects_drift(
    tmp_path: Path,
    stress_config_file: Path,
    experiment_config: ExperimentConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["generate-corpus", "--check"]) == 0
    assert "matches the generator" in capsys.readouterr().out

    copy = tmp_path / "datasets" / "corpus-large"
    shutil.copytree(experiment_config.corpora["large"], copy)
    (copy / "cards-api-v1.yaml").write_bytes(
        (copy / "cards-api-v1.yaml").read_bytes() + b"# drift\n"
    )
    text = stress_config_file.read_text(encoding="utf-8").replace(
        str(experiment_config.corpora["large"]), str(copy)
    )
    stress_config_file.write_text(text, encoding="utf-8")
    assert cli.main(["--config", str(stress_config_file), "generate-corpus", "--check"]) == 1
    assert "differs: cards-api-v1.yaml" in capsys.readouterr().out
    assert corpus_checksum(copy) != corpus_checksum(experiment_config.corpora["large"])
