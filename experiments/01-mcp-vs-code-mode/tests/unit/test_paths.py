"""Unit tests for run path helpers."""

from pathlib import Path

import pytest

from mcp_vs_code_mode.bench.paths import EXPERIMENT_DIR, RunPaths, new_run_id

pytestmark = pytest.mark.unit


def test_experiment_dir_has_configs() -> None:
    assert (EXPERIMENT_DIR / "configs").is_dir()


def test_run_id_has_kind_suffix() -> None:
    assert new_run_id("canary").endswith("Z-canary")


def test_dry_run_paths_live_under_dry_run(tmp_path: Path) -> None:
    paths = RunPaths.for_run("r-dry-run", "dry-run", results_dir=tmp_path / "results")
    assert paths.raw == tmp_path / "results" / "dry-run" / "r-dry-run" / "raw"
    assert paths.linkedin.parent.name == "r-dry-run"


def test_find_locates_both_locations(tmp_path: Path) -> None:
    results = tmp_path / "results"
    full = RunPaths.for_run("a-full", "full", results_dir=results)
    full.ensure()
    dry = RunPaths.for_run("b-dry-run", "dry-run", results_dir=results)
    dry.ensure()
    assert RunPaths.find("a-full", results_dir=results).kind == "full"
    assert RunPaths.find("b-dry-run", results_dir=results).kind == "dry-run"
    with pytest.raises(FileNotFoundError):
        RunPaths.find("missing-full", results_dir=results)
