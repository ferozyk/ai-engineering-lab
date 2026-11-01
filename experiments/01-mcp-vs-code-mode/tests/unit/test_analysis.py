"""Unit tests for the analysis step, using hand-made raw data with known statistics."""

import json
from typing import Any

import pytest

from mcp_vs_code_mode.bench.analysis import (
    Summary,
    load_tasks,
    summarise,
    write_summary,
)

pytestmark = pytest.mark.unit

ALL_CELLS = (
    "A:mcp",
    "A:code",
    "B10:mcp",
    "B10:code",
    "B50:mcp",
    "B50:code",
    "B100:mcp",
    "B100:code",
    "B200:mcp",
    "B200:code",
)


def _grid(
    synthetic: Any,
    n: int,
    tokens: dict[str, list[int]],
    latency_ms: dict[str, list[float]],
    **kwargs: Any,
) -> list[Any]:
    return list(synthetic.uniform(n, tokens, latency_ms, **kwargs))


def _uniform_inputs(
    mcp: dict[str, int], code: dict[str, int], lat_mcp: dict[str, float], lat_code: dict[str, float]
) -> tuple[dict[str, list[int]], dict[str, list[float]]]:
    tokens: dict[str, list[int]] = {}
    latency: dict[str, list[float]] = {}
    for scope in ("A", "B10", "B50", "B100", "B200"):
        tokens[f"{scope}:mcp"] = [mcp[scope]]
        tokens[f"{scope}:code"] = [code[scope]]
        latency[f"{scope}:mcp"] = [lat_mcp[scope]]
        latency[f"{scope}:code"] = [lat_code[scope]]
    return tokens, latency


def test_exact_statistics(synthetic: Any) -> None:
    rows = _grid(
        synthetic,
        3,
        {c: [100, 200, 300] for c in ALL_CELLS},
        {c: [1000.0, 2000.0, 4000.0] for c in ALL_CELLS},
    )
    summary = summarise(synthetic.build(rows))
    cell = summary.cell("B", 50, "mcp")
    assert cell is not None
    assert cell.n_tasks == cell.n_measured == 3
    assert cell.accuracy == 1.0
    assert cell.tokens_mean == pytest.approx(200.0)
    assert cell.tokens_median == pytest.approx(200.0)
    assert (cell.tokens_min, cell.tokens_max) == (100.0, 300.0)
    assert cell.tokens_std == pytest.approx(100.0)
    assert cell.latency_mean_s == pytest.approx(7 / 3)
    assert cell.latency_p50_s == pytest.approx(2.0)
    assert cell.latency_p95_s == pytest.approx(3.8)  # linear interpolation
    assert cell.input_tokens_mean == pytest.approx(180.0)
    assert cell.cost_usd_mean == pytest.approx(0.01)
    assert cell.cost_usd_per_1k_tasks == pytest.approx(10.0)
    assert cell.model_calls_mean == pytest.approx(2.0)
    assert [c.cell for c in summary.cells] == list(ALL_CELLS)


def test_comparison_numbers(synthetic: Any) -> None:
    tokens, latency = _uniform_inputs(
        {"A": 1000, "B10": 2000, "B50": 8000, "B100": 8000, "B200": 20000},
        {"A": 1100, "B10": 1000, "B50": 1000, "B100": 1000, "B200": 5000},
        {"A": 1000.0, "B10": 2000.0, "B50": 4000.0, "B100": 4000.0, "B200": 10000.0},
        {"A": 1100.0, "B10": 1500.0, "B50": 1000.0, "B100": 1000.0, "B200": 2500.0},
    )
    summary = summarise(synthetic.build(_grid(synthetic, 3, tokens, latency)))
    comp = summary.comparison("B", 200)
    assert comp is not None
    assert comp.tokens_reduction_pct == pytest.approx(75.0)
    assert comp.tokens_difference == pytest.approx(15000.0)
    assert comp.latency_p50_change_pct == pytest.approx(-75.0)
    assert comp.cost_reduction_pct == pytest.approx(0.0)
    parity = summary.comparison("A", None)
    assert parity is not None
    assert parity.tokens_reduction_pct == pytest.approx(-10.0)


def test_warmups_and_superseded_records(synthetic: Any) -> None:
    rows = [
        synthetic.row("w1-A-mcp", "A:mcp", warmup=True, tokens=999_999),
        synthetic.row("01-A-mcp", "A:mcp", outcome="infra_error", tokens=0),
        synthetic.row("01-A-mcp", "A:mcp", tokens=100),
        synthetic.row("02-A-mcp", "A:mcp", tokens=300),
    ]
    paths = synthetic.build(rows)
    frame = load_tasks(paths)
    assert sorted(frame["task_id"]) == ["01-A-mcp", "02-A-mcp"]
    summary = summarise(paths)
    assert summary.excluded_warmup_tasks == 1
    assert summary.superseded_records == 1
    cell = summary.cell("A", None, "mcp")
    assert cell is not None
    assert cell.n_tasks == 2
    assert cell.n_infra_error == 0
    assert cell.tokens_mean == pytest.approx(200.0)


