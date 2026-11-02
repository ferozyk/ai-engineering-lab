"""Unit tests for benchmark configuration loading and validation."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from mcp_vs_code_mode.bench.config import BenchmarkConfig, load_config
from mcp_vs_code_mode.bench.paths import CONFIG_PATH

pytestmark = pytest.mark.unit


def _raw() -> dict[str, Any]:
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_repo_config_loads() -> None:
    config = load_config()
    assert config.iterations == 10
    assert config.volumes == [10, 100]
    assert config.rate_limit_per_minute == 15
    assert config.daily_request_cap == 900
    assert config.llm_seed is None
    assert config.experiment_version == "0.2.0"
    assert config.modes == ["mcp", "mcp_agg", "code"]
    assert config.scenario_c.volumes == [100]
    assert config.scenario_c.modes == ["mcp_agg", "code"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("iterations", 0),
        ("volumes", [10, 77]),
        ("volumes", []),
        ("rate_limit_per_minute", 21),
        ("daily_request_cap", 1001),
        ("unexpected", 1),
        ("modes", ["mcp", "other"]),
        ("modes", []),
        ("modes", ["mcp", "mcp"]),
        ("scenario_c", {"volumes": [100], "modes": ["mcp"]}),  # not in modes below
        ("scenario_c", {"volumes": [77], "modes": ["code"]}),
        ("scenario_c", {"volumes": [100], "modes": ["nope"]}),
    ],
)
def test_invalid_values_are_rejected(key: str, value: object) -> None:
    data = _raw()
    if key == "scenario_c" and value == {"volumes": [100], "modes": ["mcp"]}:
        data["modes"] = ["mcp_agg", "code"]
    data[key] = value
    with pytest.raises(ValidationError):
        BenchmarkConfig.model_validate(data)


def test_override_iterations() -> None:
    config = load_config().with_overrides(iterations=2)
    assert config.iterations == 2
    assert load_config().iterations == 10


def test_load_from_explicit_path(tmp_path: Path) -> None:
    data = _raw()
    data["iterations"] = 3
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert load_config(path).iterations == 3


def test_old_config_without_modes_or_scenario_c_still_loads() -> None:
    data = _raw()
    del data["modes"]
    del data["scenario_c"]
    config = BenchmarkConfig.model_validate(data)
    assert config.modes == ["mcp", "code"]
    assert config.scenario_c.volumes == []
