"""Benchmark cells and deterministic task schedules."""

import random
import re
from collections.abc import Sequence
from dataclasses import dataclass

from mcp_vs_code_mode.agent.records import Mode
from mcp_vs_code_mode.bench.config import BenchmarkConfig
from mcp_vs_code_mode.scenarios.definitions import ScenarioId

_MODES: tuple[Mode, ...] = ("mcp", "code")
_LABEL = re.compile(r"^(A|B(\d+)):(mcp|code)$")


@dataclass(frozen=True, order=True)
class Cell:
    """One scenario/volume/mode combination."""

    scenario: ScenarioId
    volume: int | None
    mode: Mode

    @property
    def label(self) -> str:
        """Short label such as ``A:mcp`` or ``B200:code``."""
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
            raise ValueError(f"Invalid cell label {text!r}; expected e.g. 'A:mcp' or 'B200:code'")
        mode: Mode = "mcp" if match.group(3) == "mcp" else "code"
        if match.group(1) == "A":
            return cls("A", None, mode)
        return cls("B", int(match.group(2)), mode)


def all_cells(volumes: Sequence[int]) -> tuple[Cell, ...]:
    """Canonical cell order: scenario A, then scenario B per volume; mcp before code."""
    cells = [Cell("A", None, mode) for mode in _MODES]
    cells.extend(Cell("B", volume, mode) for volume in volumes for mode in _MODES)
    return tuple(cells)


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
        for mode in _MODES:
            cell = Cell("A", None, mode)
            tasks.append(ScheduledTask(f"w{n}-{cell.name}", cell, 0, True, len(tasks)))
    base = list(all_cells(config.volumes))
    for iteration in range(1, config.iterations + 1):
        cells = list(base)
        random.Random(config.order_seed + iteration).shuffle(cells)
        for cell in cells:
            task_id = f"{iteration:02d}-{cell.name}"
            tasks.append(ScheduledTask(task_id, cell, iteration, False, len(tasks)))
    return tuple(tasks)


def build_canary_schedule(config: BenchmarkConfig) -> tuple[ScheduledTask, ...]:
    """One task per configured canary cell."""
    tasks: list[ScheduledTask] = []
    for text in config.canary.cells:
        cell = Cell.parse(text)
        tasks.append(ScheduledTask(f"c-{cell.name}", cell, 1, False, len(tasks)))
    return tuple(tasks)
