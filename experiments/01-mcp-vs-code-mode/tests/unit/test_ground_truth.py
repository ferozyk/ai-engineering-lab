"""Unit tests for ground-truth computation."""

from datetime import date

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
from mcp_vs_code_mode.scenarios import expected_answer_a, expected_answer_b

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
