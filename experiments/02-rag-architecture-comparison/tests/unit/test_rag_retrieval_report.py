"""The report is rendered from a hand-made summary; no retrieval runs."""

from datetime import UTC, datetime

import pytest

from rag_experiment.evaluation.retrieval_metrics import QuestionRetrieval, RankedChunk, summarize
from rag_experiment.evaluation.retrieval_run import (
    EmbeddingMetadata,
    RetrievalRunMetadata,
    make_run_id,
    render_report,
)

pytestmark = pytest.mark.unit

ZERO = {1: 0.0, 3: 0.0, 5: 0.0, 10: 0.0}


def _record(qid: str, category: str, rank: int | None) -> QuestionRetrieval:
    hit = {k: 1.0 if rank is not None and rank <= k else 0.0 for k in ZERO}
    return QuestionRetrieval(
        run_id="r",
        question_id=qid,
        category=category,
        paraphrase_of=None,
        retriever="dense",
        k=10,
        excluded=False,
        ranked=(RankedChunk(rank=1, chunk_id="doc:c1", score=0.5, relevant=rank == 1),),
        relevant_chunk_ids=("doc:c1",),
        n_relevant_sources=1,
        hit=hit,
        recall=dict(hit),
        precision=dict(ZERO),
        reciprocal_rank=0.0 if rank is None else 1 / rank,
        first_relevant_rank=rank,
        embed_ms=10.0,
        search_ms=1.0,
    )


def test_run_id_format() -> None:
    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=UTC)
    assert (
        make_run_id("measured", "dense", False, now) == "20261111T120000Z-retrieval-measured-dense"
    )
    assert make_run_id("dev", "dense", True, now).endswith("-retrieval-dev-dense-fake")


def test_report_contains_the_expected_sections() -> None:
    records = [_record("Q1", "semantic", 1), _record("Q2", "exact_identifier", None)]
    summary = summarize("r", "measured", records, [])
    now = datetime(2026, 11, 11, tzinfo=UTC)
    metadata = RetrievalRunMetadata(
        run_id="r",
        kind="retrieval",
        simulated=False,
        experiment="e",
        experiment_version="0.1.0",
        git_sha="abc",
        git_dirty=False,
        started_at=now,
        finished_at=now,
        hardware={},
        os="os",
        python_version="3.12",
        package_versions={},
        corpus_version="1.0.0",
        corpus_checksum="cs",
        question_set="measured",
        question_set_version="1.0.0",
        question_set_checksum="qs",
        embedding=EmbeddingMetadata(
            model_id="m/x",
            revision="rev",
            device="cpu",
            dimension=4,
            normalize=True,
            max_seq_length=8,
            batch_size=2,
        ),
        chunking={"max_chunk_chars": 10},
        retrieval={"top_k_eval": 10, "top_k_generation": 5},
        collection="col",
        retriever="dense",
        torch_threads=4,
        deterministic=True,
    )
    ingest = {
        "this_invocation": {"chunks": 2, "embedded": 0, "cached": 2, "up_to_date": True},
        "index_build": {
            "chunks": 2,
            "embedded": 2,
            "cached": 0,
            "embed_seconds": 1.5,
            "upsert_seconds": 0.1,
        },
    }
    text = render_report(metadata, summary, records, ingest)
    for heading in (
        "## Setup",
        "## Metrics",
        "## Hypothesis verdicts",
        "## Per question",
        "## Paraphrase pairs",
        "## Latency",
        "## Indexing cost",
    ):
        assert heading in text
    assert "not in top 10" in text
    assert "| HA1 |" in text and "pending (needs generation" in text
    assert "Simulated run" not in text
    assert "embedding 1.50 s" in text
