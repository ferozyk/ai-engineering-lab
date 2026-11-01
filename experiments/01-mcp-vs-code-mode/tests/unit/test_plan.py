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
    assert plan.tasks == 2 + 120
    # warm-ups: 2 modes x 2 calls; per iteration: A (2+2) + B mcp 3 volumes x 3 + B code 3 x 2
    assert plan.oracle_requests == 2 * 2 + 15 * (2 + 2 + 3 * 3 + 2 * 3) == 289
    assert plan.worst_case_requests == 122 * 8 == 976
    assert plan.minutes_at_rate_limit == pytest.approx(289 / 15)
    assert plan.per_cell["A:mcp"] == 16
    assert plan.per_cell["B200:code"] == 15


def test_canary_plan_and_format() -> None:
    config = load_config()
    plan = estimate_requests(build_canary_schedule(config), config)
    assert plan.oracle_requests == 2 + 2 + 3 + 2 + 3
    text = format_plan(plan, 800)
    assert "Estimates, not measurements." in text
    assert "800" in text
    assert "lower bound" in text
