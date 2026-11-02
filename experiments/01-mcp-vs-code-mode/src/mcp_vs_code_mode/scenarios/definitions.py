"""Scenario definitions: task prompts and answer schemas."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mcp_vs_code_mode.banking.dataset import VOLUMES, WINDOW_END, WINDOW_START, customer_id_for

ScenarioId = Literal["A", "B", "C"]
SCENARIO_A_ACCOUNT_ID = "ACC-0050-1"

_PROMPT_A = (
    f"What is the available balance of account {SCENARIO_A_ACCOUNT_ID}?\n"
    'Respond with only a JSON object with keys: "account_id" (string), '
    '"available_balance" (number), "currency" (string).'
)

_PROMPT_B = """\
For customer {cid}, analyse the period {start} to {end} (inclusive).
For each of the customer's accounts, report:
- "account_id"
- "available_balance"
- "spend_by_category": for debit transactions (negative amounts) in the period, the sum of absolute amounts grouped by category, rounded to 2 decimal places. Include only categories with at least one debit.
- "large_debit_ids": IDs of debit transactions whose absolute amount is greater than 1000, sorted ascending.
Also report "total_available_balance": the sum of available balances across all accounts, rounded to 2 decimal places.
Respond with only a JSON object of this shape:
{{"customer_id": "...", "accounts": [{{"account_id": "...", "available_balance": 0.0, "spend_by_category": {{"<category>": 0.0}}, "large_debit_ids": ["..."]}}], "total_available_balance": 0.0}}"""  # noqa: E501


_PROMPT_C = """\
For customer {cid}, analyse the period {start} to {end} (inclusive), across all of the customer's accounts.
Report:
- "top_merchants": the 3 merchants with the highest total debit spend (sum of absolute amounts of debit transactions, i.e. negative amounts), as a list of {{"merchant": ..., "total": ...}} sorted by total descending, totals rounded to 2 decimal places.
- "weekend_debit_count": the number of debit transactions dated on a Saturday or Sunday.
Respond with only a JSON object of this shape:
{{"customer_id": "...", "top_merchants": [{{"merchant": "...", "total": 0.0}}], "weekend_debit_count": 0}}"""  # noqa: E501


class AnswerA(BaseModel):
    """Answer schema for scenario A."""

    model_config = ConfigDict(extra="ignore")

    account_id: str
    available_balance: float
    currency: str


class AccountSummary(BaseModel):
    """Per-account summary in scenario B."""

    model_config = ConfigDict(extra="ignore")

    account_id: str
    available_balance: float
    spend_by_category: dict[str, float]
    large_debit_ids: list[str]


class AnswerB(BaseModel):
    """Answer schema for scenario B."""

    model_config = ConfigDict(extra="ignore")

    customer_id: str
    accounts: list[AccountSummary]
    total_available_balance: float


class MerchantTotal(BaseModel):
    """One ranked merchant in scenario C."""

    model_config = ConfigDict(extra="ignore")

    merchant: str
    total: float


class AnswerC(BaseModel):
    """Answer schema for scenario C."""

    model_config = ConfigDict(extra="ignore")

    customer_id: str
    top_merchants: list[MerchantTotal]
    weekend_debit_count: int


@dataclass(frozen=True)
class TaskSpec:
    """A scenario task presented to the model."""

    scenario: ScenarioId
    volume: int | None
    user_prompt: str


def scenario_a_task() -> TaskSpec:
    """Build the scenario A (simple lookup) task."""
    return TaskSpec(scenario="A", volume=None, user_prompt=_PROMPT_A)


def scenario_b_task(volume: int) -> TaskSpec:
    """Build the scenario B (chained aggregation) task for a volume level."""
    if volume not in VOLUMES:
        raise ValueError(f"volume must be one of {VOLUMES}, got {volume}")
    prompt = _PROMPT_B.format(
        cid=customer_id_for(volume),
        start=WINDOW_START.isoformat(),
        end=WINDOW_END.isoformat(),
    )
    return TaskSpec(scenario="B", volume=volume, user_prompt=prompt)


def scenario_c_task(volume: int) -> TaskSpec:
    """Build the scenario C (unanticipated query) task for a volume level."""
    if volume not in VOLUMES:
        raise ValueError(f"volume must be one of {VOLUMES}, got {volume}")
    prompt = _PROMPT_C.format(
        cid=customer_id_for(volume),
        start=WINDOW_START.isoformat(),
        end=WINDOW_END.isoformat(),
    )
    return TaskSpec(scenario="C", volume=volume, user_prompt=prompt)
