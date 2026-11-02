"""Unit tests for the request plan numbers."""

import pytest

from mcp_vs_code_mode.bench.cells import build_canary_schedule, build_schedule
from mcp_vs_code_mode.bench.config import load_config
from mcp_vs_code_mode.bench.plan import estimate_requests, format_plan

pytestmark = pytest.mark.unit


def test_default_plan_numbers() -> None:
    config = load_config()
    plan = estimate_requests(build_schedule(config), config)
    assert plan.warmup_tasks == 3
    assert plan.tasks == 3 + 110 == 113
    # warm-ups: 3 modes x 2 calls = 6.
    # Per iteration: A 3 modes x 2 = 6; B mcp 2 volumes x 3 = 6; B mcp_agg 2 x 3 = 6;
    # B code 2 x 2 = 4; C mcp_agg 3; C code 2 -> 27.
    assert plan.oracle_requests == 3 * 2 + 10 * (6 + 6 + 6 + 4 + 3 + 2) == 276
    assert plan.worst_case_requests == 113 * 8 == 904
    assert plan.minutes_at_rate_limit == pytest.approx(276 / 15)
    assert plan.per_cell["A:mcp"] == 11
    assert plan.per_cell["B100:code"] == 10
    assert plan.per_cell["C100:mcp_agg"] == 10


def test_format_plan_notes_worst_case_above_daily_cap() -> None:
    config = load_config()
    plan = estimate_requests(build_schedule(config), config)
    text = format_plan(plan, None, config.daily_request_cap)
    assert "904" in text
    assert "exceeds the daily cap" in text
    assert "--resume" in text
    small = estimate_requests(build_canary_schedule(config), config)
    assert "exceeds" not in format_plan(small, None, config.daily_request_cap)


def test_canary_plan_and_format() -> None:
    config = load_config()
    plan = estimate_requests(build_canary_schedule(config), config)
    assert plan.oracle_requests == 2 + 3 + 3 + 2
    text = format_plan(plan, 800)
    assert "Estimates, not measurements." in text
    assert "800" in text
    assert "lower bound" in text
