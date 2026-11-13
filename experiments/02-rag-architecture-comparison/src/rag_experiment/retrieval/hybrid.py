"""Hybrid retrieval: dense and BM25 rankings fused with Reciprocal Rank Fusion (RRF).

Dense scores (cosine similarity) and BM25 scores live on different scales, so they cannot be
added. RRF ignores the scores and uses only ranks: a chunk at rank ``r`` in a list contributes
``1 / (rrf_k + r)``, and contributions from every list that contains the chunk are summed.
"""

import time

from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.base import RetrievalResult, RetrievedChunk
from rag_experiment.retrieval.bm25 import BM25Retriever
from rag_experiment.retrieval.vector import DenseRetriever


def fuse(
    rankings: dict[str, list[Chunk]], rrf_k: int, k: int
) -> list[tuple[Chunk, float, dict[str, int]]]:
    """RRF over named ranked lists (best first). Returns the top ``k`` as
    ``(chunk, rrf_score, component_ranks)``, sorted by ``(-score, chunk_id)``.
    """
    scores: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}
    ranks: dict[str, dict[str, int]] = {}
    for name, ranking in rankings.items():
        for rank, chunk in enumerate(ranking, start=1):
            cid = chunk.chunk_id
            chunks[cid] = chunk
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
            ranks.setdefault(cid, {})[name] = rank
    ordered = sorted(scores, key=lambda cid: (-scores[cid], cid))
    return [(chunks[cid], scores[cid], ranks[cid]) for cid in ordered[:k]]


class HybridRetriever:
    """Dense plus BM25, fused by RRF over the top ``depth`` of each list."""

    def __init__(
        self,
        dense: DenseRetriever,
        bm25: BM25Retriever,
        rrf_k: int,
        depth: int,
        name: str = "hybrid",
    ) -> None:
        self._dense = dense
        self._bm25 = bm25
        self._rrf_k = rrf_k
        self._depth = depth
        self.name = name

    def retrieve(self, query: str, k: int) -> RetrievalResult:
        """Top ``k`` fused chunks. ``score`` is the RRF score; ``component_ranks`` shows the
        1-based rank in each list (a missing key means: not in that list's top ``depth``).

        ``embed_ms`` is the dense query embedding; ``search_ms`` is dense search + BM25 search +
        fusion.
        """
        if not query.strip():
            raise ValueError("query must not be empty")
        if k < 1:
            raise ValueError("k must be at least 1")
        depth = max(self._depth, k)
        dense = self._dense.retrieve(query, depth)
        lexical = self._bm25.retrieve(query, depth)
        start = time.perf_counter()
        fused = fuse(
            {
                "dense": [c.chunk for c in dense.chunks],
                "bm25": [c.chunk for c in lexical.chunks],
            },
            self._rrf_k,
            k,
        )
        fusion_ms = (time.perf_counter() - start) * 1000
        chunks = tuple(
            RetrievedChunk(
                chunk=chunk,
                score=score,
                rank=rank,
                retriever=self.name,
                component_ranks=component,
            )
            for rank, (chunk, score, component) in enumerate(fused, start=1)
        )
        return RetrievalResult(
            chunks=chunks,
            embed_ms=dense.embed_ms,
            search_ms=dense.search_ms + lexical.search_ms + fusion_ms,
        )
