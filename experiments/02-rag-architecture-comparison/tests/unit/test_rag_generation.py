"""Unit tests for answer parsing, the generator and the fake chat model."""

import json
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from ai_lab.llm import LLMInfraError, LLMResponse, Usage
from rag_experiment.evaluation.dataset import Question, QuestionConstraints
from rag_experiment.generation.fake import FakeChatModel
from rag_experiment.generation.prompts import build_messages
from rag_experiment.generation.provider import (
    Generator,
    ParsedAnswer,
    ParseFailure,
    parse_answer,
)
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.base import RetrievedChunk

pytestmark = pytest.mark.unit

ChunkFactory = Callable[..., Chunk]
GOOD = (
    '{"answer": "Use GET /v1/x.", "cited_chunk_ids": ["c1", "c2"], "insufficient_context": false}'
)


def _parsed(raw: str | None) -> ParsedAnswer:
    result = parse_answer(raw)
    assert isinstance(result, ParsedAnswer), result
    return result


def _failure(raw: str | None) -> str:
    result = parse_answer(raw)
    assert isinstance(result, ParseFailure), result
    return result.reason


def test_plain_json() -> None:
    parsed = _parsed(GOOD)
    assert parsed.answer == "Use GET /v1/x."
    assert parsed.cited_chunk_ids == ("c1", "c2")
    assert parsed.insufficient_context is False


def test_fenced_json_with_and_without_language() -> None:
    assert _parsed(f"```json\n{GOOD}\n```").answer == "Use GET /v1/x."
    assert _parsed(f"```\n{GOOD}\n```").answer == "Use GET /v1/x."
    assert _parsed(f"  \n```JSON\n{GOOD}\n```\n ").cited_chunk_ids == ("c1", "c2")


def test_prose_around_json() -> None:
    assert _parsed(f"Sure, here you go: {GOOD} Hope that helps.").answer == "Use GET /v1/x."


def test_nested_braces_inside_strings_do_not_break_matching() -> None:
    raw = (
        'Result: {"answer": "Path /v1/{id}/x and a } brace, \\"quoted {\\"", '
        '"cited_chunk_ids": [], "insufficient_context": true} trailing {'
    )
    parsed = _parsed(raw)
    assert parsed.answer == 'Path /v1/{id}/x and a } brace, "quoted {"'
    assert parsed.insufficient_context is True
    assert parsed.cited_chunk_ids == ()


def test_missing_citations_default_to_empty() -> None:
    parsed = _parsed('{"answer": "a", "insufficient_context": false}')
    assert parsed.cited_chunk_ids == ()


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (None, "empty reply"),
        ("   ", "empty reply"),
        ("no json here", "no JSON object found"),
        ("{not json}", "invalid JSON"),
        ("[1, 2]", "JSON value is not an object"),
        ('{"answer": "a"}', "'insufficient_context' is missing or not a boolean"),
        ('{"answer": "a", "insufficient_context": "yes"}', "'insufficient_context'"),
        ('{"answer": 5, "insufficient_context": false}', "'answer' is missing"),
        ('{"insufficient_context": false}', "'answer' is missing"),
        (
            '{"answer": "a", "cited_chunk_ids": "c1", "insufficient_context": false}',
            "'cited_chunk_ids' is not a list of strings",
        ),
        (
            '{"answer": "a", "cited_chunk_ids": [1], "insufficient_context": false}',
            "'cited_chunk_ids' is not a list of strings",
        ),
        ('{"answer": "cut off', "no JSON object found"),
    ],
)
def test_failures(raw: str | None, reason: str) -> None:
    assert reason in _failure(raw)


class _StubChat:
    def __init__(self, content: str | None, finish_reason: str | None = "stop") -> None:
        self.content = content
        self.finish_reason = finish_reason
        self.messages: list[Sequence[Any]] = []
        self.tools: list[Any] = []

    async def complete(self, messages: Sequence[Any], tools: Sequence[Any] = ()) -> LLMResponse:
        self.messages.append(messages)
        self.tools.append(tools)
        return LLMResponse(
            content=self.content,
            tool_calls=(),
            finish_reason=self.finish_reason,
            usage=Usage(prompt_tokens=7, completion_tokens=3, total_tokens=10),
            latency_ms=12.5,
            attempts=2,
            client_wait_ms=1.5,
            provider="P",
            model="m",
            request_id="r",
            assistant_message={"role": "assistant", "content": self.content},
        )


class _FailingChat:
    async def complete(self, messages: Sequence[Any], tools: Sequence[Any] = ()) -> LLMResponse:
        raise LLMInfraError("down", kind="server", attempts=3)


@pytest.mark.anyio
async def test_generator_parses_and_records_measurements(make_chunk: ChunkFactory) -> None:
    chat = _StubChat(GOOD)
    chunk = RetrievedChunk(chunk=make_chunk("c1"), score=0.1, rank=1, retriever="dense")
    answer = await Generator(chat).generate("Q?", [chunk])
    assert answer.answer == "Use GET /v1/x."
    assert answer.cited_chunk_ids == ("c1", "c2")
    assert answer.parse_error is None
    assert answer.usage.total_tokens == 10
    assert (answer.latency_ms, answer.attempts, answer.client_wait_ms) == (12.5, 2, 1.5)
    assert (answer.model_served, answer.provider, answer.request_id) == ("m", "P", "r")
    assert answer.simulated is False
    assert chat.tools == [()]
    assert list(chat.messages[0]) == build_messages("Q?", [chunk])


