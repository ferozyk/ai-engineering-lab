"""Unit tests for BM25."""

import math
from collections.abc import Callable

import pytest

from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.bm25 import BM25Index, BM25Retriever

pytestmark = pytest.mark.unit

ChunkFactory = Callable[..., Chunk]
K1, B = 1.2, 0.75


def _index(make_chunk: ChunkFactory, docs: dict[str, str]) -> BM25Index:
    chunks = [make_chunk(cid, text, f"#/paths/~1{cid}/get") for cid, text in docs.items()]
    return BM25Index(chunks, K1, B)


DOCS = {"d1": "alpha beta beta", "d2": "beta gamma", "d3": "delta delta delta delta"}


def test_scores_match_the_formula_computed_by_hand(make_chunk: ChunkFactory) -> None:
    index = _index(make_chunk, DOCS)
    # N = 3; document lengths 3, 2, 4; avgdl = 3. df(alpha) = 1, df(beta) = 2.
    n, avgdl = 3, 3.0
    idf_alpha = math.log((n - 1 + 0.5) / (1 + 0.5) + 1)
    idf_beta = math.log((n - 2 + 0.5) / (2 + 0.5) + 1)

    def term(idf: float, tf: int, dl: int) -> float:
        return idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * dl / avgdl))

    expected = {
        "d1": term(idf_alpha, 1, 3) + term(idf_beta, 2, 3),
        "d2": term(idf_beta, 1, 2),
    }
    hits = index.search("alpha beta", 10)
    scores = {chunk.chunk_id: score for chunk, score in hits}
    assert set(scores) == {"d1", "d2"}
    for cid, value in expected.items():
        assert scores[cid] == pytest.approx(value, abs=1e-9)
    assert index.idf("alpha") == pytest.approx(idf_alpha, abs=1e-9)


def test_order_zero_scores_excluded_and_cut(make_chunk: ChunkFactory) -> None:
    index = _index(make_chunk, DOCS)
    hits = index.search("alpha beta", 10)
    assert [c.chunk_id for c, _ in hits] == ["d1", "d2"]  # d3 scores 0 and is excluded
    assert [c.chunk_id for c, _ in index.search("alpha beta", 1)] == ["d1"]


def test_repeated_query_tokens_count_once(make_chunk: ChunkFactory) -> None:
    index = _index(make_chunk, DOCS)
    once = index.search("beta", 5)
    repeated = index.search("beta beta beta", 5)
    assert [(c.chunk_id, s) for c, s in once] == [(c.chunk_id, s) for c, s in repeated]


def test_unknown_tokens(make_chunk: ChunkFactory) -> None:
    index = _index(make_chunk, DOCS)
    assert index.search("zzzz", 5) == []
    assert index.idf("zzzz") == 0.0
    assert [c.chunk_id for c, _ in index.search("zzzz gamma", 5)] == ["d2"]


def test_ties_broken_by_chunk_id(make_chunk: ChunkFactory) -> None:
    index = _index(make_chunk, {"z": "same words", "a": "same words", "m": "same words"})
    assert [c.chunk_id for c, _ in index.search("same", 3)] == ["a", "m", "z"]


def test_retriever_contract(make_chunk: ChunkFactory) -> None:
    retriever = BM25Retriever(_index(make_chunk, DOCS))
    result = retriever.retrieve("alpha beta", 5)
    assert retriever.name == "bm25"
    assert [c.rank for c in result.chunks] == [1, 2]
    assert result.embed_ms == 0.0 and result.search_ms >= 0.0
    assert all(c.component_ranks is None and c.retriever == "bm25" for c in result.chunks)
    with pytest.raises(ValueError, match="empty"):
        retriever.retrieve("  ", 3)
    with pytest.raises(ValueError, match="at least 1"):
        retriever.retrieve("alpha", 0)


def test_empty_index_is_rejected() -> None:
    with pytest.raises(ValueError, match="zero chunks"):
        BM25Index([], K1, B)
