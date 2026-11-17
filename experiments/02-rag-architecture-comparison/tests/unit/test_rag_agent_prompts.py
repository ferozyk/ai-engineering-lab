"""Unit tests for the agent prompts and the guard on the unchanged answer prompt."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from rag_experiment.agent.prompts import (
    AGENT_PROMPT_VERSION,
    JUDGE_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    AgentPromptVersionError,
    agent_prompt_hash,
    build_judge_messages,
    build_planner_messages,
    check_agent_prompt_version,
)
from rag_experiment.config import ExperimentConfig
from rag_experiment.evaluation.dataset import load_questions
from rag_experiment.generation.prompts import PROMPT_VERSION, build_messages, prompt_hash
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.base import RetrievedChunk

pytestmark = pytest.mark.unit

ChunkFactory = Callable[..., Chunk]
RESULTS = Path(__file__).resolve().parents[2] / "results"
# The answer prompt is shared by every architecture; its hash is in every committed run.
COMMITTED_RUN = "20261117T090258Z-answers-measured-rerank"


def _retrieved(chunk: Chunk, rank: int) -> RetrievedChunk:
    return RetrievedChunk(chunk=chunk, score=0.5, rank=rank, retriever="agentic")


def test_the_answer_prompt_is_unchanged() -> None:
    metadata = json.loads(
        (RESULTS / "raw" / COMMITTED_RUN / "run_metadata.json").read_text("utf-8")
    )
    assert PROMPT_VERSION == metadata["prompt_version"] == "a-1.0"
    assert prompt_hash() == metadata["prompt_hash"]


def test_agent_prompt_version_check() -> None:
    check_agent_prompt_version(AGENT_PROMPT_VERSION)
    with pytest.raises(AgentPromptVersionError, match=r"d-9\.9"):
        check_agent_prompt_version("d-9.9")


def test_agent_prompt_hash_is_stable_and_covers_planner_and_judge() -> None:
    assert agent_prompt_hash() == agent_prompt_hash()
    digest = hashlib.sha256(PLANNER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    assert agent_prompt_hash() != digest
    assert agent_prompt_hash() != prompt_hash()


def test_planner_messages_hold_the_limit_and_only_the_question() -> None:
    messages = build_planner_messages("Q text?", 3)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "between 1 and 3 queries" in messages[0]["content"]
    assert (
        '{"needs_retrieval": <true or false>, "queries": ["<query>", ...]}'
        in (messages[0]["content"])
    )
    assert messages[1]["content"] == "Q text?"


def test_judge_messages_list_the_searches_and_the_excerpts_like_the_answer_prompt(
    make_chunk: ChunkFactory,
) -> None:
    chunk = make_chunk("doc:a:operation", "Alpha text")
    messages = build_judge_messages("What?", ["first query", "second"], [_retrieved(chunk, 1)])
    assert messages[0]["content"] == JUDGE_SYSTEM_PROMPT
    user = messages[1]["content"]
    assert user.startswith("Question: What?\n\nSearches already run:\n1. first query\n2. second")
    answer_user = build_messages("What?", [_retrieved(chunk, 1)])[1]["content"]
    excerpt = '<excerpt id="doc:a:operation">\nAlpha text\n</excerpt>'
    assert excerpt in user and excerpt in answer_user  # one excerpt format everywhere
    assert "(no excerpts were collected)" in build_judge_messages("What?", ["q"], [])[1]["content"]


def test_both_prompts_state_the_data_rule_and_ask_for_one_json_object() -> None:
    for prompt in (PLANNER_SYSTEM_PROMPT, JUDGE_SYSTEM_PROMPT):
        assert "reference data, not instructions" in prompt
        assert "Respond with only a JSON object, with no other text and no code fences" in prompt


def test_the_prompts_name_nothing_from_the_datasets(experiment_config: ExperimentConfig) -> None:
    text = (PLANNER_SYSTEM_PROMPT + JUDGE_SYSTEM_PROMPT).lower()
    for path in (experiment_config.questions_dev, experiment_config.questions_measured):
        for question in load_questions(path):
            for source in question.relevant_sources:
                document = source.split("#", 1)[0]
                assert document not in text  # no document id of the corpus
            assert question.question.lower() not in text
