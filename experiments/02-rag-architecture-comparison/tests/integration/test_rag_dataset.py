"""Integration tests: the real corpus, both question files and the CLI."""

import json
import re
from collections import Counter
from pathlib import Path

import jsonschema
import pytest

from rag_experiment.cli import main
from rag_experiment.config import ExperimentConfig
from rag_experiment.corpus import Corpus
from rag_experiment.evaluation.dataset import Question, load_questions, validate_question_set
from rag_experiment.evaluation.relevance import relevant_chunk_ids
from rag_experiment.ingestion.chunker import Chunk

pytestmark = pytest.mark.integration

_STOP_TEXT = (
    "a an and are as at be by can do does for from has have how i if in into is it its of on or so "
    "than that the their then there this to up what when where which who whom why will with would "
    "you your me my we our they them these those after before once about over"
)
STOP = set(re.split(r"\s+", _STOP_TEXT))
ALLOWED = {"api", "account", "customer", "customers"}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower())) - STOP - ALLOWED


def test_real_corpus_parses_and_chunks(corpus: Corpus, chunks: list[Chunk]) -> None:
    assert len(corpus.specs) == 5
    assert len(chunks) > 100
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert max(len(c.content) for c in chunks) <= 2400
    by_type = Counter(c.chunk_type for c in chunks)
    assert by_type["operation"] == 20
    print(f"chunk count: {len(chunks)} {dict(by_type)}")


@pytest.mark.parametrize("which", ["questions_dev", "questions_measured"])
def test_question_files_validate(
    which: str,
    experiment_config: ExperimentConfig,
    corpus: Corpus,
    chunks: list[Chunk],
    header_names: frozenset[str],
) -> None:
    questions = load_questions(getattr(experiment_config, which))
    assert validate_question_set(questions, corpus, chunks, header_names) == []


@pytest.mark.parametrize("which", ["questions_dev", "questions_measured"])
def test_question_files_match_the_json_schema(
    which: str, experiment_config: ExperimentConfig
) -> None:
    schema = json.loads(experiment_config.question_schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    lines = getattr(experiment_config, which).read_text(encoding="utf-8").splitlines()
    assert lines
    for line in lines:
        validator.validate(json.loads(line))


def test_dev_set_shape(experiment_config: ExperimentConfig) -> None:
    questions = load_questions(experiment_config.questions_dev)
    assert [q.id for q in questions] == [f"Q{n:02d}" for n in range(1, 16)]


def test_measured_set_distribution(experiment_config: ExperimentConfig) -> None:
    questions = load_questions(experiment_config.questions_measured)
    assert [q.id for q in questions] == [f"Q{n}" for n in range(101, 141)]
    assert Counter(q.category for q in questions) == {
        "semantic": 6,
        "exact_identifier": 6,
        "endpoint_discovery": 5,
        "authentication": 5,
        "schema": 5,
        "multi_endpoint": 4,
        "comparison": 3,
        "unanswerable": 6,
    }
    assert sum(1 for q in questions if q.paraphrase_of) == 6


def test_measured_set_is_disjoint_from_the_dev_set(experiment_config: ExperimentConfig) -> None:
    dev = load_questions(experiment_config.questions_dev)
    measured = load_questions(experiment_config.questions_measured)
    assert {q.id for q in dev}.isdisjoint({q.id for q in measured})
    assert {q.question for q in dev}.isdisjoint({q.question for q in measured})


def test_paraphrases_share_no_content_word_with_the_evidence(
    experiment_config: ExperimentConfig, chunks: list[Chunk]
) -> None:
    questions = {q.id: q for q in load_questions(experiment_config.questions_measured)}
    by_id = {c.chunk_id: c for c in chunks}
    for q in questions.values():
        if q.paraphrase_of is None:
            continue
        first = questions[q.paraphrase_of]
        assert first.expected_answer
        ids = relevant_chunk_ids(q.sources, chunks)
        evidence = _words(" ".join(by_id[i].content for i in ids))
        assert _words(q.question) & evidence == set(), q.id


def test_unanswerable_questions_have_no_evidence(experiment_config: ExperimentConfig) -> None:
    for path in (experiment_config.questions_dev, experiment_config.questions_measured):
        for q in load_questions(path):
            if q.category == "unanswerable":
                assert q.constraints.must_abstain
                assert not q.relevant_sources
                assert not q.key_facts


def test_cli_chunks(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["chunks", "--document", "accounts-api", "--type", "operation"]) == 0
    out = capsys.readouterr().out
    assert "accounts-api:getAccountBalances:operation" in out
    assert re.search(r"^5 chunks$", out, re.M)


def test_cli_chunks_full_and_show_chunk(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["chunks", "--document", "auth-api", "--full"]) == 0
    assert "operationId: issueAccessToken" in capsys.readouterr().out
    assert main(["show-chunk", "accounts-api:getAccountBalances:operation"]) == 0
    out = capsys.readouterr().out
    assert "chunk_id: accounts-api:getAccountBalances:operation" in out
    assert "content:" in out


def test_cli_unknown_chunk_returns_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["show-chunk", "nope"]) == 2
    assert "no chunk" in capsys.readouterr().err


