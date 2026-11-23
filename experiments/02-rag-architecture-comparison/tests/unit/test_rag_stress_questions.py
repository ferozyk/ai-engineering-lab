"""Validation rules of the five stress categories, on a five-question fixture."""

import json
from collections.abc import Callable

import jsonschema
import pytest

from rag_experiment.config import ExperimentConfig
from rag_experiment.corpus import Corpus
from rag_experiment.evaluation.corpus_facts import CorpusFacts
from rag_experiment.evaluation.dataset import ABSTAIN_CATEGORIES, Question, validate_question_set
from rag_experiment.evaluation.facts import corpus_header_names
from rag_experiment.ingestion.chunker import Chunk

pytestmark = pytest.mark.unit

Records = list[dict[str, object]]
Validate = Callable[[Records], list[str]]


@pytest.fixture
def records(stress_records: Records) -> Records:
    return stress_records


@pytest.fixture
def validate(large_corpus: Corpus, large_chunks: list[Chunk], large_facts: CorpusFacts) -> Validate:
    names = corpus_header_names(large_corpus)

    def run(rows: Records) -> list[str]:
        questions = [Question.model_validate(r) for r in rows]
        return validate_question_set(questions, large_corpus, large_chunks, names, large_facts)

    return run


def _with(rows: Records, qid: str, **changes: object) -> Records:
    return [{**r, **changes} if r["id"] == qid else r for r in rows]


def test_the_fixture_covers_every_stress_category(records: Records, validate: Validate) -> None:
    assert {r["category"] for r in records} == {
        "exact_identifier_lookalike",
        "version_lookalike",
        "everyday_wording",
        "multi_document",
        "near_miss",
    }
    assert validate(records) == []


def test_schema_accepts_the_new_categories_and_rejects_others(
    records: Records, experiment_config: ExperimentConfig
) -> None:
    schema = json.loads(experiment_config.question_schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for row in records:
        validator.validate(row)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate({**records[0], "category": "made_up"})


def test_near_miss_must_abstain_and_has_no_facts(records: Records, validate: Validate) -> None:
    assert "near_miss" in ABSTAIN_CATEGORIES
    problems = validate(
        _with(records, "Q205", constraints={"must_cite": True, "must_abstain": False})
    )
    assert any("must go together" in p for p in problems)
    problems = validate(_with(records, "Q205", key_facts=["freezeCard"]))
    assert any("no sources or key facts" in p for p in problems)
    # an abstention flag on a non-abstaining category is also refused
    problems = validate(
        _with(records, "Q204", constraints={"must_cite": False, "must_abstain": True})
    )
    assert any("must go together" in p for p in problems)


def test_multi_document_needs_two_documents(records: Records, validate: Validate) -> None:
    one_source = _with(
        records,
        "Q203",
        relevant_sources=["cards-api-v1#/paths/~1v1~1cards/get"],
        relevant_document_ids=["cards-api-v1"],
        key_facts=["listCards"],
    )
    problems = validate(one_source)
    assert any("at least 2 sources" in p for p in problems)
    assert any("2 documents" in p for p in problems)
    same_document = _with(
        records,
        "Q203",
        relevant_sources=[
            "cards-api-v1#/paths/~1v1~1cards/get",
            "cards-api-v1#/paths/~1v1~1cards~1{cardId}/get",
        ],
        relevant_document_ids=["cards-api-v1"],
        key_facts=["listCards", "getCard"],
    )
    assert any("2 documents" in p for p in validate(same_document))


def test_multi_document_every_source_owns_a_fact(records: Records, validate: Validate) -> None:
    problems = validate(_with(records, "Q203", key_facts=["listCards"]))
    assert any("loans-api-v1" in p and "owns no key fact" in p for p in problems)
    # a fact that both sources contain does not count as owned by either
    shared = validate(_with(records, "Q203", key_facts=["listCards", "AUTH-001"]))
    assert any("loans-api-v1" in p and "owns no key fact" in p for p in shared)


def test_version_lookalike_rules(records: Records, validate: Validate) -> None:
    question = str(next(r for r in records if r["id"] == "Q202")["question"])
    unnamed = question.replace("v2", "the latest").replace("v3", "the latest")
    assert any(
        "must name a version" in p for p in validate(_with(records, "Q202", question=unnamed))
    )
    wrong_fact = validate(_with(records, "Q202", key_facts=["pageToken"]))
    assert any("no key fact differs" in p for p in wrong_fact)
    other = "v1" if "v2" in question else "v2"
    other_version = (
        question.replace("v2", other) if "v2" in question else question.replace("v3", other)
    )
    assert any(
        "question names" in p for p in validate(_with(records, "Q202", question=other_version))
    )
    unversioned = _with(
        records,
        "Q202",
        relevant_sources=["accounts-api#/paths/~1v1~1accounts/get"],
        relevant_document_ids=["accounts-api"],
        key_facts=["listAccounts"],
    )
    assert any("versioned product specs" in p for p in validate(unversioned))


def test_exact_identifier_lookalike_must_quote_a_catalogued_code(
    records: Records, validate: Validate
) -> None:
    problems = validate(_with(records, "Q201", question="What does ERR-ZZZ-999 mean?"))
    assert any("must quote an identifier" in p for p in problems)
    assert any(
        "must quote an identifier" in p
        for p in validate(_with(records, "Q201", question="What does that error mean?"))
    )


def test_version_and_identifier_rules_need_the_catalogues(
    records: Records, large_corpus: Corpus, large_chunks: list[Chunk]
) -> None:
    names = corpus_header_names(large_corpus)
    questions = [Question.model_validate(r) for r in records]
    problems = validate_question_set(questions, large_corpus, large_chunks, names)
    assert any("CHANGES.json" in p for p in problems)
    assert any("IDENTIFIERS.json" in p for p in problems)
