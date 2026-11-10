"""Embedding providers and the on-disk embedding cache.

An *embedding provider* turns text into vectors. The retriever and the indexer depend only on the
``EmbeddingProvider`` protocol, so a real model and a test double are interchangeable.
"""

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from rag_experiment.config import EmbeddingConfig
from rag_experiment.ingestion.chunker import Chunk

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Raised when the embedding model cannot be loaded or fails to encode."""


class EmbeddingProvider(Protocol):
    """Turns text into float32 vectors of a fixed dimension."""

    @property
    def model_id(self) -> str:
        """Model identifier."""
        ...

    @property
    def revision(self) -> str:
        """Pinned revision, or ``"unpinned"``."""
        ...

    @property
    def dimension(self) -> int:
        """Embedding dimension."""
        ...

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """Embed documents; shape ``(n, dimension)``."""
        ...

    def embed_query(self, text: str) -> np.ndarray:
        """Embed one query; shape ``(dimension,)``."""
        ...


class SentenceTransformerProvider:
    """A local sentence-transformers model, loaded lazily on first use.

    No query prefix is added: the BGE-M3 model card says none is needed for retrieval.
    """

    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config
        self._model: Any = None
        self._dimension: int | None = None
        self.model_id = config.model_id
        self.revision = config.revision or "unpinned"

    @property
    def dimension(self) -> int:
        """Embedding dimension (loads the model if needed)."""
        if self._dimension is None:
            dim = self._load().get_embedding_dimension()
            if not isinstance(dim, int):
                raise EmbeddingError("The model did not report an embedding dimension")
            self._dimension = dim
        return self._dimension

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(
                self._config.model_id,
                revision=self._config.revision,
                device=self._config.device,
                model_kwargs=(
                    {}
                    if self._config.use_safetensors is None
                    else {"use_safetensors": self._config.use_safetensors}
                ),
            )
            model.max_seq_length = self._config.max_seq_length
        except Exception as exc:
            raise EmbeddingError(
                f"Cannot load embedding model {self._config.model_id!r} "
                f"(revision {self.revision}, device {self._config.device}). It may not be "
                f"downloaded and the network may be unavailable, or the device may be "
                f"unsupported: {exc}"
            ) from exc
        self._model = model
        return model

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        model = self._load()
        try:
            vectors = model.encode(
                list(texts),
                normalize_embeddings=self._config.normalize,
                batch_size=self._config.batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise EmbeddingError(f"Embedding failed: {exc}") from exc
        return np.asarray(vectors, dtype=np.float32)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """Embed documents; shape ``(n, dimension)``."""
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        return self._encode(texts)

    def embed_query(self, text: str) -> np.ndarray:
        """Embed one query; shape ``(dimension,)``."""
        return np.asarray(self._encode([text])[0], dtype=np.float32)

    def token_count(self, text: str) -> int:
        """Number of tokens the model's tokenizer produces for ``text``."""
        tokenizer = self._load().tokenizer
        return len(tokenizer(text, add_special_tokens=True)["input_ids"])


class EmbeddingCache:
    """``{content_hash: vector}`` stored in one ``.npz`` file per embedding configuration."""

    def __init__(self, path: Path | None) -> None:
        """``path=None`` gives a memory-only cache (used for fake-embedding dry runs)."""
        self.path = path
        self._vectors: dict[str, np.ndarray] = {}
        if path is not None and path.is_file():
            with np.load(path) as data:
                self._vectors = {key: data[key] for key in data.files}

    @classmethod
    def for_provider(
        cls, directory: Path, provider: EmbeddingProvider, normalize: bool, max_seq_length: int
    ) -> "EmbeddingCache":
        """Cache file keyed by model id, revision, normalisation and max sequence length."""
        key = f"{provider.model_id}|{provider.revision}|{normalize}|{max_seq_length}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        return cls(directory / "embeddings" / f"{digest}.npz")

    def __contains__(self, content_hash: str) -> bool:
        return content_hash in self._vectors

    def __len__(self) -> int:
        return len(self._vectors)

    def get(self, content_hash: str) -> np.ndarray:
        """The cached vector for ``content_hash``."""
        return self._vectors[content_hash]

    def put(self, content_hash: str, vector: np.ndarray) -> None:
        """Store a vector (in memory until :meth:`save`)."""
        self._vectors[content_hash] = np.asarray(vector, dtype=np.float32)

    def save(self) -> None:
        """Write the cache to disk (no-op for a memory-only cache)."""
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.path, **self._vectors)  # type: ignore[arg-type]


@dataclass(frozen=True)
class EmbedStats:
    """How many chunk vectors were computed and how many came from the cache."""

    embedded: int
    cached: int


def embed_chunks(
    chunks: Sequence[Chunk], provider: EmbeddingProvider, cache: EmbeddingCache
) -> tuple[np.ndarray, EmbedStats]:
    """Vectors for ``chunks`` in chunk order, embedding only those missing from the cache."""
    missing: dict[str, str] = {}
    for chunk in chunks:
        if chunk.content_hash not in cache and chunk.content_hash not in missing:
            missing[chunk.content_hash] = chunk.content
    if missing:
        vectors = provider.embed_documents(list(missing.values()))
        for content_hash, vector in zip(missing, vectors, strict=True):
            cache.put(content_hash, vector)
        cache.save()
    stats = EmbedStats(embedded=len(missing), cached=len(chunks) - len(missing))
    if not chunks:
        return np.zeros((0, provider.dimension), dtype=np.float32), stats
    return np.stack([cache.get(c.content_hash) for c in chunks]).astype(np.float32), stats
