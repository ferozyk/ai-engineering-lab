"""Unit tests for Markdown report generation."""

import re
from pathlib import Path
from typing import Any

import pytest

from mcp_vs_code_mode.bench.analysis import summarise
from mcp_vs_code_mode.bench.report import render_report

pytestmark = pytest.mark.unit

HEADINGS = (
    "## Executive summary",
    "## Research question",
    "## Experimental setup",
    "## Environment",
    "## Methodology",
    "## Results table",
    "## Graphical comparisons",
    "## Key observations",
    "## Engineering trade-offs",
    "## Limitations",
    "## Conclusion",
)


def _report(synthetic: Any, tmp_path: Path, *, simulated: bool, sparse: bool = False) -> str:
    tokens = {"A:mcp": [1000, 1200], "A:code": [1100, 1300]}
    latency = {"A:mcp": [1000.0, 1500.0], "A:code": [900.0, 1100.0]}
    if not sparse:
        for key in ("B10", "B50", "B200"):
            tokens[f"{key}:mcp"], tokens[f"{key}:code"] = [5000, 6000], [900, 1000]
            latency[f"{key}:mcp"], latency[f"{key}:code"] = [2000.0, 3000.0], [800.0, 900.0]
    paths = synthetic.build(synthetic.uniform(2, tokens, latency), simulated=simulated)
    summary = summarise(paths)
    out = tmp_path / "reports" / "report.md"
    charts = [tmp_path / "charts" / "tokens_vs_volume.png"]
    render_report(summary, charts, out)
    return out.read_text(encoding="utf-8")


def test_all_sections_present(synthetic: Any, tmp_path: Path) -> None:
    text = _report(synthetic, tmp_path, simulated=False)
    for heading in HEADINGS:
        assert heading in text, heading
    assert text.startswith("# Benchmark report — MCP vs Code Mode (")


def test_simulated_prefix_and_banner(synthetic: Any, tmp_path: Path) -> None:
    text = _report(synthetic, tmp_path, simulated=True)
    assert text.startswith("# SIMULATED — Benchmark report")
    assert "SIMULATED DATA — NOT A RESULT" in text


def test_no_nan_or_none_strings_even_with_missing_cells(synthetic: Any, tmp_path: Path) -> None:
    for sparse in (False, True):
        text = _report(synthetic, tmp_path, simulated=True, sparse=sparse)
        assert not re.search(r"\b(nan|None|NaN)\b", text), sparse


def test_author_sections_are_placeholders(synthetic: Any, tmp_path: Path) -> None:
    text = _report(synthetic, tmp_path, simulated=False)
    assert "> Author interpretation: _pending" in text
    assert "> Author interpretation pending." in text
    assert text.count("> Author section — pending.") == 2


def test_chart_links_are_relative_and_table_marks_estimates(synthetic: Any, tmp_path: Path) -> None:
    text = _report(synthetic, tmp_path, simulated=False)
    assert "](../charts/tokens_vs_volume.png)" in text
    assert "Cost per 1k tasks (est.)" in text
    assert "| H1 |" in text


def test_truncation_in_report(synthetic: Any, tmp_path: Path) -> None:
    paths = synthetic.truncated_run(3)
    summary = summarise(paths)
    out = tmp_path / "reports" / "report.md"
    render_report(summary, [], out)
    text = out.read_text(encoding="utf-8")
    assert (
        "**B200 · MCP**: 3 of 3 tasks were cut off at the 32,768-token output limit while "
        "reasoning; mean 100,000 tokens per task (lower bound)."
    ) in text
    assert "B200 · Code Mode**: " not in text
    assert "| Cell | n | completed | cut off | Accuracy |" in text
    assert "| B200:mcp | 3 | 0 | 3 | 0.0% |" in text
    assert "| B10:mcp | 3 | 3 | 0 | 100.0% |" in text
    assert "Output-limit rule" in text
    assert "methodology.md#3-controls" in text
