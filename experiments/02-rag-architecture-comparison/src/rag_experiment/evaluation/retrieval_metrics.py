"""Retrieval metrics: pure functions, per-question records and the run summary.

Definitions follow ``docs/evaluation-methodology.md`` section 4. Nothing here does I/O.
"""

from collections import defaultdict
from collections.abc import Collection, Sequence

from pydantic import BaseModel, ConfigDict

from ai_lab.benchmarking import percentile
from rag_experiment.evaluation.relevance import covered_sources
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.ingestion.pointers import Source

KS = (1, 3, 5, 10)
HA1_CATEGORIES = ("semantic", "endpoint_discovery")
HA2_CATEGORIES = ("exact_identifier",)
# Frozen criteria (methodology section 8).
HA1_MIN_HIT5 = 0.80
HA2_MIN_GAP = 0.20


def hit_at_k(ranked_ids: Sequence[str], relevant_ids: Collection[str], k: int) -> float:
    """1.0 if any of the top ``k`` chunks is relevant, else 0.0."""
    relevant = set(relevant_ids)
    return 1.0 if any(i in relevant for i in ranked_ids[:k]) else 0.0


def recall_at_k(
    ranked_ids: Sequence[str], sources: Collection[Source], chunks: Sequence[Chunk], k: int
) -> float:
    """Labelled sources covered by the top ``k`` chunks, divided by all labelled sources."""
    if not sources:
        raise ValueError("recall needs at least one labelled source")
    return len(covered_sources(ranked_ids[:k], sources, chunks)) / len(sources)


def precision_at_k(ranked_ids: Sequence[str], relevant_ids: Collection[str], k: int) -> float:
    """Relevant chunks in the top ``k`` divided by ``k``."""
    relevant = set(relevant_ids)
    return sum(1 for i in ranked_ids[:k] if i in relevant) / k


def first_relevant_rank(
    ranked_ids: Sequence[str], relevant_ids: Collection[str], max_rank: int = 10
) -> int | None:
    """1-based rank of the first relevant chunk within ``max_rank``, or ``None``."""
    relevant = set(relevant_ids)
    for rank, chunk_id in enumerate(ranked_ids[:max_rank], start=1):
        if chunk_id in relevant:
            return rank
    return None


def reciprocal_rank(
    ranked_ids: Sequence[str], relevant_ids: Collection[str], max_rank: int = 10
) -> float:
    """1 / rank of the first relevant chunk, or 0.0 if none within ``max_rank``."""
    rank = first_relevant_rank(ranked_ids, relevant_ids, max_rank)
    return 0.0 if rank is None else 1.0 / rank


class RankedChunk(BaseModel):
    """One retrieved chunk in a question record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rank: int
    chunk_id: str
    score: float
    relevant: bool


class QuestionRetrieval(BaseModel):
    """Retrieval outcome and metrics for one question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    question_id: str
    category: str
    paraphrase_of: str | None
    retriever: str
    k: int
    excluded: bool
    ranked: tuple[RankedChunk, ...]
    relevant_chunk_ids: tuple[str, ...]
    n_relevant_sources: int
    hit: dict[int, float]
    recall: dict[int, float]
    precision: dict[int, float]
    reciprocal_rank: float
    first_relevant_rank: int | None
    embed_ms: float
    search_ms: float


