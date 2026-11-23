"""Quality gates for the generated corpus: size, shape and wording, with a printable report."""

import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from rag_experiment.config import ChunkingConfig
from rag_experiment.corpus_gen.render import DISCLAIMER
from rag_experiment.ingestion.chunker import chunk_spec
from rag_experiment.ingestion.parser import parse_spec

MIN_CHUNKS = 1800
MAX_CHUNKS = 2400
_FORBIDDEN = ("lorem", "ipsum", "todo", "fixme", "tbd")


class GateError(Exception):
    """One or more quality gates failed; the message lists every problem."""


@dataclass(frozen=True)
class GateReport:
    """Measured size of a corpus."""

    documents: int
    operations: int
    chunks: int
    by_type: dict[str, int]
    by_document: dict[str, int]
    max_chunk_chars: int
    split_chunks: int


def _descriptions(node: object, where: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            here = f"{where}/{key}"
            if key == "description" and isinstance(value, str):
                found.append((here, value))
            else:
                found.extend(_descriptions(value, here))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(_descriptions(value, f"{where}/{i}"))
    return found


def _wording_problems(name: str, data: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    for where, text in _descriptions(data):
        if not text.endswith("."):
            problems.append(f"{name}: description at {where} does not end with a full stop")
        lowered = text.lower()
        problems += [
            f"{name}: description at {where} contains {word!r}"
            for word in _FORBIDDEN
            if word in lowered.replace("\n", " ").split() or f" {word} " in f" {lowered} "
        ]
    return problems


def check_generated(
    files: Mapping[str, bytes],
    originals: Mapping[str, bytes],
    chunking: ChunkingConfig,
    *,
    require_size: bool = True,
) -> GateReport:
    """Parse and chunk every spec; raise :class:`GateError` listing every failed gate."""
    problems: list[str] = []
    by_type: Counter[str] = Counter()
    by_document: dict[str, int] = {}
    longest = 0
    split = 0
    operations = 0
    spec_names = sorted(n for n in files if n.endswith(".yaml"))
    for name, data in originals.items():
        if files.get(name) != data:
            problems.append(f"{name}: the original spec is not a byte-identical copy")
    with tempfile.TemporaryDirectory() as tmp:
        for name in spec_names:
            path = Path(tmp) / name
            path.write_bytes(files[name])
            try:
                spec = parse_spec(path)  # validates the structure and every $ref
            except Exception as exc:
                problems.append(f"{name}: {exc}")
                continue
            ids = [op.operation_id for op in spec.operations]
            if len(ids) != len(set(ids)):
                problems.append(f"{name}: operationIds are not unique")
            operations += len(ids)
            chunks = chunk_spec(spec, chunking)
            by_document[spec.document_id] = len(chunks)
            by_type.update(c.chunk_type for c in chunks)
            longest = max([longest, *(len(c.content) for c in chunks)])
            split += sum(1 for c in chunks if ":p" in c.chunk_id.rsplit(":", 1)[-1])
            if name not in originals:
                loaded = yaml.safe_load(files[name])
                problems += _wording_problems(name, loaded)
                if DISCLAIMER not in str(loaded["info"]["description"]):
                    problems.append(f"{name}: info.description lacks the synthetic-data sentence")
    total = sum(by_document.values())
    if longest > chunking.max_chunk_chars:
        problems.append(f"a chunk has {longest} characters (limit {chunking.max_chunk_chars})")
    if split:
        problems.append(f"{split} chunk(s) were split")
    if require_size and not MIN_CHUNKS <= total <= MAX_CHUNKS:
        problems.append(f"{total} chunks, outside {MIN_CHUNKS}-{MAX_CHUNKS}")
    if problems:
        raise GateError("\n".join(problems))
    return GateReport(
        documents=len(by_document),
        operations=operations,
        chunks=total,
        by_type=dict(by_type),
        by_document=by_document,
        max_chunk_chars=longest,
        split_chunks=split,
    )
