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
from pydantic import BaseModel, model_validator

from mcp_vs_code_mode.agent.records import Mode
from mcp_vs_code_mode.bench.cells import Cell, cells_for
from mcp_vs_code_mode.bench.metadata import RunMetadata
from mcp_vs_code_mode.bench.paths import RunPaths
from mcp_vs_code_mode.bench.records import LLMCallRow, TaskRow, load_rows

MIN_TASKS_FOR_VERDICT = 10
H1_THRESHOLD = 0.25
H4_MAX_CODE_ACCURACY_SPREAD = 0.10
H5_MAX_TOKEN_RATIO = 1.25
H5_MIN_ACCURACY = 0.90
H6_MIN_CODE_ACCURACY = 0.90
H6_MIN_ACCURACY_GAP = 0.30

# Comparison pairs (baseline, challenger), in the order they are generated.
COMPARISON_PAIRS: tuple[tuple[Mode, Mode], ...] = (
    ("mcp", "code"),
    ("mcp_agg", "code"),
    ("mcp", "mcp_agg"),
)

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
    n_truncated: int = 0
    completed: int = 0
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

    @model_validator(mode="before")
    @classmethod
    def _default_completed(cls, data: object) -> object:
        """Older summaries lack ``completed``; derive it so they still load."""
        if isinstance(data, dict) and "completed" not in data and "n_measured" in data:
            data = {**data, "completed": data["n_measured"] - data.get("n_truncated", 0)}
        return data


class Comparison(BaseModel):
    """Mode ``mode_b`` (challenger) against mode ``mode_a`` (baseline) at one scenario/volume.

    Reductions are ``(a - b) / a``: positive means the challenger used fewer tokens or less cost.
    """

    scenario: str
    volume: int | None
    mode_a: Mode = "mcp"
    mode_b: Mode = "code"
    tokens_reduction_pct: float | None
    tokens_difference: float | None
    latency_p50_change_pct: float | None
    cost_reduction_pct: float | None
    accuracy_a: float | None
    accuracy_b: float | None
    correct_a: int = 0
    correct_b: int = 0
    truncated_a: int = 0
    truncated_b: int = 0
    n_a: int = 0
    n_b: int = 0

    @model_validator(mode="before")
    @classmethod
    def _rename_legacy_fields(cls, data: object) -> object:
        """Summaries written before 01b used ``*_mcp`` / ``*_code`` field names."""
        if not isinstance(data, dict) or "accuracy_mcp" not in data:
            return data
        renames = {
            "accuracy_mcp": "accuracy_a",
            "accuracy_code": "accuracy_b",
            "mcp_correct": "correct_a",
            "code_correct": "correct_b",
            "mcp_truncated": "truncated_a",
            "code_truncated": "truncated_b",
            "n_mcp": "n_a",
            "n_code": "n_b",
        }
        out = {renames.get(key, key): value for key, value in data.items()}
        out.setdefault("mode_a", "mcp")
        out.setdefault("mode_b", "code")
        return out


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

    def comparison(
        self,
        scenario: str,
        volume: int | None,
        mode_a: Mode = "mcp",
        mode_b: Mode = "code",
    ) -> Comparison | None:
        """Look up the comparison of ``mode_b`` against ``mode_a`` at one scenario/volume."""
        for comp in self.comparisons:
            if (
                comp.scenario == scenario
                and comp.volume == volume
                and comp.mode_a == mode_a
                and comp.mode_b == mode_b
            ):
                return comp
        return None

    @property
    def volumes(self) -> list[int]:
        """Scenario B volumes present in the summary, ascending."""
        return sorted({c.volume for c in self.cells if c.scenario == "B" and c.volume is not None})

    @property
    def c_volumes(self) -> list[int]:
        """Scenario C volumes present in the summary, ascending."""
        return sorted({c.volume for c in self.cells if c.scenario == "C" and c.volume is not None})

    @property
    def modes(self) -> list[Mode]:
        """Modes present in the summary, in canonical order."""
        present = {c.mode for c in self.cells}
        return [m for m in ("mcp", "mcp_agg", "code") if m in present]


