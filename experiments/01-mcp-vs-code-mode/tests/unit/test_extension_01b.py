"""Tests for the 01b extension: three modes, scenario C, H5/H6, charts, report, regression."""

import json
import re
import struct
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from mcp_vs_code_mode import cli
from mcp_vs_code_mode.agent.toolsets import MCPToolset
from mcp_vs_code_mode.bench.analysis import Summary, load_tasks, mode_label, summarise
from mcp_vs_code_mode.bench.charts import (
    CHART_STEMS,
    UNANTICIPATED_STEM,
    group_label,
    render_all,
    spread_positions,
)
from mcp_vs_code_mode.bench.linkedin import render_linkedin, takeaway_three_mode
from mcp_vs_code_mode.bench.paths import RunPaths
from mcp_vs_code_mode.bench.report import render_report
from mcp_vs_code_mode.mcp_server.server import build_server
from mcp_vs_code_mode.tools import AGGREGATION_TOOL_SPECS, ToolExecutor

pytestmark = pytest.mark.unit

MODES = ("mcp", "mcp_agg", "code")
B_TOKENS = {"mcp": 60_000, "mcp_agg": 8_000, "code": 7_000}
C_TOKENS = {"mcp_agg": 30_000, "code": 7_000}


def _rows(synthetic: Any, *, agg_c_correct: int = 4, n: int = 10) -> list[Any]:
    tokens: dict[str, list[int]] = {}
    latency: dict[str, list[float]] = {}
    outcomes: dict[str, list[str]] = {}
    for mode in MODES:
        tokens[f"A:{mode}"], latency[f"A:{mode}"] = [1_000], [1_000.0]
        for volume, scale in ((10, 0.2), (100, 1.0)):
            tokens[f"B{volume}:{mode}"] = [int(B_TOKENS[mode] * scale)]
            latency[f"B{volume}:{mode}"] = [2_000.0 if mode == "code" else 5_000.0]
    for mode, value in C_TOKENS.items():
        tokens[f"C100:{mode}"], latency[f"C100:{mode}"] = [value], [3_000.0]
    outcomes["C100:mcp_agg"] = ["correct"] * agg_c_correct + ["incorrect"] * (n - agg_c_correct)
    return list(synthetic.uniform(n, tokens, latency, outcomes=outcomes))


def _summary(synthetic: Any, **kwargs: Any) -> tuple[Summary, RunPaths]:
    paths = synthetic.build(
        _rows(synthetic, **kwargs),
        volumes=(10, 100),
        modes=MODES,
        scenario_c={"volumes": [100], "modes": ["mcp_agg", "code"]},
    )
    return summarise(paths), paths


def test_cells_comparisons_and_labels(synthetic: Any) -> None:
    summary, _ = _summary(synthetic)
    assert summary.modes == ["mcp", "mcp_agg", "code"]
    assert summary.volumes == [10, 100]
    assert summary.c_volumes == [100]
    assert len(summary.cells) == 11
    assert [mode_label(m, summary) for m in MODES] == [
        "MCP (raw tools)",
        "MCP + aggregation tool",
        "Code Mode",
    ]
    pairs = {(c.mode_a, c.mode_b) for c in summary.comparisons if c.scenario == "B"}
    assert pairs == {("mcp", "code"), ("mcp_agg", "code"), ("mcp", "mcp_agg")}
    assert {(c.mode_a, c.mode_b) for c in summary.comparisons if c.scenario == "C"} == {
        ("mcp_agg", "code")
    }
    comp = summary.comparison("B", 100, "mcp_agg", "code")
    assert comp is not None
    assert comp.tokens_reduction_pct == pytest.approx((8_000 - 7_000) / 8_000 * 100)
    default = summary.comparison("B", 100)
    assert default is not None
    assert (default.mode_a, default.mode_b) == ("mcp", "code")


def test_old_run_label_is_plain_mcp(synthetic: Any) -> None:
    rows = synthetic.uniform(10, {"A:mcp": [1], "A:code": [1]}, {"A:mcp": [1.0], "A:code": [1.0]})
    summary = summarise(synthetic.build(rows))
    assert mode_label("mcp", summary) == "MCP"


def test_h5_and_h6_supported(synthetic: Any) -> None:
    summary, _ = _summary(synthetic)
    verdicts = {h.id: h.verdict for h in summary.hypotheses}
    assert verdicts["H5"] == "supported"
    assert verdicts["H6"] == "supported"
    h5 = summary.hypotheses[4].evidence
    assert "B100: tokens mcp_agg 8,000 vs code 7,000 (ratio 1.14)" in h5
    assert "accuracy mcp_agg 100.0% vs code 100.0%" in h5
    h6 = summary.hypotheses[5].evidence
    assert "C100: accuracy code 100.0% vs mcp_agg 40.0%" in h6


