"""BM25 keyword retrieval, written from the formula (no search library).

BM25 scores a document higher when it contains the query's rare terms often, with diminishing
returns for repeats and a penalty for long documents. For a query, a document ``d`` scores::

    sum over unique query tokens t of
        idf(t) * tf(t, d) * (k1 + 1) / (tf(t, d) + k1 * (1 - b + b * dl / avgdl))

``idf(t) = ln((N - df(t) + 0.5) / (df(t) + 0.5) + 1)``. This is the non-negative (Lucene) variant:
the classic form can go negative for terms that appear in more than half the documents; adding 1
inside the logarithm keeps every term worth at least a little.
"""

import math
import time
from collections import Counter
from collections.abc import Sequence

from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.base import RetrievalResult, RetrievedChunk
from rag_experiment.retrieval.tokenize import tokenize


class BM25Index:
    """An in-memory BM25 index over chunk contents."""

    def __init__(self, chunks: Sequence[Chunk], k1: float, b: float) -> None:
        if not chunks:
            raise ValueError("cannot index zero chunks")
        self._chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self._tf: list[Counter[str]] = [Counter(tokenize(c.content)) for c in self._chunks]
        self._lengths = [sum(tf.values()) for tf in self._tf]
        self.n_docs = len(self._chunks)
        self.avgdl = sum(self._lengths) / self.n_docs
        self._df: Counter[str] = Counter()
        for tf in self._tf:
            self._df.update(tf.keys())

    def idf(self, token: str) -> float:
        """Lucene-style inverse document frequency; 0.0 for a token not in the vocabulary."""
        df = self._df.get(token, 0)
        if df == 0:
            return 0.0
        return math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1.0)

    def in_vocabulary(self, token: str) -> bool:
        """Whether any indexed chunk contains the token."""
        return token in self._df

    def _score(self, index: int, query_tokens: Sequence[str]) -> float:
        tf = self._tf[index]
        norm = self.k1 * (1.0 - self.b + self.b * self._lengths[index] / self.avgdl)
        score = 0.0
        for token in query_tokens:
            f = tf.get(token, 0)
            if f:
                score += self.idf(token) * f * (self.k1 + 1.0) / (f + norm)
        return score

    def search(self, query: str, k: int) -> list[tuple[Chunk, float]]:
        """Top ``k`` chunks by ``(-score, chunk_id)``. Chunks scoring 0 are never returned."""
        unique = sorted(set(tokenize(query)))
        known = [t for t in unique if self.in_vocabulary(t)]
        if not known:
            return []
        scored = [(self._chunks[i], self._score(i, known)) for i in range(self.n_docs)]
        hits = [(chunk, score) for chunk, score in scored if score > 0.0]
        hits.sort(key=lambda hit: (-hit[1], hit[0].chunk_id))
        return hits[:k]


class BM25Retriever:
    """The ``Retriever`` interface over a :class:`BM25Index`. No embedding is involved."""

    def __init__(self, index: BM25Index, name: str = "bm25") -> None:
        self._index = index
        self.name = name

    def retrieve(self, query: str, k: int) -> RetrievalResult:
        """Top ``k`` chunks; ``embed_ms`` is 0 because nothing is embedded."""
        if not query.strip():
            raise ValueError("query must not be empty")
        if k < 1:
            raise ValueError("k must be at least 1")
        start = time.perf_counter()
        hits = self._index.search(query, k)
        search_ms = (time.perf_counter() - start) * 1000
        chunks = tuple(
            RetrievedChunk(chunk=chunk, score=score, rank=rank, retriever=self.name)
            for rank, (chunk, score) in enumerate(hits, start=1)
        )
        return RetrievalResult(chunks=chunks, embed_ms=0.0, search_ms=search_ms)