def test_infra_errors_excluded_from_statistics(synthetic: Any) -> None:
    rows = [
        synthetic.row("01-A-mcp", "A:mcp", tokens=100, latency_ms=1000.0),
        synthetic.row("02-A-mcp", "A:mcp", tokens=300, latency_ms=3000.0),
        synthetic.row("03-A-mcp", "A:mcp", outcome="incorrect", tokens=200, latency_ms=2000.0),
        synthetic.row("04-A-mcp", "A:mcp", outcome="infra_error", tokens=0, latency_ms=0.0),
    ]
    cell = summarise(synthetic.build(rows)).cell("A", None, "mcp")
    assert cell is not None
    assert (cell.n_tasks, cell.n_measured, cell.n_infra_error) == (4, 3, 1)
    assert cell.accuracy == pytest.approx(2 / 3)
    assert cell.tokens_mean == pytest.approx(200.0)
    assert cell.outcomes == {"correct": 2, "incorrect": 1, "infra_error": 1}


def test_empty_cells_are_none_not_nan(synthetic: Any, tmp_path: Any) -> None:
    rows = [synthetic.row("01-A-mcp", "A:mcp")]
    paths = synthetic.build(rows)
    summary = summarise(paths)
    empty = summary.cell("B", 200, "code")
    assert empty is not None
    assert empty.n_tasks == 0
    assert empty.accuracy is None
    assert empty.tokens_mean is None
    assert empty.latency_p95_s is None
    assert empty.cost_usd_per_1k_tasks is None
    comp = summary.comparison("B", 200)
    assert comp is not None
    assert comp.tokens_reduction_pct is None
    write_summary(summary, paths)
    text = (paths.processed / "summary.json").read_text(encoding="utf-8")
    assert "NaN" not in text
    assert "Infinity" not in text
    json.loads(text)  # strict JSON
    assert (paths.processed / "cells.csv").stat().st_size > 0
    assert (paths.processed / "comparisons.csv").stat().st_size > 0
    assert Summary.model_validate_json(text).run_id == summary.run_id


def _verdicts(summary: Summary) -> dict[str, str]:
    return {h.id: h.verdict for h in summary.hypotheses}


def test_hypotheses_supported(synthetic: Any) -> None:
    tokens, latency = _uniform_inputs(
        {"A": 1000, "B10": 2000, "B50": 8000, "B100": 12000, "B200": 20000},
        {"A": 1100, "B10": 1000, "B50": 1000, "B100": 1000, "B200": 1000},
        {"A": 1000.0, "B10": 1000.0, "B50": 4000.0, "B100": 6000.0, "B200": 10000.0},
        {"A": 1100.0, "B10": 900.0, "B50": 1000.0, "B100": 1000.0, "B200": 2000.0},
    )
    outcomes = {"B10:mcp": ["correct"], "B200:mcp": ["correct", "incorrect"]}
    rows = synthetic.uniform(10, tokens, latency, outcomes=outcomes)
    summary = summarise(synthetic.build(rows))
    assert _verdicts(summary) == {
        "H1": "supported",
        "H2": "supported",
        "H3": "supported",
        "H4": "supported",
    }
    h1 = summary.hypotheses[0]
    assert "tokens mcp 1,000 vs code 1,100 (+10.0%)" in h1.evidence
    assert "p50 latency mcp 1.00 s vs code 1.10 s (+10.0%)" in h1.evidence


def test_hypotheses_not_supported(synthetic: Any) -> None:
    tokens, latency = _uniform_inputs(
        {"A": 1000, "B10": 1000, "B50": 1000, "B100": 1000, "B200": 1000},
        {"A": 2000, "B10": 1500, "B50": 1500, "B100": 1500, "B200": 1500},
        {"A": 1000.0, "B10": 1000.0, "B50": 1000.0, "B100": 1000.0, "B200": 1000.0},
        {"A": 2000.0, "B10": 1000.0, "B50": 2000.0, "B100": 2000.0, "B200": 2000.0},
    )
    summary = summarise(synthetic.build(synthetic.uniform(10, tokens, latency)))
    assert _verdicts(summary) == {
        "H1": "not supported",  # A differs by 100%
        "H2": "not supported",  # code uses more tokens
        "H3": "not supported",  # code is slower
        "H4": "not supported",  # MCP accuracy does not decrease
    }


