"""Integration test: the whole offline pipeline from dry run to publishable artefacts."""

import json
from pathlib import Path

import pytest

from mcp_vs_code_mode import cli
from mcp_vs_code_mode.bench import paths as paths_module
from mcp_vs_code_mode.bench.charts import CHART_STEMS

pytestmark = pytest.mark.integration


def test_dry_run_publishes_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(paths_module, "RESULTS_DIR", tmp_path / "results")
    assert cli.main(["dry-run", "--iterations", "2"]) == 0
    out = capsys.readouterr().out
    assert "H1" in out
    assert "inconclusive" in out  # n=2 per cell is below the 10-task threshold

    (run_dir,) = (tmp_path / "results" / "dry-run").iterdir()
    processed = run_dir / "processed"
    summary = json.loads((processed / "summary.json").read_text(encoding="utf-8"))
    assert summary["simulated"] is True
    assert len(summary["cells"]) == 8
    for cell in summary["cells"]:
        assert cell["n_measured"] == 2
        assert cell["accuracy"] == 1.0  # the oracle always answers correctly
    assert summary["excluded_warmup_tasks"] == 2
    assert (processed / "cells.csv").exists()
    assert (processed / "comparisons.csv").exists()

    for stem in CHART_STEMS:
        assert (run_dir / "charts" / f"{stem}.png").stat().st_size > 0
        assert (run_dir / "charts" / f"{stem}.svg").stat().st_size > 0
    report = (run_dir / "reports" / "report.md").read_text(encoding="utf-8")
    assert report.startswith("# SIMULATED — Benchmark report")
    for name in ("linkedin-landscape.png", "linkedin-portrait.png"):
        assert (run_dir / "linkedin" / name).stat().st_size > 0


def test_stage_commands_work_on_an_existing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(paths_module, "RESULTS_DIR", tmp_path / "results")
    assert cli.main(["dry-run", "--iterations", "1"]) == 0
    (run_dir,) = (tmp_path / "results" / "dry-run").iterdir()
    run_id = run_dir.name
    for path in (run_dir / "charts").iterdir():
        path.unlink()
    (run_dir / "reports" / "report.md").unlink()
    assert cli.main(["charts", run_id]) == 0
    assert cli.main(["report", run_id]) == 0
    assert cli.main(["linkedin-assets", run_id]) == 0
    assert cli.main(["analyze", run_id]) == 0
    assert "![" in (run_dir / "reports" / "report.md").read_text(encoding="utf-8")


def test_charts_without_summary_is_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(paths_module, "RESULTS_DIR", tmp_path / "results")
    assert cli.main(["charts", "nonexistent-dry-run"]) == 2
    assert "Error:" in capsys.readouterr().err
