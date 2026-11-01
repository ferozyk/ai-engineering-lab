"""Unit tests for CodeModeToolset result shaping."""

import json
from collections.abc import Iterator

import pytest

from mcp_vs_code_mode.agent import CodeModeToolset
from mcp_vs_code_mode.agent.toolsets import MAX_RESULT_CHARS
from mcp_vs_code_mode.banking import AuditLog, BankingService, benchmark_principal, generate_dataset
from mcp_vs_code_mode.code_mode import CodeSandbox
from mcp_vs_code_mode.tools import ToolExecutor

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


@pytest.fixture(scope="module")
def toolset() -> Iterator[CodeModeToolset]:
    service = BankingService(generate_dataset(), AuditLog())
    executor = ToolExecutor(service, benchmark_principal(), "code_mode")
    with CodeSandbox(executor) as sandbox:
        yield CodeModeToolset(sandbox)


async def test_single_run_python_definition(toolset: CodeModeToolset) -> None:
    definitions = toolset.tool_definitions()
    assert len(definitions) == 1
    assert definitions[0]["function"]["name"] == "run_python"
    assert definitions[0]["function"]["parameters"]["required"] == ["code"]


async def test_result_shape(toolset: CodeModeToolset) -> None:
    outcome = await toolset.call("run_python", json.dumps({"code": "{'a': 1}"}))
    assert not outcome.is_error
    assert outcome.content == '{"result":{"a":1}}'
    assert outcome.host_calls == 0


async def test_stdout_included_only_when_printed(toolset: CodeModeToolset) -> None:
    outcome = await toolset.call("run_python", json.dumps({"code": "print('hi')\n1"}))
    assert json.loads(outcome.content) == {"result": 1, "stdout": "hi\n"}


async def test_host_calls_counted(toolset: CodeModeToolset) -> None:
    code = "get_balance('ACC-0050-1')\nget_balance('ACC-0050-1')\n1"
    outcome = await toolset.call("run_python", json.dumps({"code": code}))
    assert outcome.host_calls == 2


async def test_output_too_large(toolset: CodeModeToolset) -> None:
    code = f"'x' * {MAX_RESULT_CHARS + 1}"
    outcome = await toolset.call("run_python", json.dumps({"code": code}))
    assert outcome.is_error
    assert outcome.error_type == "output_too_large"
    assert "the limit is 20000" in outcome.content
    assert "Aggregate inside the code" in outcome.content


async def test_runtime_error_outcome(toolset: CodeModeToolset) -> None:
    outcome = await toolset.call("run_python", json.dumps({"code": "1 / 0"}))
    assert outcome.is_error
    assert outcome.error_type == "runtime_error"
    assert json.loads(outcome.content)["error"]["type"] == "runtime_error"


@pytest.mark.parametrize("arguments", ["not json", "[1]", "{}", '{"code": 5}'])
async def test_invalid_arguments(toolset: CodeModeToolset, arguments: str) -> None:
    outcome = await toolset.call("run_python", arguments)
    assert outcome.is_error
    assert outcome.error_type == "invalid_arguments"


async def test_unknown_tool(toolset: CodeModeToolset) -> None:
    outcome = await toolset.call("get_balance", "{}")
    assert outcome.is_error
    assert outcome.error_type == "unknown_tool"