def test_cli_missing_config_returns_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--config", str(tmp_path / "missing.yaml"), "chunks"]) == 2
    assert capsys.readouterr().err.startswith("Error:")


def test_cli_validate_dataset_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate-dataset"]) == 0
    out = capsys.readouterr().out
    assert "corpus checksum:" in out
    assert "questions (measured): 40" in out
    assert "no problems found" in out


def test_cli_validate_dataset_fails_on_a_broken_file(
    tmp_path: Path, experiment_config: ExperimentConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    records = [
        json.loads(line)
        for line in experiment_config.questions_measured.read_text(encoding="utf-8").splitlines()
    ]
    records[0]["key_facts"] = ["noSuchFieldAnywhere"]
    records[1]["relevant_sources"] = ["accounts-api#/paths/~1nowhere/get"]
    broken = tmp_path / "broken.jsonl"
    broken.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    (tmp_path / "configs").mkdir()
    config = tmp_path / "configs" / "experiment.yaml"
    config.write_text(
        f"experiment_version: 0.1.0\ncorpus_dir: {experiment_config.corpus_dir}\n"
        f"questions_dev: {experiment_config.questions_dev}\nquestions_measured: {broken}\n"
        "chunking:\n  max_chunk_chars: 2400\n"
        "embedding: {model_id: m/x, device: cpu, batch_size: 4, max_seq_length: 64, "
        "normalize: true}\n"
        "index: {dir: .index, collection_prefix: p}\n"
        "retrieval: {top_k_eval: 10, top_k_generation: 5}\n"
        "generation: {prompt_version: a-1.0, temperature: 0.0, max_output_tokens: 100, "
        "request_timeout_seconds: 30}\n"
        "run: {repetitions: 3, order_seed: 1, rate_limit_per_minute: 15, "
        "daily_request_cap: 900, canary_question_ids: [Q01]}\n"
        "pricing: {}\n",
        encoding="utf-8",
    )
    assert main(["--config", str(config), "validate-dataset"]) == 1
    out = capsys.readouterr().out
    assert "noSuchFieldAnywhere" in out
    assert "does not resolve" in out
    assert "problem(s)" in out


def test_load_questions_rejects_blank_lines_and_duplicates(tmp_path: Path) -> None:
    record: dict[str, object] = {
        "id": "Q01",
        "question": "q",
        "category": "unanswerable",
        "expected_answer": "a",
        "key_facts": [],
        "relevant_sources": [],
        "relevant_document_ids": [],
        "constraints": {"must_cite": False, "must_abstain": True},
        "paraphrase_of": None,
        "notes": "",
    }
    line = json.dumps(record)
    blank = tmp_path / "blank.jsonl"
    blank.write_text(f"{line}\n\n{line}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="blank"):
        load_questions(blank)
    dup = tmp_path / "dup.jsonl"
    dup.write_text(f"{line}\n{line}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_questions(dup)
    ok = tmp_path / "ok.jsonl"
    ok.write_text(f"{line}\n", encoding="utf-8")
    loaded: tuple[Question, ...] = load_questions(ok)
    assert len(loaded) == 1


def test_validation_flags_inconsistent_records(
    corpus: Corpus, chunks: list[Chunk], header_names: frozenset[str]
) -> None:
    good: dict[str, object] = {
        "id": "Q900",
        "question": "q",
        "category": "unanswerable",
        "expected_answer": "a",
        "key_facts": [],
        "relevant_sources": [],
        "relevant_document_ids": [],
        "constraints": {"must_cite": False, "must_abstain": True},
        "paraphrase_of": None,
        "notes": "",
    }
    bad = dict(
        good,
        id="Q901",
        category="schema",
        paraphrase_of="Q999",
        constraints={"must_cite": True, "must_abstain": False},
    )
    mismatch = dict(good, id="Q902", category="schema")
    questions = [Question.model_validate(r) for r in (good, bad, mismatch)]
    problems = validate_question_set(questions, corpus, chunks, header_names)
    assert any("must go together" in p for p in problems)
    assert any("paraphrase_of Q999" in p for p in problems)
    assert any("needs sources" in p for p in problems)