def test_h2_requires_widening_gap(synthetic: Any) -> None:
    tokens, latency = _uniform_inputs(
        {"A": 1000, "B10": 5000, "B50": 5000, "B100": 5000, "B200": 6000},
        {"A": 1000, "B10": 1000, "B50": 1000, "B100": 1000, "B200": 1000},
        dict.fromkeys(("A", "B10", "B50", "B100", "B200"), 1000.0),
        dict.fromkeys(("A", "B10", "B50", "B100", "B200"), 1000.0),
    )
    summary = summarise(synthetic.build(synthetic.uniform(10, tokens, latency)))
    assert _verdicts(summary)["H2"] == "not supported"  # gap 4000, 4000, 5000: not strict


def test_h4_requires_stable_code_accuracy(synthetic: Any) -> None:
    keys = ("A", "B10", "B50", "B100", "B200")
    tokens, latency = _uniform_inputs(
        dict.fromkeys(keys, 1000), dict.fromkeys(keys, 500),
        dict.fromkeys(keys, 1000.0), dict.fromkeys(keys, 500.0),
    )  # fmt: skip
    outcomes = {
        "B10:mcp": ["correct"],
        "B200:mcp": ["correct", "incorrect"],
        "B200:code": ["correct", "incorrect"],  # 50% vs 100% at other volumes
    }
    summary = summarise(synthetic.build(synthetic.uniform(10, tokens, latency, outcomes=outcomes)))
    assert _verdicts(summary)["H4"] == "not supported"


def test_hypotheses_inconclusive_below_ten_tasks(synthetic: Any) -> None:
    tokens, latency = _uniform_inputs(
        {"A": 1000, "B10": 2000, "B50": 8000, "B100": 8000, "B200": 20000},
        {"A": 1100, "B10": 1000, "B50": 1000, "B100": 1000, "B200": 1000},
        dict.fromkeys(("A", "B10", "B50", "B100", "B200"), 1000.0),
        dict.fromkeys(("A", "B10", "B50", "B100", "B200"), 900.0),
    )
    summary = summarise(synthetic.build(synthetic.uniform(9, tokens, latency)))
    assert set(_verdicts(summary).values()) == {"inconclusive"}
    assert "fewer than 10 measured tasks" in summary.hypotheses[0].evidence


def test_infra_errors_can_make_a_hypothesis_inconclusive(synthetic: Any) -> None:
    keys = ("A", "B10", "B50", "B100", "B200")
    tokens, latency = _uniform_inputs(
        dict.fromkeys(keys, 1000), dict.fromkeys(keys, 1050),
        dict.fromkeys(keys, 1000.0), dict.fromkeys(keys, 1000.0),
    )  # fmt: skip
    outcomes = {"A:mcp": ["correct"] * 9 + ["infra_error"] * 2}  # 11 tasks, 9 measured
    summary = summarise(synthetic.build(synthetic.uniform(11, tokens, latency, outcomes=outcomes)))
    assert _verdicts(summary)["H1"] == "inconclusive"
    assert _verdicts(summary)["H2"] != "inconclusive"


def test_truncated_and_completed_counts(synthetic: Any) -> None:
    call = synthetic.call
    rows = [
        synthetic.row("01-B200-mcp", "B200:mcp", outcome="invalid_answer", tokens=100),
        synthetic.row("02-B200-mcp", "B200:mcp", outcome="incorrect", tokens=100),
        synthetic.row("03-B200-mcp", "B200:mcp", outcome="invalid_answer", tokens=100),
        synthetic.row("04-B200-mcp", "B200:mcp", outcome="infra_error", tokens=0),
        synthetic.row("04-B200-mcp", "B200:mcp", outcome="correct", tokens=100),
        synthetic.row("05-B200-mcp", "B200:mcp", outcome="infra_error", tokens=0),
        synthetic.row("01-B200-code", "B200:code", tokens=50),
    ]
    calls = [
        call("01-B200-mcp", 1, "tool_calls"),
        call("01-B200-mcp", 2, "length"),  # truncated
        call("02-B200-mcp", 1, "length"),  # wrong answer: outcome is incorrect, not counted
        call("03-B200-mcp", 1, "length"),
        call("03-B200-mcp", 2, "stop"),  # invalid answer but the final call finished normally
        call("04-B200-mcp", 1, "length"),  # superseded infra attempt
        call("04-B200-mcp", 1, "tool_calls"),
        call("04-B200-mcp", 2, "stop"),  # latest attempt finished
        call("05-B200-mcp", 1, "length"),  # infra error: not measured
    ]
    summary = summarise(synthetic.build(rows, llm_calls=calls))
    cell = summary.cell("B", 200, "mcp")
    assert cell is not None
    assert (cell.n_measured, cell.n_infra_error) == (4, 1)
    assert cell.n_truncated == 1
    assert cell.completed == 3
    code = summary.cell("B", 200, "code")
    assert code is not None
    assert (code.n_truncated, code.completed) == (0, 1)
    comp = summary.comparison("B", 200)
    assert comp is not None
    assert (comp.mcp_correct, comp.code_correct) == (1, 1)
    assert (comp.mcp_truncated, comp.code_truncated) == (1, 0)
    assert (comp.n_mcp, comp.n_code) == (4, 1)


