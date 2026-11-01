"""Unit tests for scenario definitions."""

import pytest

from mcp_vs_code_mode.scenarios import scenario_a_task, scenario_b_task

pytestmark = pytest.mark.unit


def test_scenario_a_prompt() -> None:
    task = scenario_a_task()
    assert task.scenario == "A"
    assert task.volume is None
    assert "ACC-0050-1" in task.user_prompt
    assert '"available_balance" (number)' in task.user_prompt


@pytest.mark.parametrize("volume", [10, 50, 100, 200])
def test_scenario_b_prompt(volume: int) -> None:
    task = scenario_b_task(volume)
    assert task.scenario == "B"
    assert task.volume == volume
    assert f"CUST-{volume:04d}" in task.user_prompt
    assert "2026-07-03 to 2026-10-01 (inclusive)" in task.user_prompt
    assert '"total_available_balance"' in task.user_prompt
    assert "{cid}" not in task.user_prompt


def test_invalid_volume() -> None:
    with pytest.raises(ValueError, match="volume"):
        scenario_b_task(30)
