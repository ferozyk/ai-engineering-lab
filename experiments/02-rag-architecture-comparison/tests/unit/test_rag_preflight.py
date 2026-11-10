"""Unit tests for the preflight checks (no network: the provider is mocked)."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest

from ai_lab.config import Settings, load_settings
from ai_lab.llm import LLMResponse, Usage
from rag_experiment import answer_commands
from rag_experiment.answer_commands import (
    CheckResult,
    format_report,
    index_status,
    largest_prompt,
    live_checks,
    offline_checks,
)
from rag_experiment.config import ExperimentConfig
from rag_experiment.corpus import Corpus
from rag_experiment.embeddings.fake import FakeEmbeddingProvider
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.store import collection_name, open_local_store

pytestmark = pytest.mark.unit

EXP_ROOT = Path(__file__).resolve().parents[2]
SECRET = "secret-key-value-123"


def _settings(monkeypatch: pytest.MonkeyPatch, *, key: bool, model: bool) -> Settings:
    if key:
        monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    if model:
        monkeypatch.setenv("LLM_MODEL", "test/model")
    return load_settings(env_file=None)


def _by_name(results: Sequence[CheckResult]) -> dict[str, CheckResult]:
    return {r.name: r for r in results}


def _config_with_index(config: ExperimentConfig, directory: Path) -> ExperimentConfig:
    return config.model_copy(update={"index": config.index.model_copy(update={"dir": directory})})


def test_index_status_missing_incomplete_and_complete(
    experiment_config: ExperimentConfig, corpus: Corpus, chunks: list[Chunk], tmp_path: Path
) -> None:
    config = _config_with_index(experiment_config, tmp_path / "index")
    assert index_status(config, corpus, chunks).status == "fail"
    assert not (tmp_path / "index").exists()  # the check never creates an index

    collection = collection_name(
        config.index,
        corpus,
        config.chunking,
        config.embedding.model_id,
        config.embedding.revision or "unpinned",
    )
    fake = FakeEmbeddingProvider()
    with open_local_store(tmp_path / "index", collection) as store:
        store.recreate(fake.dimension)
        store.upsert(chunks[:3], fake.embed_documents([c.content for c in chunks[:3]]))
    partial = index_status(config, corpus, chunks)
    assert partial.status == "fail" and "3 of" in partial.detail
    with open_local_store(tmp_path / "index", collection) as store:
        store.upsert(chunks, fake.embed_documents([c.content for c in chunks]))
    assert index_status(config, corpus, chunks).status == "pass"


def test_offline_checks_report_key_state_without_the_value(
    monkeypatch: pytest.MonkeyPatch,
    experiment_config: ExperimentConfig,
    corpus: Corpus,
    chunks: list[Chunk],
) -> None:
    monkeypatch.setattr(
        answer_commands, "index_status", lambda *a, **k: CheckResult("index", "pass", "ok")
    )
    results_base = EXP_ROOT / "results"
    ok = offline_checks(
        experiment_config,
        _settings(monkeypatch, key=True, model=True),
        corpus,
        chunks,
        results_base,
        None,
    )
    by_name = _by_name(ok)
    assert by_name["api_key"].detail == "OPENROUTER_API_KEY is set"
    assert by_name["model"].detail == "LLM_MODEL = test/model"
    assert by_name["config"].status == "pass" and by_name["questions"].status == "pass"
    assert by_name["prompt_size"].status == "pass" and "characters" in by_name["prompt_size"].detail
    assert "123 requests" in by_name["request_plan"].detail
    assert SECRET not in format_report(ok)

    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.delenv("LLM_MODEL")
    bad = _by_name(
        offline_checks(
            experiment_config,
            _settings(monkeypatch, key=False, model=False),
            corpus,
            chunks,
            results_base,
            None,
        )
    )
    assert bad["api_key"].status == "fail" and bad["model"].status == "fail"


def test_largest_prompt_reads_a_committed_retrieval_run(
    experiment_config: ExperimentConfig, chunks: list[Chunk]
) -> None:
    run_id = answer_commands.find_retrieval_run(EXP_ROOT / "results", "measured")
    assert run_id is not None and "retrieval-measured" in run_id
    size, question_id = largest_prompt(experiment_config, chunks, EXP_ROOT / "results", run_id)
    assert size > 1000 and question_id.startswith("Q")


class _Chat:
    def __init__(self, content: str | None, total_tokens: int = 5) -> None:
        self.content = content
        self.total_tokens = total_tokens
        self.calls = 0

    async def complete(self, messages: Sequence[Any], tools: Sequence[Any] = ()) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            content=self.content,
            tool_calls=(),
            finish_reason="stop",
            usage=Usage(prompt_tokens=3, completion_tokens=2, total_tokens=self.total_tokens),
            latency_ms=1.0,
            attempts=1,
            client_wait_ms=0.0,
            assistant_message={"role": "assistant", "content": self.content},
        )


def _transport(models: list[dict[str, Any]], key: dict[str, Any] | None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": models})
        if request.url.path.endswith("/key"):
            if key is None:
                return httpx.Response(500, json={})
            return httpx.Response(200, json={"data": key})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


_MODEL = {
    "id": "test/model",
    "context_length": 100_000,
    "pricing": {"prompt": "0.000001", "completion": "0.000002"},
}
_KEY = {"free_model_daily_requests": {"used": 10, "limit": 1000, "remaining": 990}}


@pytest.mark.anyio
async def test_live_checks_pass(
    monkeypatch: pytest.MonkeyPatch, experiment_config: ExperimentConfig
) -> None:
    settings = _settings(monkeypatch, key=True, model=True)
    chat = _Chat("OK")
    async with httpx.AsyncClient(transport=_transport([_MODEL], _KEY)) as http:
        results = await live_checks(experiment_config, settings, http, chat, 5000)
    by_name = _by_name(results)
    assert all(r.status == "pass" for r in results), format_report(results)
    assert {"model_listed", "context_window", "pricing", "key", "completion"} <= set(by_name)
    assert "990/1000" in by_name["key"].detail
    assert chat.calls == 1
    assert SECRET not in format_report(results)


@pytest.mark.anyio
async def test_live_checks_fail_on_unknown_model_bad_completion_and_key_error(
    monkeypatch: pytest.MonkeyPatch, experiment_config: ExperimentConfig
) -> None:
    settings = _settings(monkeypatch, key=True, model=True)
    other = {**_MODEL, "id": "other/model"}
    async with httpx.AsyncClient(transport=_transport([other], None)) as http:
        results = await live_checks(experiment_config, settings, http, _Chat(None), None)
    by_name = _by_name(results)
    assert by_name["model_listed"].status == "fail"
    assert by_name["pricing"].status == "fail"
    assert by_name["key"].status == "fail"
    assert by_name["completion"].status == "fail"


@pytest.mark.anyio
async def test_live_checks_flag_a_too_small_context_window(
    monkeypatch: pytest.MonkeyPatch, experiment_config: ExperimentConfig
) -> None:
    settings = _settings(monkeypatch, key=True, model=True)
    small = {**_MODEL, "context_length": 1000}
    async with httpx.AsyncClient(transport=_transport([small], _KEY)) as http:
        results = await live_checks(experiment_config, settings, http, _Chat("OK"), 50_000)
    assert _by_name(results)["context_window"].status == "fail"
