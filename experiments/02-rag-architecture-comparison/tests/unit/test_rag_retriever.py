"""Unit tests for the dense retriever."""

from collections.abc import Callable

import pytest
from qdrant_client import QdrantClient

from rag_experiment.embeddings.fake import FakeEmbeddingProvider
from rag_experiment.embeddings.provider import EmbeddingCache
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.store import QdrantStore, ingest
from rag_experiment.retrieval.vector import DenseRetriever

pytestmark = pytest.mark.unit

ChunkFactory = Callable[..., Chunk]


def _retriever(
    make_chunk: ChunkFactory, contents: dict[str, str], build: bool = True
) -> DenseRetriever:
    provider = FakeEmbeddingProvider()
    store = QdrantStore(QdrantClient(":memory:"), "t")
    if build:
        chunks = [make_chunk(cid, text, f"#/paths/~1{cid}/get") for cid, text in contents.items()]
        ingest(chunks, provider, EmbeddingCache(None), store)
    return DenseRetriever(provider, store)


def test_ranks_by_similarity(make_chunk: ChunkFactory) -> None:
    retriever = _retriever(
        make_chunk,
        {"a": "list customer accounts", "b": "cancel payment", "c": "statement format"},
    )
    result = retriever.retrieve("customer accounts", 3)
    assert retriever.name == "dense"
    assert [c.rank for c in result.chunks] == [1, 2, 3]
    assert result.chunks[0].chunk.chunk_id == "a"
    assert result.chunks[0].retriever == "dense"
    scores = [c.score for c in result.chunks]
    assert scores == sorted(scores, reverse=True)
    assert result.embed_ms >= 0 and result.search_ms >= 0


def test_ties_are_broken_by_chunk_id(make_chunk: ChunkFactory) -> None:
    retriever = _retriever(make_chunk, {"z": "same words", "m": "same words", "a": "same words"})
    result = retriever.retrieve("same words", 3)
    assert [c.chunk.chunk_id for c in result.chunks] == ["a", "m", "z"]


def test_errors_and_empty_store(make_chunk: ChunkFactory) -> None:
    retriever = _retriever(make_chunk, {"a": "x"})
    with pytest.raises(ValueError, match="empty"):
        retriever.retrieve("   ", 3)
    with pytest.raises(ValueError, match="at least 1"):
        retriever.retrieve("x", 0)
    empty = _retriever(make_chunk, {}, build=False)
    assert empty.retrieve("anything", 3).chunks == ()
