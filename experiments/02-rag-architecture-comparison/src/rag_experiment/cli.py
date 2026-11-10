"""Command-line interface: inspect chunks and validate the dataset."""

import argparse
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rag_experiment.config import ConfigError, ExperimentConfig, default_config_path, load_config
from rag_experiment.corpus import Corpus, load_corpus, load_manifest
from rag_experiment.embeddings.fake import FakeEmbeddingProvider
from rag_experiment.embeddings.provider import (
    EmbeddingCache,
    EmbeddingError,
    EmbeddingProvider,
    SentenceTransformerProvider,
)
from rag_experiment.evaluation.dataset import (
    Question,
    load_questions,
    validate_question_set,
)
from rag_experiment.evaluation.facts import corpus_header_names
from rag_experiment.evaluation.relevance import relevant_chunk_ids
from rag_experiment.evaluation.retrieval_metrics import KS, summarize
from rag_experiment.evaluation.retrieval_run import (
    build_metadata,
    make_run_id,
    metrics_table,
    run_questions,
    write_run,
)
from rag_experiment.ingestion.chunker import Chunk, chunk_corpus
from rag_experiment.ingestion.parser import SpecError
from rag_experiment.retrieval.store import (
    IndexLockedError,
    IngestReport,
    QdrantStore,
    collection_name,
    ingest,
    open_local_store,
)
from rag_experiment.retrieval.vector import DenseRetriever

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

    fake_help = "use the deterministic fake embedder (dry run, nothing is measured)"
    index = sub.add_parser("index", help="embed the chunks and build the local Qdrant index")
    index.add_argument("--rebuild", action="store_true", help="rebuild even if up to date")
    index.add_argument("--fake-embeddings", action="store_true", help=fake_help)
    retrieve = sub.add_parser("retrieve", help="retrieve the top chunks for a question")
    retrieve.add_argument("question", nargs="?", help="question text")
    retrieve.add_argument("-k", type=int, default=5, help="number of chunks (default 5)")
    retrieve.add_argument("--question-id", help="take the text from a question set; marks hits")
    retrieve.add_argument("--show", action="store_true", help="print the top chunk's content")
    retrieve.add_argument("--fake-embeddings", action="store_true", help=fake_help)
    evaluate = sub.add_parser(
        "evaluate-retrieval", help="compute retrieval metrics on a question set (no LLM calls)"
    )
    evaluate.add_argument("--set", dest="question_set", choices=("dev", "measured"), required=True)
    evaluate.add_argument("--fake-embeddings", action="store_true", help=fake_help)
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


# --------------------------------------------------------------------- retrieval commands


@dataclass
class _Session:
    corpus: Corpus
    chunks: list[Chunk]
    provider: EmbeddingProvider
    cache: EmbeddingCache
    store: QdrantStore
    index_dir: Path | None


def _results_root(config: ExperimentConfig, fake: bool) -> Path:
    """Where run files go. Fake runs never touch raw/processed/reports of the real results."""
    base = _results_root_base(config)
    return base / "dry-run" if fake else base


def _results_root_base(config: ExperimentConfig) -> Path:
    """The results folder (a separate function so tests can redirect it)."""
    return config.results_dir


def _make_provider(config: ExperimentConfig, fake: bool) -> EmbeddingProvider:
    if fake:
        return FakeEmbeddingProvider()
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    print(
        f"Loading local embedding model {config.embedding.model_id} "
        "(the first run downloads about 2.3 GB)..."
    )
    return SentenceTransformerProvider(config.embedding)


@contextmanager
def _session(config: ExperimentConfig, fake: bool) -> Iterator[_Session]:
    corpus, chunks = _load(config)
    provider = _make_provider(config, fake)
    collection = collection_name(
        config.index, corpus, config.chunking, provider.model_id, provider.revision
    )
    index_dir = None if fake else config.index_dir
    cache = (
        EmbeddingCache(None)
        if index_dir is None
        else EmbeddingCache.for_provider(
            index_dir, provider, config.embedding.normalize, config.embedding.max_seq_length
        )
    )
    with open_local_store(index_dir, collection) as store:
        yield _Session(corpus, chunks, provider, cache, store, index_dir)


def _ingest_record_path(index_dir: Path, collection: str) -> Path:
    return index_dir / "ingest" / f"{collection}.json"


def _ingest(session: _Session, rebuild: bool) -> tuple[IngestReport, IngestReport | None]:
    """Ingest; returns this invocation's report and the stored report of the last real build."""
    report = ingest(session.chunks, session.provider, session.cache, session.store, rebuild)
    if session.index_dir is None:
        return report, None
    record = _ingest_record_path(session.index_dir, session.store.collection)
    if not report.up_to_date:
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return report, report
    if record.is_file():
        return report, IngestReport.model_validate(json.loads(record.read_text(encoding="utf-8")))
    return report, None


