"""Unit tests for system prompt construction."""

import pytest

from mcp_vs_code_mode.agent import CodeModeToolset, MCPToolset, build_system_prompt
from mcp_vs_code_mode.agent.toolsets import Toolset
from mcp_vs_code_mode.code_mode.sandbox import CodeSandbox
from mcp_vs_code_mode.tools import ToolExecutor

pytestmark = pytest.mark.unit

_HEADER = "You are a banking data assistant acting for relationship manager rm-001."


def test_mcp_prompt(executor: ToolExecutor) -> None:
    del executor
    toolset: Toolset = MCPToolset.__new__(MCPToolset)
    prompt = build_system_prompt(toolset)
    assert prompt.startswith(_HEADER)
    assert "reply with only the JSON object requested and no other text." in prompt
    assert prompt.endswith(toolset.prompt_section())


def test_code_prompt(executor: ToolExecutor) -> None:
    toolset = CodeModeToolset(CodeSandbox(executor))
    prompt = build_system_prompt(toolset)
    assert prompt.startswith(_HEADER)
    assert prompt.endswith(toolset.prompt_section())
    assert "def get_transactions(" in prompt
