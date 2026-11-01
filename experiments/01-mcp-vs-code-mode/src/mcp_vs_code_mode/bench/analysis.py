"""Turn the raw task records of a run into processed statistics and hypothesis verdicts.

Everything here is computed from ``tasks.jsonl`` and ``run_metadata.json``. Statistics cover
measured tasks (outcome other than ``infra_error``); accuracy uses the same denominator.
"""

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from itertools import pairwise
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel

from mcp_vs_code_mode.bench.cells import Cell, all_cells
from mcp_vs_code_mode.bench.metadata import RunMetadata
from mcp_vs_code_mode.bench.paths import RunPaths
from mcp_vs_code_mode.bench.records import TaskRow, load_rows

MIN_TASKS_FOR_VERDICT = 10
H1_THRESHOLD = 0.25
H4_MAX_CODE_ACCURACY_SPREAD = 0.10

Verdict = Literal["supported", "not supported", "inconclusive"]


class CellStats(BaseModel):
    """Aggregated statistics for one (scenario, volume, mode) cell."""

    cell: str
    scenario: str
    volume: int | None
    mode: str
    n_tasks: int
    n_measured: int
    n_infra_error: int
    outcomes: dict[str, int]
    accuracy: float | None
    mean_partial_score: float | None
    tokens_mean: float | None
    tokens_median: float | None
    tokens_min: float | None
    tokens_max: float | None
    tokens_std: float | None
    input_tokens_mean: float | None
    output_tokens_mean: float | None
    reasoning_tokens_mean: float | None
    peak_prompt_tokens_mean: float | None
    peak_prompt_tokens_max: float | None
    latency_mean_s: float | None
    latency_p50_s: float | None
    latency_p95_s: float | None
    latency_min_s: float | None
    latency_max_s: float | None
    llm_s_mean: float | None
    tool_s_mean: float | None
    overhead_s_mean: float | None
    client_wait_s_mean: float | None
    model_calls_mean: float | None
    tool_calls_mean: float | None
    tool_errors_mean: float | None
    cost_usd_mean: float | None
    cost_usd_per_1k_tasks: float | None


class Comparison(BaseModel):
    """Code Mode against MCP at one scenario/volume."""

    scenario: str
    volume: int | None
    tokens_reduction_pct: float | None
    tokens_difference: float | None
    latency_p50_change_pct: float | None
    cost_reduction_pct: float | None
    accuracy_mcp: float | None
    accuracy_code: float | None


class HypothesisResult(BaseModel):
    """Verdict for one pre-registered hypothesis, with the numbers behind it."""

    id: str
    statement: str
    verdict: Verdict
    evidence: str


class Summary(BaseModel):
    """Processed output for one run (``processed/summary.json``)."""

    run_id: str
    simulated: bool
    model_id: str
    generated_at: datetime
    metadata: RunMetadata
    cells: list[CellStats]
    comparisons: list[Comparison]
    hypotheses: list[HypothesisResult]
    excluded_warmup_tasks: int
    superseded_records: int

    def cell(self, scenario: str, volume: int | None, mode: str) -> CellStats | None:
        """Look up one cell, or ``None`` when it is not in the summary."""
        for stats in self.cells:
            if stats.scenario == scenario and stats.volume == volume and stats.mode == mode:
                return stats
        return None

    def comparison(self, scenario: str, volume: int | None) -> Comparison | None:
        """Look up the comparison at one scenario/volume."""
        for comp in self.comparisons:
            if comp.scenario == scenario and comp.volume == volume:
                return comp
        return None

    @property
    def volumes(self) -> list[int]:
        """Scenario B volumes present in the summary, ascending."""
        return sorted({c.volume for c in self.cells if c.volume is not None})


# --------------------------------------------------------------------------- loading


def _load_frame(paths: RunPaths) -> tuple[pd.DataFrame, int, int]:
    """Latest record per task id, warm-ups removed; also return (warm-ups, superseded)."""
    rows = load_rows(paths.raw / "tasks.jsonl", TaskRow)
    latest: dict[str, TaskRow] = {}
    for row in rows:
        latest[row.task_id] = row
    superseded = len(rows) - len(latest)
    warmups = sum(1 for row in latest.values() if row.warmup)
    kept = [row for row in latest.values() if not row.warmup]
    records = [row.model_dump(mode="python") for row in kept]
    frame = pd.DataFrame.from_records(records, columns=list(TaskRow.model_fields))
    return frame, warmups, superseded


def load_tasks(paths: RunPaths) -> pd.DataFrame:
    """Latest record per ``task_id`` (by file order) with warm-up tasks excluded."""
    return _load_frame(paths)[0]


# --------------------------------------------------------------------------- statistics


