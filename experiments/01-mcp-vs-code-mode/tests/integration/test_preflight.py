"""Integration tests for preflight checks (MockTransport and scripted models only)."""

import httpx
import pytest
from pydantic import SecretStr

from ai_lab.config import Settings
from mcp_vs_code_mode.agent import LLMInfraError
from mcp_vs_code_mode.agent.fakes import (
    ScriptedChatModel,
    scripted_text,
    scripted_tool_call,
)
from mcp_vs_code_mode.bench import preflight as preflight_module
from mcp_vs_code_mode.bench.config import load_config
from mcp_vs_code_mode.bench.preflight import (
    CheckResult,
    format_report,
    has_failures,
    run_preflight,
)

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

_MODEL = "test/model:free"


def _settings(model: str | None = _MODEL, key: str | None = "sk-test") -> Settings:
    return Settings(
        _env_file=None,
        openrouter_api_key=SecretStr(key) if key is not None else None,
        llm_model=model,
    )


def _models(
    *, tools: bool = True, context: int = 1_000_000, paid_price: str = "0.000001"
) -> dict[str, object]:
    def entry(model_id: str, price: str) -> dict[str, object]:
        return {
            "id": model_id,
            "context_length": context,
            "pricing": {"prompt": price, "completion": price},
            "supported_parameters": ["tools"] if tools else ["temperature"],
            "top_provider": {"context_length": context, "max_completion_tokens": 131072},
        }

    return {
        "data": [entry(_MODEL, "0"), entry("test/model", paid_price)],
        "links": {"next": None},
    }


def _http(models: dict[str, object], limit: int = 1000, remaining: int = 1000) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=models)
        if request.url.path.endswith("/key"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "free_model_daily_requests": {
                            "used": limit - remaining,
                            "limit": limit,
                            "remaining": remaining,
                        }
                    }
                },
            )
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _by_name(results: list[CheckResult]) -> dict[str, CheckResult]:
    return {r.name: r for r in results}


async def _run(
    models: dict[str, object] | None = None,
    *,
    settings: Settings | None = None,
    live: bool = False,
    chat: ScriptedChatModel | None = None,
    limit: int = 1000,
    remaining: int = 1000,
) -> dict[str, CheckResult]:
    results = await run_preflight(
        settings=settings or _settings(),
        config=load_config(),
        http=_http(models or _models(), limit, remaining),
        live=live,
        chat_model_factory=(lambda: chat) if chat is not None else None,
    )
    return _by_name(results)


async def test_all_pass_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight_module, "git_state", lambda: ("a" * 40, False))
    checks = await _run()
    assert {c.status for c in checks.values()} == {"pass"}, checks
    assert "live_tool_call" not in checks
    report = format_report(list(checks.values()))
    assert "context_window" in report
    assert not has_failures(list(checks.values()))
    assert "chars/4" in checks["context_window"].detail


async def test_model_missing() -> None:
    models = _models()
    models["data"] = []
    checks = await _run(models)
    assert checks["model_listed"].status == "fail"
    assert "tool_calling" not in checks


async def test_no_tool_support() -> None:
    checks = await _run(_models(tools=False))
    assert checks["tool_calling"].status == "fail"


async def test_small_context_fails() -> None:
    checks = await _run(_models(context=2000))
    assert checks["context_window"].status == "fail"


async def test_tier_limit_fails() -> None:
    checks = await _run(limit=50, remaining=50)
    assert checks["key_tier"].status == "fail"
    assert "50" in checks["key_tier"].detail


async def test_low_remaining_warns() -> None:
    checks = await _run(remaining=100)
    assert checks["key_tier"].status == "warn"
    assert "--resume" in checks["key_tier"].detail


async def test_missing_credentials_fail_config() -> None:
    checks = await _run(settings=_settings(model=None, key=None))
    assert checks["config"].status == "fail"
    assert "model_listed" not in checks
    assert checks["mcp_server"].status == "pass"


async def test_no_pricing_fails() -> None:
    checks = await _run(_models(paid_price="0"))
    assert checks["pricing"].status == "fail"


async def test_live_check_passes() -> None:
    chat = ScriptedChatModel([scripted_tool_call("ping", {"message": "ok"}, "c1")])
    checks = await _run(live=True, chat=chat)
    assert checks["live_tool_call"].status == "pass"
    assert chat.seen_messages[0][1]["content"].startswith("Call the ping tool")


async def test_live_check_fails_without_tool_call() -> None:
    checks = await _run(live=True, chat=ScriptedChatModel([scripted_text("hello")]))
    assert checks["live_tool_call"].status == "fail"


async def test_live_check_reports_infra_error() -> None:
    chat = ScriptedChatModel([LLMInfraError("x", kind="server", attempts=3)])
    checks = await _run(live=True, chat=chat)
    assert checks["live_tool_call"].status == "fail"
    assert "server" in checks["live_tool_call"].detail


async def test_live_check_detail_includes_provider_message() -> None:
    error = LLMInfraError(
        "x", kind="auth", status_code=403, attempts=1, provider_message="only on agentic harnesses"
    )
    checks = await _run(live=True, chat=ScriptedChatModel([error]))
    assert checks["live_tool_call"].detail == (
        "provider error kind=auth status=403: only on agentic harnesses"
    )
