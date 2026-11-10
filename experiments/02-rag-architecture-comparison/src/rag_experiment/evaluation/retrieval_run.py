"""Run retrieval over a question set, write the run files and render the report.

Layout (relative to the results root)::

    raw/<run_id>/run_metadata.json, retrieval.jsonl, ingest.json
    processed/<run_id>/retrieval_summary.json, retrieval_by_question.csv
    reports/<run_id>/retrieval_report.md
"""

import csv
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ai_lab.benchmarking import collect_environment, git_state
from rag_experiment.config import ExperimentConfig
from rag_experiment.corpus import Corpus, load_manifest
from rag_experiment.evaluation.dataset import Question
from rag_experiment.evaluation.relevance import relevant_chunk_ids
from rag_experiment.evaluation.retrieval_metrics import (
    KS,
    QuestionRetrieval,
    RetrievalSummary,
    score_question,
)
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.base import Retriever

PACKAGES = (
    "torch",
    "sentence-transformers",
    "transformers",
    "qdrant-client",
    "numpy",
    "pydantic",
    "pyyaml",
)


class EmbeddingMetadata(BaseModel):
    """Embedding settings as used in the run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    revision: str
    device: str
    dimension: int
    normalize: bool
    max_seq_length: int
    batch_size: int


class RetrievalRunMetadata(BaseModel):
    """Everything recorded about a retrieval run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    kind: str
    simulated: bool
    experiment: str
    experiment_version: str
    git_sha: str
    git_dirty: bool
    started_at: datetime
    finished_at: datetime
    hardware: dict[str, str]
    os: str
    python_version: str
    package_versions: dict[str, str]
    corpus_version: str
    corpus_checksum: str
    question_set: str
    question_set_version: str
    question_set_checksum: str
    embedding: EmbeddingMetadata
    chunking: dict[str, int]
    retrieval: dict[str, int]
    collection: str
    retriever: str
    torch_threads: int | None
    deterministic: bool


