"""Run generation over a question set with a checkpoint after every attempt.

Layout (relative to the results root)::

    raw/<run_id>/run_metadata.json, answers.jsonl, transcripts/<question>-r<rep>.json
    processed/<run_id>/answer_summary.json, answers_by_attempt.csv
    reports/<run_id>/answer_report.md
    charts/<run_id>/*.png, *.svg

Simulated (fake model) runs use ``results/dry-run/`` as their results root. Retrieval happens
once per question (it is deterministic) and is reused across repetitions.
"""

import json
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ai_lab.benchmarking import BudgetExhaustedError, PricingSnapshot, RequestBudget
from ai_lab.llm import FreeModelDailyRequests, InfraErrorKind, LLMInfraError, Usage
from rag_experiment.evaluation.answer_metrics import (
    Outcome,
    Vocabulary,
    citations_valid,
    cites_relevant,
    context_hit,
    context_vocabulary,
    determine_outcome,
    mentions_endpoint,
    score_correctness,
    score_groundedness,
)
from rag_experiment.evaluation.dataset import Question
from rag_experiment.evaluation.relevance import relevant_chunk_ids
from rag_experiment.evaluation.retrieval_run import RetrievalRunMetadata
from rag_experiment.generation.prompts import build_messages
from rag_experiment.generation.provider import GeneratedAnswer, Generator
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.base import RetrievalResult, RetrievedChunk

# Errors that repeat on every request; continuing would only waste the daily budget.
HALT_KINDS: frozenset[InfraErrorKind] = frozenset(
    {"daily_limit", "auth", "not_found", "bad_request", "no_usage"}
)
MAX_CONSECUTIVE_INFRA = 5


# ------------------------------------------------------------------------------ records


class AnswerRecord(BaseModel):
    """One generation attempt: identity, context, answer, scoring, timing and provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    attempt_id: str
    question_id: str
    repetition: int
    category: str
    paraphrase_of: str | None
    must_abstain: bool
    context_chunk_ids: tuple[str, ...]
    context_hit: bool
    relevant_chunk_ids: tuple[str, ...]
    outcome: Outcome
    answer: str
    cited_chunk_ids: tuple[str, ...]
    insufficient_context: bool
    parse_error: str | None
    finish_reason: str | None
    correct: bool | None
    missing_key_facts: tuple[str, ...]
    false_refusal: bool | None
    correct_refusal: bool | None
    made_up_answer: bool | None
    unsupported_identifiers: tuple[str, ...]
    invented_identifiers: tuple[str, ...]
    citations_valid: bool | None
    cites_relevant: bool | None
    mentions_endpoint: bool
    embed_ms: float
    search_ms: float
    generation_ms: float
    total_ms: float
    client_wait_ms: float
    attempts: int
    usage: Usage
    model_served: str | None
    provider: str | None
    request_id: str | None
    simulated: bool
    error_kind: str | None
    error_message: str | None


class AnswerRunMetadata(RetrievalRunMetadata):
    """Everything recorded about an answer run (retrieval metadata plus generation details)."""

    provider: str
    model_id: str
    models_served: list[str]
    providers_served: list[str]
    prompt_version: str
    prompt_hash: str
    generation: dict[str, object]
    run: dict[str, object]
    pricing: PricingSnapshot
    question_ids: list[str]
    is_canary: bool
    requests_sent: int
    failed_requests: int
    infra_errors: int
    attempts_planned: int
    attempts_completed: int
    free_model_daily_requests_before: FreeModelDailyRequests | None
    free_model_daily_requests_after: FreeModelDailyRequests | None
    halted: bool
    halt_reason: str | None


# ------------------------------------------------------------------------------ paths


@dataclass(frozen=True)
class RunPaths:
    """Where the files of one run live."""

    root: Path
    run_id: str

    @property
    def raw(self) -> Path:
        """Raw run files."""
        return self.root / "raw" / self.run_id

    @property
    def processed(self) -> Path:
        """Processed summaries."""
        return self.root / "processed" / self.run_id

    @property
    def reports(self) -> Path:
        """Markdown reports."""
        return self.root / "reports" / self.run_id

    @property
    def charts(self) -> Path:
        """Charts."""
        return self.root / "charts" / self.run_id

    @property
    def metadata(self) -> Path:
        """``run_metadata.json``."""
        return self.raw / "run_metadata.json"

    @property
    def answers(self) -> Path:
        """``answers.jsonl``."""
        return self.raw / "answers.jsonl"

    @property
    def transcripts(self) -> Path:
        """One JSON file per attempt."""
        return self.raw / "transcripts"


def find_run(results_dir: Path, run_id: str) -> RunPaths:
    """Locate a run under ``results/`` or ``results/dry-run/``."""
    for root in (results_dir, results_dir / "dry-run"):
        if (root / "raw" / run_id / "run_metadata.json").is_file():
            return RunPaths(root, run_id)
    raise ValueError(f"no run {run_id!r} under {results_dir} or {results_dir / 'dry-run'}")


def make_answer_run_id(
    set_name: str,
    retriever: str,
    *,
    fake: bool,
    canary: bool = False,
    now: datetime | None = None,
) -> str:
    """``{UTC}-answers-{set}-{retriever}`` plus ``-canary`` and ``-fake`` suffixes."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return (
        f"{stamp}-answers-{set_name}-{retriever}"
        + ("-canary" if canary else "")
        + ("-fake" if fake else "")
    )


