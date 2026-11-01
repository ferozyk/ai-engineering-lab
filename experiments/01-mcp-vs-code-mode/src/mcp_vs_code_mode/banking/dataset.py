"""Deterministic synthetic dataset generator.

All randomness comes from a single local ``random.Random(seed)``; the global
``random`` module is never used.
"""

import random
from datetime import date, timedelta

from mcp_vs_code_mode.banking.models import (
    SPEND_CATEGORIES,
    Account,
    Balance,
    Customer,
    Dataset,
    SpendCategory,
    Transaction,
    TransactionCategory,
)

DATASET_VERSION = "1.1.0"
DEFAULT_SEED = 20261001
REFERENCE_DATE = date(2026, 10, 1)
WINDOW_START = date(2026, 7, 3)  # 90 days inclusive ending on REFERENCE_DATE
WINDOW_END = REFERENCE_DATE
VOLUMES: tuple[int, ...] = (10, 50, 100, 200)
ACCOUNT_TYPES = ("current", "savings", "credit_card", "joint_current")
UNAUTHORIZED_CUSTOMER_ID = "CUST-9999"

_UNAUTHORIZED_VOLUME = 9999
# Generation order matters: all customers draw from one random stream. Volumes 10, 50 and 200
# (and the unauthorized customer) are generated first, exactly as in dataset 1.0.0, so their
# data stays byte-identical to the canary runs. Volume 100 is generated last, appended after.
_PRIMARY_VOLUMES: tuple[int, ...] = (10, 50, 200)
_APPENDED_VOLUMES: tuple[int, ...] = (100,)
_UNAUTHORIZED_TXN_COUNT = 5
_SEGMENTS = ("retail", "premier", "business")
_MERCHANTS: dict[TransactionCategory, tuple[str, ...]] = {
    "groceries": ("Corner Grocer", "Fresh Market", "Daily Pantry", "Green Basket"),
    "dining": ("Local Diner", "Noodle House", "Cafe Central", "Pizza Corner"),
    "transport": ("City Transit", "Metro Fuel", "Quick Cab", "Park & Ride"),
    "utilities": ("Power Utility", "Water Board", "Net Provider", "Gas Supply"),
    "shopping": ("Home Goods Store", "Apparel Outlet", "Gadget Shop", "Book Corner"),
    "entertainment": ("Cinema Hall", "Streaming Service", "Game Arcade", "Concert Hall"),
    "income": ("Employer Payroll", "Interest Credit", "Transfer In", "Refund"),
}


def customer_id_for(volume: int) -> str:
    """Return the customer id for a volume level."""
    return f"CUST-{volume:04d}"


def account_ids_for(volume: int) -> tuple[str, ...]:
    """Return the four account ids for a volume level."""
    return tuple(f"ACC-{volume:04d}-{i}" for i in range(1, len(ACCOUNT_TYPES) + 1))


def _generate_transactions(
    rng: random.Random, volume: int, index: int, account_id: str, count: int
) -> list[Transaction]:
    """Generate ``count`` transactions for one account, sorted and numbered."""
    large = max(1, count // 25)
    drafts: list[tuple[date, float, TransactionCategory]] = []
    for position in range(count):
        category: TransactionCategory
        if position < large:
            amount = -round(rng.uniform(1000.5, 4000.0), 2)
            category = rng.choice(SPEND_CATEGORIES)
        elif rng.random() < 0.15:
            amount = round(rng.uniform(50.0, 3000.0), 2)
            category = "income"
        else:
            amount = -round(rng.uniform(3.0, 400.0), 2)
            category = rng.choice(SPEND_CATEGORIES)
        txn_date = WINDOW_START + timedelta(days=rng.randint(0, 89))
        drafts.append((txn_date, amount, category))

    transactions: list[Transaction] = []
    ordered = sorted(enumerate(drafts), key=lambda item: (item[1][0], item[0]))
    for k, (_, (txn_date, amount, category)) in enumerate(ordered, start=1):
        merchant = rng.choice(_MERCHANTS[category])
        transactions.append(
            Transaction(
                transaction_id=f"TXN-{volume:04d}-{index}-{k:04d}",
                account_id=account_id,
                date=txn_date,
                amount=amount,
                currency="USD",
                merchant=merchant,
                category=category,
                description=f"{merchant} ref {rng.randint(100000, 999999)}",
            )
        )
    return transactions


def generate_dataset(seed: int = DEFAULT_SEED) -> Dataset:
    """Generate the full synthetic dataset deterministically from ``seed``."""
    rng = random.Random(seed)
    customers: list[Customer] = []
    accounts: list[Account] = []
    balances: list[Balance] = []
    transactions: list[Transaction] = []

    plan: list[tuple[int, int, int]] = [
        (volume, len(ACCOUNT_TYPES), volume) for volume in _PRIMARY_VOLUMES
    ]
    plan.append((_UNAUTHORIZED_VOLUME, 1, _UNAUTHORIZED_TXN_COUNT))
    plan.extend((volume, len(ACCOUNT_TYPES), volume) for volume in _APPENDED_VOLUMES)

    for volume, account_count, txn_count in plan:
        customer_id = customer_id_for(volume)
        segment = rng.choice(_SEGMENTS)
        customers.append(
            Customer(
                customer_id=customer_id,
                name=f"Synthetic Customer {volume:04d}",
                segment=segment,  # type: ignore[arg-type]
            )
        )
        for i in range(1, account_count + 1):
            account_id = f"ACC-{volume:04d}-{i}"
            accounts.append(
                Account(
                    account_id=account_id,
                    customer_id=customer_id,
                    account_type=ACCOUNT_TYPES[i - 1],  # type: ignore[arg-type]
                    currency="USD",
                )
            )
            transactions.extend(_generate_transactions(rng, volume, i, account_id, txn_count))
            available = round(rng.uniform(500.0, 25000.0), 2)
            ledger = round(available + rng.uniform(0.0, 300.0), 2)
            balances.append(
                Balance(
                    account_id=account_id,
                    available_balance=available,
                    ledger_balance=ledger,
                    currency="USD",
                    as_of=REFERENCE_DATE,
                )
            )

    return Dataset(
        version=DATASET_VERSION,
        reference_date=REFERENCE_DATE,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        customers=tuple(customers),
        accounts=tuple(accounts),
        balances=tuple(balances),
        transactions=tuple(transactions),
    )


__all__ = [
    "ACCOUNT_TYPES",
    "DATASET_VERSION",
    "DEFAULT_SEED",
    "REFERENCE_DATE",
    "UNAUTHORIZED_CUSTOMER_ID",
    "VOLUMES",
    "WINDOW_END",
    "WINDOW_START",
    "SpendCategory",
    "account_ids_for",
    "customer_id_for",
    "generate_dataset",
]
