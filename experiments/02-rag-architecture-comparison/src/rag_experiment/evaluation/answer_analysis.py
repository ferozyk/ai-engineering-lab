"""Summarise an answer run: quality, guardrails, grounding, citations, latency, tokens, cost.

Only the latest record of each attempt is used. ``infra_error`` attempts are counted but excluded
from every quality denominator. The summary interprets nothing beyond the frozen HA3 and HA4
criteria (methodology section 8).
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Sequence
from statistics import fmean
from typing import Any

from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, model_serializer

from ai_lab.benchmarking import PricingSnapshot, estimate_cost_usd, percentile
from rag_experiment.evaluation.answer_run import AnswerRecord, failed_requests, latest_by_attempt
from rag_experiment.evaluation.dataset import Question
from rag_experiment.evaluation.retrieval_metrics import LatencyStats, RatioValue, Verdict

HA3_MIN_HIT = 0.80
HA3_MAX_MISS = 0.20
HA3_MIN_MISS_N = 3
HA4_MIN_REFUSAL = 0.80
TOP_OFFENDERS = 5


class AnswerGroup(BaseModel):
    """Outcome counts and correctness for a group of scored attempts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n: int
    outcomes: dict[str, int]
    answerable: RatioValue  # numerator: correct answers, denominator: answerable attempts
    false_refusals: RatioValue  # over answerable attempts
    correct_refusals: RatioValue  # over unanswerable attempts


class QuestionSummary(BaseModel):
    """Per-question view across repetitions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    category: str
    must_abstain: bool
    context_hit: bool
    attempts: int
    correct: int  # correct answers, or correct refusals for an unanswerable question
    outcomes: tuple[str, ...]
    repetitions_agree: bool
    missing_key_facts: tuple[str, ...]


class GroundednessSummary(BaseModel):
    """Rates over attempts that produced an answer text (answered or refused)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    with_unsupported: RatioValue
    with_invented: RatioValue
    top_unsupported: tuple[tuple[str, int], ...]
    top_invented: tuple[tuple[str, int], ...]


class CitationSummary(BaseModel):
    """Rates over answered attempts of questions that must cite."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    citations_valid: RatioValue
    cites_relevant: RatioValue


class GuardrailSummary(BaseModel):
    """Refusal behaviour: unanswerable questions and false refusals on answerable ones."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correct_refusal: RatioValue
    made_up_answer: RatioValue
    unanswerable_invalid: int
    unanswerable_cut_off: int
    false_refusal: RatioValue
    mentions_endpoint_on_unanswerable: int


class TokenStats(BaseModel):
    """Mean, p50 and p95 of a token count over ``n`` attempts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n: int
    mean: float
    p50: float
    p95: float


class CostEstimate(BaseModel):
    """Estimated cost, never a billed amount."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    per_1000_questions_usd: float
    run_total_usd: float
    source: str
    note: str


class RequestCounts(BaseModel):
    """Requests sent, failed and retried, derived from the records."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sent: int
    failed: int
    retried: int
    infra_error_attempts: int


class CountStats(BaseModel):
    """A per-attempt count: mean, p50, maximum and how often each value occurred."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mean: float
    p50: float
    max: int
    distribution: dict[str, int]  # value -> attempts, ascending by value