def _clean(value: float | None) -> float | None:
    if value is None or math.isnan(value) or math.isinf(value):
        return None
    return float(value)


def _mean(values: pd.Series) -> float | None:
    return _clean(float(np.mean(values.to_numpy(dtype=float)))) if len(values) else None


def _pct(values: pd.Series, q: float) -> float | None:
    if not len(values):
        return None
    return _clean(float(np.percentile(values.to_numpy(dtype=float), q, method="linear")))


def _extreme(values: pd.Series, fn: str) -> float | None:
    if not len(values):
        return None
    array = values.to_numpy(dtype=float)
    return _clean(float(array.min() if fn == "min" else array.max()))


def _std(values: pd.Series) -> float | None:
    if len(values) < 2:
        return None
    return _clean(float(np.std(values.to_numpy(dtype=float), ddof=1)))


def _scaled(value: float | None, factor: float) -> float | None:
    return None if value is None else value * factor


def _cell_stats(cell: Cell, frame: pd.DataFrame) -> CellStats:
    subset = frame[frame["cell"] == cell.label] if len(frame) else frame
    measured = subset[subset["outcome"] != "infra_error"] if len(subset) else subset
    n_measured = len(measured)
    outcomes = {str(k): int(v) for k, v in subset["outcome"].value_counts().items()}
    correct = int((measured["outcome"] == "correct").sum()) if n_measured else 0
    latency_s = measured["latency_ms"] / 1000 if n_measured else measured["latency_ms"]
    cost_mean = _mean(measured["estimated_cost_usd"])
    return CellStats(
        cell=cell.label,
        scenario=cell.scenario,
        volume=cell.volume,
        mode=cell.mode,
        n_tasks=len(subset),
        n_measured=n_measured,
        n_infra_error=len(subset) - n_measured,
        outcomes=outcomes,
        accuracy=_clean(correct / n_measured) if n_measured else None,
        mean_partial_score=_mean(measured["partial_score"]),
        tokens_mean=_mean(measured["total_tokens"]),
        tokens_median=_pct(measured["total_tokens"], 50),
        tokens_min=_extreme(measured["total_tokens"], "min"),
        tokens_max=_extreme(measured["total_tokens"], "max"),
        tokens_std=_std(measured["total_tokens"]),
        input_tokens_mean=_mean(measured["input_tokens"]),
        output_tokens_mean=_mean(measured["output_tokens"]),
        reasoning_tokens_mean=_mean(measured["reasoning_tokens"]),
        peak_prompt_tokens_mean=_mean(measured["peak_prompt_tokens"]),
        peak_prompt_tokens_max=_extreme(measured["peak_prompt_tokens"], "max"),
        latency_mean_s=_mean(latency_s),
        latency_p50_s=_pct(latency_s, 50),
        latency_p95_s=_pct(latency_s, 95),
        latency_min_s=_extreme(latency_s, "min"),
        latency_max_s=_extreme(latency_s, "max"),
        llm_s_mean=_scaled(_mean(measured["llm_ms"]), 1 / 1000),
        tool_s_mean=_scaled(_mean(measured["tool_ms"]), 1 / 1000),
        overhead_s_mean=_scaled(_mean(measured["overhead_ms"]), 1 / 1000),
        client_wait_s_mean=_scaled(_mean(measured["client_wait_ms"]), 1 / 1000),
        model_calls_mean=_mean(measured["model_calls"]),
        tool_calls_mean=_mean(measured["tool_call_count"]),
        tool_errors_mean=_mean(measured["tool_errors"]),
        cost_usd_mean=cost_mean,
        cost_usd_per_1k_tasks=_scaled(cost_mean, 1000),
    )


def _relative(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _compare(scenario: str, volume: int | None, mcp: CellStats, code: CellStats) -> Comparison:
    reduction = _relative(
        None
        if mcp.tokens_mean is None or code.tokens_mean is None
        else mcp.tokens_mean - code.tokens_mean,
        mcp.tokens_mean,
    )
    latency = _relative(
        None
        if mcp.latency_p50_s is None or code.latency_p50_s is None
        else code.latency_p50_s - mcp.latency_p50_s,
        mcp.latency_p50_s,
    )
    cost = _relative(
        None
        if mcp.cost_usd_mean is None or code.cost_usd_mean is None
        else mcp.cost_usd_mean - code.cost_usd_mean,
        mcp.cost_usd_mean,
    )
    difference = (
        None
        if mcp.tokens_mean is None or code.tokens_mean is None
        else mcp.tokens_mean - code.tokens_mean
    )
    return Comparison(
        scenario=scenario,
        volume=volume,
        tokens_reduction_pct=_scaled(reduction, 100),
        tokens_difference=difference,
        latency_p50_change_pct=_scaled(latency, 100),
        cost_reduction_pct=_scaled(cost, 100),
        accuracy_mcp=mcp.accuracy,
        accuracy_code=code.accuracy,
    )


def _comparisons(cells: Sequence[CellStats]) -> list[Comparison]:
    by_key = {(c.scenario, c.volume, c.mode): c for c in cells}
    keys = list(dict.fromkeys((c.scenario, c.volume) for c in cells))
    out: list[Comparison] = []
    for scenario, volume in keys:
        mcp, code = by_key.get((scenario, volume, "mcp")), by_key.get((scenario, volume, "code"))
        if mcp is not None and code is not None:
            out.append(_compare(scenario, volume, mcp, code))
    return out


# --------------------------------------------------------------------------- hypotheses


def _int(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.0f}"


def _sec(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f} s"


def _signed_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:+.1f}%"