def make_run_id(set_name: str, retriever: str, fake: bool, now: datetime | None = None) -> str:
    """``{UTC timestamp}-retrieval-{set}-{retriever}`` (plus ``-fake`` for dry runs)."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-retrieval-{set_name}-{retriever}" + ("-fake" if fake else "")


def run_questions(
    run_id: str,
    questions: Sequence[Question],
    chunks: Sequence[Chunk],
    retriever: Retriever,
    k: int,
) -> tuple[list[QuestionRetrieval], list[str]]:
    """Retrieve every question twice. Returns the first-pass records and non-deterministic ids."""
    records: list[QuestionRetrieval] = []
    differing: list[str] = []
    for question in questions:
        first = retriever.retrieve(question.question, k)
        second = retriever.retrieve(question.question, k)
        if [c.chunk.chunk_id for c in first.chunks] != [c.chunk.chunk_id for c in second.chunks]:
            differing.append(question.id)
        excluded = question.category == "unanswerable"
        sources = question.sources
        records.append(
            score_question(
                run_id=run_id,
                question_id=question.id,
                category=question.category,
                paraphrase_of=question.paraphrase_of,
                retriever=retriever.name,
                k=k,
                sources=sources,
                chunks=chunks,
                relevant_ids=relevant_chunk_ids(sources, chunks),
                ranked=[(c.chunk.chunk_id, c.score) for c in first.chunks],
                embed_ms=first.embed_ms,
                search_ms=first.search_ms,
                excluded=excluded,
            )
        )
    return records, differing


def _torch_threads() -> int | None:
    try:
        import torch

        return int(torch.get_num_threads())
    except ImportError:
        return None


def build_metadata(
    *,
    config: ExperimentConfig,
    corpus: Corpus,
    run_id: str,
    set_name: str,
    question_path: Path,
    retriever_name: str,
    fake: bool,
    model_id: str,
    revision: str,
    dimension: int,
    collection: str,
    started_at: datetime,
    deterministic: bool,
) -> RetrievalRunMetadata:
    """Collect environment, versions and settings for the run."""
    manifest = load_manifest(config.manifest_path)
    env = collect_environment(PACKAGES)
    sha, dirty = git_state(config.root)
    emb = config.embedding
    return RetrievalRunMetadata(
        run_id=run_id,
        kind="retrieval",
        simulated=fake,
        experiment="02-rag-architecture-comparison",
        experiment_version=config.experiment_version,
        git_sha=sha,
        git_dirty=dirty,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        hardware=env.hardware,
        os=env.os,
        python_version=env.python_version,
        package_versions=env.package_versions,
        corpus_version=corpus.version,
        corpus_checksum=corpus.checksum,
        question_set=set_name,
        question_set_version=(
            manifest.eval_measured_version if set_name == "measured" else manifest.eval_dev_version
        ),
        question_set_checksum=hashlib.sha256(question_path.read_bytes()).hexdigest(),
        embedding=EmbeddingMetadata(
            model_id=model_id,
            revision=revision,
            device=emb.device,
            dimension=dimension,
            normalize=emb.normalize,
            max_seq_length=emb.max_seq_length,
            batch_size=emb.batch_size,
        ),
        chunking={"max_chunk_chars": config.chunking.max_chunk_chars},
        retrieval={
            "top_k_eval": config.retrieval.top_k_eval,
            "top_k_generation": config.retrieval.top_k_generation,
        },
        collection=collection,
        retriever=retriever_name,
        torch_threads=None if fake else _torch_threads(),
        deterministic=deterministic,
    )


# ------------------------------------------------------------------------------ files


def _write_json(path: Path, payload: BaseModel | dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _csv_rows(records: Sequence[QuestionRetrieval]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for r in records:
        row: dict[str, object] = {
            "question_id": r.question_id,
            "category": r.category,
            "excluded": r.excluded,
            "first_relevant_rank": "" if r.first_relevant_rank is None else r.first_relevant_rank,
        }
        for k in KS:
            row[f"hit@{k}"] = r.hit[k]
        for k in KS:
            row[f"recall@{k}"] = r.recall[k]
        for k in KS:
            row[f"precision@{k}"] = r.precision[k]
        row["reciprocal_rank"] = r.reciprocal_rank
        row["embed_ms"] = round(r.embed_ms, 3)
        row["search_ms"] = round(r.search_ms, 3)
        row["top3_chunk_ids"] = " ".join(c.chunk_id for c in r.ranked[:3])
        rows.append(row)
    return rows


def write_run(
    results_root: Path,
    metadata: RetrievalRunMetadata,
    records: Sequence[QuestionRetrieval],
    summary: RetrievalSummary,
    ingest_payload: dict[str, object],
) -> dict[str, Path]:
    """Write every run file under ``results_root`` and return their paths."""
    run_id = metadata.run_id
    raw = results_root / "raw" / run_id
    processed = results_root / "processed" / run_id
    reports = results_root / "reports" / run_id
    paths = {
        "metadata": raw / "run_metadata.json",
        "retrieval": raw / "retrieval.jsonl",
        "ingest": raw / "ingest.json",
        "summary": processed / "retrieval_summary.json",
        "csv": processed / "retrieval_by_question.csv",
        "report": reports / "retrieval_report.md",
    }
    _write_json(paths["metadata"], metadata)
    paths["retrieval"].parent.mkdir(parents=True, exist_ok=True)
    paths["retrieval"].write_text(
        "".join(json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )
    _write_json(paths["ingest"], ingest_payload)
    _write_json(paths["summary"], summary)
    rows = _csv_rows(records)
    paths["csv"].parent.mkdir(parents=True, exist_ok=True)
    with paths["csv"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["question_id"])
        writer.writeheader()
        writer.writerows(rows)
    paths["report"].parent.mkdir(parents=True, exist_ok=True)
    paths["report"].write_text(
        render_report(metadata, summary, records, ingest_payload), encoding="utf-8"
    )
    return paths


# ------------------------------------------------------------------------------ report


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def _rank(value: int | None) -> str:
    return "not in top 10" if value is None else str(value)


def metrics_table(summary: RetrievalSummary) -> list[str]:
    """Markdown rows: overall and by category."""
    header = ["group", "n"] + [f"Hit@{k}" for k in KS] + [f"Recall@{k}" for k in KS]
    header += [f"Precision@{k}" for k in KS] + ["MRR"]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    groups = [("overall", summary.overall), *summary.by_category.items()]
    for name, g in groups:
        cells = [name, str(g.n)]
        cells += [_fmt(g.hit[k]) for k in KS]
        cells += [_fmt(g.recall[k]) for k in KS]
        cells += [_fmt(g.precision[k]) for k in KS]
        cells.append(_fmt(g.mrr))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def render_report(
    metadata: RetrievalRunMetadata,
    summary: RetrievalSummary,
    records: Sequence[QuestionRetrieval],
    ingest_payload: dict[str, object],
) -> str:
    """The generated Markdown report. It states measurements only; no interpretation."""
    emb = metadata.embedding
    out: list[str] = [f"# Retrieval report: {metadata.run_id}", ""]
    if metadata.simulated:
        out += ["> Simulated run with fake embeddings. Not a measurement.", ""]
    out += [
        "## Setup",
        "",
        f"- Corpus: version {metadata.corpus_version}, checksum `{metadata.corpus_checksum}`",
        f"- Question set: {metadata.question_set}, version {metadata.question_set_version}, "
        f"checksum `{metadata.question_set_checksum}`",
        f"- Embedding model: `{emb.model_id}`, revision `{emb.revision}`, device {emb.device}, "
        f"dimension {emb.dimension}, normalised {emb.normalize}",
        f"- Retriever: {metadata.retriever}; collection `{metadata.collection}`",
        f"- Questions: {summary.n_questions} ({summary.n_excluded} unanswerable, excluded from "
        "metrics)",
        f"- K values: {', '.join(str(k) for k in KS)}; "
        f"retrieved depth {metadata.retrieval['top_k_eval']}",
        f"- Git: `{metadata.git_sha}` (dirty: {metadata.git_dirty}); "
        f"deterministic retrieval: {summary.deterministic}",
        "",
        "## Metrics",
        "",
        *metrics_table(summary),
        "",
        "## Hypothesis verdicts (frozen criteria, computed mechanically)",
        "",
        "| hypothesis | criterion | verdict | evidence |",
        "|---|---|---|---|",
    ]
    for v in summary.verdicts:
        out.append(f"| {v.hypothesis} | {v.criterion} | {v.verdict} | {v.evidence} |")
    out += [
        "",
        "## Per question",
        "",
        "| id | category | first relevant rank | hit@5 | recall@5 | top 3 chunks |",
        "|---|---|---|---|---|---|",
    ]
    for r in records:
        if r.excluded:
            out.append(
                f"| {r.question_id} | {r.category} | excluded | | | "
                f"{', '.join(f'`{c.chunk_id}`' for c in r.ranked[:3])} |"
            )
        else:
            out.append(
                f"| {r.question_id} | {r.category} | {_rank(r.first_relevant_rank)} | "
                f"{_fmt(r.hit[5])} | {_fmt(r.recall[5])} | "
                f"{', '.join(f'`{c.chunk_id}`' for c in r.ranked[:3])} |"
            )
    out += ["", "## Paraphrase pairs", ""]
    if summary.paraphrase_pairs:
        out += [
            "| original | paraphrase | original first relevant rank | "
            "paraphrase first relevant rank |",
            "|---|---|---|---|",
        ]
        for p in summary.paraphrase_pairs:
            out.append(
                f"| {p.original} | {p.paraphrase} | {_rank(p.original_first_relevant_rank)} | "
                f"{_rank(p.paraphrase_first_relevant_rank)} |"
            )
    else:
        out.append("This question set has no paraphrase pairs.")
    out += [
        "",
        "## Latency",
        "",
        "Qdrant local mode, in-process, exact search; CPU; not representative of a Qdrant server.",
        "",
        "| stage | n | p50 (ms) | p95 (ms) |",
        "|---|---|---|---|",
    ]
    for name, lat in (
        ("query embedding", summary.latency_embed_ms),
        ("vector search", summary.latency_search_ms),
        ("total", summary.latency_total_ms),
    ):
        out.append(f"| {name} | {lat.n} | {lat.p50:.2f} | {lat.p95:.2f} |")
    out += ["", "## Indexing cost", ""]
    build = ingest_payload.get("index_build")
    this = ingest_payload.get("this_invocation")
    if isinstance(build, dict):
        out.append(
            f"- Index build: {build['chunks']} chunks, {build['embedded']} embedded, "
            f"{build['cached']} from cache, embedding {build['embed_seconds']:.2f} s, "
            f"upsert {build['upsert_seconds']:.2f} s"
        )
    if isinstance(this, dict):
        out.append(
            f"- This run: {this['chunks']} chunks, {this['embedded']} embedded, "
            f"{this['cached']} from cache, up to date: {this['up_to_date']}"
        )
    out += [
        "",
        "The analysis of these results is in the experiment README, written by the author.",
        "",
    ]
    return "\n".join(out)
