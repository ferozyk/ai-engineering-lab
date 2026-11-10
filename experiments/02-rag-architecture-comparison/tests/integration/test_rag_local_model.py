"""Tests that load the real embedding model. Opt in with ``pytest -m local_model``.

They need the model downloaded (or in the Hugging Face cache) and are never part of the default
suite or CI.
"""

from pathlib import Path

import numpy as np
import pytest

from rag_experiment.config import ExperimentConfig
from rag_experiment.embeddings.provider import EmbeddingCache, SentenceTransformerProvider
from rag_experiment.evaluation.dataset import load_questions
from rag_experiment.evaluation.relevance import relevant_chunk_ids
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.store import ingest, open_local_store
from rag_experiment.retrieval.vector import DenseRetriever

pytestmark = [pytest.mark.integration, pytest.mark.local_model]


@pytest.fixture(scope="module")
def provider(experiment_config: ExperimentConfig) -> SentenceTransformerProvider:
    return SentenceTransformerProvider(experiment_config.embedding)


def test_dimension_norm_and_determinism(provider: SentenceTransformerProvider) -> None:
    assert provider.dimension == 1024
    texts = ["List the accounts of a customer.", "Cancel a payment."]
    first = provider.embed_documents(texts)
    second = provider.embed_documents(texts)
    assert first.shape == (2, 1024) and first.dtype == np.float32
    assert np.allclose(np.linalg.norm(first, axis=1), 1.0, atol=1e-4)
    assert np.array_equal(first, second)
    assert np.array_equal(provider.embed_query(texts[0]), first[0])


def test_semantic_sanity(provider: SentenceTransformerProvider, chunks: list[Chunk]) -> None:
    by_id = {c.chunk_id: c for c in chunks}
    accounts = by_id["customers-api:listCustomerAccounts:operation"]
    cancel = by_id["payments-api:cancelPayment:operation"]
    query = provider.embed_query("Which endpoint lists a customer's accounts?")
    docs = provider.embed_documents([accounts.content, cancel.content])
    assert float(query @ docs[0]) > float(query @ docs[1])


def test_index_and_retrieve_one_dev_question(
    provider: SentenceTransformerProvider,
    experiment_config: ExperimentConfig,
    chunks: list[Chunk],
    tmp_path: Path,
) -> None:
    question = next(q for q in load_questions(experiment_config.questions_dev) if q.id == "Q01")
    with open_local_store(tmp_path, "test-collection") as store:
        ingest(chunks, provider, EmbeddingCache(None), store)
        assert store.count() == len(chunks)
        result = DenseRetriever(provider, store).retrieve(question.question, 5)
    relevant = relevant_chunk_ids(question.sources, chunks)
    assert len(result.chunks) == 5
    assert any(c.chunk.chunk_id in relevant for c in result.chunks)
