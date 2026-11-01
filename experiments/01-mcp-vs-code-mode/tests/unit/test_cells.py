"""Unit tests for cells and schedules."""

from collections import Counter

import pytest

from mcp_vs_code_mode.bench.cells import (
    Cell,
    all_cells,
    build_canary_schedule,
    build_schedule,
)
from mcp_vs_code_mode.bench.config import load_config

pytestmark = pytest.mark.unit


def test_eight_cells_in_canonical_order() -> None:
    cells = all_cells([10, 50, 200])
    assert [c.label for c in cells] == [
        "A:mcp",
        "A:code",
        "B10:mcp",
        "B10:code",
        "B50:mcp",
        "B50:code",
        "B200:mcp",
        "B200:code",
    ]


def test_parse_round_trip() -> None:
    for cell in all_cells([10, 50, 200]):
        assert Cell.parse(cell.label) == cell
    with pytest.raises(ValueError):
        Cell.parse("C:mcp")


def test_schedule_shape_and_ids() -> None:
    config = load_config()
    schedule = build_schedule(config)
    assert len(schedule) == 2 + config.iterations * 8
    assert [t.task_id for t in schedule[:2]] == ["w1-A-mcp", "w1-A-code"]
    assert all(t.warmup and t.iteration == 0 for t in schedule[:2])
    assert [t.order_index for t in schedule] == list(range(len(schedule)))
    assert len({t.task_id for t in schedule}) == len(schedule)


def test_each_cell_once_per_iteration() -> None:
    config = load_config()
    schedule = build_schedule(config)
    for iteration in range(1, config.iterations + 1):
        labels = Counter(t.cell.label for t in schedule if t.iteration == iteration)
        assert set(labels) == {c.label for c in all_cells(config.volumes)}
        assert set(labels.values()) == {1}


def test_schedule_is_deterministic_and_seeded() -> None:
    config = load_config()
    assert build_schedule(config) == build_schedule(config)
    other = config.model_copy(update={"order_seed": config.order_seed + 1})
    assert build_schedule(other) != build_schedule(config)


def test_canary_schedule_matches_config() -> None:
    config = load_config()
    schedule = build_canary_schedule(config)
    assert [t.cell.label for t in schedule] == config.canary.cells
    assert schedule[2].task_id == "c-B10-mcp"
    assert not any(t.warmup for t in schedule)