@pytest.mark.anyio
async def test_parse_failure_is_recorded_not_raised() -> None:
    answer = await Generator(_StubChat("plain words", "length"), simulated=True).generate("Q?", [])
    assert answer.parse_error == "no JSON object found"
    assert (answer.answer, answer.cited_chunk_ids, answer.insufficient_context) == ("", (), False)
    assert answer.raw_content == "plain words"
    assert answer.finish_reason == "length"
    assert answer.simulated is True


@pytest.mark.anyio
async def test_infra_error_propagates() -> None:
    with pytest.raises(LLMInfraError):
        await Generator(_FailingChat()).generate("Q?", [])


# ------------------------------------------------------------------------------ fake model


def _question(qid: str, text: str, *, abstain: bool, source: str) -> Question:
    return Question(
        id=qid,
        question=text,
        category="unanswerable" if abstain else "semantic",
        expected_answer="Reference answer.",
        key_facts=() if abstain else ("fact",),
        relevant_sources=() if abstain else (source,),
        relevant_document_ids=() if abstain else ("doc",),
        constraints=QuestionConstraints(must_cite=not abstain, must_abstain=abstain),
        paraphrase_of=None,
        notes="",
    )


@pytest.fixture
def fake_setup(make_chunk: ChunkFactory) -> tuple[list[Question], list[Chunk]]:
    chunks = [
        make_chunk("doc:a:operation", "A", "#/paths/~1a/get"),
        make_chunk("doc:b:operation", "B", "#/paths/~1b/get"),
    ]
    questions = [
        _question("Q1", "About a?", abstain=False, source="doc#/paths/~1a/get"),
        _question("Q2", "Nothing?", abstain=True, source=""),
    ]
    return questions, chunks


def _user(question: str, ids: Sequence[str]) -> list[dict[str, str]]:
    excerpts = "\n\n".join(f'<excerpt id="{i}">\nx\n</excerpt>' for i in ids)
    return [
        {"role": "system", "content": "s"},
        {
            "role": "user",
            "content": f"Documentation excerpts:\n\n{excerpts}\n\nQuestion: {question}",
        },
    ]


@pytest.mark.anyio
async def test_fake_answers_from_relevant_context_and_refuses_otherwise(
    fake_setup: tuple[list[Question], list[Chunk]],
) -> None:
    questions, chunks = fake_setup
    fake = FakeChatModel(questions, chunks)
    hit = await fake.complete(_user("About a?", ["doc:b:operation", "doc:a:operation"]))
    payload = json.loads(hit.content or "")
    assert payload["insufficient_context"] is False
    assert payload["cited_chunk_ids"] == ["doc:a:operation"]
    assert "Reference answer." in payload["answer"] and "fact" in payload["answer"]
    assert hit.simulated and hit.provider == "simulated" and hit.latency_ms == 0.0
    assert hit.usage.prompt_tokens > 0

    miss = json.loads((await fake.complete(_user("About a?", ["doc:b:operation"]))).content or "")
    assert miss["insufficient_context"] is True and miss["cited_chunk_ids"] == []
    abstain = json.loads(
        (await fake.complete(_user("Nothing?", ["doc:a:operation"]))).content or ""
    )
    assert abstain["insufficient_context"] is True
    none = json.loads((await fake.complete(_user("About a?", []))).content or "")
    assert none["insufficient_context"] is True


@pytest.mark.anyio
async def test_fake_fault_knobs(fake_setup: tuple[list[Question], list[Chunk]]) -> None:
    questions, chunks = fake_setup
    fake = FakeChatModel(
        questions,
        chunks,
        invalid_json_for={"Q1-r1"},
        cut_off_for={"Q1-r2"},
        infra_error_for={"Q1-r3"},
        infra_error_kind="daily_limit",
    )
    messages = _user("About a?", ["doc:a:operation"])
    fake.set_attempt("Q1-r1")
    invalid = await fake.complete(messages)
    assert isinstance(parse_answer(invalid.content), ParseFailure)
    fake.set_attempt("Q1-r2")
    cut = await fake.complete(messages)
    assert cut.finish_reason == "length" and isinstance(parse_answer(cut.content), ParseFailure)
    fake.set_attempt("Q1-r3")
    with pytest.raises(LLMInfraError) as caught:
        await fake.complete(messages)
    assert caught.value.kind == "daily_limit"
    fake.set_attempt("Q1-r4")
    assert isinstance(parse_answer((await fake.complete(messages)).content), ParsedAnswer)


@pytest.mark.anyio
async def test_fake_calls_before_request_hook(
    fake_setup: tuple[list[Question], list[Chunk]],
) -> None:
    questions, chunks = fake_setup
    calls = 0

    async def hook() -> None:
        nonlocal calls
        calls += 1

    fake = FakeChatModel(questions, chunks, before_request=hook)
    await fake.complete(_user("About a?", []))
    assert calls == 1
