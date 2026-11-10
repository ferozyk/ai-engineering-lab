"""Unit tests for the OpenRouter client using httpx.MockTransport (no network)."""

import httpx
import pytest

from ai_lab.llm.openrouter import OpenRouterClient, OpenRouterError

pytestmark = [pytest.mark.unit, pytest.mark.anyio]

_KEY = "sk-test-secret-key"


def _model(model_id: str) -> dict[str, object]:
    return {
        "id": model_id,
        "context_length": 1000,
        "pricing": {"prompt": "0.000001", "completion": "0.000002"},
        "supported_parameters": ["tools"],
        "top_provider": {"context_length": 900, "max_completion_tokens": None},
        "unknown_field": True,
    }


def _client(handler: httpx.MockTransport, page_limit: int = 2) -> OpenRouterClient:
    http = httpx.AsyncClient(transport=handler)
    return OpenRouterClient(
        base_url="https://example.invalid/api/v1/", api_key=_KEY, http=http, page_limit=page_limit
    )


async def test_pagination_and_auth_header() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        offset = int(request.url.params["offset"])
        pages = {
            0: {"data": [_model("a/1"), _model("a/2")], "links": {"next": "x"}},
            2: {"data": [_model("a/3")], "links": {"next": None}},
        }
        return httpx.Response(200, json=pages[offset])

    models = await _client(httpx.MockTransport(handler)).list_models()
    assert [m.id for m in models] == ["a/1", "a/2", "a/3"]
    assert len(seen) == 2
    assert all(r.headers["authorization"] == f"Bearer {_KEY}" for r in seen)
    first = models[0]
    assert first.pricing is not None
    assert first.pricing.prompt == pytest.approx(1e-6)
    assert first.top_provider_context_length == 900
    assert first.top_provider_max_completion_tokens is None


async def test_missing_fields_do_not_crash() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "bare/model"}]})

    models = await _client(httpx.MockTransport(handler)).list_models()
    assert models[0].pricing is None
    assert models[0].supported_parameters == []


async def test_key_info_parsing_and_missing_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/key"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "label": "k",
                        "is_free_tier": False,
                        "free_model_daily_requests": {"used": 3, "limit": 1000, "remaining": 997},
                    }
                },
            )
        return httpx.Response(404)

    info = await _client(httpx.MockTransport(handler)).key_info()
    assert info.free_model_daily_requests is not None
    assert info.free_model_daily_requests.remaining == 997

    bare = _client(httpx.MockTransport(lambda r: httpx.Response(200, json={"data": {}})))
    assert (await bare.key_info()).free_model_daily_requests is None


async def test_non_2xx_raises_without_key() -> None:
    client = _client(httpx.MockTransport(lambda r: httpx.Response(401, text="nope")))
    with pytest.raises(OpenRouterError) as excinfo:
        await client.key_info()
    assert "401" in str(excinfo.value)
    assert "/key" in str(excinfo.value)
    assert _KEY not in str(excinfo.value)
