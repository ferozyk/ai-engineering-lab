"""Source coverage: how many of a question's labelled sources a context covers.

A labelled source is covered when at least one chunk of the context is relevant to it (the same
ownership rule as retrieval recall). One function is used for every architecture, so the numbers of
different runs are comparable.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from rag_experiment.evaluation.answer_run import AnswerRecord, latest_by_attempt
from rag_experiment.evaluation.dataset import Question
from rag_experiment.evaluation.relevance import covered_sources
from rag_experiment.ingestion.chunker import Chunk

MULTI_ENDPOINT = "multi_endpoint"


@dataclass(frozen=True)
class CoverageContext:
    """The labelled questions (by id) and the corpus chunks needed to compute coverage."""

    questions: Mapping[str, Question]
    chunks: Sequence[Chunk]


def attempt_coverage(
    ctx: CoverageContext, question_id: str, context_ids: Collection[str]
) -> tuple[int, int]:
    """``(sources covered, labelled sources)`` of a context for one question."""
    sources = frozenset(ctx.questions[question_id].sources)
    return len(covered_sources(context_ids, sources, ctx.chunks)), len(sources)


def full_coverage(
    records: Sequence[AnswerRecord], ctx: CoverageContext, category: str = MULTI_ENDPOINT
) -> tuple[int, int]:
    """Attempts whose context covers every labelled source, over the answerable attempts of
    ``category`` (latest record of each attempt; infrastructure errors excluded).
    """
    scored = [
        r
        for r in latest_by_attempt(records).values()
        if r.outcome != "infra_error" and not r.must_abstain and r.category == category
    ]
    full = 0
    for record in scored:
        covered, total = attempt_coverage(ctx, record.question_id, record.context_chunk_ids)
        full += covered == total
    return full, len(scored)