def score_question(
    run_id: str,
    question_id: str,
    category: str,
    paraphrase_of: str | None,
    retriever: str,
    k: int,
    sources: Collection[Source],
    chunks: Sequence[Chunk],
    relevant_ids: Collection[str],
    ranked: Sequence[tuple[str, float]],
    embed_ms: float,
    search_ms: float,
    excluded: bool,
) -> QuestionRetrieval:
    """Build the record for one question. Excluded questions carry zeroed metrics."""
    ids = [chunk_id for chunk_id, _ in ranked]
    relevant = set(relevant_ids)
    records = tuple(
        RankedChunk(rank=r, chunk_id=cid, score=score, relevant=cid in relevant)
        for r, (cid, score) in enumerate(ranked, start=1)
    )
    if excluded:
        zeros = dict.fromkeys(KS, 0.0)
        return QuestionRetrieval(
            run_id=run_id,
            question_id=question_id,
            category=category,
            paraphrase_of=paraphrase_of,
            retriever=retriever,
            k=k,
            excluded=True,
            ranked=records,
            relevant_chunk_ids=(),
            n_relevant_sources=0,
            hit=zeros,
            recall=dict(zeros),
            precision=dict(zeros),
            reciprocal_rank=0.0,
            first_relevant_rank=None,
            embed_ms=embed_ms,
            search_ms=search_ms,
        )
    return QuestionRetrieval(
        run_id=run_id,
        question_id=question_id,
        category=category,
        paraphrase_of=paraphrase_of,
        retriever=retriever,
        k=k,
        excluded=False,
        ranked=records,
        relevant_chunk_ids=tuple(sorted(relevant)),
        n_relevant_sources=len(sources),
        hit={kk: hit_at_k(ids, relevant, kk) for kk in KS},
        recall={kk: recall_at_k(ids, sources, chunks, kk) for kk in KS},
        precision={kk: precision_at_k(ids, relevant, kk) for kk in KS},
        reciprocal_rank=reciprocal_rank(ids, relevant),
        first_relevant_rank=first_relevant_rank(ids, relevant),
        embed_ms=embed_ms,
        search_ms=search_ms,
    )


# ------------------------------------------------------------------------------ summary


class GroupMetrics(BaseModel):
    """Mean metrics over a group of answerable questions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n: int
    hit: dict[int, float]
    recall: dict[int, float]
    precision: dict[int, float]
    mrr: float


class RatioValue(BaseModel):
    """A rate with its numerator and denominator."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    numerator: int
    denominator: int
    value: float | None


class ParaphrasePair(BaseModel):
    """First relevant rank of a question and its paraphrase (``None`` = not in the top 10)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    original: str
    paraphrase: str
    original_first_relevant_rank: int | None
    paraphrase_first_relevant_rank: int | None


class LatencyStats(BaseModel):
    """p50 and p95 in milliseconds over ``n`` questions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n: int
    p50: float
    p95: float


class Verdict(BaseModel):
    """A hypothesis outcome computed mechanically from the frozen criterion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis: str
    criterion: str
    verdict: str
    evidence: str


class RetrievalSummary(BaseModel):
    """Everything the report shows."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    question_set: str
    n_questions: int
    n_excluded: int
    overall: GroupMetrics
    by_category: dict[str, GroupMetrics]
    ha1_group: RatioValue
    ha2_group: RatioValue
    paraphrase_pairs: tuple[ParaphrasePair, ...]
    latency_embed_ms: LatencyStats
    latency_search_ms: LatencyStats
    latency_total_ms: LatencyStats
    verdicts: tuple[Verdict, ...]
    deterministic: bool
    nondeterministic_questions: tuple[str, ...]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def group_metrics(records: Sequence[QuestionRetrieval]) -> GroupMetrics:
    """Mean metrics over answerable records (callers pass non-excluded records only)."""
    if not records:
        zeros = dict.fromkeys(KS, 0.0)
        return GroupMetrics(n=0, hit=zeros, recall=dict(zeros), precision=dict(zeros), mrr=0.0)
    return GroupMetrics(
        n=len(records),
        hit={k: _mean([r.hit[k] for r in records]) for k in KS},
        recall={k: _mean([r.recall[k] for r in records]) for k in KS},
        precision={k: _mean([r.precision[k] for r in records]) for k in KS},
        mrr=_mean([r.reciprocal_rank for r in records]),
    )


def hit5_ratio(records: Sequence[QuestionRetrieval], categories: Collection[str]) -> RatioValue:
    """Hit@5 over the answerable questions in ``categories``, with numerator and denominator."""
    group = [r for r in records if not r.excluded and r.category in categories]
    hits = sum(1 for r in group if r.hit[5] == 1.0)
    return RatioValue(
        numerator=hits, denominator=len(group), value=hits / len(group) if group else None
    )


def _latency(values: Sequence[float]) -> LatencyStats:
    if not values:
        return LatencyStats(n=0, p50=0.0, p95=0.0)
    return LatencyStats(n=len(values), p50=percentile(values, 50), p95=percentile(values, 95))