def _print_ingest(report: IngestReport) -> None:
    print(f"collection: {report.collection}")
    print(f"dimension: {report.dimension}")
    print(f"chunks: {report.chunks}")
    if report.up_to_date:
        print("up to date: nothing embedded, nothing upserted")
    print(f"embedded: {report.embedded}")
    print(f"from cache: {report.cached}")
    print(f"embed seconds: {report.embed_seconds:.2f}")
    print(f"upsert seconds: {report.upsert_seconds:.2f}")


def _cmd_index(config: ExperimentConfig, rebuild: bool, fake: bool) -> int:
    with _session(config, fake) as session:
        report, _ = _ingest(session, rebuild)
        _print_ingest(report)
        if isinstance(session.provider, SentenceTransformerProvider):
            limit = config.embedding.max_seq_length
            too_long = [
                c.chunk_id
                for c in session.chunks
                if session.provider.token_count(c.content) > limit
            ]
            if too_long:
                print(f"warning: {len(too_long)} chunk(s) exceed {limit} tokens: {too_long[:5]}")
            else:
                print(f"token check: no chunk exceeds {limit} tokens")
    return 0


def _find_question(config: ExperimentConfig, question_id: str) -> Question:
    for path in (config.questions_dev, config.questions_measured):
        for question in load_questions(path):
            if question.id == question_id:
                return question
    raise ValueError(f"no question with id {question_id!r}")


def _cmd_retrieve(
    config: ExperimentConfig,
    text: str | None,
    k: int,
    question_id: str | None,
    show: bool,
    fake: bool,
) -> int:
    question = _find_question(config, question_id) if question_id else None
    query = text or (question.question if question else None)
    if not query:
        print("Error: give a question or --question-id", file=sys.stderr)
        return 2
    with _session(config, fake) as session:
        if session.store.count() == 0 and fake:
            _ingest(session, rebuild=False)
        retriever = DenseRetriever(session.provider, session.store)
        result = retriever.retrieve(query, k)
        relevant = relevant_chunk_ids(question.sources, session.chunks) if question else None
        for item in result.chunks:
            mark = (
                ""
                if relevant is None
                else f" · {'relevant' if item.chunk.chunk_id in relevant else '-'}"
            )
            print(f"{item.rank} · {item.score:.4f} · {item.chunk.chunk_id}{mark}")
        print(f"embed {result.embed_ms:.1f} ms, search {result.search_ms:.1f} ms")
        if show and result.chunks:
            print()
            print(result.chunks[0].chunk.content)
    return 0


def _cmd_evaluate(config: ExperimentConfig, set_name: str, fake: bool) -> int:
    path = config.questions_measured if set_name == "measured" else config.questions_dev
    questions = load_questions(path)
    started = datetime.now(UTC)
    with _session(config, fake) as session:
        report, build = _ingest(session, rebuild=False)
        retriever = DenseRetriever(session.provider, session.store)
        run_id = make_run_id(set_name, retriever.name, fake, started)
        records, differing = run_questions(
            run_id, questions, session.chunks, retriever, config.retrieval.top_k_eval
        )
        summary = summarize(run_id, set_name, records, differing)
        metadata = build_metadata(
            config=config,
            corpus=session.corpus,
            run_id=run_id,
            set_name=set_name,
            question_path=path,
            retriever_name=retriever.name,
            fake=fake,
            model_id=session.provider.model_id,
            revision=session.provider.revision,
            dimension=session.provider.dimension,
            collection=session.store.collection,
            started_at=started,
            deterministic=summary.deterministic,
        )
    ingest_payload: dict[str, object] = {
        "this_invocation": report.model_dump(mode="json"),
        "index_build": build.model_dump(mode="json") if build else None,
    }
    root = _results_root(config, fake)
    paths = write_run(root, metadata, records, summary, ingest_payload)
    print(f"run id: {run_id}")
    if fake:
        print("fake embeddings: dry run, files written under results/dry-run (not a measurement)")
    print(f"questions: {summary.n_questions} ({summary.n_excluded} unanswerable excluded)")
    print(f"deterministic: {summary.deterministic} {list(summary.nondeterministic_questions)}")
    print()
    print("\n".join(metrics_table(summary)))
    print()
    print(f"HA1 group Hit@5: {summary.ha1_group.numerator}/{summary.ha1_group.denominator}")
    print(f"HA2 group Hit@5: {summary.ha2_group.numerator}/{summary.ha2_group.denominator}")
    for verdict in summary.verdicts:
        print(f"{verdict.hypothesis}: {verdict.verdict} {verdict.evidence}".rstrip())
    print()
    print(f"report: {paths['report']}")
    print(f"K values: {list(KS)}")
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
        if args.command == "index":
            return _cmd_index(config, args.rebuild, args.fake_embeddings)
        if args.command == "retrieve":
            return _cmd_retrieve(
                config, args.question, args.k, args.question_id, args.show, args.fake_embeddings
            )
        if args.command == "evaluate-retrieval":
            return _cmd_evaluate(config, args.question_set, args.fake_embeddings)
        return _cmd_validate(config)
    except (ConfigError, SpecError, ValueError, OSError, EmbeddingError, IndexLockedError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