class AgentSummary(BaseModel):
    """Behaviour of the agent loop (architecture D), from the scored attempts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_attempts: int
    model_calls: CountStats
    searches: CountStats
    context_chunks_mean: float
    context_chunks_max: int
    needs_retrieval_false: int
    plan_parse_errors: int  # attempts whose plan reply could not be used
    judge_parse_errors: int  # judge replies that could not be parsed, over all attempts
    first_judge_enough: RatioValue  # attempts whose first judge decision was "enough"
    full_coverage_by_category: dict[str, RatioValue]  # answerable attempts
    sources_covered_by_question: dict[str, tuple[int, ...]]  # repetition order
    n_sources_by_question: dict[str, int]
    multi_endpoint_queries: dict[str, tuple[str, ...]]  # repetition 1, verbatim model output


class AnswerSummary(BaseModel):
    """Everything the report and the charts show."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    question_set: str
    simulated: bool
    n_attempts: int
    n_scored: int
    n_infra_errors: int
    overall: AnswerGroup
    by_category: dict[str, AnswerGroup]
    per_question: tuple[QuestionSummary, ...]
    ha3_hit: RatioValue
    ha3_miss: RatioValue
    verdicts: tuple[Verdict, ...]
    guardrails: GuardrailSummary
    groundedness: GroundednessSummary
    citations: CitationSummary
    latency_ms: dict[str, LatencyStats]
    tokens: dict[str, TokenStats]
    tokens_by_category: dict[str, tuple[int, ...]]
    cost: CostEstimate
    requests: RequestCounts
    agent: AgentSummary | None = None  # agentic runs only; omitted from the file otherwise

    @model_serializer(mode="wrap")
    def _omit_agent(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if data.get("agent") is None:
            data.pop("agent", None)
        return data


def _ratio(numerator: int, denominator: int) -> RatioValue:
    return RatioValue(
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator if denominator else None,
    )


def _count(records: Sequence[AnswerRecord], predicate: Callable[[AnswerRecord], bool]) -> int:
    return sum(1 for r in records if predicate(r))


def _group(records: Sequence[AnswerRecord]) -> AnswerGroup:
    answerable = [r for r in records if not r.must_abstain]
    unanswerable = [r for r in records if r.must_abstain]
    return AnswerGroup(
        n=len(records),
        outcomes=dict(sorted(Counter(r.outcome for r in records).items())),
        answerable=_ratio(_count(answerable, lambda r: r.correct is True), len(answerable)),
        false_refusals=_ratio(
            _count(answerable, lambda r: r.false_refusal is True), len(answerable)
        ),
        correct_refusals=_ratio(
            _count(unanswerable, lambda r: r.correct_refusal is True), len(unanswerable)
        ),
    )


def _latency(values: Sequence[float]) -> LatencyStats:
    if not values:
        return LatencyStats(n=0, p50=0.0, p95=0.0)
    return LatencyStats(n=len(values), p50=percentile(values, 50), p95=percentile(values, 95))


def _tokens(values: Sequence[int]) -> TokenStats:
    if not values:
        return TokenStats(n=0, mean=0.0, p50=0.0, p95=0.0)
    floats = [float(v) for v in values]
    return TokenStats(
        n=len(values), mean=fmean(floats), p50=percentile(floats, 50), p95=percentile(floats, 95)
    )


def _top(identifiers: Collection[str] | Counter[str]) -> tuple[tuple[str, int], ...]:
    counter = identifiers if isinstance(identifiers, Counter) else Counter(identifiers)
    ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return tuple(ordered[:TOP_OFFENDERS])


def _count_stats(values: Sequence[int]) -> CountStats:
    if not values:
        return CountStats(mean=0.0, p50=0.0, max=0, distribution={})
    floats = [float(v) for v in values]
    counts = Counter(values)
    return CountStats(
        mean=fmean(floats),
        p50=percentile(floats, 50),
        max=max(values),
        distribution={str(v): counts[v] for v in sorted(counts)},
    )


def _agent_summary(scored: Sequence[AnswerRecord]) -> AgentSummary:
    """The "Agent behaviour" numbers. Coverage comes from the counts stored in each record."""
    answerable = [r for r in scored if not r.must_abstain]
    by_category: dict[str, list[AnswerRecord]] = defaultdict(list)
    for r in answerable:
        by_category[r.category].append(r)
    first = [r.judge_decisions[0] for r in scored if r.judge_decisions]
    by_question: dict[str, list[AnswerRecord]] = defaultdict(list)
    for r in scored:
        by_question[r.question_id].append(r)
    covered: dict[str, tuple[int, ...]] = {}
    totals: dict[str, int] = {}
    queries: dict[str, tuple[str, ...]] = {}
    for qid, rs in by_question.items():
        ordered = sorted(rs, key=lambda r: r.repetition)
        if ordered[0].must_abstain:
            continue
        covered[qid] = tuple(r.sources_covered for r in ordered)
        totals[qid] = ordered[0].n_sources
        if ordered[0].category == "multi_endpoint" and ordered[0].repetition == 1:
            queries[qid] = ordered[0].queries
    return AgentSummary(
        n_attempts=len(scored),
        model_calls=_count_stats([r.model_calls for r in scored]),
        searches=_count_stats([r.searches for r in scored]),
        context_chunks_mean=fmean([float(len(r.context_chunk_ids)) for r in scored])
        if scored
        else 0.0,
        context_chunks_max=max((len(r.context_chunk_ids) for r in scored), default=0),
        needs_retrieval_false=_count(scored, lambda r: r.needs_retrieval is False),
        plan_parse_errors=_count(scored, lambda r: r.plan_parse_error is not None),
        judge_parse_errors=sum(r.judge_parse_errors for r in scored),
        first_judge_enough=_ratio(sum(first), len(first)),
        full_coverage_by_category={
            c: _ratio(_count(rs, lambda r: r.sources_covered == r.n_sources), len(rs))
            for c, rs in sorted(by_category.items())
        },
        sources_covered_by_question=covered,
        n_sources_by_question=totals,
        multi_endpoint_queries=queries,
    )


def _verdicts(
    hit: RatioValue, miss: RatioValue, refusal: RatioValue, applicability: str | None
) -> tuple[Verdict, ...]:
    ha3_criterion = (
        f"correctness >= {HA3_MIN_HIT:.2f} when the top-5 context has a relevant chunk and "
        f"<= {HA3_MAX_MISS:.2f} when it has none; the 'none' half needs at least "
        f"{HA3_MIN_MISS_N} attempts"
    )
    ha4_criterion = f"correct-refusal rate over unanswerable attempts >= {HA4_MIN_REFUSAL:.2f}"
    hit_text = f"context hit {hit.numerator}/{hit.denominator} correct"
    miss_text = f"context miss {miss.numerator}/{miss.denominator} correct"
    ref_text = f"correct refusals {refusal.numerator}/{refusal.denominator}"
    if applicability is not None:
        return (
            Verdict(
                hypothesis="HA3",
                criterion=ha3_criterion,
                verdict=applicability,
                evidence=f"{hit_text}; {miss_text}",
            ),
            Verdict(
                hypothesis="HA4", criterion=ha4_criterion, verdict=applicability, evidence=ref_text
            ),
        )
    if hit.value is None:
        ha3 = Verdict(
            hypothesis="HA3",
            criterion=ha3_criterion,
            verdict="not testable",
            evidence="no answerable attempts with a relevant chunk in the context",
        )
    else:
        hit_ok = hit.value >= HA3_MIN_HIT - 1e-9
        if miss.denominator < HA3_MIN_MISS_N:
            ok = hit_ok
            note = f"; miss half not testable (n<{HA3_MIN_MISS_N})"
        else:
            miss_ok = miss.value is not None and miss.value <= HA3_MAX_MISS + 1e-9
            ok = hit_ok and miss_ok
            note = ""
        miss_rate = "n/a" if miss.value is None else f"{miss.value:.3f}"
        ha3 = Verdict(
            hypothesis="HA3",
            criterion=ha3_criterion,
            verdict="supported" if ok else "not supported",
            evidence=f"{hit_text} = {hit.value:.3f}; {miss_text} = {miss_rate}{note}",
        )
    if refusal.value is None:
        ha4 = Verdict(
            hypothesis="HA4",
            criterion=ha4_criterion,
            verdict="not testable",
            evidence="no scored unanswerable attempts",
        )
    else:
        ha4 = Verdict(
            hypothesis="HA4",
            criterion=ha4_criterion,
            verdict="supported" if refusal.value >= HA4_MIN_REFUSAL - 1e-9 else "not supported",
            evidence=f"{ref_text} = {refusal.value:.3f}",
        )
    return ha3, ha4


def summarise_answers(
    records: Sequence[AnswerRecord],
    questions: Sequence[Question],
    *,
    question_set: str,
    pricing: PricingSnapshot,
) -> AnswerSummary:
    """Aggregate the latest record of each attempt."""
    if not records:
        raise ValueError("no answer records to summarise")
    latest = list(latest_by_attempt(records).values())
    scored = [r for r in latest if r.outcome != "infra_error"]
    simulated = any(r.simulated for r in latest)
    answerable = [r for r in scored if not r.must_abstain]
    unanswerable = [r for r in scored if r.must_abstain]

    by_category_records: dict[str, list[AnswerRecord]] = defaultdict(list)
    for r in scored:
        by_category_records[r.category].append(r)

    order = {q.id: i for i, q in enumerate(questions)}
    per_question: list[QuestionSummary] = []
    by_question: dict[str, list[AnswerRecord]] = defaultdict(list)
    for r in scored:
        by_question[r.question_id].append(r)
    for qid in sorted(by_question, key=lambda x: (order.get(x, len(order)), x)):
        rs = sorted(by_question[qid], key=lambda r: r.repetition)
        first = rs[0]
        if first.must_abstain:
            flags = [r.correct_refusal is True for r in rs]
        else:
            flags = [r.correct is True for r in rs]
        missing = sorted({f for r in rs for f in r.missing_key_facts})
        per_question.append(
            QuestionSummary(
                question_id=qid,
                category=first.category,
                must_abstain=first.must_abstain,
                context_hit=first.context_hit,
                attempts=len(rs),
                correct=sum(flags),
                outcomes=tuple(r.outcome for r in rs),
                repetitions_agree=len(set(flags)) == 1 and len({r.outcome for r in rs}) == 1,
                missing_key_facts=tuple(missing),
            )
        )

    hit_group = [r for r in answerable if r.context_hit]
    miss_group = [r for r in answerable if not r.context_hit]
    ha3_hit = _ratio(_count(hit_group, lambda r: r.correct is True), len(hit_group))
    ha3_miss = _ratio(_count(miss_group, lambda r: r.correct is True), len(miss_group))
    refusal = _ratio(_count(unanswerable, lambda r: r.correct_refusal is True), len(unanswerable))
    applicability: str | None = None
    if simulated:
        applicability = "not applicable (simulated)"
    elif question_set != "measured":
        applicability = "not applicable (development set)"

    texted = [r for r in scored if r.outcome in ("answered", "refused")]
    unsupported_counter: Counter[str] = Counter(
        i for r in texted for i in r.unsupported_identifiers
    )
    invented_counter: Counter[str] = Counter(i for r in texted for i in r.invented_identifiers)
    cited = [r for r in scored if r.citations_valid is not None]

    guardrails = GuardrailSummary(
        correct_refusal=refusal,
        made_up_answer=_ratio(
            _count(unanswerable, lambda r: r.made_up_answer is True), len(unanswerable)
        ),
        unanswerable_invalid=_count(unanswerable, lambda r: r.outcome == "invalid_answer"),
        unanswerable_cut_off=_count(unanswerable, lambda r: r.outcome == "cut_off"),
        false_refusal=_ratio(
            _count(answerable, lambda r: r.false_refusal is True), len(answerable)
        ),
        mentions_endpoint_on_unanswerable=_count(unanswerable, lambda r: r.mentions_endpoint),
    )

    latency = {
        "embed": _latency([r.embed_ms for r in scored]),
        "search": _latency([r.search_ms for r in scored]),
        "generation": _latency([r.generation_ms for r in scored]),
        "total": _latency([r.total_ms for r in scored]),
    }
    if any(r.rerank_ms > 0 for r in scored):  # a rerank stage exists only for reranked runs
        latency = {
            "embed": latency["embed"],
            "search": latency["search"],
            "rerank": _latency([r.rerank_ms for r in scored]),
            "generation": latency["generation"],
            "total": latency["total"],
        }
    agentic = any(r.agentic for r in scored)
    if agentic:  # the agent stage (planner and judge calls) exists for agentic runs only
        latency = {
            "embed": latency["embed"],
            "search": latency["search"],
            "agent": _latency([r.agent_ms for r in scored]),
            "generation": latency["generation"],
            "total": latency["total"],
        }
    tokens = {
        "prompt": _tokens([r.usage.prompt_tokens for r in scored]),
        "completion": _tokens([r.usage.completion_tokens for r in scored]),
        "total": _tokens([r.usage.total_tokens for r in scored]),
    }
    reasoning = [r.usage.reasoning_tokens for r in scored if r.usage.reasoning_tokens is not None]
    if reasoning:
        tokens["reasoning"] = _tokens(reasoning)
    tokens_by_category = {
        c: tuple(r.usage.total_tokens for r in rs) for c, rs in sorted(by_category_records.items())
    }

    costs = [
        estimate_cost_usd(r.usage.prompt_tokens, r.usage.completion_tokens, pricing) for r in scored
    ]
    cost = CostEstimate(
        per_1000_questions_usd=fmean(costs) * 1000 if costs else 0.0,
        run_total_usd=sum(costs),
        source=pricing.source,
        note=f"Estimated, not billed. {pricing.note}",
    )

    infra = [r for r in latest if r.outcome == "infra_error"]
    all_infra = [r for r in records if r.outcome == "infra_error"]
    all_ok = [r for r in records if r.outcome != "infra_error"]
    requests = RequestCounts(
        sent=sum(r.attempts for r in records),
        failed=sum(failed_requests(r) for r in records),
        retried=sum(failed_requests(r) for r in all_ok),
        infra_error_attempts=len(all_infra),
    )

    return AnswerSummary(
        run_id=latest[0].run_id,
        question_set=question_set,
        simulated=simulated,
        n_attempts=len(latest),
        n_scored=len(scored),
        n_infra_errors=len(infra),
        overall=_group(scored),
        by_category={c: _group(rs) for c, rs in sorted(by_category_records.items())},
        per_question=tuple(per_question),
        ha3_hit=ha3_hit,
        ha3_miss=ha3_miss,
        verdicts=_verdicts(ha3_hit, ha3_miss, refusal, applicability),
        guardrails=guardrails,
        groundedness=GroundednessSummary(
            with_unsupported=_ratio(
                _count(texted, lambda r: bool(r.unsupported_identifiers)), len(texted)
            ),
            with_invented=_ratio(
                _count(texted, lambda r: bool(r.invented_identifiers)), len(texted)
            ),
            top_unsupported=_top(unsupported_counter),
            top_invented=_top(invented_counter),
        ),
        citations=CitationSummary(
            citations_valid=_ratio(_count(cited, lambda r: r.citations_valid is True), len(cited)),
            cites_relevant=_ratio(_count(cited, lambda r: r.cites_relevant is True), len(cited)),
        ),
        latency_ms=latency,
        tokens=tokens,
        tokens_by_category=tokens_by_category,
        cost=cost,
        requests=requests,
        agent=_agent_summary(scored) if agentic else None,
    )