def test_h6_not_supported_when_gap_is_small(synthetic: Any) -> None:
    summary, _ = _summary(synthetic, agg_c_correct=8)  # gap 20 points < 30
    assert {h.id: h.verdict for h in summary.hypotheses}["H6"] == "not supported"


def test_h5_not_supported_when_tokens_too_high(synthetic: Any) -> None:
    rows = _rows(synthetic)
    rows = [
        r.model_copy(update={"total_tokens": 20_000}) if r.cell == "B100:mcp_agg" else r
        for r in rows
    ]
    paths = synthetic.build(
        rows,
        volumes=(10, 100),
        modes=MODES,
        scenario_c={"volumes": [100], "modes": ["mcp_agg", "code"]},
    )
    assert {h.id: h.verdict for h in summarise(paths).hypotheses}["H5"] == "not supported"


def test_h5_h6_inconclusive_with_too_few_tasks(synthetic: Any) -> None:
    paths = synthetic.build(
        _rows(synthetic, n=5, agg_c_correct=2),
        volumes=(10, 100),
        modes=MODES,
        scenario_c={"volumes": [100], "modes": ["mcp_agg", "code"]},
    )
    verdicts = {h.id: h.verdict for h in summarise(paths).hypotheses}
    assert verdicts["H5"] == verdicts["H6"] == "inconclusive"


def test_legacy_comparison_fields_load() -> None:
    legacy = {
        "scenario": "B",
        "volume": 100,
        "tokens_reduction_pct": 50.0,
        "tokens_difference": 10.0,
        "latency_p50_change_pct": -10.0,
        "cost_reduction_pct": 1.0,
        "accuracy_mcp": 0.0,
        "accuracy_code": 1.0,
        "mcp_correct": 0,
        "code_correct": 10,
        "mcp_truncated": 5,
        "code_truncated": 0,
        "n_mcp": 10,
        "n_code": 10,
    }
    from mcp_vs_code_mode.bench.analysis import Comparison

    comp = Comparison.model_validate(legacy)
    assert (comp.mode_a, comp.mode_b) == ("mcp", "code")
    assert (comp.accuracy_a, comp.accuracy_b, comp.correct_b, comp.truncated_a) == (0.0, 1.0, 10, 5)


def _svg_text(path: Path) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", path.read_text(encoding="utf-8")).split())


def test_three_mode_charts_render_with_all_labels(synthetic: Any, tmp_path: Path) -> None:
    summary, paths = _summary(synthetic)
    out = tmp_path / "charts"
    written = render_all(summary, load_tasks(paths), out)
    assert {p.name for p in written} == {
        f"{stem}.{ext}" for stem in (*CHART_STEMS, UNANTICIPATED_STEM) for ext in ("png", "svg")
    }
    for stem in ("tokens_vs_volume", "latency_vs_volume", "accuracy_by_cell", "scenario_a_parity"):
        text = _svg_text(out / f"{stem}.svg")
        for label in ("MCP (raw tools)", "MCP + aggregation tool", "Code Mode"):
            assert label in text, (stem, label)
    c_text = _svg_text(out / "unanticipated_query.svg")
    assert "Unanticipated query: tokens, latency and accuracy" in c_text
    assert "MCP + aggregation tool" in c_text
    assert "Code Mode" in c_text
    assert "MCP (raw tools)" not in c_text  # raw MCP is not run on scenario C
    assert "Unanticipated query" in _svg_text(out / "accuracy_by_cell.svg")
    assert "SIMULATED DATA" in c_text


def test_group_label_for_scenario_c() -> None:
    assert group_label("C", 100) == "Unanticipated query · 100 tx/account"
    assert group_label("C", 100, multiline=True) == "Unanticipated query\n100 tx/account"


