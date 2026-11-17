"""Rerankers: score how well each text answers a query.

A *bi-encoder* (the embedding model) turns the query and each chunk into vectors separately and
compares the vectors. A *cross-encoder* reads the query and one chunk together in a single pass and
outputs one relevance score, which is slower but can model their interaction directly. The
retrieval pipeline depends only on the ``Reranker`` protocol, so a real model and a test double
are interchangeable.
"""

import logging
from collections.abc import Sequence
from typing import Any, Protocol

from rag_experiment.config import RerankConfig

logger = logging.getLogger(__name__)


class RerankError(RuntimeError):
    """Raised when the reranker model cannot be loaded or fails to score."""


class Reranker(Protocol):
    """Scores a list of texts against a query; a higher score means more relevant."""

    model_id: str
    revision: str

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        """One score per text, in input order."""
        ...


class CrossEncoderReranker:
    """A local sentence-transformers ``CrossEncoder``, loaded lazily on first use.

    Installed sentence-transformers 6.2.0: ``CrossEncoder(model_name_or_path, *, device, revision,
    model_kwargs, max_length, activation_fn, ...)`` and ``predict(inputs, batch_size,
    show_progress_bar, activation_fn, apply_softmax=False, convert_to_numpy=True, ...)``. When no
    ``activation_fn`` is passed, the model's own default is used: a sigmoid for single-label models
    (this one), applied to the logit. The sigmoid is monotonic, so the order of the texts is the
    order of the raw logits; the scores are therefore in (0, 1). The default is left unchanged.
    """

    def __init__(self, config: RerankConfig) -> None:
        self._config = config
        self._model: Any = None
        self.model_id = config.model_id
        self.revision = config.revision

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import CrossEncoder

            model = CrossEncoder(
                self._config.model_id,
                revision=self._config.revision,
                device=self._config.device,
                max_length=self._config.max_length,
                model_kwargs=(
                    {}
                    if self._config.use_safetensors is None
                    else {"use_safetensors": self._config.use_safetensors}
                ),
            )
        except Exception as exc:
            raise RerankError(
                f"Cannot load reranker model {self._config.model_id!r} "
                f"(revision {self.revision}, device {self._config.device}). It may not be "
                f"downloaded and the network may be unavailable, or the device may be "
                f"unsupported: {exc}"
            ) from exc
        self._model = model
        return model

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        """Relevance score of each text for the query, as plain floats in input order."""
        if not texts:
            return []
        model = self._load()
        try:
            scores = model.predict(
                [(query, text) for text in texts],
                batch_size=self._config.batch_size,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise RerankError(
                f"Reranking failed with model {self._config.model_id!r}: {exc}"
            ) from exc
        return [float(s) for s in scores]
