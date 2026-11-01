"""Tool registry and executor shared by MCP mode and Code Mode."""

from mcp_vs_code_mode.tools.errors import (
    ToolAccessError,
    ToolError,
    ToolInputError,
    ToolNotFoundError,
    UnknownToolError,
)
from mcp_vs_code_mode.tools.registry import (
    TOOL_SPECS,
    AccountIdArg,
    CustomerIdArg,
    EndDateArg,
    GetBalanceInput,
    GetCustomerInput,
    GetTransactionsInput,
    ListAccountsInput,
    StartDateArg,
    ToolExecutor,
    ToolSpec,
    compact_json,
)

__all__ = [
    "TOOL_SPECS",
    "AccountIdArg",
    "CustomerIdArg",
    "EndDateArg",
    "GetBalanceInput",
    "GetCustomerInput",
    "GetTransactionsInput",
    "ListAccountsInput",
    "StartDateArg",
    "ToolAccessError",
    "ToolError",
    "ToolExecutor",
    "ToolInputError",
    "ToolNotFoundError",
    "ToolSpec",
    "UnknownToolError",
    "compact_json",
]
