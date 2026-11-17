"""Unit tests for the agent graph: paths, bounds, dedup, errors and the no-network guarantee."""

import json
import socket
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pytest

from ai_lab.benchmarking import BudgetExhaustedError
from ai_lab.llm import LLMInfraError, LLMResponse, Usage
from rag_experiment.agent.graph import AGENT_RETRIEVER_NAME, AgentGraph
from rag_experiment.agent.prompts import JUDGE_SYSTEM_PROMPT, PLANNER_SYSTEM_PROMPT
from rag_experiment.config import AgentConfig
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.base import RetrievalResult, RetrievedChunk

pytestmark = pytest.mark.unit

ChunkFactory = Callable[..., Chunk]
CONFIG = AgentConfig(
    prompt_version="d-1.0",
    max_searches=3,
    results_per_search=5,
    max_context_chunks=10,
    max_planned_queries=3,
)
QUESTION = "What does the thing do?"
ANSWER = json.dumps({"answer": "It does.", "cited_chunk_ids": [], "insufficient_context": False})


def _judge(enough: bool, next_query: str | None = None) -> str:
    return json.dumps({"enough": enough, "missing": "", "next_query": next_query})


def _plan(*queries: str, needs: bool = True) -> str:
    return json.dumps({"needs_retrieval": needs, "queries": list(queries)})


class ScriptedChat:
    """A chat model that replies per step from queues; it records every call."""

    def __init__(
        self,
        plan: str,
        judges: Sequence[str] = (),
        answer: str = ANSWER,
        *,
        fail_on_call: int | None = None,
        exhaust_on_call: int | None = None,
    ) -> None:
        self._plan = plan
        self._judges = list(judges)
        self._answer = answer
        self._fail_on = fail_on_call
        self._exhaust_on = exhaust_on_call
        self.steps: list[str] = []
        self.messages: list[list[Mapping[str, Any]]] = []

    async def complete(
        self, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]] = ()
    ) -> LLMResponse:
        number = len(self.steps) + 1
        system = str(messages[0]["content"])
        if system.startswith(PLANNER_SYSTEM_PROMPT.split("{max_queries}")[0]):
            step, content = "plan", self._plan
        elif system == JUDGE_SYSTEM_PROMPT:
            step = "judge"
            content = self._judges.pop(0) if self._judges else _judge(True)
        else:
            step, content = "answer", self._answer
        self.steps.append(step)
        self.messages.append(list(messages))
        if number == self._exhaust_on:
            raise BudgetExhaustedError("cap")
        if number == self._fail_on:
            raise LLMInfraError("down", kind="server", attempts=2)
        return LLMResponse(
            content=content,
            tool_calls=(),
            finish_reason="stop",
            usage=Usage(
                prompt_tokens=10 * number, completion_tokens=number, total_tokens=11 * number
            ),
            latency_ms=float(number),
            attempts=1,
            client_wait_ms=0.0,
            provider="p",
            model="m",
            request_id=f"req-{number}",
            assistant_message={"role": "assistant", "content": content},
        )


class StubRetriever:
    """Returns the chunks scripted for a query (an empty result for any other query)."""

    name = "hybrid"

    def __init__(self, results: Mapping[str, Sequence[Chunk]]) -> None:
        self._results = {q.lower(): list(c) for q, c in results.items()}
        self.queries: list[tuple[str, int]] = []

    def retrieve(self, query: str, k: int) -> RetrievalResult:
        self.queries.append((query, k))
        found = self._results.get(query.lower(), [])[:k]
        return RetrievalResult(
            chunks=tuple(
                RetrievedChunk(chunk=c, score=1.0 / rank, rank=rank, retriever="hybrid")
                for rank, c in enumerate(found, start=1)
            ),
            embed_ms=1.0,
            search_ms=2.0,
        )


def _chunks(make_chunk: ChunkFactory, prefix: str, n: int) -> list[Chunk]:
    return [make_chunk(f"{prefix}{i}", f"content {prefix}{i}") for i in range(n)]


def _graph(chat: ScriptedChat, retriever: StubRetriever) -> AgentGraph:
    return AgentGraph(chat, retriever, CONFIG, simulated=True)


