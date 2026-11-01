"""Shared agent loop, toolsets and model clients."""

from mcp_vs_code_mode.agent.llm import ChatModel, LLMInfraError, OpenAIChatModel
from mcp_vs_code_mode.agent.loop import MAX_TURNS, run_task
from mcp_vs_code_mode.agent.prompts import build_system_prompt
from mcp_vs_code_mode.agent.records import (
    LLMCallRecord,
    LLMResponse,
    LLMToolCall,
    Mode,
    TaskOutcome,
    TaskResult,
    ToolCallRecord,
    Usage,
)
from mcp_vs_code_mode.agent.toolsets import CodeModeToolset, MCPToolset, ToolOutcome, Toolset

__all__ = [
    "MAX_TURNS",
    "ChatModel",
    "CodeModeToolset",
    "LLMCallRecord",
    "LLMInfraError",
    "LLMResponse",
    "LLMToolCall",
    "MCPToolset",
    "Mode",
    "OpenAIChatModel",
    "TaskOutcome",
    "TaskResult",
    "ToolCallRecord",
    "ToolOutcome",
    "Toolset",
    "Usage",
    "build_system_prompt",
    "run_task",
]
