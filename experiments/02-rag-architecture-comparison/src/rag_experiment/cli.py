"""Command-line interface: inspect chunks and validate the dataset."""

import argparse
import re
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from rag_experiment.config import ConfigError, ExperimentConfig, default_config_path, load_config
from rag_experiment.corpus import Corpus, load_corpus, load_manifest
from rag_experiment.evaluation.dataset import load_questions, validate_question_set
from rag_experiment.evaluation.facts import corpus_header_names
from rag_experiment.ingestion.chunker import Chunk, chunk_corpus
from rag_experiment.ingestion.parser import SpecError

_SPLIT_SUFFIX = re.compile(r":p\d+$")
_CHUNK_TYPES = (
    "operation",
    "parameters",
    "request_body",
    "response",
    "security_scheme",
    "component_schema",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rag-experiment", description="Experiment 02: RAG architecture comparison."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="path to experiment.yaml (default: shipped config)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    chunks = sub.add_parser("chunks", help="list the chunks of the corpus")
    chunks.add_argument("--document", metavar="ID", help="only this document")
    chunks.add_argument("--type", dest="chunk_type", choices=_CHUNK_TYPES, help="only this type")
    chunks.add_argument("--full", action="store_true", help="print each chunk's content")
    show = sub.add_parser("show-chunk", help="print one chunk with its metadata")
    show.add_argument("chunk_id")
    sub.add_parser("validate-dataset", help="validate the corpus and both question files")
    return parser


def _load(config: ExperimentConfig) -> tuple[Corpus, list[Chunk]]:
    corpus = load_corpus(config.corpus_dir)
    return corpus, chunk_corpus(corpus, config.chunking)


def _cmd_chunks(
    config: ExperimentConfig, document: str | None, chunk_type: str | None, full: bool
) -> int:
    _, chunks = _load(config)
    selected = [
        c
        for c in chunks
        if (document is None or c.document_id == document)
        and (chunk_type is None or c.chunk_type == chunk_type)
    ]
    for chunk in selected:
        print(
            f"{chunk.chunk_id} · {chunk.chunk_type} · {len(chunk.content)} chars · {chunk.source}"
        )
        if full:
            print(chunk.content)
            print()
    print(f"{len(selected)} chunks")
    return 0


def _cmd_show_chunk(config: ExperimentConfig, chunk_id: str) -> int:
    _, chunks = _load(config)
    for chunk in chunks:
        if chunk.chunk_id == chunk_id:
            print(f"chunk_id: {chunk.chunk_id}")
            print(f"chunk_type: {chunk.chunk_type}")
            print(f"document: {chunk.document_id} ({chunk.document_name}, v{chunk.spec_version})")
            print(f"source_reference: {chunk.source}")
            print(f"operation: {chunk.http_method} {chunk.api_path} ({chunk.operation_id})")
            print(f"tags: {', '.join(chunk.tags)}")
            print(f"refs: {', '.join(chunk.refs)}")
            print(f"chars: {len(chunk.content)}")
            print(f"content_hash: {chunk.content_hash}")
            print("content:")
            print(chunk.content)
            return 0
    print(f"Error: no chunk with id {chunk_id!r}", file=sys.stderr)
    return 2


def _cmd_validate(config: ExperimentConfig) -> int:
    corpus, chunks = _load(config)
    manifest = load_manifest(config.manifest_path)
    problems: list[str] = []
    if manifest.corpus_checksum != corpus.checksum:
        problems.append(
            f"manifest corpus_checksum {manifest.corpus_checksum} does not match {corpus.checksum}"
        )
    print(f"corpus version: {corpus.version}")
    print(f"corpus checksum: {corpus.checksum}")
    print(f"documents: {len(corpus.specs)}")
    print(f"operations: {sum(len(s.operations) for s in corpus.specs)}")
    by_type: Counter[str] = Counter(c.chunk_type for c in chunks)
    print(f"chunks: {len(chunks)}")
    for chunk_type in _CHUNK_TYPES:
        print(f"  {chunk_type}: {by_type.get(chunk_type, 0)}")
    print(f"max chunk length: {max(len(c.content) for c in chunks)} chars")
    print(f"split chunks: {sum(1 for c in chunks if _SPLIT_SUFFIX.search(c.chunk_id))}")

    header_names = corpus_header_names(corpus)
    for label, path in (("dev", config.questions_dev), ("measured", config.questions_measured)):
        questions = load_questions(path)
        problems.extend(
            f"[{label}] {p}" for p in validate_question_set(questions, corpus, chunks, header_names)
        )
        per_category = Counter(q.category for q in questions)
        pairs = sum(1 for q in questions if q.paraphrase_of is not None)
        print(f"questions ({label}): {len(questions)}")
        for category in sorted(per_category):
            print(f"  {category}: {per_category[category]}")
        print(f"  paraphrase pairs: {pairs}")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nno problems found")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        config = load_config(args.config or default_config_path())
        if args.command == "chunks":
            return _cmd_chunks(config, args.document, args.chunk_type, args.full)
        if args.command == "show-chunk":
            return _cmd_show_chunk(config, args.chunk_id)
        return _cmd_validate(config)
    except (ConfigError, SpecError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
