"""Integration tests: the real MCP server over a stdio subprocess."""

import json
import secrets
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.client.stdio import get_default_environment

from mcp_vs_code_mode.banking import (
    AuditLog,
    BankingService,
    benchmark_principal,
    generate_dataset,
    token_fingerprint,
)
from mcp_vs_code_mode.mcp_server import server_parameters
from mcp_vs_code_mode.tools import TOOL_SPECS, ToolExecutor, compact_json

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

_CASES: list[tuple[str, dict[str, Any]]] = [
    ("get_customer", {"customer_id": "CUST-0050"}),
    ("list_accounts", {"customer_id": "CUST-0050"}),
    ("get_balance", {"account_id": "ACC-0050-1"}),
    (
        "get_transactions",
        {"account_id": "ACC-0050-1", "start_date": "2026-07-03", "end_date": "2026-10-01"},
    ),
]


def _strip_titles(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_titles(v) for k, v in value.items() if k != "title"}
    return value


def _params(tmp_path: Path, token: str | None = None, trusted_for: str | None = None) -> Any:
    token = token or secrets.token_urlsafe(16)
    trusted = {token_fingerprint(trusted_for or token): "rm-001"}
    return server_parameters(token=token, trusted=trusted, audit_log=tmp_path / "audit.jsonl")


async def test_lists_tools_in_registry_order(tmp_path: Path) -> None:
    async with Client(_params(tmp_path)) as client:
        tools = (await client.list_tools()).tools
    assert [t.name for t in tools] == [s.name for s in TOOL_SPECS]
    for tool, spec in zip(tools, TOOL_SPECS, strict=True):
        assert tool.description == spec.description
        expected = _strip_titles(spec.input_model.model_json_schema()["properties"])
        assert _strip_titles(tool.input_schema["properties"]) == expected
        assert tool.input_schema.get("required") == spec.input_model.model_json_schema().get(
            "required"
        )


async def test_results_byte_identical_to_executor(tmp_path: Path) -> None:
    executor = ToolExecutor(
        BankingService(generate_dataset(), AuditLog()), benchmark_principal(), "test"
    )
    async with Client(_params(tmp_path)) as client:
        for name, args in _CASES:
            result = await client.call_tool(name, args, read_timeout_seconds=10.0)
            assert not result.is_error
            assert len(result.content) == 1
            assert result.content[0].text == compact_json(executor.execute(name, args))  # type: ignore[union-attr]


async def test_access_denied_and_unknown_tool(tmp_path: Path) -> None:
    async with Client(_params(tmp_path)) as client:
        denied = await client.call_tool("get_balance", {"account_id": "ACC-9999-1"})
        assert denied.is_error
        assert "access_denied" in denied.content[0].text  # type: ignore[union-attr]
        unknown = await client.call_tool("nope", {})
        assert unknown.is_error


async def test_audit_file_has_mcp_channel(tmp_path: Path) -> None:
    async with Client(_params(tmp_path)) as client:
        await client.call_tool("get_balance", {"account_id": "ACC-0050-1"})
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert lines
    assert {json.loads(line)["channel"] for line in lines} == {"mcp"}


async def test_invalid_token_fails_to_connect(tmp_path: Path) -> None:
    token = "super-secret-session-token"
    params = _params(tmp_path, token=token, trusted_for="a-different-token")
    with pytest.raises(BaseException) as info:
        async with Client(params) as client:
            await client.list_tools()
    assert token not in str(info.value)


def test_api_key_not_inherited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-should-not-leak")
    assert "OPENROUTER_API_KEY" not in get_default_environment()


def test_server_parameters_only_bank_vars(tmp_path: Path) -> None:
    params = _params(tmp_path)
    assert set(params.env or {}) == {
        "BANK_SESSION_TOKEN",
        "BANK_TRUSTED_SESSIONS",
        "BANK_AUDIT_LOG",
    }
