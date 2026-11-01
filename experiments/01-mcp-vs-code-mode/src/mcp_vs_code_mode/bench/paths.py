"""Filesystem layout for benchmark runs."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

EXPERIMENT_DIR = Path(__file__).resolve().parents[3]
CONFIG_PATH = EXPERIMENT_DIR / "configs" / "benchmark.yaml"
RESULTS_DIR = EXPERIMENT_DIR / "results"
DRY_RUN_DIR = RESULTS_DIR / "dry-run"
LINKEDIN_DIR = EXPERIMENT_DIR / "linkedin"

RunKind = Literal["full", "canary", "dry-run"]


def new_run_id(kind: RunKind) -> str:
    """Return a sortable run id such as ``20261101T093000Z-full``."""
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{kind}"


def _kind_from_id(run_id: str) -> RunKind:
    suffix = run_id.rsplit("-", 1)[-1]
    if suffix == "full":
        return "full"
    if suffix == "canary":
        return "canary"
    if suffix == "dry-run":
        return "dry-run"
    raise ValueError(f"Cannot infer run kind from run id {run_id!r}")


@dataclass(frozen=True)
class RunPaths:
    """Output directories for one run."""

    run_id: str
    kind: RunKind
    raw: Path
    processed: Path
    charts: Path
    reports: Path
    linkedin: Path

    @classmethod
    def for_run(cls, run_id: str, kind: RunKind, *, results_dir: Path | None = None) -> "RunPaths":
        """Build paths for ``run_id`` (dry runs live under ``results/dry-run``)."""
        results = results_dir if results_dir is not None else RESULTS_DIR
        if kind == "dry-run":
            base = results / "dry-run" / run_id
            return cls(
                run_id=run_id,
                kind=kind,
                raw=base / "raw",
                processed=base / "processed",
                charts=base / "charts",
                reports=base / "reports",
                linkedin=base / "linkedin",
            )
        linkedin_root = (
            LINKEDIN_DIR / "visual-assets"
            if results_dir is None
            else results.parent / "linkedin" / "visual-assets"
        )
        return cls(
            run_id=run_id,
            kind=kind,
            raw=results / "raw" / run_id,
            processed=results / "processed" / run_id,
            charts=results / "charts" / run_id,
            reports=results / "reports" / run_id,
            linkedin=linkedin_root / run_id,
        )

    @classmethod
    def find(cls, run_id: str, *, results_dir: Path | None = None) -> "RunPaths":
        """Locate an existing run by id (checks both the normal and dry-run locations)."""
        results = results_dir if results_dir is not None else RESULTS_DIR
        for kind in ("full", "canary", "dry-run"):
            candidate = cls.for_run(run_id, kind, results_dir=results_dir)
            if candidate.raw.is_dir():
                return candidate
        raise FileNotFoundError(f"No run {run_id!r} found under {results}")

    def ensure(self) -> None:
        """Create the raw directory (and its transcripts folder)."""
        (self.raw / "transcripts").mkdir(parents=True, exist_ok=True)
