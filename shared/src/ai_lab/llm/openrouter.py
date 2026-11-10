"""Minimal OpenRouter client for the model list and key information (no model requests)."""

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

_PAGE_LIMIT = 1000
_MAX_PAGES = 50


class OpenRouterError(Exception):
    """A non-2xx or unparseable response. Messages never contain credentials."""


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _price(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


class ModelPricing(_Lenient):
    """USD per token; ``None`` means unknown."""

    prompt: float | None = None
    completion: float | None = None

    @field_validator("prompt", "completion", mode="before")
    @classmethod
    def _parse(cls, value: object) -> float | None:
        return _price(value)


class ModelInfo(BaseModel):
    """Flattened model entry."""

    id: str
    context_length: int | None = None
    pricing: ModelPricing | None = None
    supported_parameters: list[str] = []
    top_provider_context_length: int | None = None
    top_provider_max_completion_tokens: int | None = None


class _TopProvider(_Lenient):
    context_length: int | None = None
    max_completion_tokens: int | None = None


class _RawModel(_Lenient):
    id: str
    context_length: int | None = None
    pricing: ModelPricing | None = None
    supported_parameters: list[str] | None = None
    top_provider: _TopProvider | None = None

    def to_info(self) -> ModelInfo:
        top = self.top_provider
        return ModelInfo(
            id=self.id,
            context_length=self.context_length,
            pricing=self.pricing,
            supported_parameters=self.supported_parameters or [],
            top_provider_context_length=top.context_length if top else None,
            top_provider_max_completion_tokens=top.max_completion_tokens if top else None,
        )


class _Links(_Lenient):
    next: str | None = None


class _ModelsPage(_Lenient):
    data: list[_RawModel] = []
    links: _Links | None = None


class FreeModelDailyRequests(_Lenient):
    """Free-tier daily request counters."""

    used: int
    limit: int
    remaining: int


class KeyInfo(_Lenient):
    """Selected fields from ``GET /key``."""

    label: str | None = None
    is_free_tier: bool | None = None
    free_model_daily_requests: FreeModelDailyRequests | None = None


class _KeyEnvelope(_Lenient):
    data: KeyInfo = KeyInfo()


class OpenRouterClient:
    """Reads the model list and key info. The ``http`` client is injected."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        http: httpx.AsyncClient,
        page_limit: int = _PAGE_LIMIT,
    ) -> None:
        self._page_limit = page_limit
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._http = http

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = await self._http.get(
                f"{self._base}{path}", headers=self._headers, params=params
            )
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"GET {path} failed: {type(exc).__name__}") from exc
        if not response.is_success:
            raise OpenRouterError(f"GET {path} returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise OpenRouterError(f"GET {path} returned invalid JSON") from exc

    async def list_models(self) -> list[ModelInfo]:
        """All models, following pagination."""
        models: list[ModelInfo] = []
        offset = 0
        for _ in range(_MAX_PAGES):
            payload = await self._get("/models", {"offset": offset, "limit": self._page_limit})
            try:
                page = _ModelsPage.model_validate(payload)
            except ValidationError as exc:
                raise OpenRouterError("GET /models returned an unexpected shape") from exc
            models.extend(item.to_info() for item in page.data)
            has_next = page.links is not None and page.links.next is not None
            if not has_next or len(page.data) < self._page_limit:
                break
            offset += len(page.data)
        return models

    async def key_info(self) -> KeyInfo:
        """Key metadata including free-model daily counters (not a model request)."""
        payload = await self._get("/key")
        try:
            return _KeyEnvelope.model_validate(payload).data
        except ValidationError as exc:
            raise OpenRouterError("GET /key returned an unexpected shape") from exc
