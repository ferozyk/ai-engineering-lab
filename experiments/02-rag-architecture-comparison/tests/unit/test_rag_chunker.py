"""Unit tests for the chunker."""

from pathlib import Path

import pytest

from rag_experiment.config import ChunkingConfig
from rag_experiment.corpus import Corpus
from rag_experiment.ingestion.chunker import Chunk, chunk_corpus, chunk_spec
from rag_experiment.ingestion.parser import ParsedSpec, parse_spec

pytestmark = pytest.mark.unit

BIG = ChunkingConfig(max_chunk_chars=2400)


@pytest.fixture
def tiny(tiny_spec_path: Path) -> ParsedSpec:
    return parse_spec(tiny_spec_path)


def _by_id(chunks: list[Chunk]) -> dict[str, Chunk]:
    return {c.chunk_id: c for c in chunks}


def test_operation_chunk_golden(tiny: ParsedSpec) -> None:
    chunk = _by_id(chunk_spec(tiny, BIG))["tiny:getThing:operation"]
    assert chunk.content == (
        "[tiny] GET /v1/things/{thingId} · operation\n"
        "operationId: getThing\n"
        "Summary: Get a thing\n"
        "Description: Returns one thing.\n"
        "Tags: Things\n"
        "Security: bearerAuth (OAuth2 bearer token in the Authorization header; "
        "scopes: things:read) AND apiKey (API key in header X-Api-Key)\n"
        "Parameters: thingId (path), verbose (query)\n"
        "Responses: 200, 404"
    )
    assert chunk.source_reference == "#/paths/~1v1~1things~1{thingId}/get"
    assert chunk.chunk_type == "operation"
    assert chunk.http_method == "GET"
    assert chunk.api_path == "/v1/things/{thingId}"
    assert chunk.spec_version == "2.0.0"
    assert chunk.document_name == "Tiny API"
    assert len(chunk.content_hash) == 64


def test_other_templates_golden(tiny: ParsedSpec) -> None:
    chunks = _by_id(chunk_spec(tiny, BIG))
    assert chunks["tiny:getThing:parameters"].content == (
        "[tiny] GET /v1/things/{thingId} · parameters\n"
        "- thingId (path, required, string): Identifier of the thing.\n"
        "- verbose (query, optional, boolean, default false): Include extra fields."
    )
    assert chunks["tiny:getThing:response:200"].content == (
        "[tiny] GET /v1/things/{thingId} · response 200\n"
        "Response 200: The thing.\n"
        "Headers:\n"
        "- X-Trace (string): Trace identifier.\n"
        "Content application/json: Thing\n"
        "- id (string, required): Identifier.\n"
        "- nickname (string, max length 20, nullable, optional): Optional nickname.\n"
        "- labels (array of string, optional)\n"
        "- owner (Owner, optional)\n"
        "- owners (array of Owner, optional)"
    )
    assert chunks["tiny:replaceThing:request_body"].content.splitlines()[:4] == [
        "[tiny] PUT /v1/things/{thingId} · request body",
        "Request body (required): The new thing.",
        "Content application/json: Thing",
        "Required fields: id",
    ]
    assert chunks["tiny:bearerAuth:security_scheme"].content == (
        "[tiny] security scheme bearerAuth\n"
        "Type: oauth2\n"
        "Description: Bearer token.\n"
        "Flow clientCredentials: token URL https://example.invalid/token\n"
        "- scope things:read: Read things."
    )
    assert (
        chunks["tiny:apiKey:security_scheme"].content.splitlines()[-1]
        == "API key: header X-Api-Key"
    )
    assert chunks["tiny:Owner:component_schema"].content == (
        "[tiny] component schema Owner\n"
        "Schema Owner: object\n"
        "Description: An owner.\n"
        "- name (string, optional)"
    )
    assert chunks["tiny:Thing:component_schema"].refs == ("Owner",)
    assert chunks["tiny:getThing:response:200"].refs == ("Owner", "Thing")


