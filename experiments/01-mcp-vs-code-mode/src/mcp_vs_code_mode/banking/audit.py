"""Audit logging for every banking service call."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

AuditOutcome = Literal["allowed", "denied", "not_found", "invalid", "error"]
Channel = Literal["mcp", "mcp_agg", "code_mode", "test"]


class AuditRecord(BaseModel):
    """One audit entry. ``timestamp`` is timezone-aware UTC."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    principal_id: str
    channel: Channel
    operation: str
    arguments: dict[str, str]
    outcome: AuditOutcome
    duration_ms: float


class AuditLog:
    """In-memory audit log with optional append-only JSONL persistence."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._records: list[AuditRecord] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, entry: AuditRecord) -> None:
        """Append ``entry`` in memory and, if configured, as one JSON line."""
        self._records.append(entry)
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(entry.model_dump_json() + "\n")
                handle.flush()

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        """All records written so far."""
        return tuple(self._records)
