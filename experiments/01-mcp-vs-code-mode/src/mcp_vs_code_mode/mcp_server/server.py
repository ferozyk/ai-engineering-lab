"""MCP server exposing the benchmark tools over stdio (MCPServer, mcp 2.x; formerly FastMCP)."""

import json
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from mcp.client.stdio import StdioServerParameters
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError as MCPToolError
from pydantic import JsonValue

from mcp_vs_code_mode.banking import (
    AuditLog,
    AuthenticationError,
    BankingService,
    authenticate_token,
    generate_dataset,
)
from mcp_vs_code_mode.tools import (
    TOOL_SPECS,
    AccountIdArg,
    CustomerIdArg,
    EndDateArg,
    StartDateArg,
    ToolError,
    ToolExecutor,
    compact_json,
)

TOKEN_ENV = "BANK_SESSION_TOKEN"
TRUSTED_ENV = "BANK_TRUSTED_SESSIONS"
AUDIT_ENV = "BANK_AUDIT_LOG"


def _run(executor: ToolExecutor, name: str, arguments: dict[str, object]) -> str:
    try:
        return compact_json(executor.execute(name, arguments))
    except ToolError as exc:
        raise MCPToolError(compact_json(cast(JsonValue, exc.to_payload()))) from exc


def build_server(executor: ToolExecutor) -> MCPServer:
    """Register one wrapper per ``ToolSpec``, in registry order."""
    server = MCPServer(name="synthetic-bank", log_level="WARNING")

    def get_customer(customer_id: CustomerIdArg) -> str:
        return _run(executor, "get_customer", {"customer_id": customer_id})

    def list_accounts(customer_id: CustomerIdArg) -> str:
        return _run(executor, "list_accounts", {"customer_id": customer_id})

    def get_balance(account_id: AccountIdArg) -> str:
        return _run(executor, "get_balance", {"account_id": account_id})

    def get_transactions(
        account_id: AccountIdArg, start_date: StartDateArg, end_date: EndDateArg
    ) -> str:
        return _run(
            executor,
            "get_transactions",
            {"account_id": account_id, "start_date": start_date, "end_date": end_date},
        )

    wrappers: dict[str, Callable[..., str]] = {
        "get_customer": get_customer,
        "list_accounts": list_accounts,
        "get_balance": get_balance,
        "get_transactions": get_transactions,
    }
    for spec in TOOL_SPECS:
        server.add_tool(
            wrappers[spec.name],
            name=spec.name,
            description=spec.description,
            structured_output=False,
        )
    return server


def server_parameters(
    *, token: str, trusted: Mapping[str, str], audit_log: Path | None
) -> StdioServerParameters:
    """Parameters to spawn this server as a stdio subprocess with only the BANK_* variables."""
    env = {TOKEN_ENV: token, TRUSTED_ENV: json.dumps(dict(trusted))}
    if audit_log is not None:
        env[AUDIT_ENV] = str(audit_log)
    return StdioServerParameters(
        command=sys.executable, args=["-m", "mcp_vs_code_mode.mcp_server"], env=env
    )


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    """Authenticate from the environment, then serve over stdio."""
    token = os.environ.get(TOKEN_ENV, "")
    raw_trusted = os.environ.get(TRUSTED_ENV, "")
    if not token or not raw_trusted:
        _fail(f"{TOKEN_ENV} and {TRUSTED_ENV} are required")
    try:
        parsed = json.loads(raw_trusted)
    except ValueError:
        _fail(f"{TRUSTED_ENV} must be a JSON object")
    if not isinstance(parsed, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
    ):
        _fail(f"{TRUSTED_ENV} must be a JSON object of strings")
    try:
        principal = authenticate_token(token, parsed)
    except AuthenticationError:
        _fail("Authentication failed: invalid session token")
    audit_path = os.environ.get(AUDIT_ENV)
    audit = AuditLog(Path(audit_path) if audit_path else None)
    service = BankingService(generate_dataset(), audit)
    executor = ToolExecutor(service, principal, "mcp")
    build_server(executor).run("stdio")
