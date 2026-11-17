"""What one agentic attempt records: model calls, searches and the final result."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ai_lab.llm import LLMInfraError, Usage
from rag_experiment.generation.provider import GeneratedAnswer
from rag_experiment.retrieval.base import RetrievedChunk

Step = Literal["plan", "judge", "answer"]


class AgentCall(BaseModel):
    """One model call of the agent loop (a call that failed after retries is not listed)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step: Step
    latency_ms: float
    attempts: int
    usage: Usage
    finish_reason: str | None
    model_served: str | None
    provider: str | None
    request_id: str | None


class SearchRecord(BaseModel):
    """One call of the search tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    chunk_ids: tuple[str, ...]
    embed_ms: float
    search_ms: float


@dataclass(frozen=True)
class AgentResult:
    """The trace of one attempt, complete or cut short by an infrastructure error."""

    context: tuple[RetrievedChunk, ...]  # what the answer step saw (or would have seen)
    generated: GeneratedAnswer | None
    error: LLMInfraError | None
    calls: tuple[AgentCall, ...]
    searches: tuple[SearchRecord, ...]
    steps: tuple[dict[str, object], ...]  # every call's messages and raw reply, in order
    needs_retrieval: bool | None
    plan_parse_error: str | None
    judge_parse_errors: int
    judge_decisions: tuple[bool, ...]

    @property
    def queries(self) -> tuple[str, ...]:
        """The queries run, in order."""
        return tuple(s.query for s in self.searches)

    @property
    def failed_attempts(self) -> int:
        """HTTP requests spent on the call that raised (0 when nothing failed)."""
        return self.error.attempts if self.error else 0
