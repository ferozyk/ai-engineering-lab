"""Integration tests for the command-line interface (offline)."""

from pathlib import Path

import pytest

from mcp_vs_code_mode import cli
from mcp_vs_code_mode.bench import paths as paths_module

pytestmark = pytest.mark.integration


def test_plan_prints_numbers(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["plan"]) == 0
    out = capsys.readouterr().out
    assert "276" in out
    assert "904" in out
    assert "exceeds the daily cap" in out
    assert "Estimates, not measurements." in out


def test_dry_run_prints_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(paths_module, "RESULTS_DIR", tmp_path / "results")
    assert cli.main(["dry-run", "--iterations", "1"]) == 0
    out = capsys.readouterr().out
    assert "Run id: " in out
    assert "-dry-run" in out
    assert "SIMULATED" in out
    runs = list((tmp_path / "results" / "dry-run").iterdir())
    assert len(runs) == 1
    assert (runs[0] / "raw" / "tasks.jsonl").exists()


def test_run_refuses_dirty_tree(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "git_state", lambda: ("a" * 40, True))
    assert cli.main(["run", "--yes"]) == 1
    assert "--allow-dirty" in capsys.readouterr().out


def test_canary_rejects_invalid_cell_label(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["canary", "--cells", "A:mcp,Z9:code"]) == 2
    assert "Invalid cell label 'Z9:code'" in capsys.readouterr().err


def test_canary_rejects_empty_cells(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["canary", "--cells", " , "]) == 2
    assert "at least one cell" in capsys.readouterr().err


def test_canary_cells_parsing_and_schedule() -> None:
    from mcp_vs_code_mode.bench.cells import build_canary_schedule
    from mcp_vs_code_mode.bench.config import load_config

    labels = cli._parse_cells("A:mcp, B200:code")
    assert labels == ["A:mcp", "B200:code"]
    assert cli._parse_cells(None) is None
    schedule = build_canary_schedule(load_config(), labels)
    assert [t.cell.label for t in schedule] == ["A:mcp", "B200:code"]
    assert [t.task_id for t in schedule] == ["c-A-mcp", "c-B200-code"]
