"""Request budget estimate (estimates, not measurements)."""

from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel

from mcp_vs_code_mode.bench.cells import Cell, ScheduledTask
from mcp_vs_code_mode.bench.config import BenchmarkConfig


class RequestPlan(BaseModel):
    """Planned task and request counts."""

    tasks: int
    warmup_tasks: int
    oracle_requests: int
    worst_case_requests: int
    minutes_at_rate_limit: float
    per_cell: dict[str, int]


def _ideal_requests(cell: Cell) -> int:
    """Minimum model calls for an ideal agent."""
    if cell.scenario == "B" and cell.mode == "mcp":
        return 3
    return 2


def estimate_requests(schedule: Sequence[ScheduledTask], config: BenchmarkConfig) -> RequestPlan:
    """Lower-bound and worst-case request counts for a schedule."""
    per_cell = Counter(task.cell.label for task in schedule)
    oracle = sum(_ideal_requests(task.cell) for task in schedule)
    return RequestPlan(
        tasks=len(schedule),
        warmup_tasks=sum(1 for task in schedule if task.warmup),
        oracle_requests=oracle,
        worst_case_requests=len(schedule) * config.max_turns,
        minutes_at_rate_limit=oracle / config.rate_limit_per_minute,
        per_cell=dict(per_cell),
    )


def format_plan(plan: RequestPlan, remaining_today: int | None, daily_cap: int = 900) -> str:
    """Human-readable plan."""
    lines = [
        f"Tasks: {plan.tasks} ({plan.warmup_tasks} warm-up, "
        f"{plan.tasks - plan.warmup_tasks} measured)",
        f"Model requests, lower bound (ideal agent): {plan.oracle_requests}",
        f"Model requests, worst case (every task uses all turns): {plan.worst_case_requests}",
        f"Time at the throttle, lower bound: {plan.minutes_at_rate_limit:.1f} minutes",
        f"Daily request cap for this tool: {daily_cap}",
    ]
    if remaining_today is not None:
        lines.append(f"Free-model requests remaining today (provider): {remaining_today}")
    lines.append("Estimates, not measurements.")
    return "\n".join(lines)
