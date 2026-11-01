"""Unit tests for the banking service and audit log."""

import json
from datetime import date
from pathlib import Path

import pytest

from mcp_vs_code_mode.banking import (
    AuditLog,
    AuthorizationError,
    BankingService,
    Dataset,
    InvalidRequestError,
    NotFoundError,
    Principal,
    SessionStore,
)

pytestmark = pytest.mark.unit


def test_allowed_calls(service: BankingService, principal: Principal) -> None:
    customer = service.get_customer(principal, "CUST-0050", channel="test")
    assert customer.customer_id == "CUST-0050"
    accounts = service.list_accounts(principal, "CUST-0050", channel="test")
    assert [a.account_id for a in accounts] == [f"ACC-0050-{i}" for i in range(1, 5)]
    balance = service.get_balance(principal, "ACC-0050-1", channel="test")
    assert balance.account_id == "ACC-0050-1"


def test_get_transactions_filters_and_orders(
    service: BankingService, principal: Principal, dataset: Dataset
) -> None:
    start, end = date(2026, 8, 1), date(2026, 8, 31)
    txns = service.get_transactions(principal, "ACC-0050-1", start, end, channel="test")
    expected = [
        t for t in dataset.transactions if t.account_id == "ACC-0050-1" and start <= t.date <= end
    ]
    assert 0 < len(txns) < 50
    assert {t.transaction_id for t in txns} == {t.transaction_id for t in expected}
    assert [(t.date, t.transaction_id) for t in txns] == sorted(
        (t.date, t.transaction_id) for t in txns
    )


def test_denied(service: BankingService, principal: Principal) -> None:
    with pytest.raises(AuthorizationError):
        service.get_customer(principal, "CUST-9999", channel="test")
    with pytest.raises(AuthorizationError):
        service.get_balance(principal, "ACC-9999-1", channel="test")
    with pytest.raises(AuthorizationError):
        service.get_transactions(
            principal, "ACC-9999-1", date(2026, 7, 3), date(2026, 10, 1), channel="test"
        )


def test_not_found(service: BankingService, principal: Principal) -> None:
    with pytest.raises(NotFoundError):
        service.get_customer(principal, "CUST-0001", channel="test")
    with pytest.raises(NotFoundError):
        service.get_balance(principal, "ACC-0001-1", channel="test")


def test_start_after_end(service: BankingService, principal: Principal) -> None:
    with pytest.raises(InvalidRequestError):
        service.get_transactions(
            principal, "ACC-0050-1", date(2026, 9, 1), date(2026, 8, 1), channel="test"
        )


def test_audit_one_record_per_call(dataset: Dataset, principal: Principal, tmp_path: Path) -> None:
    path = tmp_path / "logs" / "audit.jsonl"
    log = AuditLog(path)
    service = BankingService(dataset, log)
    token = SessionStore().issue(principal)

    service.get_customer(principal, "CUST-0050", channel="mcp")
    with pytest.raises(AuthorizationError):
        service.get_customer(principal, "CUST-9999", channel="code_mode")
    with pytest.raises(NotFoundError):
        service.get_balance(principal, "ACC-0001-1", channel="test")
    with pytest.raises(InvalidRequestError):
        service.get_transactions(
            principal, "ACC-0050-1", date(2026, 9, 1), date(2026, 8, 1), channel="test"
        )

    assert [(r.outcome, r.channel) for r in log.records] == [
        ("allowed", "mcp"),
        ("denied", "code_mode"),
        ("not_found", "test"),
        ("invalid", "test"),
    ]
    assert all(r.timestamp.tzinfo is not None and r.duration_ms >= 0 for r in log.records)
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert len(lines) == 4
    assert [json.loads(line)["outcome"] for line in lines] == [r.outcome for r in log.records]
    assert token not in content


def test_unexpected_error_audited_as_error(
    service: BankingService,
    principal: Principal,
    audit_log: AuditLog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "_balances", {})
    with pytest.raises(KeyError):
        service.get_balance(principal, "ACC-0050-1", channel="test")
    assert [r.outcome for r in audit_log.records] == ["error"]
