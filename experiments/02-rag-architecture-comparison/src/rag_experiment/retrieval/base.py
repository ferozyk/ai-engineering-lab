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


class RetrievalResult(BaseModel):
    """The ranked chunks of one query and the time each stage took."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunks: tuple[RetrievedChunk, ...]
    embed_ms: float
    search_ms: float


class Retriever(Protocol):
    """Anything that returns ranked chunks for a query."""

    name: str

    def retrieve(self, query: str, k: int) -> RetrievalResult:
        """Return the top ``k`` chunks. ``embed_ms`` is 0 for retrievers that do not embed."""
        ...
