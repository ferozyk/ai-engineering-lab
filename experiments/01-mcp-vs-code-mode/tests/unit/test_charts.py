"""Unit tests for chart rendering from a synthetic summary."""

from pathlib import Path
from typing import Any

import pytest

from mcp_vs_code_mode.bench.analysis import Summary, load_tasks, summarise
from mcp_vs_code_mode.bench.charts import CHART_STEMS, render_all

pytestmark = pytest.mark.unit

KEYS = ("A", "B10", "B50", "B200")


def _rows(synthetic: Any, cells: tuple[str, ...] | None = None) -> list[Any]:
    tokens: dict[str, list[int]] = {}
    latency: dict[str, list[float]] = {}
    for key in KEYS:
        tokens[f"{key}:mcp"] = [1000, 2000, 3000]
        tokens[f"{key}:code"] = [800, 900, 1000]
        latency[f"{key}:mcp"] = [1000.0, 2000.0, 3000.0]
        latency[f"{key}:code"] = [900.0, 1000.0, 1100.0]
    if cells is not None:
        tokens = {k: v for k, v in tokens.items() if k in cells}
    return list(synthetic.uniform(3, tokens, latency))


def _render(
    synthetic: Any, tmp_path: Path, *, simulated: bool = True
) -> tuple[Summary, list[Path]]:
    paths = synthetic.build(_rows(synthetic), simulated=simulated)
    summary = summarise(paths)
    return summary, render_all(summary, load_tasks(paths), tmp_path / "charts")


def test_all_charts_written_as_png_and_svg(synthetic: Any, tmp_path: Path) -> None:
    _, written = _render(synthetic, tmp_path)
    assert {p.name for p in written} == {
        f"{stem}.{ext}" for stem in CHART_STEMS for ext in ("png", "svg")
    }
    assert all(p.stat().st_size > 0 for p in written)


def test_simulated_watermark_in_every_svg(synthetic: Any, tmp_path: Path) -> None:
    _, written = _render(synthetic, tmp_path)
    svgs = [p for p in written if p.suffix == ".svg"]
    assert len(svgs) == len(CHART_STEMS)
    for svg in svgs:
        text = svg.read_text(encoding="utf-8")
        assert "SIMULATED DATA" in text, svg.name
        assert "SIMULATED" in text


def test_real_run_has_no_watermark(synthetic: Any, tmp_path: Path) -> None:
    _, written = _render(synthetic, tmp_path, simulated=False)
    for svg in (p for p in written if p.suffix == ".svg"):
        assert "SIMULATED" not in svg.read_text(encoding="utf-8")


def test_chart_with_missing_cells_still_renders(synthetic: Any, tmp_path: Path) -> None:
    paths = synthetic.build(_rows(synthetic, cells=("A:mcp", "A:code", "B10:mcp")))
    summary = summarise(paths)
    written = render_all(summary, load_tasks(paths), tmp_path / "sparse")
    assert len(written) == 2 * len(CHART_STEMS)
    assert all(p.stat().st_size > 0 for p in written)


def test_empty_run_renders_no_data_charts(synthetic: Any, tmp_path: Path) -> None:
    paths = synthetic.build([])
    summary = summarise(paths)
    written = render_all(summary, load_tasks(paths), tmp_path / "empty")
    assert len(written) == 2 * len(CHART_STEMS)
    svg = (tmp_path / "empty" / "tokens_vs_volume.svg").read_text(encoding="utf-8")
    assert "No data" in svg
