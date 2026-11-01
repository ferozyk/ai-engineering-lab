"""End-to-end: Oracle model + real toolset + run_task for every mode and task."""

import secrets
from pathlib import Path

import pytest

from mcp_vs_code_mode.agent import CodeModeToolset, MCPToolset, TaskResult, run_task
from mcp_vs_code_mode.agent.fakes import OracleChatModel
from mcp_vs_code_mode.banking import (
    AuditLog,
    BankingService,
    Dataset,
    authenticate_token,
    token_fingerprint,
)
from mcp_vs_code_mode.code_mode import CodeSandbox
from mcp_vs_code_mode.mcp_server import server_parameters
from mcp_vs_code_mode.scenarios import (
    TaskSpec,
    expected_answer_a,
    expected_answer_b,
    scenario_a_task,
    scenario_b_task,
)
from mcp_vs_code_mode.tools import ToolExecutor

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

_TASKS = {
    "A": scenario_a_task(),
    "B10": scenario_b_task(10),
    "B50": scenario_b_task(50),
    "B200": scenario_b_task(200),
}


def _expected(dataset: Dataset, task: TaskSpec):  # type: ignore[no-untyped-def]
    if task.scenario == "A":
        return expected_answer_a(dataset)
    assert task.volume is not None
    return expected_answer_b(dataset, task.volume)


def _assert_clean(result: TaskResult, token: str, model_calls: int) -> None:
    assert result.outcome == "correct", (result.field_errors, result.final_text)
    assert result.partial_score == 1.0
    assert result.model_calls == model_calls
    assert result.tool_errors == 0
    assert token not in str(result.transcript)
    assert all(call.simulated for call in result.llm_calls)


@pytest.mark.parametrize("name", _TASKS)
async def test_mcp_mode(name: str, dataset: Dataset, tmp_path: Path) -> None:
    task = _TASKS[name]
    token = secrets.token_urlsafe(24)
    params = server_parameters(
        token=token, trusted={token_fingerprint(token): "rm-001"}, audit_log=tmp_path / "a.jsonl"
    )
    async with MCPToolset.open(params) as toolset:
        result = await run_task(
            task_id=name,
            task=task,
            expected=_expected(dataset, task),
            model=OracleChatModel(task, "mcp"),
            toolset=toolset,
        )
    _assert_clean(result, token, 2 if task.scenario == "A" else 3)
    assert result.mode == "mcp"
    if task.scenario == "B":
        assert result.llm_calls[1].tool_call_count == 8


@pytest.mark.parametrize("name", _TASKS)
async def test_code_mode(name: str, dataset: Dataset) -> None:
    task = _TASKS[name]
    token = secrets.token_urlsafe(24)
    principal = authenticate_token(token, {token_fingerprint(token): "rm-001"})
    audit = AuditLog()
    executor = ToolExecutor(BankingService(dataset, audit), principal, "code_mode")
    with CodeSandbox(executor) as sandbox:
        result = await run_task(
            task_id=name,
            task=task,
            expected=_expected(dataset, task),
            model=OracleChatModel(task, "code"),
            toolset=CodeModeToolset(sandbox),
        )
    _assert_clean(result, token, 2)
    assert result.mode == "code"
    assert result.tool_calls[0].host_calls == (1 if task.scenario == "A" else 9)
    assert {r.channel for r in audit.records} == {"code_mode"}
