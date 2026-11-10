"""Unit tests for pricing resolution and cost arithmetic."""

import pytest

from ai_lab.benchmarking import (
    PricingError,
    PricingReference,
    estimate_cost_usd,
    resolve_pricing,
    simulated_pricing,
)
from ai_lab.llm import ModelInfo, ModelPricing

pytestmark = pytest.mark.unit


def _model(model_id: str, prompt: float | None, completion: float | None) -> ModelInfo:
    return ModelInfo(id=model_id, pricing=ModelPricing(prompt=prompt, completion=completion))


def test_paid_variant_for_free_model() -> None:
    models = [_model("x/y:free", 0.0, 0.0), _model("x/y", 1e-6, 3e-6)]
    snapshot = resolve_pricing("x/y:free", models, None)
    assert snapshot.source == "paid_variant"
    assert snapshot.priced_model == "x/y"
    assert snapshot.prompt_usd_per_token == 1e-6
    assert "paid variant" in snapshot.note


def test_same_model_when_priced() -> None:
    snapshot = resolve_pricing("x/z", [_model("x/z", 2e-6, 4e-6)], None)
    assert snapshot.source == "same_model"


def test_reference_fallback() -> None:
    reference = PricingReference(
        label="ref", prompt_usd_per_million=1.0, completion_usd_per_million=2.0
    )
    snapshot = resolve_pricing("x/y:free", [_model("x/y:free", 0.0, 0.0)], reference)
    assert snapshot.source == "config_reference"
    assert snapshot.priced_model == "ref"
    assert snapshot.prompt_usd_per_token == pytest.approx(1e-6)
    assert snapshot.completion_usd_per_token == pytest.approx(2e-6)


def test_error_when_nothing_available() -> None:
    models = [_model("x/y:free", 0.0, 0.0)]
    with pytest.raises(PricingError, match="reference_prompt_usd_per_million"):
        resolve_pricing("x/y:free", models, None)
    with pytest.raises(PricingError, match="reference_prompt_usd_per_million"):
        resolve_pricing("x/y:free", models, PricingReference(label="empty"))


def test_cost_arithmetic_and_simulated() -> None:
    pricing = simulated_pricing()
    assert pricing.source == "simulated"
    assert "not a real price" in pricing.note
    assert estimate_cost_usd(1000, 500, pricing) == pytest.approx(1000 * 1e-6 + 500 * 2e-6)
