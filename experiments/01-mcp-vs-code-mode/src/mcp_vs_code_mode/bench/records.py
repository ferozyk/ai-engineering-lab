"""Row models for the raw output files (the contract read by the analysis phase)."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from mcp_vs_code_mode.agent.records import Mode, TaskOutcome
from mcp_vs_code_mode.scenarios.definitions import ScenarioId


class TaskRow(BaseModel):
    """One line of ``tasks.jsonl``: a ``TaskResult`` without transcript or per-call lists."""

    run_id: str
    task_id: str
    iteration: int
    warmup: bool
    order_index: int
    cell: str
    started_at: datetime
    simulated: bool
    estimated_cost_usd: float
    mode: Mode
    scenario: ScenarioId
    volume: int | None
    outcome: TaskOutcome
    partial_score: float
    field_errors: tuple[str, ...]
    final_text: str | None
    error: str | None
    infra_error_kind: str | None
    infra_attempts: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    peak_prompt_tokens: int
    model_calls: int
    tool_call_count: int
    tool_errors: int
    wall_ms: float
    client_wait_ms: float
    latency_ms: float
    llm_ms: float
    tool_ms: float
    overhead_ms: float


class LLMCallRow(BaseModel):
    """One line of ``llm_calls.jsonl``."""

    task_id: str
    turn: int
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    reasoning_tokens: int | None
    cached_tokens: int | None
    finish_reason: str | None
    tool_call_count: int
    attempts: int
    client_wait_ms: float
    provider: str | None
    model: str | None
    request_id: str | None
    simulated: bool


class ToolCallRow(BaseModel):
    """One line of ``tool_calls.jsonl``."""

    task_id: str
    mode: Mode
    turn: int
    name: str
    arguments: str
    duration_ms: float
    is_error: bool
    error_type: str | None
    result_chars: int
    host_calls: int | None


def load_rows[RowT: BaseModel](path: Path, model: type[RowT]) -> list[RowT]:
    """Read a JSONL file into validated rows (missing file gives an empty list)."""
    if not path.exists():
        return []
    rows: list[RowT] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(model.model_validate_json(line))
    return rows


def append_row(path: Path, row: BaseModel) -> None:
    """Append one JSON line and flush."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(row.model_dump_json() + "\n")
        handle.flush()
