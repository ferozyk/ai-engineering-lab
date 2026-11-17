"""Reranking: a cross-encoder re-orders the top candidates of another retriever.

The base retriever (hybrid) supplies a candidate pool. The reranker scores each
``(query, chunk content)`` pair, and the pool is re-sorted by that score. A chunk that is not in the
pool can never be returned, so reranking can only change the order within the pool.
"""

import time

from rag_experiment.rerank.provider import Reranker
from rag_experiment.retrieval.base import RetrievalResult, RetrievedChunk, Retriever


class RerankRetriever:
    """Top ``depth`` chunks of ``base``, re-ordered by a cross-encoder score."""

    def __init__(
        self, base: Retriever, reranker: Reranker, depth: int, name: str = "rerank"
    ) -> None:
        self._base = base
        self._reranker = reranker
        self._depth = depth
        self.name = name

    def retrieve(self, query: str, k: int) -> RetrievalResult:
        """Top ``k`` of the re-ordered pool. ``score`` is the reranker score; ``component_ranks``
        keeps the base ranks and adds ``hybrid``, the 1-based rank in the pool.

        ``embed_ms`` and ``search_ms`` come from the base retriever; ``rerank_ms`` is the time spent
        scoring only.
        """
        if not query.strip():
            raise ValueError("query must not be empty")
        if k < 1:
            raise ValueError("k must be at least 1")
        pool = self._base.retrieve(query, max(self._depth, k))
        if not pool.chunks:
            return RetrievalResult(
                chunks=(),
                embed_ms=pool.embed_ms,
                search_ms=pool.search_ms,
                rerank_ms=0.0,
                candidate_ids=(),
            )
        start = time.perf_counter()
        scores = self._reranker.score(query, [c.chunk.content for c in pool.chunks])
        rerank_ms = (time.perf_counter() - start) * 1000
        if len(scores) != len(pool.chunks):
            raise ValueError("the reranker returned a different number of scores than candidates")
        scored = sorted(
            zip(enumerate(pool.chunks, start=1), scores, strict=True),
            key=lambda pair: (-pair[1], pair[0][1].chunk.chunk_id),
        )
        chunks = tuple(
            RetrievedChunk(
                chunk=item.chunk,
                score=score,
                rank=rank,
                retriever=self.name,
                component_ranks={**(item.component_ranks or {}), "hybrid": pool_rank},
            )
            for rank, ((pool_rank, item), score) in enumerate(scored[:k], start=1)
        )
        return RetrievalResult(
            chunks=chunks,
            embed_ms=pool.embed_ms,
            search_ms=pool.search_ms,
            rerank_ms=rerank_ms,
            candidate_ids=tuple(c.chunk.chunk_id for c in pool.chunks),
        )