def mode_label(mode: str, summary: "Summary") -> str:
    """Display label of a mode; raw MCP is qualified only when the run also has ``mcp_agg``."""
    if mode == "mcp":
        return "MCP (raw tools)" if "mcp_agg" in summary.modes else "MCP"
    if mode == "mcp_agg":
        return "MCP + aggregation tool"
    return "Code Mode"


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


_TRUNCATABLE_OUTCOMES = frozenset({"invalid_answer", "max_turns"})


def truncated_task_ids(paths: RunPaths, frame: pd.DataFrame) -> set[str]:
    """Task ids whose final model call stopped at the output limit (``finish_reason == "length"``).

    Only the latest record of each task counts, and only when it is a measured failure
    (``invalid_answer`` or ``max_turns``). ``llm_calls.jsonl`` is append-only and may hold calls
    of earlier, superseded attempts (turns restart per attempt); the last row written for a task
    id is the final call of its latest attempt, which is the one inspected.
    """
    if not len(frame):
        return set()
    candidates = set(frame.loc[frame["outcome"].isin(_TRUNCATABLE_OUTCOMES), "task_id"])
    last_call: dict[str, LLMCallRow] = {}
    for call in load_rows(paths.raw / "llm_calls.jsonl", LLMCallRow):
        if call.task_id not in candidates:
            continue
        last_call[call.task_id] = call  # file order: the last row is the latest attempt's end
    return {tid for tid, call in last_call.items() if call.finish_reason == "length"}


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


