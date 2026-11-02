"""Benchmark cells and deterministic task schedules."""

import random
import re
from collections.abc import Sequence
from dataclasses import dataclass

from mcp_vs_code_mode.agent.records import Mode
from mcp_vs_code_mode.bench.config import BenchmarkConfig
from mcp_vs_code_mode.scenarios.definitions import ScenarioId

MODE_ORDER: tuple[Mode, ...] = ("mcp", "mcp_agg", "code")
_LABEL = re.compile(r"^(A|B(\d+)|C(\d+)):(mcp_agg|mcp|code)$")


@dataclass(frozen=True, order=True)
class Cell:
    """One scenario/volume/mode combination."""

    scenario: ScenarioId
    volume: int | None
    mode: Mode

    @property
    def label(self) -> str:
        """Short label such as ``A:mcp``, ``B200:code`` or ``C100:mcp_agg``."""
        return f"{self.scenario}{self.volume if self.volume is not None else ''}:{self.mode}"

    @property
    def name(self) -> str:
        """Label without the colon, used in task ids (``B200-mcp``)."""
        return self.label.replace(":", "-")

    @classmethod
    def parse(cls, text: str) -> "Cell":
        """Parse a label such as ``B200:mcp``."""
        match = _LABEL.match(text)
        if match is None:
            raise ValueError(
                f"Invalid cell label {text!r}; expected e.g. 'A:mcp', 'B200:code' or 'C100:mcp_agg'"
            )
        mode = _as_mode(match.group(4))
        if match.group(1) == "A":
            return cls("A", None, mode)
        if match.group(1).startswith("B"):
            return cls("B", int(match.group(2)), mode)
        return cls("C", int(match.group(3)), mode)


def _as_mode(text: str) -> Mode:
    for mode in MODE_ORDER:
        if mode == text:
            return mode
    raise ValueError(f"Unknown mode {text!r}")


def cells_for(
    modes: Sequence[str],
    volumes: Sequence[int],
    c_volumes: Sequence[int] = (),
    c_modes: Sequence[str] = (),
) -> tuple[Cell, ...]:
    """Canonical cell order: A per mode, B per volume per mode, then C per volume per mode."""
    ordered = [m for m in MODE_ORDER if m in modes]
    c_ordered = [m for m in MODE_ORDER if m in c_modes]
    cells = [Cell("A", None, mode) for mode in ordered]
    cells.extend(Cell("B", volume, mode) for volume in volumes for mode in ordered)
    cells.extend(Cell("C", volume, mode) for volume in c_volumes for mode in c_ordered)
    return tuple(cells)


def all_cells(config: BenchmarkConfig) -> tuple[Cell, ...]:
    """Every cell the configuration schedules, in canonical order."""
    return cells_for(
        config.modes, config.volumes, config.scenario_c.volumes, config.scenario_c.modes
    )


@dataclass(frozen=True)
class ScheduledTask:
    """A task to execute, with its position in the run."""

    task_id: str
    cell: Cell
    iteration: int
    warmup: bool
    order_index: int


def build_schedule(config: BenchmarkConfig) -> tuple[ScheduledTask, ...]:
    """Warm-ups first, then every cell once per iteration in a seeded shuffled order."""
    tasks: list[ScheduledTask] = []
    for n in range(1, config.warmup_tasks_per_mode + 1):
        for mode in (m for m in MODE_ORDER if m in config.modes):
            cell = Cell("A", None, mode)
            tasks.append(ScheduledTask(f"w{n}-{cell.name}", cell, 0, True, len(tasks)))
    base = list(all_cells(config))
    for iteration in range(1, config.iterations + 1):
        cells = list(base)
        random.Random(config.order_seed + iteration).shuffle(cells)
        for cell in cells:
            task_id = f"{iteration:02d}-{cell.name}"
            tasks.append(ScheduledTask(task_id, cell, iteration, False, len(tasks)))
    return tuple(tasks)


def build_canary_schedule(
    config: BenchmarkConfig, cells: Sequence[str] | None = None
) -> tuple[ScheduledTask, ...]:
    """One task per canary cell: ``cells`` when given, else the configured canary cells."""
    tasks: list[ScheduledTask] = []
    for text in config.canary.cells if cells is None else cells:
        cell = Cell.parse(text)
        tasks.append(ScheduledTask(f"c-{cell.name}", cell, 1, False, len(tasks)))
    return tuple(tasks)
