"""The agentic pipeline as a LangGraph state graph: plan, search, judge, answer.

Only ``StateGraph``, ``START`` and ``END`` are used. Every model call goes through the shared
``ChatModel`` protocol, so the rate limiter, the request budget, retries, usage accounting and
pricing behave exactly as in architectures A to C. The search tool is the architecture B hybrid
retriever.

Edges::

    START -> plan -> search -> judge -> answer -> END
                       ^         |
                       +---------+   (judge: not enough, a new query, searches left)

An ``LLMInfraError`` in any call is stored in the state and ends the graph; the partial trace is
returned. ``BudgetExhaustedError`` is not caught: it propagates to the run loop.
"""

from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from ai_lab.llm import ChatModel, LLMInfraError, LLMResponse
from rag_experiment.agent.prompts import build_judge_messages, build_planner_messages
from rag_experiment.agent.records import AgentCall, AgentResult, SearchRecord, Step
from rag_experiment.config import AgentConfig
from rag_experiment.generation.prompts import build_messages
from rag_experiment.generation.provider import (
    GeneratedAnswer,
    Generator,
    ParseFailure,
    extract_json_object,
)
from rag_experiment.retrieval.base import RetrievedChunk, Retriever

AGENT_RETRIEVER_NAME = "agentic"
RECURSION_LIMIT = 20  # safety net only; the step logic below bounds a run at 8 node visits


class AgentState(TypedDict):
    """Everything the nodes read and write. Each node returns a partial update."""

    question: str
    pending: list[str]  # queries waiting to be searched
    queries_run: list[str]
    collected: list[RetrievedChunk]  # deduplicated by chunk id, first-retrieved order
    searches: list[SearchRecord]
    calls: list[AgentCall]
    steps: list[dict[str, object]]  # transcript: messages and raw reply of every call
    decisions: list[bool]  # the judge's "enough", after parse-error handling
    needs_retrieval: bool | None
    plan_parse_error: str | None
    judge_parse_errors: int
    step: int  # nodes visited so far
    generated: GeneratedAnswer | None
    error: LLMInfraError | None


def _normal(query: str) -> str:
    return " ".join(query.split()).lower()


def _call(step: Step, response: LLMResponse) -> AgentCall:
    return AgentCall(
        step=step,
        latency_ms=response.latency_ms,
        attempts=response.attempts,
        usage=response.usage,
        finish_reason=response.finish_reason,
        model_served=response.model,
        provider=response.provider,
        request_id=response.request_id,
    )


def _failed_step(
    step: Step, messages: list[dict[str, str]], error: LLMInfraError
) -> dict[str, Any]:
    return {
        "step": step,
        "messages": messages,
        "raw_content": None,
        "error_kind": error.kind,
        "error_message": str(error),
    }


def initial_state(question: str) -> AgentState:
    """The state before the first node."""
    return AgentState(
        question=question,
        pending=[],
        queries_run=[],
        collected=[],
        searches=[],
        calls=[],
        steps=[],
        decisions=[],
        needs_retrieval=None,
        plan_parse_error=None,
        judge_parse_errors=0,
        step=0,
        generated=None,
        error=None,
    )


