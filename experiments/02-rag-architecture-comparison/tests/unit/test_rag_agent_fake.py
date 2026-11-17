"""Unit tests for the fake agent chat model (an oracle planner, judge and answerer)."""

import json

import pytest

from ai_lab.llm import LLMInfraError
from rag_experiment.agent.fake import FakeAgentChatModel, split_question
from rag_experiment.agent.prompts import build_judge_messages, build_planner_messages
from rag_experiment.config import ExperimentConfig
from rag_experiment.evaluation.dataset import Question, load_questions
from rag_experiment.evaluation.relevance import relevant_chunk_ids
from rag_experiment.generation.prompts import build_messages
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.base import RetrievedChunk

pytestmark = pytest.mark.unit


def _context(ids: list[str], chunks: list[Chunk]) -> list[RetrievedChunk]:
    by_id = {c.chunk_id: c for c in chunks}
    return [
        RetrievedChunk(chunk=by_id[i], score=1.0, rank=r, retriever="agentic")
        for r, i in enumerate(ids, start=1)
    ]


@pytest.fixture
def questions(experiment_config: ExperimentConfig) -> list[Question]:
    return list(load_questions(experiment_config.questions_measured))


def test_split_question() -> None:
    assert split_question("a and then b") == ["a", "b"]
    assert split_question("a and b and c and d") == ["a", "b", "c"]
    assert split_question("no separator") == ["no separator"]


@pytest.mark.anyio
async def test_the_planner_splits_the_question(
    questions: list[Question], chunks: list[Chunk]
) -> None:
    fake = FakeAgentChatModel(questions, chunks)
    question = next(q for q in questions if " and then " in q.question)
    reply = await fake.complete(build_planner_messages(question.question, 3))
    payload = json.loads(reply.content or "")
    assert payload["needs_retrieval"] is True
    assert payload["queries"] == question.question.split(" and then ")
    assert reply.simulated and reply.usage.prompt_tokens > 0


@pytest.mark.anyio
async def test_the_judge_asks_once_for_more_unless_every_source_is_covered(
    questions: list[Question], chunks: list[Chunk]
) -> None:
    fake = FakeAgentChatModel(questions, chunks)
    question = next(q for q in questions if q.category == "multi_endpoint")
    relevant = sorted(relevant_chunk_ids(question.sources, chunks))
    other = next(c.chunk_id for c in chunks if c.chunk_id not in relevant)

    async def judge(queries: list[str], ids: list[str]) -> dict[str, object]:
        reply = await fake.complete(
            build_judge_messages(question.question, queries, _context(ids, chunks))
        )
        parsed: dict[str, object] = json.loads(reply.content or "")
        return parsed

    first = await judge(["q"], [other])
    assert first["enough"] is False and first["next_query"] == f"{question.question} endpoint"
    assert (await judge(["q", f"{question.question} endpoint"], [other]))["enough"] is True
    assert (await judge(["q"], relevant))["enough"] is True  # every labelled source covered
    unanswerable = next(q for q in questions if q.constraints.must_abstain)
    reply = await fake.complete(build_judge_messages(unanswerable.question, ["q"], []))
    assert json.loads(reply.content or "")["enough"] is True


@pytest.mark.anyio
async def test_the_answer_step_is_the_oracle_and_every_call_counts_against_the_budget(
    questions: list[Question], chunks: list[Chunk]
) -> None:
    calls = 0

    async def hook() -> None:
        nonlocal calls
        calls += 1

    fake = FakeAgentChatModel(questions, chunks, before_request=hook)
    question = next(q for q in questions if not q.constraints.must_abstain)
    ids = sorted(relevant_chunk_ids(question.sources, chunks))
    reply = await fake.complete(build_messages(question.question, _context(ids, chunks)))
    payload = json.loads(reply.content or "")
    assert payload["insufficient_context"] is False and payload["cited_chunk_ids"]
    await fake.complete(build_planner_messages(question.question, 3))
    assert calls == 2 and fake.calls == 2


@pytest.mark.anyio
async def test_the_fault_knobs_apply_to_every_step(
    questions: list[Question], chunks: list[Chunk]
) -> None:
    fake = FakeAgentChatModel(questions, chunks, infra_error_for={"Q1-r1"})
    fake.set_attempt("Q1-r1")
    with pytest.raises(LLMInfraError):
        await fake.complete(build_planner_messages("anything", 3))
