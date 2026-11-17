"""Unit tests for agentic records: aggregation, scoring on the collected context, omission."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from ai_lab.llm import LLMInfraError, Usage
from rag_experiment.agent.records import AgentCall, AgentResult, SearchRecord
from rag_experiment.config import ExperimentConfig
from rag_experiment.corpus import Corpus
from rag_experiment.evaluation.answer_metrics import corpus_vocabulary
from rag_experiment.evaluation.answer_run import (
    AGENT_RECORD_KEYS,
    AnswerRecord,
    PlannedAttempt,
    RunInputs,
    RunPaths,
    build_agent_record,
    failed_requests,
    sum_usage,
)
from rag_experiment.evaluation.dataset import Question, load_questions
from rag_experiment.evaluation.relevance import relevant_chunk_ids
from rag_experiment.generation.provider import GeneratedAnswer
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.base import RetrievedChunk

pytestmark = pytest.mark.unit

RecordFactory = Callable[..., AnswerRecord]


def _usage(prompt: int, reasoning: int | None = None, cached: int | None = None) -> Usage:
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=prompt // 10,
        total_tokens=prompt + prompt // 10,
        reasoning_tokens=reasoning,
        cached_tokens=cached,
    )


def _call(step: str, attempts: int, prompt: int, **usage: int | None) -> AgentCall:
    return AgentCall.model_validate(
        {
            "step": step,
            "latency_ms": float(prompt),
            "attempts": attempts,
            "usage": _usage(prompt, **usage),
            "finish_reason": "stop",
            "model_served": f"model-{step}",
            "provider": f"provider-{step}",
            "request_id": f"req-{step}",
        }
    )


def _generated(call: AgentCall, answer: str = "An answer.") -> GeneratedAnswer:
    return GeneratedAnswer(
        answer=answer,
        cited_chunk_ids=(),
        insufficient_context=False,
        raw_content="{}",
        parse_error=None,
        finish_reason=call.finish_reason,
        usage=call.usage,
        latency_ms=call.latency_ms,
        attempts=call.attempts,
        client_wait_ms=5.0,
        model_served=call.model_served,
        provider=call.provider,
        request_id=call.request_id,
        simulated=True,
    )


@pytest.fixture
def inputs(
    corpus: Corpus, chunks: list[Chunk], header_names: frozenset[str], tmp_path: Path
) -> RunInputs:
    return RunInputs(
        paths=RunPaths(tmp_path, "run"),
        run_id="run",
        chunks=chunks,
        header_names=header_names,
        corpus_vocab=corpus_vocabulary(chunks, corpus.specs),
        retrievals={},
        top_k=5,
        simulated=True,
    )


@pytest.fixture
def multi(experiment_config: ExperimentConfig) -> Question:
    """A multi_endpoint question with two labelled sources."""
    question = next(
        q
        for q in load_questions(experiment_config.questions_measured)
        if q.category == "multi_endpoint"
    )
    assert len(question.sources) == 2
    return question


def _context(ids: list[str], chunks: list[Chunk]) -> tuple[RetrievedChunk, ...]:
    by_id = {c.chunk_id: c for c in chunks}
    return tuple(
        RetrievedChunk(chunk=by_id[i], score=0.1, rank=r, retriever="agentic")
        for r, i in enumerate(ids, start=1)
    )


def _result(
    context: tuple[RetrievedChunk, ...],
    calls: tuple[AgentCall, ...],
    *,
    generated: GeneratedAnswer | None,
    error: LLMInfraError | None = None,
    searches: tuple[SearchRecord, ...] = (),
) -> AgentResult:
    return AgentResult(
        context=context,
        generated=generated,
        error=error,
        calls=calls,
        searches=searches,
        steps=(),
        needs_retrieval=True,
        plan_parse_error=None,
        judge_parse_errors=1,
        judge_decisions=(False, True),
    )


def test_usage_attempts_and_timing_are_aggregated_over_every_call(
    inputs: RunInputs, multi: Question, chunks: list[Chunk]
) -> None:
    plan = _call("plan", 2, 100, reasoning=5, cached=None)
    judge = _call("judge", 1, 200, reasoning=None, cached=None)
    answer = _call("answer", 3, 300, reasoning=7, cached=None)
    searches = (
        SearchRecord(query="a", chunk_ids=("x",), embed_ms=1.5, search_ms=10.0),
        SearchRecord(query="b", chunk_ids=("y",), embed_ms=2.5, search_ms=20.0),
    )
    result = _result(
        _context([chunks[0].chunk_id], chunks),
        (plan, judge, answer),
        generated=_generated(answer),
        searches=searches,
    )
    record = build_agent_record(inputs, PlannedAttempt(multi, 1), result)
    assert record.usage.prompt_tokens == 600 and record.usage.completion_tokens == 60
    assert record.usage.total_tokens == 660
    assert record.usage.reasoning_tokens == 12  # None only if every call reported None
    assert record.usage.cached_tokens is None
    assert record.attempts == 6  # HTTP requests over all calls, so requests_sent stays right
    assert (record.model_served, record.provider, record.request_id) == (
        "model-answer",
        "provider-answer",
        "req-answer",
    )
    assert record.embed_ms == 4.0 and record.search_ms == 30.0  # summed over the searches
    assert record.generation_ms == 300.0  # the answer call only
    assert record.agent_ms == 300.0  # plan + judge
    assert record.total_ms == 4.0 + 30.0 + 300.0 + 300.0
    assert record.client_wait_ms == 5.0
    assert (record.model_calls, record.searches) == (3, 2) and record.queries == ("a", "b")
    assert record.rerank_ms == 0.0 and record.judge_decisions == (False, True)
    assert [c.step for c in record.calls or ()] == ["plan", "judge", "answer"]


def test_context_hit_looks_at_the_whole_collected_context_and_sources_are_counted(
    inputs: RunInputs, multi: Question, chunks: list[Chunk]
) -> None:
    first, second = (sorted(relevant_chunk_ids([s], chunks))[0] for s in multi.sources)
    filler = [c.chunk_id for c in chunks if c.chunk_id not in {first, second}][:8]
    answer = _call("answer", 1, 100)
    late = build_agent_record(
        inputs,
        PlannedAttempt(multi, 1),
        _result(_context([*filler, first], chunks), (answer,), generated=_generated(answer)),
    )
    assert late.context_hit is True  # position 9: outside a top-5 window, still counted
    assert (late.sources_covered, late.n_sources) == (1, 2)
    both = build_agent_record(
        inputs,
        PlannedAttempt(multi, 1),
        _result(_context([first, second], chunks), (answer,), generated=_generated(answer)),
    )
    assert (both.sources_covered, both.n_sources) == (2, 2)
    none = build_agent_record(
        inputs,
        PlannedAttempt(multi, 1),
        _result(_context(filler[:2], chunks), (answer,), generated=_generated(answer)),
    )
    assert none.context_hit is False and none.sources_covered == 0


def test_an_infrastructure_error_keeps_the_partial_trace(
    inputs: RunInputs, multi: Question, chunks: list[Chunk]
) -> None:
    plan = _call("plan", 1, 100)
    error = LLMInfraError("down", kind="server", attempts=3)
    record = build_agent_record(
        inputs,
        PlannedAttempt(multi, 2),
        _result(_context([], chunks), (plan,), generated=None, error=error),
    )
    assert record.outcome == "infra_error" and record.error_kind == "server"
    assert record.attempts == 4 and record.usage.prompt_tokens == 100
    assert record.model_calls == 1 and record.model_served is None
    assert record.correct is None and record.generation_ms == 0.0
    assert failed_requests(record) == 3  # the three requests of the failing call
    empty = build_agent_record(
        inputs,
        PlannedAttempt(multi, 3),
        _result(_context([], chunks), (), generated=None, error=error),
    )
    assert empty.calls == () and empty.usage == Usage(
        prompt_tokens=0, completion_tokens=0, total_tokens=0
    )


def test_sum_usage_of_no_calls_is_zero_with_unreported_fields() -> None:
    zero = sum_usage(())
    assert zero.total_tokens == 0 and zero.reasoning_tokens is None and zero.cached_tokens is None


def test_failed_requests_formulas_keep_architectures_a_to_c_unchanged(
    make_record: RecordFactory,
) -> None:
    assert failed_requests(make_record(attempts=1)) == 0
    assert failed_requests(make_record(attempts=3)) == 2
    assert failed_requests(make_record(attempts=3, outcome="infra_error")) == 3
    agentic = make_record(
        attempts=5, calls=(_call("plan", 2, 10), _call("answer", 1, 10)), model_calls=2
    )
    assert failed_requests(agentic) == 3


def test_agent_keys_are_omitted_unless_the_record_is_agentic(make_record: RecordFactory) -> None:
    plain = make_record().model_dump(mode="json")
    assert not set(AGENT_RECORD_KEYS) & set(plain)
    assert "rerank_ms" not in plain
    agentic = make_record(
        calls=(_call("plan", 1, 10),), model_calls=1, searches=1, queries=("q",), n_sources=2
    )
    dumped = agentic.model_dump(mode="json")
    assert set(AGENT_RECORD_KEYS) <= set(dumped)
    assert dumped["calls"][0]["step"] == "plan" and dumped["queries"] == ["q"]
    assert AnswerRecord.model_validate_json(json.dumps(dumped)) == agentic
    assert agentic.agentic and not make_record().agentic
