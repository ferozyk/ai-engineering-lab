"""Ground truth computed directly from the dataset.

Deliberately independent of the banking service and tools so it can validate
them. The analysis window is taken from the dataset's own ``window_start`` and
``window_end`` fields.
"""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from mcp_vs_code_mode.banking.dataset import customer_id_for
from mcp_vs_code_mode.banking.models import Dataset
from mcp_vs_code_mode.scenarios.definitions import (
    SCENARIO_A_ACCOUNT_ID,
    AccountSummary,
    AnswerA,
    AnswerB,
)

_CENT = Decimal("0.01")
_LARGE_DEBIT_THRESHOLD = Decimal("1000")


def _to_float(value: Decimal) -> float:
    return float(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def expected_answer_a(dataset: Dataset) -> AnswerA:
    """Expected answer for scenario A."""
    for balance in dataset.balances:
        if balance.account_id == SCENARIO_A_ACCOUNT_ID:
            return AnswerA(
                account_id=balance.account_id,
                available_balance=balance.available_balance,
                currency=balance.currency,
            )
    raise ValueError(f"Account {SCENARIO_A_ACCOUNT_ID} not in dataset")


def expected_answer_b(dataset: Dataset, volume: int) -> AnswerB:
    """Expected answer for scenario B at the given volume."""
    customer_id = customer_id_for(volume)
    account_ids = sorted(a.account_id for a in dataset.accounts if a.customer_id == customer_id)
    if not account_ids:
        raise ValueError(f"Customer {customer_id} not in dataset")
    balances = {b.account_id: b for b in dataset.balances}

    summaries: list[AccountSummary] = []
    total = Decimal("0")
    for account_id in account_ids:
        available = Decimal(str(balances[account_id].available_balance))
        total += available
        spend: defaultdict[str, Decimal] = defaultdict(Decimal)
        large_ids: list[str] = []
        for txn in dataset.transactions:
            if txn.account_id != account_id:
                continue
            if not dataset.window_start <= txn.date <= dataset.window_end:
                continue
            if txn.amount >= 0:
                continue
            absolute = abs(Decimal(str(txn.amount)))
            spend[txn.category] += absolute
            if absolute > _LARGE_DEBIT_THRESHOLD:
                large_ids.append(txn.transaction_id)
        summaries.append(
            AccountSummary(
                account_id=account_id,
                available_balance=_to_float(available),
                spend_by_category={cat: _to_float(amount) for cat, amount in sorted(spend.items())},
                large_debit_ids=sorted(large_ids),
            )
        )
    return AnswerB(
        customer_id=customer_id,
        accounts=summaries,
        total_available_balance=_to_float(total),
    )
