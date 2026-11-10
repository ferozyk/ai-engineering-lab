"""Question records: loading and cross-validation against the corpus and its chunks."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from rag_experiment.corpus import Corpus
from rag_experiment.evaluation.facts import all_present
from rag_experiment.evaluation.relevance import relevant_chunk_ids
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.ingestion.pointers import PointerError, Source, parse_source, resolve_pointer

Category = Literal[
    "semantic",
    "exact_identifier",
    "endpoint_discovery",
    "authentication",
    "schema",
    "multi_endpoint",
    "comparison",
    "unanswerable",
]


class QuestionConstraints(BaseModel):
    """How an answer to the question is judged."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    must_cite: bool
    must_abstain: bool


class Question(BaseModel):
    """One evaluation question, mirroring ``question.schema.json``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    question: str
    category: Category
    expected_answer: str
    key_facts: tuple[str, ...]
    relevant_sources: tuple[str, ...]
    relevant_document_ids: tuple[str, ...]
    constraints: QuestionConstraints
    paraphrase_of: str | None
    notes: str

    @property
    def sources(self) -> tuple[Source, ...]:
        """The labelled sources, parsed."""
        return tuple(parse_source(s) for s in self.relevant_sources)


def load_questions(path: Path) -> tuple[Question, ...]:
    """Read a JSONL file. Blank lines and duplicate ids are errors."""
    questions: list[Question] = []
    seen: set[str] = set()
    lines = path.read_text(encoding="utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # the final newline
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            raise ValueError(f"{path}:{number}: blank lines are not allowed")
        try:
            question = Question.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"{path}:{number}: invalid question record ({exc})") from exc
        if question.id in seen:
            raise ValueError(f"{path}:{number}: duplicate question id {question.id}")
        seen.add(question.id)
        questions.append(question)
    return tuple(questions)


def validate_question_set(
    questions: Sequence[Question],
    corpus: Corpus,
    chunks: Sequence[Chunk],
    header_names: frozenset[str],
) -> list[str]:
    """Return a list of problems; an empty list means the set is valid."""
    problems: list[str] = []
    ids = {q.id for q in questions}
    by_id = {c.chunk_id: c for c in chunks}
    for q in questions:
        tag = q.id
        sources: list[Source] = []
        for text in q.relevant_sources:
            try:
                source = parse_source(text)
            except ValueError as exc:
                problems.append(f"{tag}: {exc}")
                continue
            document = corpus.documents.get(source.document_id)
            if document is None:
                problems.append(f"{tag}: unknown document in source {text}")
                continue
            try:
                resolve_pointer(document, source.pointer)
            except PointerError as exc:
                problems.append(f"{tag}: source {text} does not resolve ({exc})")
                continue
            sources.append(source)

        if set(q.relevant_document_ids) != {s.document_id for s in sources}:
            problems.append(
                f"{tag}: relevant_document_ids {sorted(q.relevant_document_ids)} do not match "
                f"the source documents {sorted({s.document_id for s in sources})}"
            )

        relevant: set[str] = set()
        for source in sources:
            ids_for_source = relevant_chunk_ids([source], chunks)
            if not ids_for_source:
                problems.append(f"{tag}: source {source} has no relevant chunk")
            relevant.update(ids_for_source)
        evidence = "\n".join(by_id[i].content for i in sorted(relevant))
        for fact in all_present(q.key_facts, evidence, header_names):
            problems.append(f"{tag}: key fact {fact!r} is not in the relevant chunks")

        abstain = q.constraints.must_abstain
        unanswerable = q.category == "unanswerable"
        if abstain != unanswerable:
            problems.append(f"{tag}: must_abstain and category 'unanswerable' must go together")
        if abstain and (q.relevant_sources or q.key_facts or q.relevant_document_ids):
            problems.append(f"{tag}: an abstention question must have no sources or key facts")
        if not abstain and not (q.relevant_sources and q.key_facts):
            problems.append(f"{tag}: an answerable question needs sources and key facts")

        if q.paraphrase_of is not None and q.paraphrase_of not in ids:
            problems.append(f"{tag}: paraphrase_of {q.paraphrase_of} is not in this file")
    return problems
