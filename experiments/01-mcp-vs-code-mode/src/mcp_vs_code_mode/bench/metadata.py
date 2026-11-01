"""Run metadata and environment collection."""

import os
import platform
import subprocess
import sys
from datetime import datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mcp_vs_code_mode.bench.openrouter import FreeModelDailyRequests
from mcp_vs_code_mode.bench.paths import EXPERIMENT_DIR, RunKind
from mcp_vs_code_mode.bench.pricing import PricingSnapshot

_PACKAGES = ("mcp", "openai", "pydantic-monty", "pandas", "matplotlib", "httpx")


class RunMetadata(BaseModel):
    """Everything recorded about a run (written at start, rewritten at the end)."""

    run_id: str
    kind: RunKind
    simulated: bool
    experiment: str
    experiment_version: str
    git_sha: str
    git_dirty: bool
    started_at: datetime
    finished_at: datetime | None = None
    hardware: dict[str, str]
    os: str
    python_version: str
    provider: str
    model_id: str
    models_served: list[str] = []
    providers_served: list[str] = []
    dataset_version: str
    dataset_checksum: str
    config: dict[str, Any]
    iterations: int
    tasks_planned: int
    tasks_completed: int = 0
    failed_requests: int = 0
    requests_sent: int = 0
    infra_errors: int = 0
    package_versions: dict[str, str]
    pricing: PricingSnapshot
    max_turns: int
    rate_limit_per_minute: int
    daily_request_cap: int
    order_seed: int
    llm_seed: int | None
    mcp_connect_ms: float = 0.0
    sandbox_warmup_ms: float = 0.0
    free_model_daily_requests_before: FreeModelDailyRequests | None = None
    free_model_daily_requests_after: FreeModelDailyRequests | None = None
    halted: bool = False
    halt_reason: str | None = None


def _git(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=EXPERIMENT_DIR,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout


def git_state() -> tuple[str, bool]:
    """Return ``(commit sha, dirty)``; untracked files under ``results/`` are ignored."""
    sha = (_git("rev-parse", "HEAD") or "unknown").strip()
    status = _git("status", "--porcelain", "--untracked-files=all")
    if status is None:
        return sha, True
    dirty = False
    for line in status.splitlines():
        path = line[3:]
        if line.startswith("??") and "/results/" in f"/{path}":
            continue
        dirty = True
        break
    return sha, dirty


def _memory_gb() -> str:
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


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _PACKAGES:
        try:
            versions[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            versions[name] = "unknown"
    return versions


def collect_environment() -> dict[str, Any]:
    """Hardware, OS, Python and package versions."""
    return {
        "hardware": {
            "machine": platform.machine() or "unknown",
            "processor": platform.processor() or "unknown",
            "cpu_count": str(os.cpu_count() or "unknown"),
            "memory_gb": _memory_gb(),
        },
        "os": platform.platform(),
        "python_version": platform.python_version(),
        "package_versions": _package_versions(),
    }
