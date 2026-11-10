"""The generator: build the prompt, call the chat model, parse the structured answer."""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from ai_lab.llm import ChatModel, LLMResponse, Usage
from rag_experiment.generation.prompts import build_messages
from rag_experiment.retrieval.base import RetrievedChunk

_FENCE = re.compile(r"^```(?:json)?[ \t]*\n?(.*?)\n?```$", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ParsedAnswer:
    """A well-formed model answer."""

    answer: str
    cited_chunk_ids: tuple[str, ...]
    insufficient_context: bool


@dataclass(frozen=True)
class ParseFailure:
    """The reply could not be turned into a ``ParsedAnswer``; ``reason`` is short and fixed."""

    reason: str


class GeneratedAnswer(BaseModel):
    """One generation: the parsed fields (or the parse error) plus measurements."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str
    cited_chunk_ids: tuple[str, ...]
    insufficient_context: bool
    raw_content: str | None
    parse_error: str | None
    finish_reason: str | None
    usage: Usage
    latency_ms: float
    attempts: int
    client_wait_ms: float
    model_served: str | None
    provider: str | None
    request_id: str | None
    simulated: bool
    messages: tuple[dict[str, str], ...] = ()


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    match = _FENCE.match(stripped)
    return match.group(1).strip() if match else stripped


def _first_object(text: str) -> str | None:
    """The substring from the first ``{`` to its matching ``}``, respecting JSON strings."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _load(text: str) -> object | None:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value


def parse_answer(raw: str | None) -> ParsedAnswer | ParseFailure:
    """Parse a model reply. Lenient about fences and surrounding prose; no other repair.

    Steps: strip one code fence; try the whole text as JSON; otherwise take the first balanced
    ``{...}`` and try that. Then validate the three fields.
    """
    if raw is None or not raw.strip():
        return ParseFailure("empty reply")
    text = _strip_fence(raw)
    data = _load(text)
    if data is None:
        candidate = _first_object(text)
        if candidate is None:
            return ParseFailure("no JSON object found")
        data = _load(candidate)
        if data is None:
            return ParseFailure("invalid JSON")
    if not isinstance(data, dict):
        return ParseFailure("JSON value is not an object")
    answer = data.get("answer")
    if not isinstance(answer, str):
        return ParseFailure("'answer' is missing or not a string")
    cited = data.get("cited_chunk_ids", [])
    if not isinstance(cited, list) or not all(isinstance(item, str) for item in cited):
        return ParseFailure("'cited_chunk_ids' is not a list of strings")
    flag = data.get("insufficient_context")
    if not isinstance(flag, bool):
        return ParseFailure("'insufficient_context' is missing or not a boolean")
    return ParsedAnswer(
        answer=answer, cited_chunk_ids=tuple(str(item) for item in cited), insufficient_context=flag
    )


class Generator:
    """Asks the chat model to answer from retrieved chunks and parses the reply."""

    def __init__(self, chat: ChatModel, simulated: bool = False) -> None:
        self._chat = chat
        self._simulated = simulated

    async def generate(self, question: str, chunks: Sequence[RetrievedChunk]) -> GeneratedAnswer:
        """Generate one answer. A parse failure is recorded; ``LLMInfraError`` propagates."""
        messages = build_messages(question, chunks)
        response: LLMResponse = await self._chat.complete(messages)
        parsed = parse_answer(response.content)
        answer: str = ""
        cited: tuple[str, ...] = ()
        flag = False
        error: str | None = None
        if isinstance(parsed, ParseFailure):
            error = parsed.reason
        else:
            answer, cited, flag = parsed.answer, parsed.cited_chunk_ids, parsed.insufficient_context
        return GeneratedAnswer(
            answer=answer,
            cited_chunk_ids=cited,
            insufficient_context=flag,
            raw_content=response.content,
            parse_error=error,
            finish_reason=response.finish_reason,
            usage=response.usage,
            latency_ms=response.latency_ms,
            attempts=response.attempts,
            client_wait_ms=response.client_wait_ms,
            model_served=response.model,
            provider=response.provider,
            request_id=response.request_id,
            simulated=self._simulated or response.simulated,
            messages=tuple(messages),
        )
