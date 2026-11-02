"""Unit tests for scenario definitions."""

import pytest

from mcp_vs_code_mode.scenarios import scenario_a_task, scenario_b_task, scenario_c_task

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


_EXPECTED_C_PROMPT = """\
For customer CUST-0100, analyse the period 2026-07-03 to 2026-10-01 (inclusive), across all of the customer's accounts.
Report:
- "top_merchants": the 3 merchants with the highest total debit spend (sum of absolute amounts of debit transactions, i.e. negative amounts), as a list of {"merchant": ..., "total": ...} sorted by total descending, totals rounded to 2 decimal places.
- "weekend_debit_count": the number of debit transactions dated on a Saturday or Sunday.
Respond with only a JSON object of this shape:
{"customer_id": "...", "top_merchants": [{"merchant": "...", "total": 0.0}], "weekend_debit_count": 0}"""  # noqa: E501


def test_scenario_c_prompt_is_verbatim_template() -> None:
    task = scenario_c_task(100)
    assert (task.scenario, task.volume) == ("C", 100)
    assert task.user_prompt == _EXPECTED_C_PROMPT


def test_scenario_c_invalid_volume() -> None:
    with pytest.raises(ValueError, match="volume"):
        scenario_c_task(30)