def compute_verdicts(ha1: RatioValue, ha2: RatioValue, frozen_set: bool) -> tuple[Verdict, ...]:
    """HA1 and HA2 from their frozen criteria; HA3 and HA4 need generation."""
    scope = "" if frozen_set else " (computed on the development set, not the frozen set)"
    ha1_criterion = f"Hit@5 over semantic + endpoint_discovery >= {HA1_MIN_HIT5:.2f}"
    ha2_criterion = f"Hit@5 over exact_identifier is at least {HA2_MIN_GAP:.2f} lower than HA1"
    if ha1.value is None:
        ha1_verdict = Verdict(
            hypothesis="HA1",
            criterion=ha1_criterion,
            verdict="not testable",
            evidence=f"no answerable questions in the group{scope}",
        )
    else:
        ok = ha1.value >= HA1_MIN_HIT5 - 1e-9
        ha1_verdict = Verdict(
            hypothesis="HA1",
            criterion=ha1_criterion,
            verdict="supported" if ok else "not supported",
            evidence=f"Hit@5 = {ha1.numerator}/{ha1.denominator} = {ha1.value:.3f}{scope}",
        )
    if ha1.value is None or ha2.value is None:
        ha2_verdict = Verdict(
            hypothesis="HA2",
            criterion=ha2_criterion,
            verdict="not testable",
            evidence=f"a group has no answerable questions{scope}",
        )
    else:
        gap = ha1.value - ha2.value
        ok = gap >= HA2_MIN_GAP - 1e-9
        ha2_verdict = Verdict(
            hypothesis="HA2",
            criterion=ha2_criterion,
            verdict="supported" if ok else "not supported",
            evidence=(
                f"exact_identifier Hit@5 = {ha2.numerator}/{ha2.denominator} = {ha2.value:.3f}; "
                f"HA1 value = {ha1.value:.3f}; gap = {gap:.3f}{scope}"
            ),
        )
    if not frozen_set:
        # Hypotheses are defined on the frozen measured set only; a development-set value is
        # shown for orientation but is never a verdict.
        not_applicable = "not applicable (development set)"
        ha1_verdict = ha1_verdict.model_copy(update={"verdict": not_applicable})
        ha2_verdict = ha2_verdict.model_copy(update={"verdict": not_applicable})
    pending = "pending (needs generation, stage 2c/2d)"
    return (
        ha1_verdict,
        ha2_verdict,
        Verdict(
            hypothesis="HA3", criterion="see methodology section 8", verdict=pending, evidence=""
        ),
        Verdict(
            hypothesis="HA4", criterion="see methodology section 8", verdict=pending, evidence=""
        ),
    )


def summarize(
    run_id: str,
    question_set: str,
    records: Sequence[QuestionRetrieval],
    nondeterministic: Sequence[str],
) -> RetrievalSummary:
    """Aggregate per-question records into the run summary."""
    answerable = [r for r in records if not r.excluded]
    by_category: dict[str, list[QuestionRetrieval]] = defaultdict(list)
    for r in answerable:
        by_category[r.category].append(r)
    by_id = {r.question_id: r for r in records}
    pairs = tuple(
        ParaphrasePair(
            original=r.paraphrase_of,
            paraphrase=r.question_id,
            original_first_relevant_rank=(
                by_id[r.paraphrase_of].first_relevant_rank if r.paraphrase_of in by_id else None
            ),
            paraphrase_first_relevant_rank=r.first_relevant_rank,
        )
        for r in records
        if r.paraphrase_of is not None
    )
    ha1 = hit5_ratio(records, HA1_CATEGORIES)
    ha2 = hit5_ratio(records, HA2_CATEGORIES)
    embed = [r.embed_ms for r in records]
    search = [r.search_ms for r in records]
    total = [r.embed_ms + r.search_ms for r in records]
    return RetrievalSummary(
        run_id=run_id,
        question_set=question_set,
        n_questions=len(records),
        n_excluded=len(records) - len(answerable),
        overall=group_metrics(answerable),
        by_category={c: group_metrics(rs) for c, rs in sorted(by_category.items())},
        ha1_group=ha1,
        ha2_group=ha2,
        paraphrase_pairs=pairs,
        latency_embed_ms=_latency(embed),
        latency_search_ms=_latency(search),
        latency_total_ms=_latency(total),
        verdicts=compute_verdicts(ha1, ha2, question_set == "measured"),
        deterministic=not nondeterministic,
        nondeterministic_questions=tuple(nondeterministic),
    )
