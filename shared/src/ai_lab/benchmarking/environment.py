"""Collect the environment a benchmark ran in: git state, hardware, OS and package versions."""

import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from importlib import metadata as importlib_metadata
from pathlib import Path

from pydantic import BaseModel


class EnvironmentInfo(BaseModel):
    """Hardware, OS, Python and package versions."""

    hardware: dict[str, str]
    os: str
    python_version: str
    package_versions: dict[str, str]


def _git(repo_path: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout


def git_state(
    repo_path: Path, ignore_untracked_under: Sequence[str] = ("results/",)
) -> tuple[str, bool]:
    """Return ``(commit sha, dirty)``.

    Untracked files under any folder named in ``ignore_untracked_under`` do not make the tree
    dirty (generated results must not invalidate their own run).
    """
    sha = (_git(repo_path, "rev-parse", "HEAD") or "unknown").strip()
    status = _git(repo_path, "status", "--porcelain", "--untracked-files=all")
    if status is None:
        return sha, True
    for line in status.splitlines():
        path = line[3:]
        if line.startswith("??") and any(
            f"/{part}" in f"/{path}" for part in ignore_untracked_under
        ):
            continue
        return sha, True
    return sha, False


def memory_gb() -> str:
    """Total RAM in GiB as a string, or ``"unknown"``."""
    try:
        if sys.platform == "darwin":
            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout
            return f"{int(out.strip()) / 1024**3:.1f}"
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    return f"{int(line.split()[1]) / 1024**2:.1f}"
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return "unknown"


def package_versions(names: Sequence[str]) -> dict[str, str]:
    """Installed version of each package, or ``"unknown"``."""
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            versions[name] = "unknown"
    return versions


def collect_environment(packages: Sequence[str]) -> EnvironmentInfo:
    """Hardware, OS, Python version and the versions of ``packages``."""
    return EnvironmentInfo(
        hardware={
            "machine": platform.machine() or "unknown",
            "processor": platform.processor() or "unknown",
            "cpu_count": str(os.cpu_count() or "unknown"),
            "memory_gb": memory_gb(),
        },
        os=platform.platform(),
        python_version=platform.python_version(),
        package_versions=package_versions(packages),
    )
