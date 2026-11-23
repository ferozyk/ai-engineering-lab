"""The two machine-readable catalogues of the large corpus: version changes and look-alike codes.

``CHANGES.json`` and ``IDENTIFIERS.json`` sit next to the generated specs. The clean corpus has
neither, so :func:`load_corpus_facts` returns ``None`` for it.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

CHANGES_FILE = "CHANGES.json"
IDENTIFIERS_FILE = "IDENTIFIERS.json"


class ChangeRecord(BaseModel):
    """One recorded difference between two versions of a product."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    product: str
    from_version: str
    to_version: str
    kind: str
    subject: str
    document: str  # the newer spec
    location: str  # JSON Pointer in the newer spec
    before: str | int | bool | None
    after: str | int | bool | None


class IdentifierRecord(BaseModel):
    """One error code in one version of a product."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    product: str
    version: str
    document: str
    location: str
    status: int
    meaning: str


class CorpusFacts(BaseModel):
    """Everything the validation of stress questions needs to know about the large corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    changes: tuple[ChangeRecord, ...]
    identifiers: tuple[IdentifierRecord, ...]

    @property
    def codes(self) -> frozenset[str]:
        """Every error code in the catalogue."""
        return frozenset(i.code for i in self.identifiers)


def load_corpus_facts(corpus_dir: Path) -> CorpusFacts | None:
    """Read both catalogues; ``None`` when the corpus has none (the clean corpus)."""
    changes_path = corpus_dir / CHANGES_FILE
    identifiers_path = corpus_dir / IDENTIFIERS_FILE
    if not (changes_path.is_file() and identifiers_path.is_file()):
        return None
    try:
        return CorpusFacts(
            changes=tuple(
                ChangeRecord.model_validate(r)
                for r in json.loads(changes_path.read_text(encoding="utf-8"))
            ),
            identifiers=tuple(
                IdentifierRecord.model_validate(r)
                for r in json.loads(identifiers_path.read_text(encoding="utf-8"))
            ),
        )
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"{corpus_dir}: cannot read the corpus catalogues ({exc})") from exc
