"""Integration tests for the command-line interface (offline)."""

from pathlib import Path

import pytest

from mcp_vs_code_mode import cli
from mcp_vs_code_mode.bench import paths as paths_module

pytestmark = pytest.mark.integration


def test_plan_prints_numbers(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["plan"]) == 0
    out = capsys.readouterr().out
    assert "289" in out
    assert "976" in out
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