def test_truncation_counts_in_outputs(synthetic: Any) -> None:
    paths = synthetic.truncated_run(3)
    summary = summarise(paths)
    write_summary(summary, paths)
    loaded = Summary.model_validate_json((paths.processed / "summary.json").read_text())
    cell = loaded.cell("B", 200, "mcp")
    assert cell is not None
    assert (cell.n_truncated, cell.completed) == (3, 0)
    header = (paths.processed / "cells.csv").read_text().splitlines()[0].split(",")
    assert "n_truncated" in header
    assert "completed" in header
    comparison_header = (paths.processed / "comparisons.csv").read_text().splitlines()[0]
    assert "mcp_truncated" in comparison_header


def test_no_llm_calls_file_means_no_truncation(synthetic: Any) -> None:
    rows = [synthetic.row("01-A-mcp", "A:mcp", outcome="invalid_answer")]
    cell = summarise(synthetic.build(rows)).cell("A", None, "mcp")
    assert cell is not None
    assert (cell.n_truncated, cell.completed) == (0, 1)


def _two_volume_run(
    synthetic: Any,
    n: int = 10,
    *,
    lat_code_100: float = 2000.0,
    outcomes: dict[str, list[str]] | None = None,
) -> Summary:
    tokens: dict[str, list[int]] = {}
    latency: dict[str, list[float]] = {}
    for key, mcp_t, code_t, mcp_l, code_l in (
        ("A", 1000, 1100, 1000.0, 1100.0),
        ("B10", 2000, 1000, 1000.0, 900.0),
        ("B100", 12000, 1000, 6000.0, lat_code_100),
    ):
        tokens[f"{key}:mcp"], tokens[f"{key}:code"] = [mcp_t], [code_t]
        latency[f"{key}:mcp"], latency[f"{key}:code"] = [mcp_l], [code_l]
    rows = synthetic.uniform(n, tokens, latency, outcomes=outcomes)
    return summarise(synthetic.build(rows, volumes=(10, 100)))


def test_two_volume_scope_hypotheses_supported(synthetic: Any) -> None:
    outcomes = {"B10:mcp": ["correct"], "B100:mcp": ["correct", "incorrect"]}
    summary = _two_volume_run(synthetic, outcomes=outcomes)
    assert summary.volumes == [10, 100]
    assert _verdicts(summary) == {
        "H1": "supported",
        "H2": "supported",
        "H3": "supported",
        "H4": "supported",
    }
    h3 = summary.hypotheses[2]
    assert "largest measured volume (100)" in h3.statement
    assert "at volume 100: p50 latency mcp 6.00 s vs code 2.00 s (-66.7%)" in h3.evidence
    h4 = summary.hypotheses[3]
    assert "(100)" in h4.statement
    assert "(10)" in h4.statement
    assert "MCP accuracy B10 100.0% vs B100 50.0%" in h4.evidence


def test_two_volume_h3_uses_largest_volume_only(synthetic: Any) -> None:
    # code is faster at 10 but slower at 100: H3 looks only at the largest volume
    summary = _two_volume_run(synthetic, lat_code_100=9000.0)
    assert _verdicts(summary)["H3"] == "not supported"


def test_two_volume_h4_needs_mcp_drop(synthetic: Any) -> None:
    summary = _two_volume_run(synthetic)  # MCP accuracy is 100% at both volumes
    assert _verdicts(summary)["H4"] == "not supported"


def test_single_volume_makes_h2_and_h4_inconclusive(synthetic: Any) -> None:
    tokens = {"A:mcp": [1000], "A:code": [1000], "B100:mcp": [5000], "B100:code": [1000]}
    latency = {k: [1000.0] for k in tokens}
    rows = synthetic.uniform(10, tokens, latency)
    summary = summarise(synthetic.build(rows, volumes=(100,)))
    verdicts = _verdicts(summary)
    assert verdicts["H2"] == verdicts["H4"] == "inconclusive"
    assert "at least 2 Scenario B volume" in summary.hypotheses[1].evidence
    assert verdicts["H3"] != "inconclusive"
