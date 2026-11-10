"""Unit tests for the retrieval metrics, including the worked example of methodology section 4."""

from collections.abc import Callable

import pytest

from rag_experiment.evaluation.retrieval_metrics import (
    QuestionRetrieval,
    RatioValue,
    compute_verdicts,
    first_relevant_rank,
    hit_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    score_question,
    summarize,
)
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.ingestion.pointers import Source

pytestmark = pytest.mark.unit

ChunkFactory = Callable[..., Chunk]

P1 = Source("doc", "#/paths/~1one/get")
P2 = Source("doc", "#/paths/~1two/get")


def _chunks(make_chunk: ChunkFactory) -> list[Chunk]:
    return [
        make_chunk("c-one", source_reference="#/paths/~1one/get"),
        make_chunk("c-two", source_reference="#/paths/~1two/get"),
        make_chunk("c-n1", source_reference="#/paths/~1n1/get"),
        make_chunk("c-n2", source_reference="#/paths/~1n2/get"),
        make_chunk("c-n3", source_reference="#/paths/~1n3/get"),
    ]


def test_worked_example(make_chunk: ChunkFactory) -> None:
    chunks = _chunks(make_chunk)
    ranked = ["c-n1", "c-one", "c-n2", "c-two", "c-n3"]
    relevant = {"c-one", "c-two"}
    assert hit_at_k(ranked, relevant, 5) == 1.0
    assert recall_at_k(ranked, [P1, P2], chunks, 5) == 1.0
    assert recall_at_k(ranked, [P1, P2], chunks, 3) == 0.5
    assert precision_at_k(ranked, relevant, 5) == 0.4
    assert reciprocal_rank(ranked, relevant) == 0.5
    assert first_relevant_rank(ranked, relevant) == 2


def test_misses_and_limits() -> None:
    assert hit_at_k(["a", "b"], {"z"}, 5) == 0.0
    assert hit_at_k(["a", "z"], {"z"}, 1) == 0.0
    assert reciprocal_rank(["a", "b"], {"z"}) == 0.0
    assert reciprocal_rank(["a", "b", "z"], {"z"}, max_rank=2) == 0.0
    assert precision_at_k(["z"], {"z"}, 5) == 0.2  # fewer results than K still divides by K
    assert first_relevant_rank(["a", "b"], {"z"}) is None


def test_recall_needs_sources(make_chunk: ChunkFactory) -> None:
    with pytest.raises(ValueError, match="at least one"):
        recall_at_k(["a"], [], [make_chunk("a")], 1)


def _record(
    make_chunk: ChunkFactory,
    qid: str,
    category: str,
    ranked: list[str],
    excluded: bool = False,
    paraphrase_of: str | None = None,
) -> QuestionRetrieval:
    chunks = _chunks(make_chunk)
    return score_question(
        run_id="r",
        question_id=qid,
        category=category,
        paraphrase_of=paraphrase_of,
        retriever="dense",
        k=10,
        sources=[] if excluded else [P1, P2],
        chunks=chunks,
        relevant_ids=set() if excluded else {"c-one", "c-two"},
        ranked=[(c, 1.0 - i / 10) for i, c in enumerate(ranked)],
        embed_ms=1.0,
        search_ms=2.0,
        excluded=excluded,
    )


def test_score_question_and_summary(make_chunk: ChunkFactory) -> None:
    rec = _record(make_chunk, "Q1", "semantic", ["c-n1", "c-one", "c-n2", "c-two", "c-n3"])
    assert rec.hit[5] == 1.0 and rec.hit[1] == 0.0
    assert rec.recall[3] == 0.5
    assert rec.first_relevant_rank == 2
    assert [r.relevant for r in rec.ranked] == [False, True, False, True, False]
    excluded = _record(make_chunk, "Q2", "unanswerable", ["c-one"], excluded=True)
    assert excluded.excluded and excluded.first_relevant_rank is None
    para = _record(make_chunk, "Q3", "semantic", ["c-n1", "c-n2"], paraphrase_of="Q1")
    summary = summarize("r", "measured", [rec, excluded, para], [])
    assert summary.n_questions == 3 and summary.n_excluded == 1
    assert summary.overall.n == 2
    assert summary.overall.hit[5] == 0.5
    assert summary.ha1_group.numerator == 1 and summary.ha1_group.denominator == 2
    assert summary.ha2_group.denominator == 0 and summary.ha2_group.value is None
    assert summary.paraphrase_pairs[0].original_first_relevant_rank == 2
    assert summary.paraphrase_pairs[0].paraphrase_first_relevant_rank is None
    assert summary.latency_total_ms.p50 == 3.0
    assert summary.deterministic is True
    assert [v.verdict for v in summary.verdicts][1] == "not testable"


def test_verdicts_follow_frozen_criteria() -> None:
    supported = compute_verdicts(
        RatioValue(numerator=9, denominator=11, value=9 / 11),
        RatioValue(numerator=3, denominator=6, value=0.5),
        frozen_set=True,
    )
    assert supported[0].verdict == "supported"
    assert supported[1].verdict == "supported"  # 0.818 - 0.5 >= 0.2
    assert supported[2].verdict.startswith("pending")
    failing = compute_verdicts(
        RatioValue(numerator=8, denominator=11, value=8 / 11),
        RatioValue(numerator=5, denominator=6, value=5 / 6),
        frozen_set=True,
    )
    assert failing[0].verdict == "not supported"
    assert failing[1].verdict == "not supported"
    development = compute_verdicts(
        RatioValue(numerator=9, denominator=11, value=9 / 11),
        RatioValue(numerator=3, denominator=6, value=0.5),
        frozen_set=False,
    )
    assert development[0].verdict == "not applicable (development set)"
    assert development[1].verdict == "not applicable (development set)"
    assert "development set" in development[0].evidence
    boundary = compute_verdicts(
        RatioValue(numerator=4, denominator=5, value=0.8),
        RatioValue(numerator=3, denominator=5, value=0.6),
        frozen_set=True,
    )
    assert boundary[0].verdict == "supported" and boundary[1].verdict == "supported"
