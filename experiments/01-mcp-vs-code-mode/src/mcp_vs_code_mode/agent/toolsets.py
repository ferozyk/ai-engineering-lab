"""Toolsets: the two ways the agent loop reaches the banking tools.

``MCPToolset`` talks to an MCP server (one model-visible tool per banking tool).
``CodeModeToolset`` exposes a single ``run_python`` tool backed by a ``CodeSandbox``.
"""

import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol

import anyio.to_thread
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.server.mcpserver import MCPServer

from mcp_vs_code_mode.agent.records import Mode
from mcp_vs_code_mode.code_mode.sandbox import CodeSandbox
from mcp_vs_code_mode.code_mode.stubs import code_mode_prompt_section
from mcp_vs_code_mode.tools.registry import compact_json

MAX_RESULT_CHARS = 20_000
_MAX_ERROR_CHARS = 2_000
_INVALID_ARGUMENTS = compact_json(
    {"error": {"type": "invalid_arguments", "message": "Arguments must be a JSON object"}}
)


@dataclass(frozen=True)
class ToolOutcome:
    """Result of one tool call as seen by the agent loop."""

    content: str
    is_error: bool
    error_type: str | None
    duration_ms: float
    host_calls: int | None


class Toolset(Protocol):
    """What the agent loop needs from a mode."""

    mode: Mode

    def tool_definitions(self) -> list[dict[str, Any]]:
        """OpenAI ``tools`` parameter entries."""
        ...

    def prompt_section(self) -> str:
        """Mode-specific part of the system prompt."""
        ...

    async def call(self, name: str, arguments: str) -> ToolOutcome:
        """Execute one tool call; never raises for tool-level failures."""
        ...


def _parse_arguments(arguments: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(arguments)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _error_outcome(
    error_type: str, message: str, started: float, host_calls: int | None = None
) -> ToolOutcome:
    return ToolOutcome(
        content=compact_json({"error": {"type": error_type, "message": message}}),
        is_error=True,
        error_type=error_type,
        duration_ms=(time.perf_counter() - started) * 1000,
        host_calls=host_calls,
    )


def _error_type_from_text(text: str) -> str:
    start = text.find("{")
    if start >= 0:
        try:
            payload, _ = json.JSONDecoder().raw_decode(text, start)
        except ValueError:
            return "tool_error"
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and isinstance(error.get("type"), str):
                return str(error["type"])
    return "tool_error"


class MCPToolset:
    """Tools discovered from, and executed through, an MCP client session."""

    mode: Mode = "mcp"

    def __init__(
        self, client: Client, definitions: list[dict[str, Any]], call_timeout: float
    ) -> None:
        self._client = client
        self._definitions = definitions
        self._call_timeout = call_timeout

    @classmethod
    @asynccontextmanager
    async def open(
        cls, target: StdioServerParameters | MCPServer, *, call_timeout: float = 10.0
    ) -> AsyncIterator["MCPToolset"]:
        """Connect, list tools once and yield a toolset (stdio params or in-process server)."""
        async with Client(target) as client:
            listed = (await client.list_tools()).tools
            definitions = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in listed
            ]
            yield cls(client, definitions, call_timeout)

    def tool_definitions(self) -> list[dict[str, Any]]:
        """Tool definitions as discovered from the server."""
        return self._definitions

    def prompt_section(self) -> str:
        """Prompt text for MCP mode."""
        return (
            "Call the provided tools to fetch data. You may request several tool calls in one turn."
        )

    async def call(self, name: str, arguments: str) -> ToolOutcome:
        """Call a tool on the server."""
        started = time.perf_counter()
        parsed = _parse_arguments(arguments)
        if parsed is None:
            return ToolOutcome(
                content=_INVALID_ARGUMENTS,
                is_error=True,
                error_type="invalid_arguments",
                duration_ms=(time.perf_counter() - started) * 1000,
                host_calls=None,
            )
        try:
            result = await self._client.call_tool(
                name, parsed, read_timeout_seconds=self._call_timeout
            )
        except Exception as exc:  # transport failures and timeouts
            return _error_outcome("transport_error", type(exc).__name__, started)
        content = "".join(c.text for c in result.content if hasattr(c, "text"))
        error_type = _error_type_from_text(content) if result.is_error else None
        return ToolOutcome(
            content=content,
            is_error=result.is_error,
            error_type=error_type,
            duration_ms=(time.perf_counter() - started) * 1000,
            host_calls=None,
        )


_RUN_PYTHON: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_python",
        "description": (
            "Execute Python code in a sandbox. Returns the value of the final expression "
            "as JSON, plus any printed output."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source code to execute."}
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
}


class CodeModeToolset:
    """A single ``run_python`` tool executing in a ``CodeSandbox``."""

    mode: Mode = "code"

    def __init__(self, sandbox: CodeSandbox) -> None:
        self._sandbox = sandbox

    def tool_definitions(self) -> list[dict[str, Any]]:
        """The single ``run_python`` tool."""
        return [json.loads(json.dumps(_RUN_PYTHON))]

    def prompt_section(self) -> str:
        """Stubs and sandbox rules."""
        return code_mode_prompt_section()

    async def call(self, name: str, arguments: str) -> ToolOutcome:
        """Run model-written code in the sandbox."""
        started = time.perf_counter()
        if name != "run_python":
            return _error_outcome("unknown_tool", f"Unknown tool: {name}", started)
        parsed = _parse_arguments(arguments)
        code = parsed.get("code") if parsed is not None else None
        if not isinstance(code, str):
            return _error_outcome(
                "invalid_arguments", "Arguments must be a JSON object with a string 'code'", started
            )
        result = await anyio.to_thread.run_sync(self._sandbox.run, code)
        if result.error_type is not None:
            message = (result.error_message or "")[:_MAX_ERROR_CHARS]
            return _error_outcome(result.error_type, message, started, result.host_calls)
        payload: dict[str, Any] = {"result": result.value}
        if result.stdout:
            payload["stdout"] = result.stdout
        try:
            content = compact_json(payload)
        except (TypeError, ValueError):
            return _error_outcome(
                "unserializable_result",
                "The final expression is not JSON-serialisable; return plain dicts, lists, "
                "strings and numbers.",
                started,
                result.host_calls,
            )
        if len(content) > MAX_RESULT_CHARS:
            return _error_outcome(
                "output_too_large",
                f"Result is {len(content)} characters; the limit is {MAX_RESULT_CHARS}. "
                "Aggregate inside the code and return only what the answer needs.",
                started,
                result.host_calls,
            )
        return ToolOutcome(
            content=content,
            is_error=False,
            error_type=None,
            duration_ms=(time.perf_counter() - started) * 1000,
            host_calls=result.host_calls,
        )