def _enough(*cells: CellStats | None) -> bool:
    return all(c is not None and c.n_measured >= MIN_TASKS_FOR_VERDICT for c in cells)


def _label(stats: CellStats | None) -> str:
    return "A" if stats is None or stats.volume is None else f"B{stats.volume}"


def _inconclusive(hid: str, statement: str, cells: Sequence[CellStats | None]) -> HypothesisResult:
    parts = [f"{c.cell}: n={c.n_measured}" if c is not None else "cell missing" for c in cells]
    return HypothesisResult(
        id=hid,
        statement=statement,
        verdict="inconclusive",
        evidence=f"fewer than {MIN_TASKS_FOR_VERDICT} measured tasks in a required cell ("
        + "; ".join(parts)
        + ")",
    )


def _h1(mcp: CellStats | None, code: CellStats | None) -> HypothesisResult:
    statement = (
        "Scenario A: mean total tokens and p50 latency differ by less than 25% between modes."
    )
    if mcp is None or code is None or not _enough(mcp, code):
        return _inconclusive("H1", statement, [mcp, code])
    token_rel = _relative(
        None
        if code.tokens_mean is None or mcp.tokens_mean is None
        else code.tokens_mean - mcp.tokens_mean,
        mcp.tokens_mean,
    )
    latency_rel = _relative(
        None
        if code.latency_p50_s is None or mcp.latency_p50_s is None
        else code.latency_p50_s - mcp.latency_p50_s,
        mcp.latency_p50_s,
    )
    if token_rel is None or latency_rel is None:
        return _inconclusive("H1", statement, [mcp, code])
    ok = abs(token_rel) < H1_THRESHOLD and abs(latency_rel) < H1_THRESHOLD
    evidence = (
        f"A: tokens mcp {_int(mcp.tokens_mean)} vs code {_int(code.tokens_mean)} "
        f"({_signed_pct(token_rel)}); p50 latency mcp {_sec(mcp.latency_p50_s)} vs "
        f"code {_sec(code.latency_p50_s)} ({_signed_pct(latency_rel)})"
    )
    return HypothesisResult(
        id="H1",
        statement=statement,
        verdict="supported" if ok else "not supported",
        evidence=evidence,
    )


def _h2(pairs: Sequence[tuple[CellStats | None, CellStats | None]]) -> HypothesisResult:
    statement = (
        "Scenario B: Code Mode uses fewer mean total tokens than MCP at every volume, "
        "and the gap widens with volume."
    )
    flat = [c for pair in pairs for c in pair]
    if not pairs or not _enough(*flat):
        return _inconclusive("H2", statement, flat)
    parts: list[str] = []
    fewer = True
    gaps: list[float] = []
    for mcp, code in pairs:
        assert mcp is not None
        assert code is not None
        if mcp.tokens_mean is None or code.tokens_mean is None:
            return _inconclusive("H2", statement, flat)
        gap = mcp.tokens_mean - code.tokens_mean
        gaps.append(gap)
        fewer = fewer and code.tokens_mean < mcp.tokens_mean
        parts.append(
            f"{_label(mcp)}: tokens mcp {_int(mcp.tokens_mean)} vs code {_int(code.tokens_mean)} "
            f"(gap {gap:,.0f})"
        )
    widening = all(later > earlier for earlier, later in pairwise(gaps))
    return HypothesisResult(
        id="H2",
        statement=statement,
        verdict="supported" if fewer and widening else "not supported",
        evidence="; ".join(parts),
    )


