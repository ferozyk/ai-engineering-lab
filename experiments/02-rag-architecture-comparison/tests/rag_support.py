"""Fixtures and helpers shared by the experiment 02 tests."""

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from rag_experiment.config import ExperimentConfig, default_config_path, load_config
from rag_experiment.corpus import Corpus, load_corpus
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