class AgentGraph:
    """The compiled graph plus the dependencies its nodes use."""

    def __init__(
        self,
        chat: ChatModel,
        retriever: Retriever,
        config: AgentConfig,
        *,
        simulated: bool = False,
    ) -> None:
        self._chat = chat
        self._retriever = retriever
        self._config = config
        self._generator = Generator(chat, simulated=simulated)
        builder: StateGraph[AgentState] = StateGraph(AgentState)
        builder.add_node("plan", self._plan)
        builder.add_node("search", self._search)
        builder.add_node("judge", self._judge)
        builder.add_node("answer", self._answer)
        builder.add_edge(START, "plan")
        builder.add_conditional_edges("plan", self._after_call("search"), ["search", END])
        builder.add_edge("search", "judge")
        builder.add_conditional_edges("judge", self._after_judge, ["search", "answer", END])
        builder.add_conditional_edges("answer", self._after_call(END), [END])
        self._app = builder.compile()

    # ---------------------------------------------------------------- routing

    @staticmethod
    def _after_call(next_node: str) -> Any:
        def route(state: AgentState) -> str:
            return END if state["error"] is not None else next_node

        return route

    @staticmethod
    def _after_judge(state: AgentState) -> str:
        if state["error"] is not None:
            return END
        return "search" if state["pending"] else "answer"

    # ---------------------------------------------------------------- helpers

    def _context(self, collected: list[RetrievedChunk]) -> tuple[RetrievedChunk, ...]:
        """The first ``max_context_chunks`` collected chunks, ranked by collection order."""
        return tuple(
            item.model_copy(
                update={"rank": rank, "retriever": AGENT_RETRIEVER_NAME, "component_ranks": None}
            )
            for rank, item in enumerate(collected[: self._config.max_context_chunks], start=1)
        )

    # ---------------------------------------------------------------- nodes

    async def _plan(self, state: AgentState) -> dict[str, Any]:
        question = state["question"]
        messages = build_planner_messages(question, self._config.max_planned_queries)
        try:
            response = await self._chat.complete(messages)
        except LLMInfraError as exc:
            return {
                "error": exc,
                "steps": [*state["steps"], _failed_step("plan", messages, exc)],
                "step": state["step"] + 1,
            }
        data = extract_json_object(response.content)
        error: str | None = None
        needs: bool | None = None
        queries: list[str] = []
        if isinstance(data, ParseFailure):
            error = data.reason
        else:
            flag = data.get("needs_retrieval")
            needs = flag if isinstance(flag, bool) else None
            raw = data.get("queries")
            if not isinstance(raw, list):
                error = "'queries' is missing or not a list"
            else:
                seen: set[str] = set()
                for item in raw:
                    if isinstance(item, str) and item.strip() and _normal(item) not in seen:
                        seen.add(_normal(item))
                        queries.append(" ".join(item.split()))
                queries = queries[: self._config.max_planned_queries]
                if not queries:
                    error = "no usable query"
        if not queries:  # the design always searches at least once
            queries = [question]
        return {
            "pending": queries,
            "needs_retrieval": needs,
            "plan_parse_error": error,
            "calls": [*state["calls"], _call("plan", response)],
            "steps": [
                *state["steps"],
                {
                    "step": "plan",
                    "messages": messages,
                    "raw_content": response.content,
                    "queries": queries,
                    "needs_retrieval": needs,
                    "parse_error": error,
                },
            ],
            "step": state["step"] + 1,
        }

    async def _search(self, state: AgentState) -> dict[str, Any]:
        collected = list(state["collected"])
        known = {item.chunk.chunk_id for item in collected}
        searches = list(state["searches"])
        queries_run = list(state["queries_run"])
        for query in state["pending"]:
            if len(searches) >= self._config.max_searches:
                break
            result = self._retriever.retrieve(query, self._config.results_per_search)
            searches.append(
                SearchRecord(
                    query=query,
                    chunk_ids=tuple(item.chunk.chunk_id for item in result.chunks),
                    embed_ms=result.embed_ms,
                    search_ms=result.search_ms,
                )
            )
            queries_run.append(query)
            for item in result.chunks:
                if item.chunk.chunk_id not in known:
                    known.add(item.chunk.chunk_id)
                    collected.append(item)
        return {
            "pending": [],
            "collected": collected,
            "searches": searches,
            "queries_run": queries_run,
            "step": state["step"] + 1,
        }

    async def _judge(self, state: AgentState) -> dict[str, Any]:
        shown = self._context(state["collected"])
        messages = build_judge_messages(state["question"], state["queries_run"], shown)
        try:
            response = await self._chat.complete(messages)
        except LLMInfraError as exc:
            return {
                "error": exc,
                "steps": [*state["steps"], _failed_step("judge", messages, exc)],
                "step": state["step"] + 1,
            }
        data = extract_json_object(response.content)
        parse_error: str | None = None
        enough = True
        next_query: str | None = None
        if isinstance(data, ParseFailure):
            parse_error = data.reason
        else:
            flag = data.get("enough")
            if isinstance(flag, bool):
                enough = flag
            else:
                parse_error = "'enough' is missing or not a boolean"
            candidate = data.get("next_query")
            if isinstance(candidate, str) and candidate.strip():
                next_query = " ".join(candidate.split())
        already = {_normal(q) for q in state["queries_run"]}
        searching = (
            not enough
            and next_query is not None
            and _normal(next_query) not in already
            and len(state["searches"]) < self._config.max_searches
        )
        return {
            "pending": [next_query] if searching and next_query is not None else [],
            "decisions": [*state["decisions"], enough],
            "judge_parse_errors": state["judge_parse_errors"] + (1 if parse_error else 0),
            "calls": [*state["calls"], _call("judge", response)],
            "steps": [
                *state["steps"],
                {
                    "step": "judge",
                    "messages": messages,
                    "raw_content": response.content,
                    "enough": enough,
                    "next_query": next_query,
                    "parse_error": parse_error,
                },
            ],
            "step": state["step"] + 1,
        }

    async def _answer(self, state: AgentState) -> dict[str, Any]:
        context = self._context(state["collected"])
        try:
            generated = await self._generator.generate(state["question"], context)
        except LLMInfraError as exc:
            return {
                "error": exc,
                "steps": [
                    *state["steps"],
                    _failed_step("answer", build_messages(state["question"], context), exc),
                ],
                "step": state["step"] + 1,
            }
        call = AgentCall(
            step="answer",
            latency_ms=generated.latency_ms,
            attempts=generated.attempts,
            usage=generated.usage,
            finish_reason=generated.finish_reason,
            model_served=generated.model_served,
            provider=generated.provider,
            request_id=generated.request_id,
        )
        return {
            "generated": generated,
            "calls": [*state["calls"], call],
            "steps": [
                *state["steps"],
                {
                    "step": "answer",
                    "messages": [dict(m) for m in generated.messages],
                    "raw_content": generated.raw_content,
                },
            ],
            "step": state["step"] + 1,
        }

    # ---------------------------------------------------------------- run

    async def run(self, question: str) -> AgentResult:
        """Run the graph for one question and return its trace."""
        final = cast(
            AgentState,
            await self._app.ainvoke(
                initial_state(question), config={"recursion_limit": RECURSION_LIMIT}
            ),
        )
        return AgentResult(
            context=self._context(final["collected"]),
            generated=final["generated"],
            error=final["error"],
            calls=tuple(final["calls"]),
            searches=tuple(final["searches"]),
            steps=tuple(final["steps"]),
            needs_retrieval=final["needs_retrieval"],
            plan_parse_error=final["plan_parse_error"],
            judge_parse_errors=final["judge_parse_errors"],
            judge_decisions=tuple(final["decisions"]),
        )
