"""Shared fixtures for unit and integration tests (imported by each conftest)."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mcp_vs_code_mode.agent.records import TaskOutcome
from mcp_vs_code_mode.banking import (
    AuditLog,
    BankingService,
    Dataset,
    Principal,
    benchmark_principal,
    generate_dataset,
)
from mcp_vs_code_mode.bench.cells import Cell
from mcp_vs_code_mode.bench.metadata import RunMetadata
from mcp_vs_code_mode.bench.paths import RunPaths
from mcp_vs_code_mode.bench.pricing import simulated_pricing
from mcp_vs_code_mode.bench.records import TaskRow, append_row
from mcp_vs_code_mode.tools import ToolExecutor


@pytest.fixture(scope="session")
def dataset() -> Dataset:
    """The default synthetic dataset, generated once per session."""
    return generate_dataset()


@pytest.fixture
def audit_log() -> AuditLog:
    """A fresh in-memory audit log."""
    return AuditLog()


@pytest.fixture
def service(dataset: Dataset, audit_log: AuditLog) -> BankingService:
    """Banking service over the default dataset."""
    return BankingService(dataset, audit_log)


@pytest.fixture
def principal() -> Principal:
    """The benchmark principal."""
    return benchmark_principal()


@pytest.fixture
def executor(service: BankingService, principal: Principal) -> ToolExecutor:
    """Tool executor on the test channel."""
    return ToolExecutor(service, principal, "test")


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-marked tests on asyncio only."""
    return "asyncio"


class SyntheticRuns:
    """Builds small hand-made raw run directories for analysis, chart and report tests."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._count = 0

    @staticmethod
    def row(
        task_id: str,
        cell: str,
        *,
        outcome: TaskOutcome = "correct",
        tokens: int = 1000,
        latency_ms: float = 1000.0,
        warmup: bool = False,
        cost: float = 0.01,
        model_calls: int = 2,
    ) -> TaskRow:
        """One ``TaskRow`` for ``cell`` (e.g. ``"B200:mcp"``) with chosen headline values."""
        parsed = Cell.parse(cell)
        input_tokens = tokens * 9 // 10
        return TaskRow(
            run_id="synthetic",
            task_id=task_id,
            iteration=0 if warmup else 1,
            warmup=warmup,
            order_index=0,
            cell=cell,
            started_at=datetime(2026, 11, 1, tzinfo=UTC),
            simulated=True,
            estimated_cost_usd=cost,
            mode=parsed.mode,
            scenario=parsed.scenario,
            volume=parsed.volume,
            outcome=outcome,
            partial_score=1.0 if outcome == "correct" else 0.5,
            field_errors=(),
            final_text=None,
            error=None,
            infra_error_kind="server" if outcome == "infra_error" else None,
            infra_attempts=0,
            input_tokens=input_tokens,
            output_tokens=tokens - input_tokens,
            reasoning_tokens=0,
            total_tokens=tokens,
            peak_prompt_tokens=input_tokens,
            model_calls=model_calls,
            tool_call_count=model_calls - 1,
            tool_errors=0,
            wall_ms=latency_ms,
            client_wait_ms=0.0,
            latency_ms=latency_ms,
            llm_ms=latency_ms * 0.8,
            tool_ms=latency_ms * 0.1,
            overhead_ms=latency_ms * 0.1,
        )

    def uniform(
        self,
        n: int,
        tokens: Mapping[str, Sequence[int]],
        latency_ms: Mapping[str, Sequence[float]],
        *,
        outcomes: Mapping[str, Sequence[TaskOutcome]] | None = None,
    ) -> list[TaskRow]:
        """``n`` tasks per cell; per-cell value lists cycle, cells missing from ``tokens`` skip."""
        rows: list[TaskRow] = []
        for cell, token_values in tokens.items():
            for i in range(n):
                outcome: TaskOutcome = "correct"
                if outcomes is not None and cell in outcomes:
                    outcome = outcomes[cell][i % len(outcomes[cell])]
                rows.append(
                    self.row(
                        f"{i + 1:02d}-{Cell.parse(cell).name}",
                        cell,
                        outcome=outcome,
                        tokens=token_values[i % len(token_values)],
                        latency_ms=latency_ms[cell][i % len(latency_ms[cell])],
                    )
                )
        return rows

    def build(self, rows: Sequence[TaskRow], *, simulated: bool = True) -> RunPaths:
        """Write ``rows`` and matching metadata under a fresh results directory."""
        self._count += 1
        run_id = f"synthetic{self._count}-dry-run"
        paths = RunPaths.for_run(run_id, "dry-run", results_dir=self._root / "results")
        paths.ensure()
        for row in rows:
            append_row(paths.raw / "tasks.jsonl", row.model_copy(update={"run_id": run_id}))
        meta = RunMetadata(
            run_id=run_id,
            kind="dry-run",
            simulated=simulated,
            experiment="mcp-vs-code-mode",
            experiment_version="0.0.0",
            git_sha="0" * 40,
            git_dirty=False,
            started_at=datetime(2026, 11, 1, tzinfo=UTC),
            finished_at=datetime(2026, 11, 1, 1, tzinfo=UTC),
            hardware={"machine": "test"},
            os="test-os",
            python_version="3.12",
            provider="simulated",
            model_id="test-model",
            dataset_version="d1",
            dataset_checksum="abc",
            config={"volumes": [10, 50, 200], "temperature": 0.0, "warmup_tasks_per_mode": 1},
            iterations=3,
            tasks_planned=len(rows),
            package_versions={"mcp": "1"},
            pricing=simulated_pricing(),
            max_turns=8,
            rate_limit_per_minute=15,
            daily_request_cap=900,
            order_seed=1,
            llm_seed=None,
        )
        (paths.raw / "run_metadata.json").write_text(meta.model_dump_json(indent=2))
        return paths


@pytest.fixture
def synthetic(tmp_path: Path) -> SyntheticRuns:
    """Builder of hand-made raw run directories."""
    return SyntheticRuns(tmp_path)