@pytest.mark.anyio
async def test_one_query_and_an_enough_judge_use_three_calls(make_chunk: ChunkFactory) -> None:
    chat = ScriptedChat(_plan("alpha"), [_judge(True)])
    retriever = StubRetriever({"alpha": _chunks(make_chunk, "a", 5)})
    result = await _graph(chat, retriever).run(QUESTION)
    assert chat.steps == ["plan", "judge", "answer"]
    assert result.queries == ("alpha",) and retriever.queries == [("alpha", 5)]
    assert [c.step for c in result.calls] == ["plan", "judge", "answer"]
    assert result.judge_decisions == (True,) and result.error is None
    assert result.generated is not None and result.generated.answer == "It does."
    assert [s["step"] for s in result.steps] == ["plan", "judge", "answer"]
    assert result.needs_retrieval is True and result.plan_parse_error is None


@pytest.mark.anyio
async def test_a_judge_that_is_never_satisfied_stops_after_three_searches(
    make_chunk: ChunkFactory,
) -> None:
    chat = ScriptedChat(
        _plan("alpha"), [_judge(False, "beta"), _judge(False, "gamma"), _judge(False, "delta")]
    )
    retriever = StubRetriever({q: _chunks(make_chunk, q[0], 5) for q in ("alpha", "beta", "gamma")})
    result = await _graph(chat, retriever).run(QUESTION)
    assert chat.steps == ["plan", "judge", "judge", "judge", "answer"]  # 5 calls
    assert result.queries == ("alpha", "beta", "gamma") and "delta" not in result.queries
    assert result.judge_decisions == (False, False, False)
    assert len(result.searches) == 3


@pytest.mark.anyio
async def test_three_planned_queries_use_all_searches_before_the_first_judge(
    make_chunk: ChunkFactory,
) -> None:
    chat = ScriptedChat(_plan("one", "two", "three"), [_judge(False, "four")])
    retriever = StubRetriever({q: _chunks(make_chunk, q[0], 2) for q in ("one", "two", "three")})
    result = await _graph(chat, retriever).run(QUESTION)
    assert chat.steps == ["plan", "judge", "answer"]  # 3 calls: no search is left to refine with
    assert result.queries == ("one", "two", "three")


@pytest.mark.anyio
async def test_a_repeated_next_query_ends_the_loop(make_chunk: ChunkFactory) -> None:
    chat = ScriptedChat(_plan("Alpha"), [_judge(False, "  alpha ")])
    retriever = StubRetriever({"alpha": _chunks(make_chunk, "a", 5)})
    result = await _graph(chat, retriever).run(QUESTION)
    assert chat.steps == ["plan", "judge", "answer"] and result.queries == ("Alpha",)
    for blank in (None, "", "   "):
        again = ScriptedChat(_plan("alpha"), [_judge(False, blank)])
        trace = await _graph(again, StubRetriever({})).run(QUESTION)
        assert again.steps == ["plan", "judge", "answer"] and len(trace.searches) == 1


@pytest.mark.anyio
async def test_a_new_query_is_searched_and_judged_again(make_chunk: ChunkFactory) -> None:
    chat = ScriptedChat(_plan("alpha"), [_judge(False, "beta"), _judge(True)])
    retriever = StubRetriever(
        {"alpha": _chunks(make_chunk, "a", 5), "beta": _chunks(make_chunk, "b", 5)}
    )
    result = await _graph(chat, retriever).run(QUESTION)
    assert chat.steps == ["plan", "judge", "judge", "answer"]  # 4 calls
    assert result.queries == ("alpha", "beta") and result.judge_decisions == (False, True)
    judge_prompt = str(chat.messages[2][-1]["content"])  # the second judge sees both searches
    assert "1. alpha" in judge_prompt and "2. beta" in judge_prompt


@pytest.mark.anyio
@pytest.mark.parametrize(
    "reply",
    [
        "not json at all",
        "[1, 2]",
        "{}",
        '{"needs_retrieval": true, "queries": []}',
        '{"queries": 3}',
    ],
)
async def test_an_unusable_plan_falls_back_to_the_question(
    reply: str, make_chunk: ChunkFactory
) -> None:
    chat = ScriptedChat(reply, [_judge(True)])
    retriever = StubRetriever({QUESTION: _chunks(make_chunk, "q", 3)})
    result = await _graph(chat, retriever).run(QUESTION)
    assert result.queries == (QUESTION,) and result.plan_parse_error is not None
    assert chat.steps == ["plan", "judge", "answer"]


