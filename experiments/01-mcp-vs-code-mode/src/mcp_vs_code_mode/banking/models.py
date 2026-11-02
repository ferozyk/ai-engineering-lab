"""Immutable Pydantic models for the synthetic banking domain."""

import hashlib
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

SpendCategory = Literal[
    "groceries", "dining", "transport", "utilities", "shopping", "entertainment"
]
TransactionCategory = SpendCategory | Literal["income"]

SPEND_CATEGORIES: tuple[SpendCategory, ...] = (
    "groceries",
    "dining",
    "transport",
    "utilities",
    "shopping",
    "entertainment",
)


class _Frozen(BaseModel):
    """Base for immutable models that reject unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Customer(_Frozen):
    """A bank customer."""

    customer_id: str
    name: str
    segment: Literal["retail", "premier", "business"]


class Account(_Frozen):
    """An account owned by a customer."""

    account_id: str
    customer_id: str
    account_type: Literal["current", "savings", "credit_card", "joint_current"]
    currency: Literal["USD"]


class Balance(_Frozen):
    """Point-in-time balance of an account."""

    account_id: str
    available_balance: float
    ledger_balance: float
    currency: Literal["USD"]
    as_of: date


class Transaction(_Frozen):
    """A single posted transaction. Negative amount = debit."""

    transaction_id: str
    account_id: str
    date: date
    amount: float
    currency: Literal["USD"]
    merchant: str
    category: TransactionCategory
    description: str


class Dataset(_Frozen):
    """A complete synthetic dataset."""

    version: str
    reference_date: date
    window_start: date
    window_end: date
    customers: tuple[Customer, ...]
    accounts: tuple[Account, ...]
    balances: tuple[Balance, ...]
    transactions: tuple[Transaction, ...]

    def checksum(self) -> str:
        """Return the sha256 hex digest of the canonical JSON serialisation."""
        return hashlib.sha256(self.model_dump_json().encode("utf-8")).hexdigest()


class SpendingSummary(_Frozen):
    """Server-side aggregate of an account's debits over a date window."""

    account_id: str
    start_date: date
    end_date: date
    spend_by_category: dict[str, float]
    large_debit_ids: list[str]
    debit_count: int
