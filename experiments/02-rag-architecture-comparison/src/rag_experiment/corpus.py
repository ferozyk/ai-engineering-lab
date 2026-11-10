"""Loading the whole corpus: parsed specs, raw documents, version and checksum."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from rag_experiment.ingestion.parser import InvalidSpecError, ParsedSpec, load_raw, parse_spec


class Manifest(BaseModel):
    """``datasets/manifest.json``: versions and checksums of the corpus and question set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus_version: str
    corpus_checksum: str
    eval_dev_version: str
    eval_measured_version: str
    eval_measured_status: Literal["draft", "frozen"]
    # sha256 of questions-measured.jsonl, recorded when the set is frozen.
    eval_measured_checksum: str | None = None


@dataclass(frozen=True)
class Corpus:
    """All specs of the corpus plus their raw YAML, for pointer resolution."""

    specs: tuple[ParsedSpec, ...]
    documents: Mapping[str, Mapping[str, object]]
    version: str
    checksum: str


def corpus_checksum(corpus_dir: Path) -> str:
    """SHA-256 over ``name + newline + bytes`` for every YAML file, in name order."""
    digest = hashlib.sha256()
    for path in sorted(corpus_dir.glob("*.yaml")):
        digest.update((path.name + "\n").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_manifest(path: Path) -> Manifest:
    """Read and validate the manifest."""
    try:
        return Manifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise InvalidSpecError(f"{path}: cannot read manifest ({exc})") from exc


def load_corpus(corpus_dir: Path) -> Corpus:
    """Parse every ``*.yaml`` file in name order. The version comes from the sibling manifest."""
    paths = sorted(corpus_dir.glob("*.yaml"))
    if not paths:
        raise InvalidSpecError(f"{corpus_dir}: no *.yaml files found")
    manifest = load_manifest(corpus_dir.parent / "manifest.json")
    return Corpus(
        specs=tuple(parse_spec(p) for p in paths),
        documents={p.stem: load_raw(p) for p in paths},
        version=manifest.corpus_version,
        checksum=corpus_checksum(corpus_dir),
    )
