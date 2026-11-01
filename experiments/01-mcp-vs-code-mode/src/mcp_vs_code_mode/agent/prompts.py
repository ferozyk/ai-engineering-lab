"""System prompt construction (identical header for both modes)."""

from mcp_vs_code_mode.agent.toolsets import Toolset

_HEADER = """\
You are a banking data assistant acting for relationship manager rm-001.
Use the available tools to obtain every value you report; never guess or invent data.
When you have the answer, reply with only the JSON object requested and no other text."""


def build_system_prompt(toolset: Toolset) -> str:
    """Common header followed by the toolset's section."""
    return f"{_HEADER}\n\n{toolset.prompt_section()}"