@pytest.mark.anyio
async def test_the_plan_is_deduplicated_capped_and_needs_retrieval_is_diagnostic(
    make_chunk: ChunkFactory,
) -> None:
    chat = ScriptedChat(
        '```json\n{"needs_retrieval": false, "queries": ["A", " a ", "", 5, "B", "C", "D"]}\n```'
    )
    result = await _graph(chat, StubRetriever({})).run(QUESTION)
    assert result.queries == ("A", "B", "C")  # case-insensitive duplicates and extras dropped
    assert result.needs_retrieval is False  # reported, but the design still searches
    assert result.plan_parse_error is None


@pytest.mark.anyio
@pytest.mark.parametrize("reply", ["garbage", '{"enough": "yes"}', "{}"])
async def test_an_unusable_judge_reply_counts_as_enough(
    reply: str, make_chunk: ChunkFactory
) -> None:
    chat = ScriptedChat(_plan("alpha"), [reply])
    result = await _graph(chat, StubRetriever({"alpha": _chunks(make_chunk, "a", 2)})).run(QUESTION)
    assert chat.steps == ["plan", "judge", "answer"]
    assert result.judge_decisions == (True,) and result.judge_parse_errors == 1


@pytest.mark.anyio
async def test_context_is_deduplicated_in_first_retrieved_order_and_capped(
    make_chunk: ChunkFactory,
) -> None:
    shared = _chunks(make_chunk, "s", 2)
    first = [shared[0], *_chunks(make_chunk, "a", 4)]
    second = [*_chunks(make_chunk, "b", 3), shared[0], shared[1]]
    third = _chunks(make_chunk, "c", 5)
    chat = ScriptedChat(_plan("one"), [_judge(False, "two"), _judge(False, "three"), _judge(True)])
    retriever = StubRetriever({"one": first, "two": second, "three": third})
    result = await _graph(chat, retriever).run(QUESTION)
    ids = [item.chunk.chunk_id for item in result.context]
    assert len(ids) == 10 == len(set(ids))  # 5 + 5 + 5 retrieved, 13 distinct, capped at 10
    assert ids[:5] == [c.chunk_id for c in first]  # first-retrieved order
    assert ids[5:8] == ["b0", "b1", "b2"] and ids[8:] == ["s1", "c0"]
    assert [item.rank for item in result.context] == list(range(1, 11))
    assert {item.retriever for item in result.context} == {AGENT_RETRIEVER_NAME}
    answer_prompt = str(chat.messages[-1][-1]["content"])
    assert answer_prompt.count("<excerpt id=") == 10 and 'id="c1"' not in answer_prompt


@pytest.mark.anyio
async def test_an_infrastructure_error_ends_the_attempt_with_the_partial_trace(
    make_chunk: ChunkFactory,
) -> None:
    chat = ScriptedChat(_plan("alpha"), [_judge(False, "beta")], fail_on_call=3)
    retriever = StubRetriever({"alpha": _chunks(make_chunk, "a", 5)})
    result = await _graph(chat, retriever).run(QUESTION)
    assert chat.steps == ["plan", "judge", "judge"]  # nothing after the failure
    assert result.error is not None and result.error.kind == "server"
    assert result.generated is None and result.failed_attempts == 2
    assert [c.step for c in result.calls] == ["plan", "judge"]
    assert result.steps[-1]["step"] == "judge" and result.steps[-1]["error_kind"] == "server"
    assert result.queries == ("alpha", "beta")


@pytest.mark.anyio
@pytest.mark.parametrize("call", [1, 2, 3])
async def test_budget_exhaustion_propagates_from_any_step(
    call: int, make_chunk: ChunkFactory
) -> None:
    chat = ScriptedChat(_plan("alpha"), [_judge(True)], exhaust_on_call=call)
    graph = _graph(chat, StubRetriever({"alpha": _chunks(make_chunk, "a", 2)}))
    with pytest.raises(BudgetExhaustedError):
        await graph.run(QUESTION)


@pytest.mark.anyio
async def test_the_graph_makes_no_network_call_and_langsmith_tracing_is_off(
    monkeypatch: pytest.MonkeyPatch, make_chunk: ChunkFactory
) -> None:
    from langsmith.utils import tracing_is_enabled

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the graph opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert tracing_is_enabled() is False
    chat = ScriptedChat(_plan("alpha"), [_judge(False, "beta"), _judge(True)])
    retriever = StubRetriever(
        {"alpha": _chunks(make_chunk, "a", 5), "beta": _chunks(make_chunk, "b", 5)}
    )
    result = await _graph(chat, retriever).run(QUESTION)
    assert result.error is None and len(result.calls) == 4
