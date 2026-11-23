"""Fixtures and helpers shared by the experiment 02 tests."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from ai_lab.llm import Usage
from rag_experiment.config import ExperimentConfig, default_config_path, load_config
from rag_experiment.corpus import Corpus, load_corpus
from rag_experiment.evaluation.answer_run import AnswerRecord
from rag_experiment.evaluation.corpus_facts import CorpusFacts, load_corpus_facts
from rag_experiment.evaluation.facts import corpus_header_names
from rag_experiment.ingestion.chunker import Chunk, chunk_corpus

EXP_ROOT = Path(__file__).resolve().parents[1]

TINY_SPEC = """\
openapi: 3.1.0
info:
  title: Tiny API
  version: 2.0.0
  description: A tiny spec for tests.
paths:
  /v1/things/{thingId}:
    parameters:
      - name: thingId
        in: path
        required: true
        description: Identifier of the thing.
        schema:
          type: string
    get:
      operationId: getThing
      summary: Get a thing
      description: Returns one thing.
      tags: [Things]
      security:
        - bearerAuth: ["things:read"]
          apiKey: []
      parameters:
        - name: verbose
          in: query
          description: Include extra fields.
          schema:
            type: boolean
            default: false
      responses:
        "404":
          description: The thing does not exist.
        "200":
          description: The thing.
          headers:
            X-Trace:
              description: Trace identifier.
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Thing"
    put:
      operationId: replaceThing
      summary: Replace a thing
      tags: [Things]
      security: []
      requestBody:
        required: true
        description: The new thing.
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/Thing"
      responses:
        "204":
          description: Replaced.
components:
  securitySchemes:
    bearerAuth:
      type: oauth2
      description: Bearer token.
      flows:
        clientCredentials:
          tokenUrl: https://example.invalid/token
          scopes:
            "things:read": Read things.
    apiKey:
      type: apiKey
      in: header
      name: X-Api-Key
      description: Application key.
  schemas:
    Thing:
      type: object
      description: A thing.
      required: [id]
      properties:
        id:
          type: string
          description: Identifier.
        nickname:
          type: [string, "null"]
          maxLength: 20
          description: Optional nickname.
        labels:
          type: array
          items:
            type: string
        owner:
          $ref: "#/components/schemas/Owner"
        owners:
          type: array
          items:
            $ref: "#/components/schemas/Owner"
    Owner:
      type: object
      description: An owner.
      properties:
        name:
          type: string
"""


@pytest.fixture(scope="session")
def experiment_config() -> ExperimentConfig:
    """The shipped configuration."""
    return load_config(default_config_path())


@pytest.fixture(scope="session")
def corpus(experiment_config: ExperimentConfig) -> Corpus:
    """The real corpus, parsed once per session."""
    return load_corpus(experiment_config.corpus_dir)


@pytest.fixture(scope="session")
def chunks(corpus: Corpus, experiment_config: ExperimentConfig) -> list[Chunk]:
    """The real corpus, chunked with the shipped configuration."""
    return chunk_corpus(corpus, experiment_config.chunking)


@pytest.fixture(scope="session")
def header_names(corpus: Corpus) -> frozenset[str]:
    """Header names that appear in the real corpus."""
    return corpus_header_names(corpus)


@pytest.fixture(scope="session")
def large_config(experiment_config: ExperimentConfig) -> ExperimentConfig:
    """The shipped configuration bound to the large corpus."""
    return experiment_config.for_corpus("large")


@pytest.fixture(scope="session")
def large_corpus(large_config: ExperimentConfig) -> Corpus:
    """The large (generated) corpus, parsed once per session."""
    return load_corpus(large_config.corpus_dir, "large")


@pytest.fixture(scope="session")
def large_chunks(large_corpus: Corpus, experiment_config: ExperimentConfig) -> list[Chunk]:
    """The large corpus, chunked with the shipped configuration."""
    return chunk_corpus(large_corpus, experiment_config.chunking)


@pytest.fixture(scope="session")
def large_facts(large_config: ExperimentConfig) -> CorpusFacts:
    """CHANGES.json and IDENTIFIERS.json of the large corpus."""
    facts = load_corpus_facts(large_config.corpus_dir)
    assert facts is not None
    return facts


@pytest.fixture
def tiny_spec_path(tmp_path: Path) -> Path:
    """The tiny inline spec written to a temporary ``tiny.yaml``."""
    path = tmp_path / "tiny.yaml"
    path.write_text(TINY_SPEC, encoding="utf-8")
    return path


ChunkFactory = Callable[..., Chunk]


@pytest.fixture
def make_chunk() -> ChunkFactory:
    """Build a small ``Chunk`` from a chunk id, text and source pointer."""

    def build(
        chunk_id: str,
        content: str = "text",
        source_reference: str = "#/paths/~1x/get",
        document_id: str = "doc",
    ) -> Chunk:
        return Chunk(
            document_id=document_id,
            document_name="Doc",
            chunk_id=chunk_id,
            chunk_type="operation",
            api_path="/x",
            http_method="GET",
            operation_id=None,
            tags=(),
            content=content,
            source_reference=source_reference,
            refs=(),
            spec_version="1.0.0",
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )

    return build


RecordFactory = Callable[..., AnswerRecord]


@pytest.fixture
def make_record() -> RecordFactory:
    """Build an ``AnswerRecord`` of an answered, correct, answerable attempt; override fields."""

    def build(**overrides: object) -> AnswerRecord:
        data: dict[str, object] = {
            "run_id": "run",
            "attempt_id": "Q01-r1",
            "question_id": "Q01",
            "repetition": 1,
            "category": "semantic",
            "paraphrase_of": None,
            "must_abstain": False,
            "context_chunk_ids": ("c1",),
            "context_hit": True,
            "relevant_chunk_ids": ("c1",),
            "outcome": "answered",
            "answer": "answer",
            "cited_chunk_ids": ("c1",),
            "insufficient_context": False,
            "parse_error": None,
            "finish_reason": "stop",
            "correct": True,
            "missing_key_facts": (),
            "false_refusal": False,
            "correct_refusal": None,
            "made_up_answer": None,
            "unsupported_identifiers": (),
            "invented_identifiers": (),
            "citations_valid": True,
            "cites_relevant": True,
            "mentions_endpoint": False,
            "embed_ms": 10.0,
            "search_ms": 2.0,
            "generation_ms": 1000.0,
            "total_ms": 1012.0,
            "client_wait_ms": 0.0,
            "attempts": 1,
            "usage": Usage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
            "model_served": "test/model",
            "provider": "TestProvider",
            "request_id": "req-1",
            "simulated": False,
            "error_kind": None,
            "error_message": None,
        }
        data.update(overrides)
        return AnswerRecord.model_validate(data)

    return build


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-marked tests on asyncio only."""
    return "asyncio"