def _cell_stats(cell: Cell, frame: pd.DataFrame, truncated: set[str]) -> CellStats:
    subset = frame[frame["cell"] == cell.label] if len(frame) else frame
    measured = subset[subset["outcome"] != "infra_error"] if len(subset) else subset
    n_measured = len(measured)
    outcomes = {str(k): int(v) for k, v in subset["outcome"].value_counts().items()}
    correct = int((measured["outcome"] == "correct").sum()) if n_measured else 0
    latency_s = measured["latency_ms"] / 1000 if n_measured else measured["latency_ms"]
    cost_mean = _mean(measured["estimated_cost_usd"])
    n_truncated = int(measured["task_id"].isin(truncated).sum()) if n_measured and truncated else 0
    return CellStats(
        cell=cell.label,
        scenario=cell.scenario,
        volume=cell.volume,
        mode=cell.mode,
        n_tasks=len(subset),
        n_measured=n_measured,
        n_infra_error=len(subset) - n_measured,
        n_truncated=n_truncated,
        completed=n_measured - n_truncated,
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


def _compare(scenario: str, volume: int | None, a: CellStats, b: CellStats) -> Comparison:
    """Compare challenger ``b`` against baseline ``a``."""
    difference = (
        None if a.tokens_mean is None or b.tokens_mean is None else a.tokens_mean - b.tokens_mean
    )
    reduction = _relative(difference, a.tokens_mean)
    latency = _relative(
        None
        if a.latency_p50_s is None or b.latency_p50_s is None
        else b.latency_p50_s - a.latency_p50_s,
        a.latency_p50_s,
    )
    cost = _relative(
        None
        if a.cost_usd_mean is None or b.cost_usd_mean is None
        else a.cost_usd_mean - b.cost_usd_mean,
        a.cost_usd_mean,
    )
    return Comparison(
        scenario=scenario,
        volume=volume,
        mode_a=_mode(a.mode),
        mode_b=_mode(b.mode),
        tokens_reduction_pct=_scaled(reduction, 100),
        tokens_difference=difference,
        latency_p50_change_pct=_scaled(latency, 100),
        cost_reduction_pct=_scaled(cost, 100),
        accuracy_a=a.accuracy,
        accuracy_b=b.accuracy,
        correct_a=a.outcomes.get("correct", 0),
        correct_b=b.outcomes.get("correct", 0),
        truncated_a=a.n_truncated,
        truncated_b=b.n_truncated,
        n_a=a.n_measured,
        n_b=b.n_measured,
    )


def _mode(text: str) -> Mode:
    for mode in ("mcp", "mcp_agg", "code"):
        if mode == text:
            return mode
    raise ValueError(f"Unknown mode {text!r}")


def _comparisons(cells: Sequence[CellStats]) -> list[Comparison]:
    by_key = {(c.scenario, c.volume, c.mode): c for c in cells}
    keys = list(dict.fromkeys((c.scenario, c.volume) for c in cells))
    out: list[Comparison] = []
    for scenario, volume in keys:
        for mode_a, mode_b in COMPARISON_PAIRS:
            a, b = by_key.get((scenario, volume, mode_a)), by_key.get((scenario, volume, mode_b))
            if a is not None and b is not None:
                out.append(_compare(scenario, volume, a, b))
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


def _too_few_volumes(
    hid: str, statement: str, present: int, *, needed: int = 2
) -> HypothesisResult:
    return HypothesisResult(
        id=hid,
        statement=statement,
        verdict="inconclusive",
        evidence=f"needs at least {needed} Scenario B volume(s) in the run; {present} present",
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
    if len(pairs) < 2:
        return _too_few_volumes("H2", statement, len(pairs))
    if not _enough(*flat):
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
    statement = (
        "Scenario B: Code Mode has lower p50 latency than MCP at the largest measured volume."
    )
    if not volumes:
        return _too_few_volumes("H3", statement, 0, needed=1)
    largest = max(volumes)
    mcp, code = volumes[largest]
    statement = (
        "Scenario B: Code Mode has lower p50 latency than MCP at the largest measured volume "
        f"({largest})."
    )
    if not _enough(mcp, code):
        return _inconclusive("H3", statement, [mcp, code])
    assert mcp is not None
    assert code is not None
    if mcp.latency_p50_s is None or code.latency_p50_s is None:
        return _inconclusive("H3", statement, [mcp, code])
    change = _relative(code.latency_p50_s - mcp.latency_p50_s, mcp.latency_p50_s)
    evidence = (
        f"at volume {largest}: p50 latency mcp {_sec(mcp.latency_p50_s)} vs "
        f"code {_sec(code.latency_p50_s)} ({_signed_pct(change)})"
    )
    return HypothesisResult(
        id="H3",
        statement=statement,
        verdict="supported" if code.latency_p50_s < mcp.latency_p50_s else "not supported",
        evidence=evidence,
    )


def _pct_text(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _h4(volumes: dict[int, tuple[CellStats | None, CellStats | None]]) -> HypothesisResult:
    statement = (
        "MCP accuracy at the largest measured volume is lower than at the smallest; Code Mode "
        "accuracy max - min across measured volumes is at most 10 percentage points."
    )
    if len(volumes) < 2:
        return _too_few_volumes("H4", statement, len(volumes))
    smallest, largest = min(volumes), max(volumes)
    statement = (
        f"MCP accuracy at the largest measured volume ({largest}) is lower than at the smallest "
        f"({smallest}); Code Mode accuracy max - min across measured volumes "
        f"({', '.join(str(v) for v in sorted(volumes))}) is at most 10 percentage points."
    )
    mcp_low = volumes[smallest][0]
    mcp_high = volumes[largest][0]
    code_cells = [pair[1] for pair in volumes.values()]
    required = [mcp_low, mcp_high, *code_cells]
    if not _enough(*required):
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
        f"MCP accuracy B{smallest} {_pct_text(mcp_low.accuracy)} vs "
        f"B{largest} {_pct_text(mcp_high.accuracy)}; "
        f"Code Mode accuracy spread across volumes {spread * 100:.1f} percentage points"
    )
    return HypothesisResult(
        id="H4",
        statement=statement,
        verdict="supported" if decreases and stable else "not supported",
        evidence=evidence,
    )


_H5_STATEMENT = (
    "Scenario B: server-side data reduction alone closes the chained-task gap. At the largest "
    "volume, mean total tokens of MCP + aggregation tool are at most 1.25 times those of Code "
    "Mode, and its accuracy is at least 90%."
)
_H6_STATEMENT = (
    "Scenario C: code execution buys flexibility. At the largest Scenario C volume, Code Mode "
    "accuracy is at least 90%, MCP + aggregation tool accuracy is at least 30 percentage points "
    "lower, and Code Mode uses fewer mean total tokens."
)
_NOT_IN_RUN = "mode/scenario not in this run"


def _h5(agg: CellStats | None, code: CellStats | None, volume: int | None) -> HypothesisResult:
    if agg is None or code is None:
        return HypothesisResult(
            id="H5", statement=_H5_STATEMENT, verdict="inconclusive", evidence=_NOT_IN_RUN
        )
    if not _enough(agg, code):
        return _inconclusive("H5", _H5_STATEMENT, [agg, code])
    if (
        agg.tokens_mean is None
        or code.tokens_mean is None
        or agg.accuracy is None
        or code.accuracy is None
        or code.tokens_mean == 0
    ):
        return _inconclusive("H5", _H5_STATEMENT, [agg, code])
    ratio = agg.tokens_mean / code.tokens_mean
    ok = ratio <= H5_MAX_TOKEN_RATIO + 1e-12 and agg.accuracy >= H5_MIN_ACCURACY - 1e-12
    evidence = (
        f"B{volume}: tokens mcp_agg {_int(agg.tokens_mean)} vs code {_int(code.tokens_mean)} "
        f"(ratio {ratio:.2f}); accuracy mcp_agg {_pct_text(agg.accuracy)} vs "
        f"code {_pct_text(code.accuracy)}"
    )
    return HypothesisResult(
        id="H5",
        statement=_H5_STATEMENT,
        verdict="supported" if ok else "not supported",
        evidence=evidence,
    )


def _h6(agg: CellStats | None, code: CellStats | None, volume: int | None) -> HypothesisResult:
    if agg is None or code is None:
        return HypothesisResult(
            id="H6", statement=_H6_STATEMENT, verdict="inconclusive", evidence=_NOT_IN_RUN
        )
    if not _enough(agg, code):
        return _inconclusive("H6", _H6_STATEMENT, [agg, code])
    if (
        agg.tokens_mean is None
        or code.tokens_mean is None
        or agg.accuracy is None
        or code.accuracy is None
    ):
        return _inconclusive("H6", _H6_STATEMENT, [agg, code])
    ok = (
        code.accuracy >= H6_MIN_CODE_ACCURACY - 1e-12
        and agg.accuracy <= code.accuracy - H6_MIN_ACCURACY_GAP + 1e-12
        and code.tokens_mean < agg.tokens_mean
    )
    evidence = (
        f"C{volume}: accuracy code {_pct_text(code.accuracy)} vs mcp_agg "
        f"{_pct_text(agg.accuracy)}; tokens code {_int(code.tokens_mean)} vs "
        f"mcp_agg {_int(agg.tokens_mean)}"
    )
    return HypothesisResult(
        id="H6",
        statement=_H6_STATEMENT,
        verdict="supported" if ok else "not supported",
        evidence=evidence,
    )


def _evaluate(cells: Sequence[CellStats]) -> list[HypothesisResult]:
    by_key = {(c.scenario, c.volume, c.mode): c for c in cells}
    volumes = sorted({c.volume for c in cells if c.scenario == "B" and c.volume is not None})
    c_volumes = sorted({c.volume for c in cells if c.scenario == "C" and c.volume is not None})
    pairs = {v: (by_key.get(("B", v, "mcp")), by_key.get(("B", v, "code"))) for v in volumes}
    b_top = max(volumes) if volumes else None
    c_top = max(c_volumes) if c_volumes else None
    return [
        _h1(by_key.get(("A", None, "mcp")), by_key.get(("A", None, "code"))),
        _h2(list(pairs.values())),
        _h3(pairs),
        _h4(pairs),
        _h5(by_key.get(("B", b_top, "mcp_agg")), by_key.get(("B", b_top, "code")), b_top),
        _h6(by_key.get(("C", c_top, "mcp_agg")), by_key.get(("C", c_top, "code")), c_top),
    ]


# --------------------------------------------------------------------------- public API


def summarise(paths: RunPaths) -> Summary:
    """Compute the processed summary for the run at ``paths`` (no network, raw data only)."""
    metadata = RunMetadata.model_validate_json(
        (paths.raw / "run_metadata.json").read_text(encoding="utf-8")
    )
    frame, warmups, superseded = _load_frame(paths)
    config = metadata.config
    volumes = [int(v) for v in config.get("volumes", [])]
    modes = [str(m) for m in config.get("modes", ["mcp", "code"])]
    scenario_c = config.get("scenario_c") or {}
    truncated = truncated_task_ids(paths, frame)
    cells = [
        _cell_stats(cell, frame, truncated)
        for cell in cells_for(
            modes,
            volumes,
            [int(v) for v in scenario_c.get("volumes", [])],
            [str(m) for m in scenario_c.get("modes", [])],
        )
    ]
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
