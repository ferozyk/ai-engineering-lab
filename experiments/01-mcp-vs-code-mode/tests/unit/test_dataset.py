"""Unit tests for the synthetic dataset generator."""

import hashlib
import json
from collections import Counter
from decimal import Decimal

import pytest

from mcp_vs_code_mode.banking import (
    UNAUTHORIZED_CUSTOMER_ID,
    VOLUMES,
    WINDOW_END,
    WINDOW_START,
    Dataset,
    account_ids_for,
    customer_id_for,
    generate_dataset,
)

pytestmark = pytest.mark.unit

# Changing the generator invalidates comparability of benchmark results;
# update deliberately and bump DATASET_VERSION. (1.1.0: volume 100 appended; the volumes
# present in 1.0.0 are guarded separately by test_existing_volumes_unchanged.)
GOLDEN_CHECKSUM = "ad579f7026dd30417869520cc9b159715625e6eea05deabaf6e8faf9dab96d96"


def test_generation_is_deterministic(dataset: Dataset) -> None:
    assert generate_dataset().checksum() == dataset.checksum()


def test_different_seed_differs(dataset: Dataset) -> None:
    assert generate_dataset(seed=1).checksum() != dataset.checksum()


def test_golden_checksum(dataset: Dataset) -> None:
    assert dataset.checksum() == GOLDEN_CHECKSUM


@pytest.mark.parametrize("volume", VOLUMES)
def test_volume_invariants(dataset: Dataset, volume: int) -> None:
    customer_id = customer_id_for(volume)
    assert [a.account_id for a in dataset.accounts if a.customer_id == customer_id] == list(
        account_ids_for(volume)
    )
    for account_id in account_ids_for(volume):
        txns = [t for t in dataset.transactions if t.account_id == account_id]
        assert len(txns) == volume
        assert all(WINDOW_START <= t.date <= WINDOW_END for t in txns)
        large = [t for t in txns if t.amount < -1000]
        assert len(large) == max(1, volume // 25)
        assert all(abs(t.amount) < 1000 for t in txns if t not in large and t.amount < 0)
        assert [t.transaction_id for t in txns] == sorted(t.transaction_id for t in txns)


def test_transaction_ids_unique(dataset: Dataset) -> None:
    counts = Counter(t.transaction_id for t in dataset.transactions)
    assert max(counts.values()) == 1


def test_amounts_have_at_most_two_decimals(dataset: Dataset) -> None:
    values = [t.amount for t in dataset.transactions]
    for b in dataset.balances:
        values.extend([b.available_balance, b.ledger_balance])
    for value in values:
        exponent = Decimal(str(value)).as_tuple().exponent
        assert isinstance(exponent, int)
        assert exponent >= -2


def test_unauthorized_customer(dataset: Dataset) -> None:
    assert any(c.customer_id == UNAUTHORIZED_CUSTOMER_ID for c in dataset.customers)
    assert [
        a.account_id for a in dataset.accounts if a.customer_id == UNAUTHORIZED_CUSTOMER_ID
    ] == ["ACC-9999-1"]
    assert len([t for t in dataset.transactions if t.account_id == "ACC-9999-1"]) == 5


def _fingerprint(ds: Dataset, customer_ids: set[str]) -> str:
    accs = [a for a in ds.accounts if a.customer_id in customer_ids]
    ids = {a.account_id for a in accs}
    payload = {
        "customers": [
            c.model_dump(mode="json") for c in ds.customers if c.customer_id in customer_ids
        ],
        "accounts": [a.model_dump(mode="json") for a in accs],
        "balances": [b.model_dump(mode="json") for b in ds.balances if b.account_id in ids],
        "transactions": [t.model_dump(mode="json") for t in ds.transactions if t.account_id in ids],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_existing_volumes_unchanged(dataset: Dataset) -> None:
    """Data of dataset 1.0.0 (canary runs) must stay byte-identical when volumes are appended."""
    assert (
        _fingerprint(dataset, {"CUST-0010", "CUST-0050", "CUST-0200"})
        == "bfe1f5b4a00634e45f873c3b15bf0b8c4792e125ba1f2592a14c4aacde041dea"
    )
    assert (
        _fingerprint(dataset, {UNAUTHORIZED_CUSTOMER_ID})
        == "dbbc13e015c52c4520f283e325f2a68cab19d682000de5a34a00c19132b96911"
    )
