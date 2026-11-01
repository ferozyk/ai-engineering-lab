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
    GetBalanceInput,
    GetCustomerInput,
    GetTransactionsInput,
    ListAccountsInput,
    ToolExecutor,
    ToolSpec,
)

__all__ = [
    "TOOL_SPECS",
    "GetBalanceInput",
    "GetCustomerInput",
    "GetTransactionsInput",
    "ListAccountsInput",
    "ToolAccessError",
    "ToolError",
    "ToolExecutor",
    "ToolInputError",
    "ToolNotFoundError",
    "ToolSpec",
    "UnknownToolError",
]
