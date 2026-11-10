"""Unit tests for the fake provider, the embedding cache and chunk embedding."""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from rag_experiment.config import EmbeddingConfig
from rag_experiment.embeddings.fake import FakeEmbeddingProvider
from rag_experiment.embeddings.provider import (
    EmbeddingCache,
    EmbeddingError,
    SentenceTransformerProvider,
    embed_chunks,
)
from rag_experiment.ingestion.chunker import Chunk

pytestmark = pytest.mark.unit

ChunkFactory = Callable[..., Chunk]


def test_fake_provider_is_deterministic_and_normalised() -> None:
    provider = FakeEmbeddingProvider()
    a = provider.embed_query("list customer accounts")
    b = provider.embed_query("list customer accounts")
    assert np.array_equal(a, b)
    assert a.shape == (32,) and a.dtype == np.float32
    assert float(np.linalg.norm(a)) == pytest.approx(1.0)
    docs = provider.embed_documents(["one two", "three"])
    assert docs.shape == (2, 32)
    assert provider.embed_documents([]).shape == (0, 32)


def test_shared_words_give_positive_similarity() -> None:
    provider = FakeEmbeddingProvider()
    query = provider.embed_query("customer accounts list")
    near = provider.embed_query("list of customer accounts")
    far = provider.embed_query("cancel payment idempotency")
    assert float(query @ near) > float(query @ far)


def test_cache_embeds_only_missing(make_chunk: ChunkFactory, tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider()
    cache = EmbeddingCache(tmp_path / "embeddings" / "k.npz")
    chunks = [make_chunk("a", "alpha text"), make_chunk("b", "beta text")]
    vectors, stats = embed_chunks(chunks, provider, cache)
    assert vectors.shape == (2, 32)
    assert (stats.embedded, stats.cached) == (2, 0)
    reloaded = EmbeddingCache(tmp_path / "embeddings" / "k.npz")
    assert len(reloaded) == 2
    more = [*chunks, make_chunk("c", "gamma text")]
    vectors2, stats2 = embed_chunks(more, provider, reloaded)
    assert (stats2.embedded, stats2.cached) == (1, 2)
    assert np.array_equal(vectors2[:2], vectors)


def test_memory_only_cache_and_empty_input(make_chunk: ChunkFactory) -> None:
    provider = FakeEmbeddingProvider()
    cache = EmbeddingCache(None)
    embed_chunks([make_chunk("a", "alpha")], provider, cache)
    cache.save()  # no-op
    assert len(cache) == 1
    vectors, stats = embed_chunks([], provider, cache)
    assert vectors.shape == (0, 32) and stats.embedded == 0


def test_cache_key_depends_on_configuration(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider()
    a = EmbeddingCache.for_provider(tmp_path, provider, True, 1024)
    b = EmbeddingCache.for_provider(tmp_path, provider, True, 512)
    c = EmbeddingCache.for_provider(tmp_path, provider, True, 1024)
    assert a.path != b.path and a.path == c.path


def test_real_provider_load_failure_is_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("model not available")

    monkeypatch.setattr("sentence_transformers.SentenceTransformer", refuse)
    config = EmbeddingConfig(
        model_id="example/not-a-real-model",
        revision="0" * 40,
        device="cpu",
        batch_size=1,
        max_seq_length=8,
        normalize=True,
    )
    provider = SentenceTransformerProvider(config)
    assert provider.revision == "0" * 40
    with pytest.raises(EmbeddingError, match="Cannot load"):
        provider.embed_query("hello")