def test_security_none_and_no_optional_lines(tiny: ParsedSpec) -> None:
    content = _by_id(chunk_spec(tiny, BIG))["tiny:replaceThing:operation"].content
    assert "Security: none" in content
    assert "Description:" not in content
    assert "Deprecated" not in content
    assert "Request body: application/json: Thing" in content


def test_empty_sections_produce_no_chunk(tiny: ParsedSpec) -> None:
    ids = _by_id(chunk_spec(tiny, BIG))
    assert "tiny:replaceThing:response:204" in ids
    # replaceThing has the path-level thingId parameter, so it has a parameters chunk, but
    # getThing's response 404 has no content and no headers, and there are no body chunks for GET.
    assert "tiny:getThing:request_body" not in ids
    assert ids["tiny:getThing:response:404"].content.count("\n") == 1


def test_no_parameters_means_no_parameters_chunk(tmp_path: Path) -> None:
    path = tmp_path / "bare.yaml"
    path.write_text(
        "openapi: 3.1.0\ninfo: {title: B}\npaths:\n  /a:\n    get:\n      operationId: a\n"
        "      responses:\n        '200': {description: ok}\n",
        encoding="utf-8",
    )
    ids = [c.chunk_id for c in chunk_spec(parse_spec(path), BIG)]
    assert ids == ["bare:a:operation", "bare:a:response:200"]


def test_chunk_ids_are_unique_and_deterministic(tiny: ParsedSpec) -> None:
    first = chunk_spec(tiny, BIG)
    second = chunk_spec(tiny, BIG)
    assert first == second
    ids = [c.chunk_id for c in first]
    assert len(ids) == len(set(ids))
    # Operations first, then security schemes, then component schemas.
    types = [c.chunk_type for c in first]
    assert types.index("security_scheme") > types.index("response")
    assert types.index("component_schema") > types.index("security_scheme")


def test_duplicate_ids_raise(tmp_path: Path) -> None:
    path = tmp_path / "dup.yaml"
    path.write_text(
        "openapi: 3.1.0\ninfo: {title: D}\npaths:\n"
        "  /a:\n    get:\n      operationId: same\n      responses: {}\n"
        "  /b:\n    get:\n      operationId: same\n      responses: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate chunk_id"):
        chunk_spec(parse_spec(path), BIG)


def test_chunk_corpus_orders_documents_and_checks_ids(tiny_spec_path: Path, tmp_path: Path) -> None:
    other = tmp_path / "aaa.yaml"
    other.write_text(tiny_spec_path.read_text(), encoding="utf-8")
    specs = (parse_spec(tiny_spec_path), parse_spec(other))
    corpus = Corpus(specs=specs, documents={}, version="0", checksum="0")
    chunks = chunk_corpus(corpus, BIG)
    assert chunks[0].document_id == "aaa"
    assert chunks[-1].document_id == "tiny"


def test_oversized_chunks_split_on_bullets(tiny: ParsedSpec) -> None:
    whole = _by_id(chunk_spec(tiny, BIG))["tiny:Thing:component_schema"]
    small = chunk_spec(tiny, ChunkingConfig(max_chunk_chars=200))
    parts = [c for c in small if c.chunk_id.startswith("tiny:Thing:component_schema")]
    assert len(parts) > 1
    assert [c.chunk_id for c in parts] == [
        f"tiny:Thing:component_schema:p{i}" for i in range(1, len(parts) + 1)
    ]
    assert {c.source_reference for c in parts} == {"#/components/schemas/Thing"}
    assert all(len(c.content) <= 200 for c in parts)
    header = whole.content.splitlines()[:4]
    assert all(c.content.splitlines()[:4] == header for c in parts)
    bullets = [line for c in parts for line in c.content.splitlines() if line.startswith("- ")]
    assert bullets == [line for line in whole.content.splitlines() if line.startswith("- ")]


def test_single_long_bullet_stays_whole(tiny: ParsedSpec, caplog: pytest.LogCaptureFixture) -> None:
    chunks = chunk_spec(tiny, ChunkingConfig(max_chunk_chars=60))
    assert any(len(c.content) > 60 for c in chunks)
    assert "keeping it whole" in caplog.text or "stays whole" in caplog.text
