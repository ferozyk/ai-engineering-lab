"""Unit tests for the rerank retriever and the fake reranker (no model)."""

from collections.abc import Callable, Sequence

import pytest

from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.rerank.fake import FakeReranker
from rag_experiment.retrieval.base import RetrievalResult, RetrievedChunk
from rag_experiment.retrieval.rerank import RerankRetriever

pytestmark = pytest.mark.unit

ChunkFactory = Callable[..., Chunk]


class FakeBase:
    """A base retriever with a fixed ranking; it records the depth it was asked for."""

    name = "hybrid"

    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self._chunks = list(chunks)
        self.asked: list[int] = []

    def retrieve(self, query: str, k: int) -> RetrievalResult:
        self.asked.append(k)
        items = tuple(
            RetrievedChunk(
                chunk=c,
                score=1.0 / rank,
                rank=rank,
                retriever="hybrid",
                component_ranks={"dense": rank, "bm25": 100 - rank},
            )
            for rank, c in enumerate(self._chunks[:k], start=1)
        )
        return RetrievalResult(chunks=items, embed_ms=3.0, search_ms=4.0)


class ScriptedReranker:
    """Returns scores from a table; records every call."""

    model_id = "scripted"
    revision = "r"

    def __init__(self, table: dict[str, float]) -> None:
        self._table = table
        self.calls: list[tuple[str, list[str]]] = []

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        self.calls.append((query, list(texts)))
        return [self._table[t] for t in texts]


def _chunks(make_chunk: ChunkFactory, *ids: str) -> list[Chunk]:
    return [make_chunk(i, content=f"content-{i}") for i in ids]


def test_reorders_by_score_and_breaks_ties_by_chunk_id(make_chunk: ChunkFactory) -> None:
    base = FakeBase(_chunks(make_chunk, "d", "c", "b", "a"))
    reranker = ScriptedReranker(
        {"content-d": 0.9, "content-c": 0.2, "content-b": 0.5, "content-a": 0.5}
    )
    result = RerankRetriever(base, reranker, depth=4).retrieve("q", 4)
    assert [c.chunk.chunk_id for c in result.chunks] == ["d", "a", "b", "c"]
    assert [c.rank for c in result.chunks] == [1, 2, 3, 4]
    assert [c.score for c in result.chunks] == [0.9, 0.5, 0.5, 0.2]
    assert all(c.retriever == "rerank" for c in result.chunks)


def test_k_cuts_and_k_above_depth_widens_the_pool(make_chunk: ChunkFactory) -> None:
    ids = list("abcdef")
    base = FakeBase(_chunks(make_chunk, *ids))
    table = {f"content-{i}": float(n) for n, i in enumerate(ids)}  # f scores highest
    reranker = ScriptedReranker(table)
    retriever = RerankRetriever(base, reranker, depth=3)
    top2 = retriever.retrieve("q", 2)
    assert base.asked == [3]
    assert [c.chunk.chunk_id for c in top2.chunks] == ["c", "b"]  # only a, b, c were candidates
    assert top2.candidate_ids == ("a", "b", "c")
    wide = retriever.retrieve("q", 5)
    assert base.asked == [3, 5]
    assert wide.candidate_ids == ("a", "b", "c", "d", "e")
    assert [c.chunk.chunk_id for c in wide.chunks] == ["e", "d", "c", "b", "a"]


def test_component_ranks_keep_base_keys_and_add_pool_rank(make_chunk: ChunkFactory) -> None:
    base = FakeBase(_chunks(make_chunk, "a", "b", "c"))
    reranker = ScriptedReranker({"content-a": 0.1, "content-b": 0.2, "content-c": 0.9})
    result = RerankRetriever(base, reranker, depth=3).retrieve("q", 3)
    ranks = {c.chunk.chunk_id: c.component_ranks for c in result.chunks}
    assert ranks["c"] == {"dense": 3, "bm25": 97, "hybrid": 3}
    assert ranks["a"] == {"dense": 1, "bm25": 99, "hybrid": 1}


def test_latency_split_and_candidate_ids(make_chunk: ChunkFactory) -> None:
    base = FakeBase(_chunks(make_chunk, "a", "b"))
    result = RerankRetriever(base, FakeReranker(), depth=2).retrieve("content a", 2)
    assert result.embed_ms == 3.0 and result.search_ms == 4.0  # passed through unchanged
    assert result.rerank_ms > 0.0  # scoring time only, measured here
    assert result.candidate_ids == ("a", "b")


def test_reranker_receives_exactly_the_chunk_content_in_pool_order(
    make_chunk: ChunkFactory,
) -> None:
    base = FakeBase(_chunks(make_chunk, "x", "y", "z"))
    reranker = ScriptedReranker({"content-x": 1.0, "content-y": 2.0, "content-z": 3.0})
    RerankRetriever(base, reranker, depth=3).retrieve("my question", 2)
    assert reranker.calls == [("my question", ["content-x", "content-y", "content-z"])]


@pytest.mark.parametrize(("query", "k"), [("", 3), ("   ", 3), ("q", 0), ("q", -1)])
def test_invalid_arguments_raise(make_chunk: ChunkFactory, query: str, k: int) -> None:
    retriever = RerankRetriever(FakeBase(_chunks(make_chunk, "a")), FakeReranker(), depth=3)
    with pytest.raises(ValueError):
        retriever.retrieve(query, k)


def test_empty_pool_skips_scoring() -> None:
    reranker = ScriptedReranker({})
    result = RerankRetriever(FakeBase([]), reranker, depth=3).retrieve("q", 3)
    assert result.chunks == () and result.candidate_ids == () and result.rerank_ms == 0.0
    assert reranker.calls == []


def test_a_wrong_number_of_scores_is_an_error(make_chunk: ChunkFactory) -> None:
    class Short:
        model_id = "short"
        revision = "r"

        def score(self, query: str, texts: Sequence[str]) -> list[float]:
            return [1.0]

    retriever = RerankRetriever(FakeBase(_chunks(make_chunk, "a", "b")), Short(), depth=2)
    with pytest.raises(ValueError, match="different number"):
        retriever.retrieve("q", 2)


def test_fake_reranker_is_deterministic_and_prefers_shared_words() -> None:
    fake = FakeReranker()
    texts = ["list the accounts of a customer", "cancel a payment", "cancel a payment"]
    first = fake.score("which endpoint lists customer accounts", texts)
    assert first == fake.score("which endpoint lists customer accounts", texts)
    assert first[0] > first[1]
    assert first[1] == first[2]
    assert fake.score("q", []) == []
