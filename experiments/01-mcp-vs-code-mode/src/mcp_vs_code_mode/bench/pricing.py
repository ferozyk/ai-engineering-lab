"""Pricing snapshot and cost estimation. Costs are estimates, never billed amounts."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from mcp_vs_code_mode.bench.config import BenchmarkConfig
from mcp_vs_code_mode.bench.openrouter import ModelInfo

PricingSource = Literal["paid_variant", "same_model", "config_reference", "simulated"]
_FREE_SUFFIX = ":free"


class PricingError(Exception):
    """No usable price could be determined."""


class PricingSnapshot(BaseModel, frozen=True):
    """The price used for cost estimates, with its provenance."""

    source: PricingSource
    priced_model: str
    prompt_usd_per_token: float
    completion_usd_per_token: float
    captured_at: datetime
    note: str


def _prices(model: ModelInfo | None) -> tuple[float, float] | None:
    if model is None or model.pricing is None:
        return None
    prompt, completion = model.pricing.prompt, model.pricing.completion
    if prompt is None or completion is None or prompt <= 0 or completion <= 0:
        return None
    return prompt, completion


def resolve_pricing(
    model_id: str, models: Sequence[ModelInfo], config: BenchmarkConfig
) -> PricingSnapshot:
    """Find the price to estimate cost with.

    Order: the paid variant of a ``:free`` model, the model itself, the configured reference.
    """
    now = datetime.now(UTC)
    by_id = {m.id: m for m in models}
    if model_id.endswith(_FREE_SUFFIX):
        paid_id = model_id.removesuffix(_FREE_SUFFIX)
        found = _prices(by_id.get(paid_id))
        if found is not None:
            return PricingSnapshot(
                source="paid_variant",
                priced_model=paid_id,
                prompt_usd_per_token=found[0],
                completion_usd_per_token=found[1],
                captured_at=now,
                note=(
                    f"Estimated at the paid variant's list price ({paid_id}) "
                    f"captured {now:%Y-%m-%d}"
                ),
            )
    found = _prices(by_id.get(model_id))
    if found is not None:
        return PricingSnapshot(
            source="same_model",
            priced_model=model_id,
            prompt_usd_per_token=found[0],
            completion_usd_per_token=found[1],
            captured_at=now,
            note=f"Estimated at the model's own list price ({model_id}) captured {now:%Y-%m-%d}",
        )
    ref = config.pricing
    if (
        ref.reference_prompt_usd_per_million is not None
        and ref.reference_completion_usd_per_million is not None
    ):
        label = ref.reference_model_label or "reference"
        return PricingSnapshot(
            source="config_reference",
            priced_model=label,
            prompt_usd_per_token=ref.reference_prompt_usd_per_million / 1_000_000,
            completion_usd_per_token=ref.reference_completion_usd_per_million / 1_000_000,
            captured_at=now,
            note=f"Estimated at a reference price from the configuration ({label})",
        )
    raise PricingError(
        f"No paid price found for {model_id!r}. Set pricing.reference_prompt_usd_per_million "
        "and pricing.reference_completion_usd_per_million (and reference_model_label) in "
        "configs/benchmark.yaml."
    )


def simulated_pricing() -> PricingSnapshot:
    """Placeholder pricing for dry runs."""
    return PricingSnapshot(
        source="simulated",
        priced_model="simulated",
        prompt_usd_per_token=1e-6,
        completion_usd_per_token=2e-6,
        captured_at=datetime.now(UTC),
        note="Simulated placeholder price — not a real price",
    )


def estimate_cost_usd(input_tokens: int, output_tokens: int, pricing: PricingSnapshot) -> float:
    """Estimate cost as input x prompt price + output x completion price.

    Output tokens include reasoning tokens as reported by the provider. Cached-token discounts
    are not applied, so this is an upper-bound style estimate.
    """
    return (
        input_tokens * pricing.prompt_usd_per_token
        + output_tokens * pricing.completion_usd_per_token
    )
