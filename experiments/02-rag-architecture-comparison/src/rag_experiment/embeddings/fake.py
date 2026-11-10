"""A deterministic stand-in embedding provider for tests and dry runs. It is not a real model."""

import hashlib
import re
from collections.abc import Sequence

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")


class FakeEmbeddingProvider:
    """Hashed bag-of-words vectors: texts that share words get a positive similarity."""

    model_id = "fake-hashed-bow"
    revision = "fake"

    def __init__(self, dimension: int = 32) -> None:
        self.dimension = dimension

    def _embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimension, dtype=np.float32)
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            sign = 1.0 if (value >> 63) & 1 else -1.0
            vector[value % self.dimension] += sign
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """Embed many texts; shape ``(n, dimension)``, float32."""
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        return np.stack([self._embed(t) for t in texts]).astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        """Embed one query; shape ``(dimension,)``."""
        return self._embed(text)
