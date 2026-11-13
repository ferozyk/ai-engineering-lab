"""Unit tests for rank fusion and the hybrid retriever."""

from collections.abc import Callable

import pytest
from qdrant_client import QdrantClient

from rag_experiment.embeddings.fake import FakeEmbeddingProvider
from rag_experiment.embeddings.provider import EmbeddingCache
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.bm25 import BM25Index, BM25Retriever
from rag_experiment.retrieval.hybrid import HybridRetriever, fuse
from rag_experiment.retrieval.store import QdrantStore, ingest
from rag_experiment.retrieval.vector import DenseRetriever

pytestmark = pytest.mark.unit

ChunkFactory = Callable[..., Chunk]


def test_rrf_literal_example(make_chunk: ChunkFactory) -> None:
    a, b, c, d = (make_chunk(x) for x in "abcd")
    # dense: a b c      bm25: b d a
    fused = fuse({"dense": [a, b, c], "bm25": [b, d, a]}, rrf_k=60, k=10)
    scores = {chunk.chunk_id: score for chunk, score, _ in fused}
    assert scores["a"] == pytest.approx(1 / 61 + 1 / 63, abs=1e-12)
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61, abs=1e-12)
    assert scores["c"] == pytest.approx(1 / 63, abs=1e-12)  # only in one list
    assert scores["d"] == pytest.approx(1 / 62, abs=1e-12)  # only in one list
    assert [chunk.chunk_id for chunk, _, _ in fused] == ["b", "a", "d", "c"]


def test_component_ranks_and_missing_list(make_chunk: ChunkFactory) -> None:
    a, b, c = (make_chunk(x) for x in "abc")
    fused = fuse({"dense": [a, b], "bm25": [c, a]}, rrf_k=60, k=10)
    ranks = {chunk.chunk_id: comp for chunk, _, comp in fused}
    assert ranks["a"] == {"dense": 1, "bm25": 2}
    assert ranks["b"] == {"dense": 2}
    assert ranks["c"] == {"bm25": 1}


def test_ties_break_by_chunk_id_and_k_cuts(make_chunk: ChunkFactory) -> None:
    z, a = make_chunk("z"), make_chunk("a")
    # symmetric: each is rank 1 in one list and rank 2 in the other, so the scores tie exactly
    fused = fuse({"dense": [z, a], "bm25": [a, z]}, rrf_k=60, k=10)
    assert [chunk.chunk_id for chunk, _, _ in fused] == ["a", "z"]
    assert fused[0][1] == fused[1][1]
    assert [chunk.chunk_id for chunk, _, _ in fuse({"x": [z, a]}, 60, 1)] == ["z"]


def _hybrid(
    make_chunk: ChunkFactory, docs: dict[str, str], depth: int = 50
) -> tuple[HybridRetriever, DenseRetriever, BM25Retriever]:
    chunks = [make_chunk(cid, text, f"#/paths/~1{cid}/get") for cid, text in docs.items()]
    provider = FakeEmbeddingProvider()
    store = QdrantStore(QdrantClient(":memory:"), "t")
    ingest(chunks, provider, EmbeddingCache(None), store)
    dense = DenseRetriever(provider, store)
    bm25 = BM25Retriever(BM25Index(chunks, 1.2, 0.75))
    return HybridRetriever(dense, bm25, rrf_k=60, depth=depth), dense, bm25


DOCS = {
    "a": "list customer accounts",
    "b": "cancel payment with X-Api-Key header",
    "c": "statement format",
    "d": "customer payment limits",
}


def test_hybrid_matches_manual_fusion(make_chunk: ChunkFactory) -> None:
    hybrid, dense, bm25 = _hybrid(make_chunk, DOCS)
    query = "customer payment"
    result = hybrid.retrieve(query, 3)
    d = dense.retrieve(query, 50)
    lex = bm25.retrieve(query, 50)
    expected = fuse(
        {"dense": [c.chunk for c in d.chunks], "bm25": [c.chunk for c in lex.chunks]}, 60, 3
    )
    assert hybrid.name == "hybrid"
    assert [c.chunk.chunk_id for c in result.chunks] == [c.chunk_id for c, _, _ in expected]
    assert [c.score for c in result.chunks] == pytest.approx([s for _, s, _ in expected])
    assert [c.rank for c in result.chunks] == [1, 2, 3]
    assert all(c.retriever == "hybrid" for c in result.chunks)
    assert [c.component_ranks for c in result.chunks] == [comp for _, _, comp in expected]
    top = result.chunks[0]
    assert top.component_ranks is not None
    assert (
        top.component_ranks["dense"]
        == [x.chunk.chunk_id for x in d.chunks].index(top.chunk.chunk_id) + 1
    )


def test_hybrid_latency_split_and_errors(make_chunk: ChunkFactory) -> None:
    hybrid, _, _ = _hybrid(make_chunk, DOCS)
    result = hybrid.retrieve("customer", 2)
    assert result.embed_ms >= 0 and result.search_ms >= 0
    assert len(result.chunks) == 2
    with pytest.raises(ValueError, match="empty"):
        hybrid.retrieve(" ", 3)
    with pytest.raises(ValueError, match="at least 1"):
        hybrid.retrieve("customer", 0)


def test_chunk_missing_from_bm25_still_ranks_via_dense(make_chunk: ChunkFactory) -> None:
    hybrid, _, _ = _hybrid(make_chunk, DOCS)
    result = hybrid.retrieve("customer accounts", 4)
    by_id = {c.chunk.chunk_id: c for c in result.chunks}
    assert "c" in by_id  # no lexical match, present through the dense list
    comp = by_id["c"].component_ranks
    assert comp is not None and "bm25" not in comp and "dense" in comp
