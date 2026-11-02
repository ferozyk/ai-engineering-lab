"""Unit tests for ground-truth computation."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

import pytest

from mcp_vs_code_mode.banking import (
    VOLUMES,
    Account,
    Balance,
    Customer,
    Dataset,
    Transaction,
    account_ids_for,
    customer_id_for,
)
from mcp_vs_code_mode.scenarios import expected_answer_a, expected_answer_b, expected_answer_c

pytestmark = pytest.mark.unit


def _txn(txn_id: str, account_id: str, day: date, amount: float, category: str) -> Transaction:
    return Transaction.model_validate(
        {
            "transaction_id": txn_id,
            "account_id": account_id,
            "date": day,
            "amount": amount,
            "currency": "USD",
            "merchant": "Test Merchant",
            "category": category,
            "description": "test",
        }
    )


def _tiny_dataset() -> Dataset:
    """One customer, two accounts, a deliberately narrower window than the real one."""
    return Dataset(
        version="test",
        reference_date=date(2026, 9, 30),
        window_start=date(2026, 7, 5),
        window_end=date(2026, 9, 30),
        customers=(Customer(customer_id="CUST-0010", name="Tiny", segment="retail"),),
        accounts=(
            Account(
                account_id="ACC-0010-2",
                customer_id="CUST-0010",
                account_type="savings",
                currency="USD",
            ),
            Account(
                account_id="ACC-0010-1",
                customer_id="CUST-0010",
                account_type="current",
                currency="USD",
            ),
        ),
        balances=(
            Balance(
                account_id="ACC-0010-1",
                available_balance=1000.10,
                ledger_balance=1000.10,
                currency="USD",
                as_of=date(2026, 9, 30),
            ),
            Balance(
                account_id="ACC-0010-2",
                available_balance=2000.25,
                ledger_balance=2000.25,
                currency="USD",
                as_of=date(2026, 9, 30),
            ),
        ),
        transactions=(
            # Outside the dataset window (but inside the module constants): excluded.
            _txn("TXN-0010-1-0001", "ACC-0010-1", date(2026, 7, 4), -77.00, "dining"),
            # Two groceries debits whose sum 30.009 must round half-up to 30.01.
            _txn("TXN-0010-1-0002", "ACC-0010-1", date(2026, 7, 10), -10.005, "groceries"),
            _txn("TXN-0010-1-0003", "ACC-0010-1", date(2026, 7, 10), -20.004, "groceries"),
            # Large debit.
            _txn("TXN-0010-1-0004", "ACC-0010-1", date(2026, 7, 11), -1500.00, "dining"),
            # Credit: excluded from spend.
            _txn("TXN-0010-1-0005", "ACC-0010-1", date(2026, 7, 12), 500.00, "income"),
            # Exactly 1000: not large.
            _txn("TXN-0010-1-0006", "ACC-0010-1", date(2026, 7, 13), -1000.00, "transport"),
            _txn("TXN-0010-2-0001", "ACC-0010-2", date(2026, 8, 1), -45.50, "utilities"),
            # Outside the window.
            _txn("TXN-0010-2-0002", "ACC-0010-2", date(2026, 6, 1), -999.00, "shopping"),
        ),
    )


def test_expected_answer_b_hand_made() -> None:
    answer = expected_answer_b(_tiny_dataset(), 10)
    assert answer.model_dump() == {
        "customer_id": "CUST-0010",
        "accounts": [
            {
                "account_id": "ACC-0010-1",
                "available_balance": 1000.10,
                "spend_by_category": {"dining": 1500.00, "groceries": 30.01, "transport": 1000.00},
                "large_debit_ids": ["TXN-0010-1-0004"],
            },
            {
                "account_id": "ACC-0010-2",
                "available_balance": 2000.25,
                "spend_by_category": {"utilities": 45.50},
                "large_debit_ids": [],
            },
        ],
        "total_available_balance": 3000.35,
    }


def test_unknown_volume_raises() -> None:
    with pytest.raises(ValueError, match="CUST-0050"):
        expected_answer_b(_tiny_dataset(), 50)


def test_expected_answer_a(dataset: Dataset) -> None:
    answer = expected_answer_a(dataset)
    balance = next(b for b in dataset.balances if b.account_id == "ACC-0050-1")
    assert answer.account_id == "ACC-0050-1"
    assert answer.available_balance == balance.available_balance
    assert answer.currency == "USD"


@pytest.mark.parametrize("volume", VOLUMES)
def test_real_dataset_ground_truth(dataset: Dataset, volume: int) -> None:
    answer = expected_answer_b(dataset, volume)
    assert answer.customer_id == customer_id_for(volume)
    assert [a.account_id for a in answer.accounts] == list(account_ids_for(volume))
    assert len(answer.accounts) == 4
    for summary in answer.accounts:
        assert len(summary.large_debit_ids) == max(1, volume // 25)
        assert "income" not in summary.spend_by_category


def _merchant_txn(
    txn_id: str, account_id: str, day: date, amount: float, merchant: str
) -> Transaction:
    return _txn(txn_id, account_id, day, amount, "income" if amount > 0 else "shopping").model_copy(
        update={"merchant": merchant}
    )


def _scenario_c_dataset() -> Dataset:
    """Window 2026-07-05..2026-09-30. 2026-07-05, 07-11 and 08-01 are weekend days."""
    base = _tiny_dataset()
    return base.model_copy(
        update={
            "transactions": (
                # Saturday but before the window: excluded everywhere.
                _merchant_txn("T1", "ACC-0010-1", date(2026, 7, 4), -500.00, "Alpha"),
                # Alpha: 10.005 (Sunday) + 20.004 (Monday) = 30.009 -> 30.01
                _merchant_txn("T2", "ACC-0010-1", date(2026, 7, 5), -10.005, "Alpha"),
                _merchant_txn("T3", "ACC-0010-1", date(2026, 7, 6), -20.004, "Alpha"),
                # Beta: 100.00 (Saturday) + 50.00 (Monday) = 150.00; Sunday credit is ignored.
                _merchant_txn("T4", "ACC-0010-1", date(2026, 7, 11), -100.00, "Beta"),
                _merchant_txn("T5", "ACC-0010-1", date(2026, 7, 12), 900.00, "Beta"),
                _merchant_txn("T6", "ACC-0010-1", date(2026, 7, 13), -50.00, "Beta"),
                # Gamma (second account): 40.00 (Saturday) + 60.005 (Monday) = 100.005 -> 100.01
                _merchant_txn("T7", "ACC-0010-2", date(2026, 8, 1), -40.00, "Gamma"),
                _merchant_txn("T8", "ACC-0010-2", date(2026, 8, 3), -60.005, "Gamma"),
                # Fourth merchant, not reported.
                _merchant_txn("T9", "ACC-0010-2", date(2026, 8, 5), -5.00, "Delta"),
                # After the window.
                _merchant_txn("T10", "ACC-0010-2", date(2026, 10, 3), -9999.00, "Delta"),
            )
        }
    )


def test_expected_answer_c_hand_made() -> None:
    answer = expected_answer_c(_scenario_c_dataset(), 10)
    assert answer.model_dump() == {
        "customer_id": "CUST-0010",
        "top_merchants": [
            {"merchant": "Beta", "total": 150.00},
            {"merchant": "Gamma", "total": 100.01},
            {"merchant": "Alpha", "total": 30.01},
        ],
        "weekend_debit_count": 3,
    }


def test_expected_answer_c_unknown_volume_raises() -> None:
    with pytest.raises(ValueError, match="CUST-0050"):
        expected_answer_c(_scenario_c_dataset(), 50)


@pytest.mark.parametrize("volume", [10, 100])
def test_real_dataset_scenario_c_has_no_tie_at_rank_three(dataset: Dataset, volume: int) -> None:
    accounts = set(account_ids_for(volume))
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for txn in dataset.transactions:
        in_window = dataset.window_start <= txn.date <= dataset.window_end
        if txn.account_id in accounts and txn.amount < 0 and in_window:
            totals[txn.merchant] += abs(Decimal(str(txn.amount)))
    ranked = sorted(totals.values(), reverse=True)
    assert len(ranked) >= 4
    assert ranked[2] != ranked[3]
    assert ranked[2].quantize(Decimal("0.01")) != ranked[3].quantize(Decimal("0.01"))
    answer = expected_answer_c(dataset, volume)
    assert [m.total for m in answer.top_merchants] == [
        float(v.quantize(Decimal("0.01"))) for v in ranked[:3]
    ]
    assert answer.weekend_debit_count > 0
