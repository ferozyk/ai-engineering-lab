"""Generate the whole large corpus in memory: specs, ``CHANGES.json`` and ``IDENTIFIERS.json``.

The output is a mapping of file name to bytes and depends on nothing but the vocabulary, the
templates and ``SEED``: it is the same on every run and on every machine.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from rag_experiment.corpus_gen.evolve import Change, State, evolve, initial_state
from rag_experiment.corpus_gen.render import document_id, first_response_with, locate, render
from rag_experiment.corpus_gen.vocab import PRODUCTS

CHANGES_FILE = "CHANGES.json"
IDENTIFIERS_FILE = "IDENTIFIERS.json"
V3_COUNT = 8


@dataclass(frozen=True)
class GeneratedCorpus:
    """The generated files and the structured records behind the two JSON files."""

    files: dict[str, bytes]
    changes: list[dict[str, Any]]
    identifiers: list[dict[str, Any]]


def v3_products() -> frozenset[str]:
    """Every second product by sorted key, up to eight, also has a v3."""
    keys = sorted(p.key for p in PRODUCTS)
    return frozenset(keys[::2][:V3_COUNT])


def dump_yaml(doc: dict[str, Any]) -> bytes:
    """One spec as YAML bytes: insertion order kept, no folding, ``\\n`` line endings."""
    text = yaml.safe_dump(
        doc, sort_keys=False, default_flow_style=False, allow_unicode=True, width=10_000
    )
    return text.encode("utf-8")


def dump_json(records: list[dict[str, Any]]) -> bytes:
    """A JSON list with sorted keys, two-space indent and a final newline."""
    return (json.dumps(records, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _identifier_records(state: State, doc_id: str, doc: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for error in state.errors:
        clause = error.clause
        records.append(
            {
                "code": error.code,
                "product": state.product.key,
                "version": f"v{state.version}",
                "document": doc_id,
                "location": first_response_with(doc, error.code),
                "status": error.status,
                "meaning": clause[:1].upper() + clause[1:] + ".",
            }
        )
    return records


def _change_record(
    state: State, newer_doc: dict[str, Any], doc_id: str, change: Change
) -> dict[str, Any]:
    return {
        "product": state.product.key,
        "from_version": f"v{state.version - 1}",
        "to_version": f"v{state.version}",
        "kind": change.kind,
        "subject": change.subject,
        "document": doc_id,
        "location": locate(newer_doc, state, change.probe),
        "before": change.before,
        "after": change.after,
    }


def generate(source_corpus: Path) -> GeneratedCorpus:
    """Build every file of the large corpus. ``source_corpus`` holds the five original specs."""
    files: dict[str, bytes] = {}
    for path in sorted(source_corpus.glob("*.yaml")):
        files[path.name] = path.read_bytes()
    changes: list[dict[str, Any]] = []
    identifiers: list[dict[str, Any]] = []
    with_v3 = v3_products()
    for index, product in enumerate(PRODUCTS):
        state = initial_state(product, index)
        versions = 3 if product.key in with_v3 else 2
        while True:
            doc = render(state)
            doc_id = document_id(product, state.version)
            files[f"{doc_id}.yaml"] = dump_yaml(doc)
            identifiers.extend(_identifier_records(state, doc_id, doc))
            if state.version == versions:
                break
            state, step_changes = evolve(state, product.key in with_v3, product.key)
            newer = render(state)
            newer_id = document_id(product, state.version)
            changes.extend(_change_record(state, newer, newer_id, c) for c in step_changes)
    changes.sort(key=lambda r: (r["product"], r["from_version"], r["location"], r["kind"]))
    identifiers.sort(key=lambda r: (r["product"], r["version"], r["code"]))
    files[CHANGES_FILE] = dump_json(changes)
    files[IDENTIFIERS_FILE] = dump_json(identifiers)
    return GeneratedCorpus(files=files, changes=changes, identifiers=identifiers)


def write_files(target: Path, files: dict[str, bytes]) -> None:
    """Write the files and remove any other ``*.yaml`` or ``*.json`` that is left from earlier."""
    target.mkdir(parents=True, exist_ok=True)
    for stale in [*target.glob("*.yaml"), *target.glob("*.json")]:
        if stale.name not in files:
            stale.unlink()
    for name, data in files.items():
        (target / name).write_bytes(data)


def differences(target: Path, files: dict[str, bytes]) -> list[str]:
    """What differs between the committed folder and a fresh generation (empty when equal)."""
    problems: list[str] = []
    present = {p.name for p in [*target.glob("*.yaml"), *target.glob("*.json")]}
    problems += [f"missing: {n}" for n in sorted(set(files) - present)]
    problems += [f"unexpected: {n}" for n in sorted(present - set(files))]
    for name, data in sorted(files.items()):
        path = target / name
        if path.is_file() and path.read_bytes() != data:
            problems.append(f"differs: {name}")
    return problems