def make_stress_records(facts: CorpusFacts) -> list[dict[str, object]]:
    """Five valid stress questions (one per condition) over the large corpus, for tests only."""

    def record(qid: str, question: str, category: str, **fields: object) -> dict[str, object]:
        base: dict[str, object] = {
            "id": qid,
            "question": question,
            "category": category,
            "expected_answer": "",
            "key_facts": [],
            "relevant_sources": [],
            "relevant_document_ids": [],
            "constraints": {"must_cite": True, "must_abstain": False},
            "paraphrase_of": None,
            "notes": "test fixture",
        }
        base.update(fields)
        return base

    code = next(
        i
        for i in facts.identifiers
        if i.product == "cards" and i.version == "v1" and i.status == 409
    )
    change = next(c for c in facts.changes if c.kind == "page_size_max_changed")
    version = change.to_version
    # .../parameters/N/schema/maximum -> .../parameters
    parameters = change.location.rsplit("/", 3)[0]
    return [
        record(
            "Q201",
            f"What does error code {code.code} mean?",
            "exact_identifier_lookalike",
            expected_answer=code.meaning,
            key_facts=[code.code],
            relevant_sources=[f"{code.document}{code.location}"],
            relevant_document_ids=[code.document],
        ),
        record(
            "Q202",
            f"In {version} of the {change.product} API, what is the largest page size?",
            "version_lookalike",
            expected_answer=str(change.after),
            key_facts=[str(change.after)],
            relevant_sources=[f"{change.document}{parameters}"],
            relevant_document_ids=[change.document],
        ),
        record(
            "Q203",
            "Which operations list cards and list loans?",
            "multi_document",
            expected_answer="listCards and listLoans",
            key_facts=["listCards", "listLoans"],
            relevant_sources=[
                "cards-api-v1#/paths/~1v1~1cards/get",
                "loans-api-v1#/paths/~1v1~1loans/get",
            ],
            relevant_document_ids=["cards-api-v1", "loans-api-v1"],
        ),
        record(
            "Q204",
            "How do I stop my card from being used for a while?",
            "everyday_wording",
            expected_answer="freezeCard",
            key_facts=["freezeCard"],
            relevant_sources=["cards-api-v1#/paths/~1v1~1cards~1{cardId}~1freeze/post"],
            relevant_document_ids=["cards-api-v1"],
        ),
        record(
            "Q205",
            "Is there an operation that unfreezes a card?",
            "near_miss",
            expected_answer="The cards API has no operation that unfreezes a card.",
            constraints={"must_cite": False, "must_abstain": True},
        ),
    ]


def write_stress_set(path: Path, records: list[dict[str, object]]) -> None:
    """Write question records as JSONL."""
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


@pytest.fixture
def stress_records(large_facts: CorpusFacts) -> list[dict[str, object]]:
    """Five valid stress questions over the large corpus (a fresh list per test)."""
    return make_stress_records(large_facts)


@pytest.fixture
def stress_config_file(
    tmp_path: Path, experiment_config: ExperimentConfig, stress_records: list[dict[str, object]]
) -> Path:
    """A config in a temp folder whose stress set is the five-question fixture.

    The folder is also the ``root``, so results and the index go to the temp folder; the corpora
    and the other two question sets are the real files.
    """
    stress_path = tmp_path / "questions-stress.jsonl"
    write_stress_set(stress_path, stress_records)
    raw = yaml.safe_load(default_config_path().read_text(encoding="utf-8"))
    cfg = experiment_config
    raw["corpus_dir"] = str(cfg.corpus_dir)
    raw["questions_dev"] = str(cfg.questions_dev)
    raw["questions_measured"] = str(cfg.questions_measured)
    raw["corpora"] = {name: str(path) for name, path in cfg.corpora.items()}
    raw["question_sets"] = {
        "dev": {"path": str(cfg.questions_dev), "corpus": "clean"},
        "measured": {"path": str(cfg.questions_measured), "corpus": "clean"},
        "stress": {"path": str(stress_path), "corpus": "large"},
    }
    (tmp_path / "configs").mkdir()
    path = tmp_path / "configs" / "experiment.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path
