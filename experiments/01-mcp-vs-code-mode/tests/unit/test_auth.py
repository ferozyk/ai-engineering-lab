"""Unit tests for authentication."""

import pytest

from mcp_vs_code_mode.banking import (
    UNAUTHORIZED_CUSTOMER_ID,
    AuthenticationError,
    SessionStore,
    benchmark_principal,
)

pytestmark = pytest.mark.unit


def test_issue_and_authenticate_roundtrip() -> None:
    store = SessionStore()
    principal = benchmark_principal()
    token = store.issue(principal)
    assert store.authenticate(token) == principal


def test_wrong_token_rejected_without_leaking_token() -> None:
    store = SessionStore()
    store.issue(benchmark_principal())
    with pytest.raises(AuthenticationError) as info:
        store.authenticate("not-a-real-token")
    assert "not-a-real-token" not in str(info.value)


def test_revoked_token_fails() -> None:
    store = SessionStore()
    token = store.issue(benchmark_principal())
    store.revoke(token)
    with pytest.raises(AuthenticationError) as info:
        store.authenticate(token)
    assert token not in str(info.value)


def test_benchmark_principal_scope() -> None:
    principal = benchmark_principal()
    assert principal.principal_id == "rm-001"
    assert {"CUST-0010", "CUST-0050", "CUST-0200"} <= principal.allowed_customer_ids
    assert UNAUTHORIZED_CUSTOMER_ID not in principal.allowed_customer_ids
