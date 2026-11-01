"""Unit tests for authentication."""

import pytest

from mcp_vs_code_mode.banking import (
    KNOWN_PRINCIPALS,
    UNAUTHORIZED_CUSTOMER_ID,
    AuthenticationError,
    SessionStore,
    authenticate_token,
    benchmark_principal,
    token_fingerprint,
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
    assert {"CUST-0010", "CUST-0050", "CUST-0100", "CUST-0200"} <= principal.allowed_customer_ids
    assert UNAUTHORIZED_CUSTOMER_ID not in principal.allowed_customer_ids


def test_authenticate_token_valid() -> None:
    token = "s3cret-token"
    principal = authenticate_token(token, {token_fingerprint(token): "rm-001"})
    assert principal == benchmark_principal()
    assert token_fingerprint(token) != token
    assert len(token_fingerprint(token)) == 64


@pytest.mark.parametrize("presented", ["wrong-token", ""])
def test_authenticate_token_rejects_wrong_or_empty(presented: str) -> None:
    trusted = {token_fingerprint("real-token"): "rm-001"}
    with pytest.raises(AuthenticationError) as info:
        authenticate_token(presented, trusted)
    assert str(info.value) == "Invalid session token"


def test_authenticate_token_rejects_empty_token_even_if_fingerprint_trusted() -> None:
    with pytest.raises(AuthenticationError):
        authenticate_token("", {token_fingerprint(""): "rm-001"})


def test_authenticate_token_unknown_principal() -> None:
    token = "tok-abc"
    with pytest.raises(AuthenticationError) as info:
        authenticate_token(token, {token_fingerprint(token): "rm-unknown"})
    assert token not in str(info.value)


def test_known_principals_immutable() -> None:
    assert set(KNOWN_PRINCIPALS) == {"rm-001"}
    with pytest.raises(TypeError):
        KNOWN_PRINCIPALS["x"] = benchmark_principal()  # type: ignore[index]
