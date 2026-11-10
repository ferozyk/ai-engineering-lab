"""Real-mode wiring with every network call replaced by a mock (no request leaves the process)."""

import shutil
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest
from openai.types.chat import ChatCompletion

from ai_lab.config import load_settings
from rag_experiment import answer_commands, cli
from rag_experiment.config import ExperimentConfig, RunConfig
from rag_experiment.evaluation.answer_run import (
    AnswerRunMetadata,
    RunPaths,
    load_records,
)

pytestmark = pytest.mark.integration

SECRET = "secret-key-value-123"
REPLY = '{"answer": "Not in the excerpts.", "cited_chunk_ids": [], "insufficient_context": true}'


class _Completions:
    def __init__(self) -> None:
        self.kwargs: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> ChatCompletion:
        self.kwargs.append(kwargs)
        return ChatCompletion.model_validate(
            {
                "id": f"gen-{len(self.kwargs)}",
                "object": "chat.completion",
                "created": 1,
                "model": "served/model",
                "provider": "MockProvider",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": REPLY},
                    }
                ],
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 50,
                    "total_tokens": 1050,
                    "completion_tokens_details": {"reasoning_tokens": 20},
                },
            }
        )


class _Chat:
    def __init__(self, completions: _Completions) -> None:
        self.completions = completions


class _Client:
    instances: ClassVar[list["_Client"]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.init = kwargs
        self.completions = _Completions()
        self.chat = _Chat(self.completions)
        _Client.instances.append(self)


def _handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    if request.url.path.endswith("/models"):
        models = [
            {
                "id": "test/model:free",
                "context_length": 128000,
                "pricing": {"prompt": "0", "completion": "0"},
            },
            {
                "id": "test/model",
                "context_length": 128000,
                "pricing": {"prompt": "0.000001", "completion": "0.000003"},
            },
        ]
        return httpx.Response(200, json={"data": models})
    if request.url.path.endswith("/key"):
        used = 100 + len(_Client.instances[0].completions.kwargs) if _Client.instances else 100
        body = {
            "free_model_daily_requests": {"used": used, "limit": 1000, "remaining": 1000 - used}
        }
        return httpx.Response(200, json={"data": body})
    return httpx.Response(404)


@pytest.fixture
def wired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, experiment_config: ExperimentConfig
) -> Path:
    _Client.instances = []
    results = tmp_path / "results"
    monkeypatch.setattr(cli, "_results_root_base", lambda config: results)
    changed = experiment_config.model_copy(
        update={
            "run": RunConfig(
                **{**experiment_config.run.model_dump(), "rate_limit_per_minute": 60000}
            )
        }
    )
    monkeypatch.setattr(cli, "load_config", lambda path: changed)
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    monkeypatch.setenv("LLM_MODEL", "test/model:free")
    monkeypatch.setattr(cli, "_settings", lambda config: load_settings(env_file=None))
    monkeypatch.setattr(answer_commands, "AsyncOpenAI", _Client)
    real_client = httpx.AsyncClient

    def mocked(**kwargs: Any) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(_handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mocked)
    # The real embedding model is not available in unit runs: use the fake embedder for retrieval.
    original = cli._prepare_retrieval
    monkeypatch.setattr(
        cli, "_prepare_retrieval", lambda config, questions, fake: original(config, questions, True)
    )
    return results


def test_real_mode_canary_with_mocked_provider(
    wired: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["canary"]) == 0
    out = capsys.readouterr().out
    assert "SIMULATED" not in out
    (run_dir,) = list((wired / "raw").iterdir())
    paths = RunPaths(wired, run_dir.name)
    assert paths.run_id.endswith("-answers-dev-dense-canary")
    records = load_records(paths.answers)
    assert sorted(r.question_id for r in records) == ["Q01", "Q05", "Q14"]
    assert all(not r.simulated and r.provider == "MockProvider" for r in records)
    assert all(r.model_served == "served/model" and r.usage.reasoning_tokens == 20 for r in records)

    (client,) = _Client.instances
    assert client.init["max_retries"] == 0 and client.init["api_key"] == SECRET
    assert client.init["timeout"] == 300
    sent = client.completions.kwargs
    assert len(sent) == 3
    for kwargs in sent:
        assert kwargs["model"] == "test/model:free" and kwargs["temperature"] == 0.0
        assert kwargs["max_tokens"] == 16384 and "tools" not in kwargs and "seed" not in kwargs
        assert [m["role"] for m in kwargs["messages"]] == ["system", "user"]

    meta = AnswerRunMetadata.model_validate_json(paths.metadata.read_text("utf-8"))
    assert (
        not meta.simulated and meta.provider == "openrouter" and meta.model_id == "test/model:free"
    )
    assert meta.pricing.source == "paid_variant" and meta.pricing.priced_model == "test/model"
    assert meta.models_served == ["served/model"] and meta.providers_served == ["MockProvider"]
    assert meta.requests_sent == 3 and meta.attempts_completed == 3
    assert meta.free_model_daily_requests_before is not None
    assert meta.free_model_daily_requests_before.used == 100
    assert meta.free_model_daily_requests_after is not None
    assert meta.free_model_daily_requests_after.used == 103
    assert meta.run["repetitions"] == 1

    # no credential anywhere in the run's files
    for path in wired.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".md", ".csv", ".svg"}:
            assert SECRET not in path.read_text("utf-8")


def test_resume_refuses_a_different_model(
    wired: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["canary"]) == 0
    (run_dir,) = list((wired / "raw").iterdir())
    monkeypatch.setenv("LLM_MODEL", "another/model")
    capsys.readouterr()
    assert cli.main(["run", "--set", "dev", "--resume", run_dir.name]) == 2
    assert "never switched silently" in capsys.readouterr().err


def test_preflight_live_sends_exactly_one_request(
    wired: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        answer_commands,
        "index_status",
        lambda *a, **k: answer_commands.CheckResult("index", "pass", "ok"),
    )
    monkeypatch.setenv("LLM_MODEL", "test/model")
    source = Path(__file__).resolve().parents[2] / "results"
    run_id = answer_commands.find_retrieval_run(source, "measured")
    assert run_id is not None
    shutil.copytree(source / "raw" / run_id, wired / "raw" / run_id)
    assert cli.main(["preflight", "--live"]) == 0
    out = capsys.readouterr().out
    assert "live checks will send 1 model request" in out
    assert SECRET not in out
    (client,) = _Client.instances
    (kwargs,) = client.completions.kwargs
    assert kwargs["max_tokens"] == 256 and kwargs["messages"] == [
        {"role": "user", "content": "Reply with the word OK."}
    ]
    for name in ("model_listed", "context_window", "pricing", "key", "completion"):
        assert name in out
