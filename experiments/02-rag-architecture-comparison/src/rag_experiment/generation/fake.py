"""A deterministic fake chat model for offline dry runs and tests. It is not a real model.

It behaves as an oracle with controllable faults: given the labelled question set, it answers
with the reference answer when a relevant excerpt is in the prompt and otherwise declares the
context insufficient. Token counts are character counts divided by four, so they are simulated.
"""

import json
import re
from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from typing import Any

from ai_lab.llm import InfraErrorKind, LLMInfraError, LLMResponse, Usage
from rag_experiment.evaluation.dataset import Question
from rag_experiment.evaluation.relevance import relevant_chunk_ids
from rag_experiment.ingestion.chunker import Chunk

_EXCERPT_ID = re.compile(r'<excerpt id="([^"]+)">')
_QUESTION_MARK = "\n\nQuestion: "
_REFUSAL = "The excerpts do not contain enough information to answer this question."


class FakeChatModel:
    """Oracle chat model. Knobs select attempt ids (``"Q01-r1"``) that misbehave."""

    def __init__(
        self,
        questions: Sequence[Question],
        chunks: Sequence[Chunk],
        *,
        invalid_json_for: Collection[str] = (),
        cut_off_for: Collection[str] = (),
        infra_error_for: Collection[str] = (),
        infra_error_kind: InfraErrorKind = "server",
        before_request: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._by_text = {q.question: q for q in questions}
        self._relevant = {
            q.id: relevant_chunk_ids(q.sources, chunks)
            for q in questions
            if not q.constraints.must_abstain
        }
        self._invalid = frozenset(invalid_json_for)
        self._cut_off = frozenset(cut_off_for)
        self._infra = frozenset(infra_error_for)
        self._infra_kind: InfraErrorKind = infra_error_kind
        self._before_request = before_request
        self.current_attempt: str | None = None
        self.calls = 0

    def set_attempt(self, attempt_id: str) -> None:
        """Tell the model which attempt the next call belongs to (used by the knobs)."""
        self.current_attempt = attempt_id

    async def complete(
        self, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]] = ()
    ) -> LLMResponse:
        """Return a simulated reply (no network, no randomness)."""
        if self._before_request is not None:
            await self._before_request()
        self.calls += 1
        attempt = self.current_attempt
        if attempt in self._infra:
            raise LLMInfraError(
                "Simulated provider failure", kind=self._infra_kind, status_code=None, attempts=1
            )
        user = str(messages[-1]["content"])
        prompt_chars = sum(len(str(m["content"])) for m in messages)
        finish = "stop"
        if attempt in self._cut_off:
            content: str | None = '{"answer": "The answer is'
            finish = "length"
        elif attempt in self._invalid:
            content = "I cannot format this as JSON."
        else:
            content = self._answer(user)
        completion_chars = len(content or "")
        usage = Usage(
            prompt_tokens=prompt_chars // 4,
            completion_tokens=completion_chars // 4,
            total_tokens=(prompt_chars + completion_chars) // 4,
        )
        return LLMResponse(
            content=content,
            tool_calls=(),
            finish_reason=finish,
            usage=usage,
            latency_ms=0.0,
            attempts=1,
            client_wait_ms=0.0,
            provider="simulated",
            model="simulated-oracle",
            request_id=f"sim-{self.calls}",
            assistant_message={"role": "assistant", "content": content},
            simulated=True,
        )

    def _answer(self, user: str) -> str:
        head, _, question_text = user.rpartition(_QUESTION_MARK)
        context_ids = _EXCERPT_ID.findall(head)
        question = self._by_text.get(question_text)
        relevant = self._relevant.get(question.id, frozenset()) if question else frozenset()
        cited = [cid for cid in context_ids if cid in relevant]
        if question is None or not cited:
            payload: dict[str, object] = {
                "answer": _REFUSAL,
                "cited_chunk_ids": [],
                "insufficient_context": True,
            }
        else:
            facts = ", ".join(question.key_facts)
            payload = {
                "answer": f"{question.expected_answer} Key facts: {facts}.",
                "cited_chunk_ids": cited,
                "insufficient_context": False,
            }
        return json.dumps(payload)
