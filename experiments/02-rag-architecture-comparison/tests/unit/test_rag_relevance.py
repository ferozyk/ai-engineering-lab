"""Unit tests for the ownership rule, on a hand-made chunk list."""

import hashlib

import pytest

from rag_experiment.evaluation.relevance import (
    covered_sources,
    is_relevant,
    owner_chunks,
    relevant_chunk_ids,
)
from rag_experiment.ingestion.chunker import Chunk, ChunkType
from rag_experiment.ingestion.pointers import parse_source

pytestmark = pytest.mark.unit

OP = "#/paths/~1v1~1accounts/get"


def _chunk(doc: str, chunk_id: str, reference: str, chunk_type: ChunkType = "operation") -> Chunk:
    return Chunk(
        document_id=doc,
        document_name=doc,
        chunk_id=chunk_id,
        chunk_type=chunk_type,
        api_path=None,
        http_method=None,
        operation_id=None,
        tags=(),
        content=chunk_id,
        source_reference=reference,
        refs=(),
        spec_version="1",
        content_hash=hashlib.sha256(chunk_id.encode()).hexdigest(),
    )


CHUNKS = [
    _chunk("a", "a:op", OP),
    _chunk("a", "a:params", OP + "/parameters", "parameters"),
    _chunk("a", "a:resp200", OP + "/responses/200", "response"),
    _chunk("a", "a:other-op", "#/paths/~1v1~1accounts-x/get"),
    _chunk("a", "a:basic", "#/components/securitySchemes/basic", "security_scheme"),
    _chunk("a", "a:key", "#/components/securitySchemes/key", "security_scheme"),
    _chunk("b", "b:key", "#/components/securitySchemes/key", "security_scheme"),
    _chunk("a", "a:big:p1", "#/components/schemas/Big", "component_schema"),
    _chunk("a", "a:big:p2", "#/components/schemas/Big", "component_schema"),
]


def _ids(chunks: list[Chunk]) -> set[str]:
    return {c.chunk_id for c in chunks}


def test_operation_chunk_owns_security() -> None:
    assert _ids(owner_chunks(parse_source(f"a{OP}/security"), CHUNKS)) == {"a:op"}


def test_parameters_chunk_owns_parameters_not_operation() -> None:
    source = parse_source(f"a{OP}/parameters")
    assert _ids(owner_chunks(source, CHUNKS)) == {"a:params"}
    assert relevant_chunk_ids([source], CHUNKS) == frozenset({"a:params"})


def test_labelling_the_operation_makes_all_its_chunks_relevant() -> None:
    assert relevant_chunk_ids([parse_source(f"a{OP}")], CHUNKS) == {
        "a:op",
        "a:params",
        "a:resp200",
    }


def test_labelling_security_schemes_covers_only_that_document() -> None:
    ids = relevant_chunk_ids([parse_source("a#/components/securitySchemes")], CHUNKS)
    assert ids == {"a:basic", "a:key"}


def test_prefix_is_segment_wise() -> None:
    source = parse_source("a#/paths/~1v1~1accounts/get")
    assert "a:other-op" not in relevant_chunk_ids([source], CHUNKS)
    # A path that is a character prefix of another path owns nothing of it.
    assert owner_chunks(parse_source("a#/paths/~1v1~1accounts"), CHUNKS) == []


def test_split_parts_all_count() -> None:
    ids = relevant_chunk_ids([parse_source("a#/components/schemas/Big")], CHUNKS)
    assert ids == {"a:big:p1", "a:big:p2"}
    assert _ids(owner_chunks(parse_source("a#/components/schemas/Big/properties/x"), CHUNKS)) == {
        "a:big:p1",
        "a:big:p2",
    }


def test_source_without_owner_is_empty() -> None:
    assert relevant_chunk_ids([parse_source("c#/paths/~1v1~1accounts/get")], CHUNKS) == frozenset()
    assert relevant_chunk_ids([parse_source("a#/paths/~1nowhere/get")], CHUNKS) == frozenset()


def test_is_relevant_and_covered_sources() -> None:
    s_op = parse_source(f"a{OP}/security")
    s_params = parse_source(f"a{OP}/parameters")
    assert is_relevant(CHUNKS[0], [s_op], CHUNKS)
    assert not is_relevant(CHUNKS[0], [s_params], CHUNKS)
    assert covered_sources({"a:op", "a:resp200"}, [s_op, s_params], CHUNKS) == {s_op}
    assert covered_sources({"a:op", "a:params"}, [s_op, s_params], CHUNKS) == {s_op, s_params}
    assert covered_sources(set(), [s_op], CHUNKS) == frozenset()
