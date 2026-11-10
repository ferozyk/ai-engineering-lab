"""Summarise an answer run: quality, guardrails, grounding, citations, latency, tokens, cost.

Only the latest record of each attempt is used. ``infra_error`` attempts are counted but excluded
from every quality denominator. The summary interprets nothing beyond the frozen HA3 and HA4
criteria (methodology section 8).
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Sequence
from statistics import fmean

from pydantic import BaseModel, ConfigDict

from ai_lab.benchmarking import PricingSnapshot, estimate_cost_usd, percentile
from rag_experiment.evaluation.answer_run import AnswerRecord, latest_by_attempt
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
        failed=sum(r.attempts for r in all_infra) + sum(max(0, r.attempts - 1) for r in all_ok),
        retried=sum(max(0, r.attempts - 1) for r in all_ok),
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
    )
