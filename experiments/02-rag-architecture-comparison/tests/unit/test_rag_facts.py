"""Unit tests for key-fact matching."""

import pytest

from rag_experiment.evaluation.facts import all_present, fact_present

pytestmark = pytest.mark.unit

HEADERS = frozenset({"X-Api-Key", "Authorization", "Retry-After"})


def test_method_path_masks_parameter_names() -> None:
    text = "[x] GET /v1/accounts/{accountId}/transactions · parameters"
    assert fact_present("GET /v1/accounts/{id}/transactions", text, HEADERS)
    assert fact_present("GET /v1/accounts/{accountId}/transactions", text, HEADERS)


def test_method_must_match_case_sensitively() -> None:
    text = "GET /v1/accounts"
    assert not fact_present("POST /v1/accounts", text, HEADERS)
    assert not fact_present("get /v1/accounts", text, HEADERS)


def test_path_does_not_match_inside_a_longer_path() -> None:
    text = "GET /v1/accounts/{accountId}/balances"
    assert not fact_present("/v1/accounts/{accountId}", text, HEADERS)
    assert fact_present("/v1/accounts/{accountId}/balances", text, HEADERS)
    assert fact_present("/v1/accounts/{accountId}", "see /v1/accounts/{accountId}.", HEADERS)


def test_whitespace_is_collapsed_for_paths() -> None:
    assert fact_present("GET /v1/x", "GET   /v1/x\n", HEADERS)


def test_header_names_are_case_insensitive() -> None:
    assert fact_present("X-Api-Key", "send the x-api-key header", HEADERS)
    assert fact_present("Authorization", "AUTHORIZATION: Bearer", HEADERS)
    assert not fact_present("X-Api-Key", "x-api-keys", HEADERS)


def test_codes_match_whole_tokens() -> None:
    assert fact_present("AUTH-001", "the code `AUTH-001`.", HEADERS)
    assert not fact_present("AUTH-001", "AUTH-0010", HEADERS)
    assert not fact_present("AUTH-001", "XAUTH-001", HEADERS)


def test_scopes_match_exactly() -> None:
    assert fact_present("accounts:read", "scopes: accounts:read, x", HEADERS)
    assert not fact_present("accounts:read", "accounts:readwrite", HEADERS)
    assert not fact_present("accounts:read", "Accounts:Read", HEADERS)


def test_plain_facts_ignore_case_and_allow_a_trailing_full_stop() -> None:
    assert fact_present("500", "limit (integer, default 100, min 1, max 500.", HEADERS)
    assert fact_present("deprecated", "Deprecated: yes", HEADERS)
    assert not fact_present("500", "5000", HEADERS)
    assert not fact_present("500", "max 500.5", HEADERS)


def test_identifiers_are_case_sensitive() -> None:
    assert not fact_present("fromDate", "fromdate", HEADERS)
    assert fact_present("fromDate", "- fromDate (string, required)", HEADERS)


def test_media_types_with_punctuation() -> None:
    assert fact_present(
        "application/problem+json", "Content application/problem+json: Problem", HEADERS
    )


def test_all_present_returns_missing_facts() -> None:
    assert all_present(["a", "zzz"], "a b c", HEADERS) == ["zzz"]
    assert all_present([], "x", HEADERS) == []
