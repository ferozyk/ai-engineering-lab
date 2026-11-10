"""Qdrant vector store (local, in-process mode) and the ingestion routine.

Local mode keeps the index in a folder and holds a file lock, so only one process can open it at a
time. Search is exact (brute force), which is fine for a few hundred chunks.
"""

import re
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from rag_experiment.config import ChunkingConfig, IndexConfig
from rag_experiment.corpus import Corpus
from rag_experiment.embeddings.provider import EmbeddingCache, EmbeddingProvider, embed_chunks
from rag_experiment.ingestion.chunker import Chunk

# A fixed namespace so a chunk id always maps to the same point id.
NAMESPACE = uuid.UUID("6f1c2f0e-7b0a-4c52-9a3e-2d5f0b8e4a11")


def point_id(chunk_id: str) -> str:
    """Deterministic UUID for a chunk id."""
    return str(uuid.uuid5(NAMESPACE, chunk_id))


def collection_name(
    index: IndexConfig,
    corpus: Corpus,
    chunking: ChunkingConfig,
    model_id: str,
    revision: str,
) -> str:
    """Name that changes with the corpus, chunking or model, so vectors are never mixed."""
    model_slug = model_id.split("/")[-1]
    raw = (
        f"{index.collection_prefix}-c{corpus.version}-{corpus.checksum[:8]}-"
        f"{model_slug}-{revision[:8]}-m{chunking.max_chunk_chars}"
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", raw.lower()))


class IndexLockedError(RuntimeError):
    """Raised when the local index is already open in another process."""


class QdrantStore:
    """One collection of chunk vectors with cosine distance."""

    def __init__(self, client: QdrantClient, collection: str) -> None:
        self._client = client
        self.collection = collection

    def exists(self) -> bool:
        """True if the collection exists."""
        return bool(self._client.collection_exists(self.collection))

    def recreate(self, dimension: int) -> None:
        """Delete the collection if present, then create it empty."""
        if self.exists():
            self._client.delete_collection(self.collection)
        self._client.create_collection(
            self.collection,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )

    def upsert(self, chunks: Sequence[Chunk], vectors: np.ndarray) -> None:
        """Insert or replace the chunks; the payload is the full chunk record."""
        points = [
            PointStruct(
                id=point_id(chunk.chunk_id),
                vector=[float(x) for x in vector],
                payload=chunk.model_dump(mode="json"),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self._client.upsert(self.collection, points=points)

    def count(self) -> int:
        """Number of stored points (0 if the collection does not exist)."""
        if not self.exists():
            return 0
        return int(self._client.count(self.collection, exact=True).count)

    def search(self, vector: np.ndarray, k: int) -> list[tuple[Chunk, float]]:
        """The ``k`` nearest chunks with their cosine similarity."""
        if not self.exists():
            return []
        response = self._client.query_points(
            self.collection,
            query=[float(x) for x in vector],
            limit=k,
            with_payload=True,
        )
        return [
            (Chunk.model_validate(point.payload), float(point.score)) for point in response.points
        ]


@contextmanager
def open_local_store(index_dir: Path | None, collection: str) -> Iterator[QdrantStore]:
    """Open the local index. Only one process may hold it at a time (file lock).

    ``index_dir=None`` opens a throwaway in-memory index (used for fake-embedding dry runs).
    """
    if index_dir is None:
        client = QdrantClient(":memory:")
    else:
        index_dir.mkdir(parents=True, exist_ok=True)
        try:
            client = QdrantClient(path=str(index_dir / "qdrant"))
        except RuntimeError as exc:
            raise IndexLockedError(
                f"Cannot open the local index at {index_dir / 'qdrant'}; it may be in use by "
                f"another process (local mode allows one at a time): {exc}"
            ) from exc
    try:
        yield QdrantStore(client, collection)
    finally:
        client.close()


class IngestReport(BaseModel):
    """What an ingestion did."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunks: int
    embedded: int
    cached: int
    embed_seconds: float
    upsert_seconds: float
    collection: str
    dimension: int
    up_to_date: bool


@dataclass(frozen=True)
class _Timer:
    start: float

    def elapsed(self) -> float:
        return time.perf_counter() - self.start


def ingest(
    chunks: Sequence[Chunk],
    provider: EmbeddingProvider,
    cache: EmbeddingCache,
    store: QdrantStore,
    rebuild: bool = False,
) -> IngestReport:
    """Embed and index the chunks. Skips when the collection already has the expected count."""
    if not rebuild and store.count() == len(chunks):
        return IngestReport(
            chunks=len(chunks),
            embedded=0,
            cached=len(chunks),
            embed_seconds=0.0,
            upsert_seconds=0.0,
            collection=store.collection,
            dimension=provider.dimension,
            up_to_date=True,
        )
    timer = _Timer(time.perf_counter())
    vectors, stats = embed_chunks(chunks, provider, cache)
    embed_seconds = timer.elapsed()
    timer = _Timer(time.perf_counter())
    store.recreate(provider.dimension)
    store.upsert(chunks, vectors)
    return IngestReport(
        chunks=len(chunks),
        embedded=stats.embedded,
        cached=stats.cached,
        embed_seconds=embed_seconds,
        upsert_seconds=timer.elapsed(),
        collection=store.collection,
        dimension=provider.dimension,
        up_to_date=False,
    )
