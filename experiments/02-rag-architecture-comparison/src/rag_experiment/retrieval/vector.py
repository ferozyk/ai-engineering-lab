"""Dense (embedding similarity) retrieval."""

import time

from rag_experiment.embeddings.provider import EmbeddingProvider
from rag_experiment.retrieval.base import RetrievalResult, RetrievedChunk
from rag_experiment.retrieval.store import QdrantStore


class DenseRetriever:
    """Embed the query and return the nearest chunks by cosine similarity."""

    def __init__(
        self, provider: EmbeddingProvider, store: QdrantStore, name: str = "dense"
    ) -> None:
        self._provider = provider
        self._store = store
        self.name = name

    def retrieve(self, query: str, k: int) -> RetrievalResult:
        """Top ``k`` chunks; ties are broken by chunk id so the order is deterministic."""
        if not query.strip():
            raise ValueError("query must not be empty")
        if k < 1:
            raise ValueError("k must be at least 1")
        start = time.perf_counter()
        vector = self._provider.embed_query(query)
        embed_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        # Ties exactly at the cut-off are theoretically possible; the store returns k hits and
        # the tie-break below only orders those.
        hits = self._store.search(vector, k)
        search_ms = (time.perf_counter() - start) * 1000
        hits.sort(key=lambda hit: (-hit[1], hit[0].chunk_id))
        chunks = tuple(
            RetrievedChunk(chunk=chunk, score=score, rank=rank, retriever=self.name)
            for rank, (chunk, score) in enumerate(hits, start=1)
        )
        return RetrievalResult(chunks=chunks, embed_ms=embed_ms, search_ms=search_ms)
