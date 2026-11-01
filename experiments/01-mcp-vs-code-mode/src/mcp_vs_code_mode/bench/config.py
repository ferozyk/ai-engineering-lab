"""Benchmark configuration loaded from ``configs/benchmark.yaml``."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from mcp_vs_code_mode.banking.dataset import VOLUMES
from mcp_vs_code_mode.bench.paths import CONFIG_PATH

_MAX_RATE_PER_MINUTE = 20
_MAX_DAILY_REQUESTS = 1000


class SandboxConfig(BaseModel):
    """Code Mode sandbox limits."""

    model_config = ConfigDict(extra="forbid")

    max_duration_secs: float = Field(gt=0)
    max_memory_mb: int = Field(gt=0)
    max_host_calls: int = Field(gt=0)


class PricingConfig(BaseModel):
    """Optional reference price used when the paid variant cannot be found."""

    model_config = ConfigDict(extra="forbid")

    reference_model_label: str | None = None
    reference_prompt_usd_per_million: float | None = Field(default=None, ge=0)
    reference_completion_usd_per_million: float | None = Field(default=None, ge=0)


class CanaryConfig(BaseModel):
    """Which cells the canary run exercises."""

    model_config = ConfigDict(extra="forbid")

    cells: list[str]


class BenchmarkConfig(BaseModel):
    """Full benchmark configuration."""

    model_config = ConfigDict(extra="forbid")

    experiment: str
    experiment_version: str
    iterations: int = Field(ge=1)
    warmup_tasks_per_mode: int = Field(ge=0)
    volumes: list[int]
    max_turns: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)
    temperature: float = Field(ge=0.0, le=2.0)
    order_seed: int
    llm_seed: int | None = None
    rate_limit_per_minute: int = Field(ge=1, le=_MAX_RATE_PER_MINUTE)
    daily_request_cap: int = Field(ge=1, le=_MAX_DAILY_REQUESTS)
    request_timeout_seconds: float = Field(gt=0)
    mcp_call_timeout_seconds: float = Field(gt=0)
    sandbox: SandboxConfig
    pricing: PricingConfig
    canary: CanaryConfig

    @field_validator("volumes")
    @classmethod
    def _volumes_in_dataset(cls, value: list[int]) -> list[int]:
        unknown = [v for v in value if v not in VOLUMES]
        if unknown or not value:
            raise ValueError(f"volumes must be a non-empty subset of {list(VOLUMES)}")
        return value

    def with_overrides(self, iterations: int | None = None) -> "BenchmarkConfig":
        """Return a copy with selected values replaced (used by dry runs and tests)."""
        data: dict[str, Any] = self.model_dump()
        if iterations is not None:
            data["iterations"] = iterations
        return BenchmarkConfig.model_validate(data)


def load_config(path: Path | None = None) -> BenchmarkConfig:
    """Load and validate the benchmark configuration."""
    source = path if path is not None else CONFIG_PATH
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    return BenchmarkConfig.model_validate(raw)
