"""Unit tests for the environment helpers (subprocess calls mocked)."""

import subprocess
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_lab.benchmarking import collect_environment, git_state, package_versions

pytestmark = pytest.mark.unit


def _fake_git(
    status: str, sha: str = "abc123\n"
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        out = sha if "rev-parse" in args else status
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    return run


def test_clean_tree() -> None:
    with patch("subprocess.run", _fake_git("")):
        assert git_state(Path(".")) == ("abc123", False)


def test_untracked_results_are_ignored() -> None:
    status = "?? experiments/x/results/raw/run/a.json\n"
    with patch("subprocess.run", _fake_git(status)):
        assert git_state(Path("."))[1] is False


def test_modified_file_is_dirty() -> None:
    with patch("subprocess.run", _fake_git(" M src/a.py\n")):
        assert git_state(Path("."))[1] is True


def test_untracked_elsewhere_is_dirty_unless_ignored() -> None:
    status = "?? notes/a.md\n"
    with patch("subprocess.run", _fake_git(status)):
        assert git_state(Path("."))[1] is True
        assert git_state(Path("."), ignore_untracked_under=("notes/",))[1] is False


def test_git_unavailable() -> None:
    with patch("subprocess.run", side_effect=OSError("no git")):
        assert git_state(Path(".")) == ("unknown", True)


def test_package_versions_and_environment() -> None:
    versions = package_versions(["pydantic", "definitely-not-installed-xyz"])
    assert versions["pydantic"] != "unknown"
    assert versions["definitely-not-installed-xyz"] == "unknown"
    info = collect_environment(["pydantic"])
    assert info.python_version.startswith("3.")
    assert set(info.hardware) == {"machine", "processor", "cpu_count", "memory_gb"}
    assert info.package_versions["pydantic"] == versions["pydantic"]
