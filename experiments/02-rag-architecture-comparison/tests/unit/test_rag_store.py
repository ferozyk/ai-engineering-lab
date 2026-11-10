"""Unit tests for the Qdrant store (in-memory client) and ingestion."""

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from qdrant_client import QdrantClient

from rag_experiment.config import ChunkingConfig, IndexConfig
from rag_experiment.corpus import Corpus
from rag_experiment.embeddings.fake import FakeEmbeddingProvider
from rag_experiment.embeddings.provider import EmbeddingCache
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.store import (
    IndexLockedError,
    QdrantStore,
    collection_name,
    ingest,
    open_local_store,
    point_id,
)

pytestmark = pytest.mark.unit

ChunkFactory = Callable[..., Chunk]

TEXTS = {
    "a": "list customer accounts endpoint",
    "b": "cancel payment idempotency key header",
    "c": "statement request date range format",
}


def _chunks(make_chunk: ChunkFactory) -> list[Chunk]:
    return [make_chunk(cid, text, f"#/paths/~1{cid}/get") for cid, text in TEXTS.items()]


def test_point_ids_are_deterministic_uuids() -> None:
    assert point_id("x:y") == point_id("x:y")
    assert point_id("x:y") != point_id("x:z")
    assert str(uuid.UUID(point_id("x:y"))) == point_id("x:y")


def test_search_returns_nearest_and_round_trips_payload(make_chunk: ChunkFactory) -> None:
    provider = FakeEmbeddingProvider()
    chunks = _chunks(make_chunk)
    store = QdrantStore(QdrantClient(":memory:"), "t")
    assert store.count() == 0 and store.search(provider.embed_query("x"), 3) == []
    store.recreate(provider.dimension)
    store.upsert(chunks, provider.embed_documents([c.content for c in chunks]))
    assert store.count() == 3
    hits = store.search(provider.embed_query("which endpoint lists customer accounts"), 2)
    assert hits[0][0] == chunks[0]  # payload rebuilt into an equal Chunk
    assert len(hits) == 2 and hits[0][1] >= hits[1][1]


def test_ingest_is_idempotent_and_rebuild_recreates(make_chunk: ChunkFactory) -> None:
    provider = FakeEmbeddingProvider()
    chunks = _chunks(make_chunk)
    cache = EmbeddingCache(None)
    store = QdrantStore(QdrantClient(":memory:"), "t")
    first = ingest(chunks, provider, cache, store)
    assert not first.up_to_date and first.embedded == 3 and store.count() == 3
    second = ingest(chunks, provider, cache, store)
    assert second.up_to_date and second.embedded == 0 and store.count() == 3
    rebuilt = ingest(chunks, provider, cache, store, rebuild=True)
    assert not rebuilt.up_to_date and rebuilt.embedded == 0 and rebuilt.cached == 3
    assert store.count() == 3


def test_ingest_recreates_on_count_mismatch(make_chunk: ChunkFactory) -> None:
    provider = FakeEmbeddingProvider()
    chunks = _chunks(make_chunk)
    store = QdrantStore(QdrantClient(":memory:"), "t")
    ingest(chunks[:2], provider, EmbeddingCache(None), store)
    report = ingest(chunks, provider, EmbeddingCache(None), store)
    assert not report.up_to_date and store.count() == 3


def test_collection_name_changes_with_inputs() -> None:
    corpus = Corpus(specs=(), documents={}, version="1.0.0", checksum="ABCDEF1234567890")
    index = IndexConfig(dir=Path("x"), collection_prefix="lab-bank")
    chunking = ChunkingConfig(max_chunk_chars=2400)
    name = collection_name(
        index, corpus, chunking, "BAAI/bge-m3", "5617a9f61b028005a4858fdac845db406aefb181"
    )
    assert name == "lab-bank-c1-0-0-abcdef12-bge-m3-5617a9f6-m2400"
    other = collection_name(
        index, corpus, ChunkingConfig(max_chunk_chars=100), "BAAI/bge-m3", "unpinned"
    )
    assert other != name and other.endswith("-m100")
    assert all((ch.isalnum() and ch.islower()) or ch.isdigit() or ch == "-" for ch in name)


def test_local_store_lock_is_reported(tmp_path: Path) -> None:
    with (
        open_local_store(tmp_path, "t"),
        pytest.raises(IndexLockedError),
        open_local_store(tmp_path, "t"),
    ):
        pass
