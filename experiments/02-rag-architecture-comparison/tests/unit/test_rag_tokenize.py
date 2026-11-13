"""Unit tests for the identifier-aware tokeniser."""

import pytest

from rag_experiment.retrieval.tokenize import tokenize

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("X-Api-Key", ["api", "key", "x-api-key"]),
        ("pageSize", ["page", "pagesize", "size"]),
        ("accounts:read", ["accounts", "accounts:read", "read"]),
        ("STM-404", ["404", "stm", "stm-404"]),
        ("{accountId}", ["account", "accountid", "id"]),
        ("What is the maximum value?", ["maximum", "value"]),
    ],
)
def test_identifier_examples(text: str, expected: list[str]) -> None:
    assert sorted(tokenize(text)) == expected


def test_path_with_template_variable() -> None:
    tokens = tokenize("GET /v1/accounts/{accountId}/balances")
    for wanted in (
        "get",
        "v1/accounts",
        "v1",
        "accounts",
        "accountid",
        "account",
        "id",
        "balances",
    ):
        assert wanted in tokens


def test_duplicates_are_kept_and_short_tokens_dropped() -> None:
    assert tokenize("key key a x") == ["key", "key"]
    assert tokenize("") == []
    assert tokenize("the and of") == []


def test_snake_case_and_dots() -> None:
    tokens = tokenize("page_size v2.1")
    assert {"page_size", "page", "size", "v2.1", "v2"} <= set(tokens)


def test_is_deterministic() -> None:
    text = "Authorization: Bearer token, scope accounts:read"
    assert tokenize(text) == tokenize(text)
