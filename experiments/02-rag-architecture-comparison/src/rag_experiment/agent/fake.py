"""A deterministic fake chat model for the agent loop (offline dry runs and tests).

Like ``FakeChatModel`` it is an oracle, not a language model. It recognises the step from the
system prompt:

- planner: the question split on " and then " or " and " into at most three queries (otherwise the
  question itself), ``needs_retrieval`` true;
- judge: ``enough`` is true when every labelled source of the question is covered by the
  collected excerpts; otherwise the first time it proposes the question plus the word "endpoint"
  as the next query, and once that query has been run it says ``enough``;
- answer: the oracle answer of ``FakeChatModel``.

Token counts are character counts divided by four, so they are simulated.
"""

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from rag_experiment.agent.prompts import (
    EXCERPTS_MARKER,
    JUDGE_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    QUESTION_PREFIX,
    SEARCHES_MARKER,
)
from rag_experiment.evaluation.dataset import Question
from rag_experiment.evaluation.relevance import covered_sources
from rag_experiment.generation.fake import FakeChatModel
from rag_experiment.ingestion.chunker import Chunk

_EXCERPT_ID = re.compile(r'<excerpt id="([^"]+)">')
_PLANNER_HEAD = PLANNER_SYSTEM_PROMPT.split("{max_queries}")[0]
MAX_FAKE_QUERIES = 3
EXTRA_WORD = "endpoint"


def split_question(text: str) -> list[str]:
    """The fake planner's queries for a question."""
    for separator in (" and then ", " and "):
        if separator in text:
            parts = [p.strip() for p in text.split(separator) if p.strip()]
            return parts[:MAX_FAKE_QUERIES] or [text]
    return [text]


class FakeAgentChatModel(FakeChatModel):
    """Oracle planner, judge and answerer. The knobs of ``FakeChatModel`` apply to every call."""

    def __init__(
        self, questions: Sequence[Question], chunks: Sequence[Chunk], **kwargs: Any
    ) -> None:
        super().__init__(questions, chunks, **kwargs)
        self._questions = {q.question: q for q in questions}
        self._chunks = list(chunks)

    def _reply(self, messages: Sequence[Mapping[str, Any]]) -> str:
        system = str(messages[0]["content"]) if messages[0].get("role") == "system" else ""
        user = str(messages[-1]["content"])
        if system.startswith(_PLANNER_HEAD):
            return self._plan(user)
        if system == JUDGE_SYSTEM_PROMPT:
            return self._judge(user)
        return self._answer(user)

    @staticmethod
    def _plan(question: str) -> str:
        return json.dumps({"needs_retrieval": True, "queries": split_question(question)})

    def _judge(self, user: str) -> str:
        head, _, excerpts = user.partition(EXCERPTS_MARKER)
        question_part, _, searches = head.partition(SEARCHES_MARKER)
        text = question_part.removeprefix(QUESTION_PREFIX)
        question = self._questions.get(text)
        queries = [line.split(". ", 1)[-1] for line in searches.splitlines() if line.strip()]
        extra_query = f"{text} {EXTRA_WORD}"
        covered = True
        if question is not None and not question.constraints.must_abstain:
            sources = set(question.sources)
            found = covered_sources(_EXCERPT_ID.findall(excerpts), sources, self._chunks)
            covered = found == sources
        if covered or extra_query in queries:
            return json.dumps({"enough": True, "missing": "", "next_query": None})
        return json.dumps(
            {"enough": False, "missing": "a labelled source", "next_query": extra_query}
        )
