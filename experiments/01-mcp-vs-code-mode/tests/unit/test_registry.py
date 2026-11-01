"""Unit tests for the tool registry and executor."""

import json
from typing import Any

import pytest

from mcp_vs_code_mode.tools import (
    TOOL_SPECS,
    ToolAccessError,
    ToolExecutor,
    ToolInputError,
    ToolNotFoundError,
    UnknownToolError,
)

pytestmark = pytest.mark.unit

TXN_ARGS = {"account_id": "ACC-0050-1", "start_date": "2026-07-03", "end_date": "2026-10-01"}


def test_tool_names_and_order() -> None:
    assert [s.name for s in TOOL_SPECS] == [
        "get_customer",
        "list_accounts",
        "get_balance",
        "get_transactions",
    ]


def test_descriptions_verbatim() -> None:
    assert [s.description for s in TOOL_SPECS] == [
        "Get a customer's profile. Returns {customer_id, name, segment}.",
        "List a customer's accounts. Returns a list of "
        "{account_id, customer_id, account_type, currency}.",
        "Get an account's balance. Returns "
        "{account_id, available_balance, ledger_balance, currency, as_of}.",
        "List an account's transactions between two dates (inclusive). Returns a list of "
        "{transaction_id, account_id, date, amount, currency, merchant, category, description}. "
        "Negative amount = debit.",
    ]


def test_fields_have_descriptions() -> None:
    for spec in TOOL_SPECS:
        for field in spec.input_model.model_fields.values():
            assert field.description


def test_unknown_tool(executor: ToolExecutor) -> None:
    with pytest.raises(UnknownToolError) as info:
        executor.execute("delete_everything", {})
    payload = info.value.to_payload()
    assert payload == {
        "error": {"type": "unknown_tool", "message": "Unknown tool: delete_everything"}
    }


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("get_customer", {"customer_id": "bad"}),
        ("get_customer", {"customer_id": "CUST-0050", "extra": "x"}),
        ("get_balance", {}),
        ("get_transactions", {**TXN_ARGS, "start_date": "2026-10-02"}),
        ("get_transactions", {**TXN_ARGS, "start_date": "not-a-date"}),
        ("get_balance", {"account_id": "ACC-50-1"}),
    ],
)
def test_invalid_inputs(executor: ToolExecutor, name: str, arguments: dict[str, Any]) -> None:
    with pytest.raises(ToolInputError) as info:
        executor.execute(name, arguments)
    assert info.value.to_payload()["error"]["type"] == "invalid_input"


def test_denied_maps_to_access_error(executor: ToolExecutor) -> None:
    with pytest.raises(ToolAccessError) as info:
        executor.execute("get_balance", {"account_id": "ACC-9999-1"})
    assert str(info.value) == "Access denied"


def test_not_found_maps(executor: ToolExecutor) -> None:
    with pytest.raises(ToolNotFoundError):
        executor.execute("get_customer", {"customer_id": "CUST-0001"})


def test_results_are_json_with_iso_dates(executor: ToolExecutor) -> None:
    customer = executor.execute("get_customer", {"customer_id": "CUST-0050"})
    accounts = executor.execute("list_accounts", {"customer_id": "CUST-0050"})
    balance = executor.execute("get_balance", {"account_id": "ACC-0050-1"})
    txns = executor.execute("get_transactions", TXN_ARGS)
    for result in (customer, accounts, balance, txns):
        json.dumps(result)
    assert isinstance(balance, dict)
    assert balance["as_of"] == "2026-10-01"
    assert isinstance(txns, list)
    assert len(txns) == 50
    first = txns[0]
    assert isinstance(first, dict)
    assert isinstance(first["date"], str)
    assert len(first["date"]) == 10