def _h3(volumes: dict[int, tuple[CellStats | None, CellStats | None]]) -> HypothesisResult:
    statement = "Scenario B: Code Mode has lower p50 latency than MCP at volumes 50 and 200."
    required = [volumes.get(50, (None, None)), volumes.get(200, (None, None))]
    flat = [c for pair in required for c in pair]
    if not _enough(*flat):
        return _inconclusive("H3", statement, flat)
    parts: list[str] = []
    faster = True
    for mcp, code in required:
        assert mcp is not None
        assert code is not None
        if mcp.latency_p50_s is None or code.latency_p50_s is None:
            return _inconclusive("H3", statement, flat)
        faster = faster and code.latency_p50_s < mcp.latency_p50_s
        change = _relative(code.latency_p50_s - mcp.latency_p50_s, mcp.latency_p50_s)
        parts.append(
            f"{_label(mcp)}: p50 latency mcp {_sec(mcp.latency_p50_s)} vs "
            f"code {_sec(code.latency_p50_s)} ({_signed_pct(change)})"
        )
    return HypothesisResult(
        id="H3",
        statement=statement,
        verdict="supported" if faster else "not supported",
        evidence="; ".join(parts),
    )


def _pct_text(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _h4(volumes: dict[int, tuple[CellStats | None, CellStats | None]]) -> HypothesisResult:
    statement = (
        "MCP accuracy decreases from volume 10 to 200; Code Mode accuracy stays within "
        "10 percentage points across volumes."
    )
    mcp_low, _ = volumes.get(10, (None, None))
    mcp_high, _ = volumes.get(200, (None, None))
    code_cells = [pair[1] for pair in volumes.values()]
    required = [mcp_low, mcp_high, *code_cells]
    if not volumes or not _enough(*required):
        return _inconclusive("H4", statement, required)
    assert mcp_low is not None
    assert mcp_high is not None
    code_acc = [c.accuracy for c in code_cells if c is not None and c.accuracy is not None]
    if mcp_low.accuracy is None or mcp_high.accuracy is None or len(code_acc) != len(code_cells):
        return _inconclusive("H4", statement, required)
    decreases = mcp_high.accuracy < mcp_low.accuracy
    spread = max(code_acc) - min(code_acc)
    stable = spread <= H4_MAX_CODE_ACCURACY_SPREAD + 1e-12
    evidence = (
        f"MCP accuracy B10 {_pct_text(mcp_low.accuracy)} vs B200 {_pct_text(mcp_high.accuracy)}; "
        f"Code Mode accuracy spread across volumes {spread * 100:.1f} percentage points"
    )
    return HypothesisResult(
        id="H4",
        statement=statement,
        verdict="supported" if decreases and stable else "not supported",
        evidence=evidence,
    )


def _evaluate(cells: Sequence[CellStats]) -> list[HypothesisResult]:
    by_key = {(c.scenario, c.volume, c.mode): c for c in cells}
    volumes = sorted({c.volume for c in cells if c.volume is not None})
    pairs = {v: (by_key.get(("B", v, "mcp")), by_key.get(("B", v, "code"))) for v in volumes}
    return [
        _h1(by_key.get(("A", None, "mcp")), by_key.get(("A", None, "code"))),
        _h2(list(pairs.values())),
        _h3(pairs),
        _h4(pairs),
    ]


# --------------------------------------------------------------------------- public API


def summarise(paths: RunPaths) -> Summary:
    """Compute the processed summary for the run at ``paths`` (no network, raw data only)."""
    metadata = RunMetadata.model_validate_json(
        (paths.raw / "run_metadata.json").read_text(encoding="utf-8")
    )
    frame, warmups, superseded = _load_frame(paths)
    volumes = [int(v) for v in metadata.config.get("volumes", [])]
    cells = [_cell_stats(cell, frame) for cell in all_cells(volumes)]
    return Summary(
        run_id=metadata.run_id,
        simulated=metadata.simulated,
        model_id=metadata.model_id,
        generated_at=datetime.now(UTC),
        metadata=metadata,
        cells=cells,
        comparisons=_comparisons(cells),
        hypotheses=_evaluate(cells),
        excluded_warmup_tasks=warmups,
        superseded_records=superseded,
    )


def write_summary(summary: Summary, paths: RunPaths) -> None:
    """Write ``summary.json``, ``cells.csv`` and ``comparisons.csv`` under ``processed/``."""
    paths.processed.mkdir(parents=True, exist_ok=True)
    (paths.processed / "summary.json").write_text(
        summary.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    cell_records = [c.model_dump(mode="json") for c in summary.cells]
    for record in cell_records:
        record["outcomes"] = ";".join(f"{k}={v}" for k, v in sorted(record["outcomes"].items()))
    pd.DataFrame.from_records(cell_records).to_csv(paths.processed / "cells.csv", index=False)
    pd.DataFrame.from_records([c.model_dump(mode="json") for c in summary.comparisons]).to_csv(
        paths.processed / "comparisons.csv", index=False
    )
