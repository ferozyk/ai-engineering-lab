"""Retriever interface and result types."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from rag_experiment.ingestion.chunker import Chunk


class RetrievedChunk(BaseModel):
    """A chunk with its score and 1-based rank."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk: Chunk
    score: float
    rank: int
    retriever: str
    # Hybrid and rerank: 1-based rank in each source list (rerank adds ``hybrid``).
    # A missing key means "not in that list".
    component_ranks: dict[str, int] | None = None


class RetrievalResult(BaseModel):
    """The ranked chunks of one query and the time each stage took."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunks: tuple[RetrievedChunk, ...]
    embed_ms: float
    search_ms: float
    # Rerank only; the defaults leave dense, BM25 and hybrid results unchanged.
    rerank_ms: float = 0.0
    candidate_ids: tuple[str, ...] | None = None  # the pool that was re-ordered, in pool order


class Retriever(Protocol):
    """Anything that returns ranked chunks for a query."""

    name: str

    def retrieve(self, query: str, k: int) -> RetrievalResult:
        """Return the top ``k`` chunks. ``embed_ms`` is 0 for retrievers that do not embed."""
        ...
