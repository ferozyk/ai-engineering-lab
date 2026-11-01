"""Unit tests for the request plan numbers."""

import pytest

from mcp_vs_code_mode.bench.cells import build_canary_schedule, build_schedule
from mcp_vs_code_mode.bench.config import load_config
from mcp_vs_code_mode.bench.plan import estimate_requests, format_plan

pytestmark = pytest.mark.unit


def test_default_plan_numbers() -> None:
    config = load_config()
    plan = estimate_requests(build_schedule(config), config)
    assert plan.warmup_tasks == 2
    assert plan.tasks == 2 + 60
    # warm-ups: 2 modes x 2 calls; per iteration: A (2+2) + B mcp 2 volumes x 3 + B code 2 x 2
    assert plan.oracle_requests == 2 * 2 + 10 * (2 + 2 + 2 * 3 + 2 * 2) == 144
    assert plan.worst_case_requests == 62 * 8 == 496
    assert plan.minutes_at_rate_limit == pytest.approx(144 / 15)
    assert plan.per_cell["A:mcp"] == 11
    assert plan.per_cell["B100:code"] == 10


def test_canary_plan_and_format() -> None:
    config = load_config()
    plan = estimate_requests(build_canary_schedule(config), config)
    assert plan.oracle_requests == 2 + 2 + 3 + 2 + 3
    text = format_plan(plan, 800)
    assert "Estimates, not measurements." in text
    assert "800" in text
    assert "lower bound" in text