def test_spread_positions_separates_neighbours() -> None:
    out = spread_positions([0.50, 0.51, 0.52], 0.075)
    assert out == sorted(out)
    assert all(b - a >= 0.075 - 1e-9 for a, b in pairwise(out))
    assert spread_positions([0.1, 0.9], 0.075) == [0.1, 0.9]
    top = spread_positions([0.97, 0.98, 0.99], 0.075)
    assert max(top) <= 0.97 + 1e-9
    assert spread_positions([], 0.075) == []


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def test_three_mode_linkedin_assets(synthetic: Any, tmp_path: Path) -> None:
    summary, _ = _summary(synthetic)
    landscape, portrait = render_linkedin(summary, tmp_path / "li")
    assert _png_size(landscape) == (1200, 627)
    assert _png_size(portrait) == (1080, 1350)
    text = takeaway_three_mode(summary)
    assert text == (
        "At 100 transactions per account (chained task), MCP + aggregation tool used 8,000 "
        "tokens per task and answered 10 of 10 correctly; Code Mode used 7,000 tokens per task "
        "and answered 10 of 10 correctly. On the unanticipated query (100 transactions per "
        "account), MCP + aggregation tool used 30,000 tokens per task and answered 4 of 10 "
        "correctly; Code Mode used 7,000 tokens per task and answered 10 of 10 correctly."
    )


def test_report_includes_three_modes_h5_h6_and_scenario_c(synthetic: Any, tmp_path: Path) -> None:
    summary, _ = _summary(synthetic)
    out = tmp_path / "r" / "report.md"
    render_report(summary, [], out)
    text = out.read_text(encoding="utf-8")
    for needle in ("| C100:mcp_agg |", "| B100:mcp_agg |", "| H5 |", "| H6 |"):
        assert needle in text, needle
    assert "Scenario C (unanticipated query), 100 transactions per account" in text
    assert "Code Mode -" in text and "vs MCP + aggregation tool" in text
    assert not re.search(r"\b(nan|None|NaN)\b", text)


def test_report_command_does_not_overwrite_author_edited_report(
    synthetic: Any, tmp_path: Path
) -> None:
    summary, paths = _summary(synthetic)
    existing = paths.reports / "report.md"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("> Author interpretation: my own words\n", encoding="utf-8")
    written = cli._report(paths, summary, [])
    assert written.name == "report.generated.md"
    assert existing.read_text(encoding="utf-8") == "> Author interpretation: my own words\n"
    assert written.exists()
    forced = cli._report(paths, summary, [], force=True)
    assert forced == existing
    assert existing.read_text(encoding="utf-8").startswith("# SIMULATED")


def test_report_command_writes_report_when_absent(synthetic: Any) -> None:
    summary, paths = _summary(synthetic)
    assert cli._report(paths, summary, []).name == "report.md"


@pytest.mark.anyio
async def test_mcp_toolset_mode_is_per_instance() -> None:
    from mcp_vs_code_mode.banking import (
        AuditLog,
        BankingService,
        benchmark_principal,
        generate_dataset,
    )

    executor = ToolExecutor(
        BankingService(generate_dataset(), AuditLog()),
        benchmark_principal(),
        "mcp_agg",
        AGGREGATION_TOOL_SPECS,
    )
    async with MCPToolset.open(build_server(executor), mode="mcp_agg") as agg:
        assert agg.mode == "mcp_agg"
        names = [d["function"]["name"] for d in agg.tool_definitions()]
        assert names[-1] == "summarise_spending"
        assert len(names) == 5
    plain = ToolExecutor(
        BankingService(generate_dataset(), AuditLog()), benchmark_principal(), "mcp"
    )
    async with MCPToolset.open(build_server(plain)) as raw:
        assert raw.mode == "mcp"
        assert len(raw.tool_definitions()) == 4
        assert raw.prompt_section() == agg.prompt_section()


# ----------------------------------------------------------------- regression on committed data


def test_committed_run_still_reproduces_published_numbers() -> None:
    paths = RunPaths.find("20261101T203521Z-full")  # read-only: nothing is written
    summary = summarise(paths)
    b100_mcp = summary.cell("B", 100, "mcp")
    b100_code = summary.cell("B", 100, "code")
    a_mcp = summary.cell("A", None, "mcp")
    assert b100_mcp is not None
    assert b100_code is not None
    assert a_mcp is not None
    assert b100_mcp.tokens_mean == pytest.approx(65_579, abs=1)
    assert b100_code.tokens_mean == pytest.approx(7_117, abs=1)
    assert a_mcp.tokens_mean == pytest.approx(2_205, abs=1)
    assert b100_mcp.accuracy == 0.0
    assert b100_mcp.n_truncated == 5
    verdicts = {h.id: h.verdict for h in summary.hypotheses}
    assert [verdicts[f"H{i}"] for i in (1, 2, 3, 4)] == ["supported"] * 4
    assert verdicts["H5"] == verdicts["H6"] == "inconclusive"
    assert summary.modes == ["mcp", "code"]
    assert mode_label("mcp", summary) == "MCP"
    saved = json.loads((paths.processed / "summary.json").read_text(encoding="utf-8"))
    assert Summary.model_validate(saved).run_id == summary.run_id
