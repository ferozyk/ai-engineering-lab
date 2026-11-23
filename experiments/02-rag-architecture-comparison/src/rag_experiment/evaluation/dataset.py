"""Question records: loading and cross-validation against the corpus and its chunks."""

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from rag_experiment.corpus import Corpus
from rag_experiment.evaluation.corpus_facts import CorpusFacts
from rag_experiment.evaluation.facts import all_present, fact_present
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
    # Experiment 02b: the five stress conditions (see docs/evaluation-methodology.md section 10).
    "exact_identifier_lookalike",
    "version_lookalike",
    "everyday_wording",
    "multi_document",
    "near_miss",
]

# Categories whose questions must be refused: the corpus has no answer to find.
ABSTAIN_CATEGORIES: frozenset[str] = frozenset({"unanswerable", "near_miss"})

_ERROR_CODE = re.compile(r"\bERR-[A-Z]{3}-\d{3}\b")
_VERSION_NAMED = re.compile(r"\b(?:v|version\s+)([1-9])\b", re.IGNORECASE)
_VERSIONED_DOCUMENT = re.compile(r"^(?P<product>.+)-api-v(?P<version>[1-9])$")


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


def _source_text(source: Source, chunks: Sequence[Chunk]) -> str:
    """The text of the chunks that cover one source."""
    by_id = {c.chunk_id: c for c in chunks}
    return "\n".join(by_id[i].content for i in sorted(relevant_chunk_ids([source], chunks)))


def _multi_document_problems(
    q: Question, sources: Sequence[Source], chunks: Sequence[Chunk], header_names: frozenset[str]
) -> list[str]:
    """At least two sources from two documents, each owning a key fact no other source holds."""
    problems: list[str] = []
    if len(q.relevant_sources) < 2:
        problems.append(f"{q.id}: a multi_document question needs at least 2 sources")
    if len({s.document_id for s in sources}) < 2:
        problems.append(f"{q.id}: a multi_document question needs sources from 2 documents")
    texts = {str(s): _source_text(s, chunks) for s in sources}
    for source in sources:
        others = [t for key, t in texts.items() if key != str(source)]
        owned = [
            f
            for f in q.key_facts
            if fact_present(f, texts[str(source)], header_names)
            and not any(fact_present(f, t, header_names) for t in others)
        ]
        if not owned:
            problems.append(
                f"{q.id}: source {source} owns no key fact (a fact in its text and in no other "
                "source's text)"
            )
    return problems


def _version_problems(
    q: Question,
    sources: Sequence[Source],
    header_names: frozenset[str],
    facts: CorpusFacts | None,
) -> list[str]:
    """The question names a version whose answer differs from another version (CHANGES.json)."""
    if facts is None:
        return [f"{q.id}: a version_lookalike question needs the corpus catalogues (CHANGES.json)"]
    named = {f"v{m}" for m in _VERSION_NAMED.findall(q.question)}
    if not named:
        return [f"{q.id}: a version_lookalike question must name a version (for example v2)"]
    documents = [_VERSIONED_DOCUMENT.match(s.document_id) for s in sources]
    if not documents or any(m is None for m in documents):
        return [f"{q.id}: version_lookalike sources must be versioned product specs"]
    matches = [m for m in documents if m is not None]
    products = {m["product"] for m in matches}
    versions = {f"v{m['version']}" for m in matches}
    if len(products) != 1:
        return [f"{q.id}: version_lookalike sources must belong to one product"]
    if not versions <= named:
        return [
            f"{q.id}: the sources are from {sorted(versions)} but the question names "
            f"{sorted(named)}"
        ]
    product = next(iter(products))
    for change in facts.changes:
        if change.product != product:
            continue
        for version in versions:
            if version == change.to_version:
                value = change.after
            elif version == change.from_version:
                value = change.before
            else:
                continue
            candidates = [change.subject] + ([] if value is None else [str(value)])
            if any(fact_present(c, fact, header_names) for c in candidates for fact in q.key_facts):
                return []
    return [
        f"{q.id}: no key fact differs between the named version and another version of {product} "
        "(see CHANGES.json)"
    ]


def _identifier_problems(q: Question, facts: CorpusFacts | None) -> list[str]:
    if facts is None:
        return [f"{q.id}: an exact_identifier_lookalike question needs IDENTIFIERS.json"]
    quoted = _ERROR_CODE.findall(q.question)
    if not any(code in facts.codes for code in quoted):
        return [f"{q.id}: the question must quote an identifier from IDENTIFIERS.json"]
    return []


def validate_question_set(
    questions: Sequence[Question],
    corpus: Corpus,
    chunks: Sequence[Chunk],
    header_names: frozenset[str],
    facts: CorpusFacts | None = None,
) -> list[str]:
    """Return a list of problems; an empty list means the set is valid.

    ``facts`` (the large corpus catalogues) is needed for ``version_lookalike`` and
    ``exact_identifier_lookalike`` questions.
    """
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
        unanswerable = q.category in ABSTAIN_CATEGORIES
        if abstain != unanswerable:
            problems.append(
                f"{tag}: must_abstain and category 'unanswerable' or 'near_miss' must go together"
            )
        if abstain and (q.relevant_sources or q.key_facts or q.relevant_document_ids):
            problems.append(f"{tag}: an abstention question must have no sources or key facts")
        if not abstain and not (q.relevant_sources and q.key_facts):
            problems.append(f"{tag}: an answerable question needs sources and key facts")

        if q.category == "multi_document":
            problems += _multi_document_problems(q, sources, chunks, header_names)
        elif q.category == "version_lookalike":
            problems += _version_problems(q, sources, header_names, facts)
        elif q.category == "exact_identifier_lookalike":
            problems += _identifier_problems(q, facts)

        if q.paraphrase_of is not None and q.paraphrase_of not in ids:
            problems.append(f"{tag}: paraphrase_of {q.paraphrase_of} is not in this file")
    return problems