def write_json(path: Path, payload: BaseModel | Mapping[str, object]) -> None:
    """Write a model or mapping as indented JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_records(path: Path) -> list[AnswerRecord]:
    """Every record of ``answers.jsonl`` in file order (empty if the file does not exist)."""
    if not path.is_file():
        return []
    return [
        AnswerRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def latest_by_attempt(records: Sequence[AnswerRecord]) -> dict[str, AnswerRecord]:
    """The last record of each attempt (a retry after an infra error replaces the earlier one)."""
    latest: dict[str, AnswerRecord] = {}
    for record in records:
        latest[record.attempt_id] = record
    return latest


def completed_attempts(records: Sequence[AnswerRecord]) -> set[str]:
    """Attempts whose latest record is not an ``infra_error``; a resume skips these."""
    return {a for a, r in latest_by_attempt(records).items() if r.outcome != "infra_error"}


# ------------------------------------------------------------------------------ plan


@dataclass(frozen=True)
class PlannedAttempt:
    """One question in one repetition."""

    question: Question
    repetition: int

    @property
    def attempt_id(self) -> str:
        """``{question id}-r{repetition}``."""
        return f"{self.question.id}-r{self.repetition}"


def plan_attempts(
    questions: Sequence[Question], repetitions: int, order_seed: int
) -> list[PlannedAttempt]:
    """Repetition-major order; each repetition shuffles the questions with ``seed + rep``."""
    plan: list[PlannedAttempt] = []
    for repetition in range(1, repetitions + 1):
        shuffled = list(questions)
        random.Random(order_seed + repetition).shuffle(shuffled)
        plan.extend(PlannedAttempt(q, repetition) for q in shuffled)
    return plan


# ------------------------------------------------------------------------------ runner


@dataclass
class RunInputs:
    """Everything a run needs besides the generator."""

    paths: RunPaths
    run_id: str
    chunks: Sequence[Chunk]
    header_names: frozenset[str]
    corpus_vocab: Vocabulary
    retrievals: Mapping[str, RetrievalResult]
    top_k: int
    simulated: bool


@dataclass
class RunOutcome:
    """How a run loop ended."""

    attempts_run: int = 0
    halted: bool = False
    halt_reason: str | None = None
    errors: list[str] = field(default_factory=list)


def _usage_zero() -> Usage:
    return Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)


def build_record(
    inputs: RunInputs,
    planned: PlannedAttempt,
    context: Sequence[RetrievedChunk],
    generated: GeneratedAnswer | None,
    error: LLMInfraError | None,
) -> AnswerRecord:
    """Score one attempt and assemble its record."""
    question = planned.question
    retrieval = inputs.retrievals[question.id]
    context_chunks = [item.chunk for item in context]
    context_ids = tuple(c.chunk_id for c in context_chunks)
    relevant = relevant_chunk_ids(question.sources, inputs.chunks)
    hit = context_hit(context_ids, relevant, inputs.top_k)
    abstain = question.constraints.must_abstain

    if generated is None:
        outcome: Outcome = "infra_error"
        answer: str = ""
        cited: tuple[str, ...] = ()
        flag = False
    else:
        outcome = determine_outcome(
            infra_error=False,
            finish_reason=generated.finish_reason,
            parse_error=generated.parse_error,
            insufficient_context=generated.insufficient_context,
        )
        answer = generated.answer
        cited = generated.cited_chunk_ids
        flag = generated.insufficient_context

    correct: bool | None = None
    missing: tuple[str, ...] = ()
    false_refusal: bool | None = None
    correct_refusal: bool | None = None
    made_up: bool | None = None
    if outcome != "infra_error":
        if abstain:
            correct_refusal = outcome == "refused"
            made_up = outcome == "answered"
        else:
            is_correct, missing_list = score_correctness(
                outcome, answer, question.key_facts, inputs.header_names, question.question
            )
            correct, missing = is_correct, tuple(missing_list)
            false_refusal = outcome == "refused"

    unsupported: tuple[str, ...] = ()
    invented: tuple[str, ...] = ()
    if outcome in ("answered", "refused"):
        grounded = score_groundedness(
            answer, question.question, context_vocabulary(context_chunks), inputs.corpus_vocab
        )
        unsupported, invented = grounded.unsupported, grounded.invented

    valid: bool | None = None
    relevant_cited: bool | None = None
    if question.constraints.must_cite and outcome == "answered":
        valid = citations_valid(cited, context_ids)
        relevant_cited = cites_relevant(cited, relevant)

    generation_ms = generated.latency_ms if generated else 0.0
    return AnswerRecord(
        run_id=inputs.run_id,
        attempt_id=planned.attempt_id,
        question_id=question.id,
        repetition=planned.repetition,
        category=question.category,
        paraphrase_of=question.paraphrase_of,
        must_abstain=abstain,
        context_chunk_ids=context_ids,
        context_hit=hit,
        relevant_chunk_ids=tuple(sorted(relevant)),
        outcome=outcome,
        answer=answer,
        cited_chunk_ids=cited,
        insufficient_context=flag,
        parse_error=generated.parse_error if generated else None,
        finish_reason=generated.finish_reason if generated else None,
        correct=correct,
        missing_key_facts=missing,
        false_refusal=false_refusal,
        correct_refusal=correct_refusal,
        made_up_answer=made_up,
        unsupported_identifiers=unsupported,
        invented_identifiers=invented,
        citations_valid=valid,
        cites_relevant=relevant_cited,
        mentions_endpoint=mentions_endpoint(answer),
        embed_ms=retrieval.embed_ms,
        search_ms=retrieval.search_ms,
        generation_ms=generation_ms,
        total_ms=retrieval.embed_ms + retrieval.search_ms + generation_ms,
        client_wait_ms=generated.client_wait_ms if generated else 0.0,
        attempts=generated.attempts if generated else (error.attempts if error else 0),
        usage=generated.usage if generated else _usage_zero(),
        model_served=generated.model_served if generated else None,
        provider=generated.provider if generated else None,
        request_id=generated.request_id if generated else None,
        simulated=inputs.simulated,
        error_kind=error.kind if error else None,
        error_message=str(error) if error else None,
    )


def _write_transcript(
    inputs: RunInputs,
    record: AnswerRecord,
    messages: Sequence[Mapping[str, str]],
    generated: GeneratedAnswer | None,
) -> None:
    """The prompt and the raw and parsed reply. It holds no headers and no credentials."""
    payload: dict[str, object] = {
        "run_id": record.run_id,
        "attempt_id": record.attempt_id,
        "question_id": record.question_id,
        "repetition": record.repetition,
        "simulated": record.simulated,
        "messages": [dict(m) for m in messages],
        "raw_content": generated.raw_content if generated else None,
        "parsed": {
            "answer": record.answer,
            "cited_chunk_ids": list(record.cited_chunk_ids),
            "insufficient_context": record.insufficient_context,
            "parse_error": record.parse_error,
            "finish_reason": record.finish_reason,
        },
        "outcome": record.outcome,
        "error_kind": record.error_kind,
        "error_message": record.error_message,
    }
    write_json(inputs.paths.transcripts / f"{record.attempt_id}.json", payload)


async def run_attempts(
    inputs: RunInputs,
    generator: Generator,
    plan: Sequence[PlannedAttempt],
    skip: set[str],
    budget: RequestBudget | None,
    on_attempt: Callable[[str], None] | None = None,
    progress: Callable[[str], None] | None = None,
) -> RunOutcome:
    """Generate and score every planned attempt that is not in ``skip``.

    Each record is appended and flushed as soon as it is scored. The loop halts cleanly when the
    provider's daily limit or the request budget is exhausted, or when an error that repeats on
    every request (bad credentials, unknown model) occurs.
    """
    outcome = RunOutcome()
    pending = [p for p in plan if p.attempt_id not in skip]
    inputs.paths.answers.parent.mkdir(parents=True, exist_ok=True)
    consecutive_infra = 0
    with inputs.paths.answers.open("a", encoding="utf-8") as handle:
        for index, planned in enumerate(pending, start=1):
            if budget is not None and budget.remaining < 1:
                outcome.halted = True
                outcome.halt_reason = "daily request cap reached; resume later with --resume"
                break
            question = planned.question
            context = inputs.retrievals[question.id].chunks[: inputs.top_k]
            if on_attempt is not None:
                on_attempt(planned.attempt_id)
            generated: GeneratedAnswer | None = None
            error: LLMInfraError | None = None
            try:
                generated = await generator.generate(question.question, context)
            except BudgetExhaustedError:
                outcome.halted = True
                outcome.halt_reason = "daily request cap reached mid-attempt; resume with --resume"
                break
            except LLMInfraError as exc:
                error = exc
            record = build_record(inputs, planned, context, generated, error)
            handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
            handle.flush()
            _write_transcript(
                inputs,
                record,
                generated.messages if generated else build_messages(question.question, context),
                generated,
            )
            outcome.attempts_run += 1
            if progress is not None:
                progress(
                    f"[{index}/{len(pending)}] {record.attempt_id} {record.outcome}"
                    + (f" ({record.error_kind})" if record.error_kind else "")
                )
            if error is None:
                consecutive_infra = 0
                continue
            consecutive_infra += 1
            if error.kind in HALT_KINDS:
                outcome.halted = True
                outcome.halt_reason = f"infrastructure error '{error.kind}': {error}"
                break
            if consecutive_infra >= MAX_CONSECUTIVE_INFRA:
                outcome.halted = True
                outcome.halt_reason = (
                    f"{MAX_CONSECUTIVE_INFRA} consecutive infrastructure errors "
                    f"(last: '{error.kind}')"
                )
                break
    return outcome
