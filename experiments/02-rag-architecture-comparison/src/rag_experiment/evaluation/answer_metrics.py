"""Answer metrics: pure functions over one answer. Definitions: methodology section 5.

Every check reads the ``answer`` field only, never the citations. Refusal is read from the
structured ``insufficient_context`` flag.
"""

import re
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from rag_experiment.evaluation.facts import fact_present
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.ingestion.parser import ParsedSpec

Outcome = Literal["answered", "refused", "invalid_answer", "cut_off", "infra_error"]
IdentifierKind = Literal["endpoint", "path", "error_code", "scope", "header", "name"]

# ------------------------------------------------------------------------------ outcome


def determine_outcome(
    *,
    infra_error: bool,
    finish_reason: str | None,
    parse_error: str | None,
    insufficient_context: bool,
) -> Outcome:
    """The first rule that applies: infra_error, cut_off, invalid_answer, refused, answered."""
    if infra_error:
        return "infra_error"
    if parse_error is not None:
        return "cut_off" if finish_reason == "length" else "invalid_answer"
    return "refused" if insufficient_context else "answered"


def required_key_facts(
    key_facts: Sequence[str], question: str, header_names: frozenset[str]
) -> list[str]:
    """Key facts a correct answer must state: those not already present in the question.

    "What is the maximum value of `pageSize`?" is fully answered by "100"; requiring the answer
    to repeat ``pageSize`` would score phrasing, not correctness. The same exclusion applies to
    groundedness. If every key fact appears in the question, all of them stay required.
    """
    required = [fact for fact in key_facts if not fact_present(fact, question, header_names)]
    return required or list(key_facts)


def score_correctness(
    outcome: Outcome,
    answer: str,
    key_facts: Sequence[str],
    header_names: frozenset[str],
    question: str = "",
) -> tuple[bool, list[str]]:
    """Whether an answerable question was answered correctly, plus the missing key facts.

    Only an ``answered`` outcome can be correct. Every other outcome counts as incorrect and
    lists all required key facts as missing. Key facts already present in ``question`` are not
    required (see ``required_key_facts``).
    """
    required = required_key_facts(key_facts, question, header_names)
    if outcome != "answered":
        return False, required
    missing = [fact for fact in required if not fact_present(fact, answer, header_names)]
    return not missing, missing


# ------------------------------------------------------------------------------ identifiers


@dataclass(frozen=True)
class Identifier:
    """An identifier found in text: its kind and normalised value."""

    kind: IdentifierKind
    value: str

    def __str__(self) -> str:
        return f"{self.kind}:{self.value}"


_STOP = r"""\s`'",;)*\]>|"""
_ENDPOINT = re.compile(rf"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[^{_STOP}]*)")
_PATH = re.compile(rf"(?<![\w/.:])(/(?:v\d+|oauth)/[^{_STOP}]*)")
_ERROR_CODE = re.compile(r"\b[A-Z]{2,5}-\d{3}\b")
_SCOPE = re.compile(r"\b[a-z]+:(?:read|write)\b")
_HEADER = re.compile(
    r"\bX-[A-Za-z0-9-]+\b|\b(?:Idempotency-Key|Retry-After|Authorization|Location)\b"
)
_BACKTICK = re.compile(r"`([^`\n]+)`")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CAMEL = re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]+)+\b")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BRACES = re.compile(r"\{[^}]*\}")


def _normalise_path(path: str) -> str:
    path = re.split(r"[?#]", path, maxsplit=1)[0]
    return _BRACES.sub("{}", path).rstrip(".:")


def extract_identifiers(text: str) -> set[Identifier]:
    """Find endpoints, paths, error codes, scopes, headers and schema, field or operation names.

    Headers are matched as written and compared case-insensitively (the value is lower-cased).
    """
    found: set[Identifier] = set()
    for match in _ENDPOINT.finditer(text):
        found.add(Identifier("endpoint", f"{match.group(1)} {_normalise_path(match.group(2))}"))
    without_endpoints = _ENDPOINT.sub(" ", text)
    for match in _PATH.finditer(without_endpoints):
        found.add(Identifier("path", _normalise_path(match.group(1))))
    found.update(Identifier("error_code", m.group(0)) for m in _ERROR_CODE.finditer(text))
    found.update(Identifier("scope", m.group(0)) for m in _SCOPE.finditer(text))
    found.update(Identifier("header", m.group(0).lower()) for m in _HEADER.finditer(text))
    for match in _BACKTICK.finditer(text):
        token = match.group(1).strip()
        if _IDENT.match(token):
            found.add(Identifier("name", token))
    found.update(Identifier("name", m.group(0)) for m in _CAMEL.finditer(text))
    return found


@dataclass(frozen=True)
class Vocabulary:
    """The identifiers known from some text, plus every word in it.

    A ``name`` identifier counts as known when the word appears anywhere in the text, because
    reference text rarely wraps names in backticks. An endpoint also makes its path known.
    """

    identifiers: frozenset[Identifier]
    words: frozenset[str]

    def contains(self, identifier: Identifier) -> bool:
        """Whether the identifier is supported by this vocabulary."""
        if identifier.kind == "name":
            return identifier.value in self.words
        return identifier in self.identifiers


def vocabulary_from_texts(texts: Iterable[str], extra_names: Iterable[str] = ()) -> Vocabulary:
    """Build a vocabulary from texts, plus extra known names (for example spec field names)."""
    identifiers: set[Identifier] = set()
    words: set[str] = set(extra_names)
    for text in texts:
        identifiers |= extract_identifiers(text)
        words.update(_WORD.findall(text))
    identifiers |= {
        Identifier("path", i.value.split(" ", 1)[1]) for i in identifiers if i.kind == "endpoint"
    }
    return Vocabulary(frozenset(identifiers), frozenset(words))


def spec_names(specs: Iterable[ParsedSpec]) -> set[str]:
    """Every schema, field, parameter and operation name in the parsed specs."""
    names: set[str] = set()
    for spec in specs:
        for operation in spec.operations:
            names.add(operation.operation_id)
            names.update(p.name for p in operation.parameters)
        for schema in spec.component_schemas:
            names.add(schema.name)
            names.update(f.name for f in schema.view.fields)
    return names


def corpus_vocabulary(chunks: Sequence[Chunk], specs: Iterable[ParsedSpec] = ()) -> Vocabulary:
    """The vocabulary of the whole corpus: all chunk texts plus the spec names."""
    return vocabulary_from_texts((c.content for c in chunks), spec_names(specs))


def context_vocabulary(context_chunks: Sequence[Chunk]) -> Vocabulary:
    """The vocabulary of everything the prompt showed for these chunks: content and excerpt id.

    The excerpt id (for example ``statements-api:getStatement:parameters``) is part of the
    prompt, so a name the model reads from it is grounded in what it was given.
    """
    return vocabulary_from_texts(f"{c.chunk_id}\n{c.content}" for c in context_chunks)


@dataclass(frozen=True)
class Groundedness:
    """Identifiers in an answer that the context (``unsupported``) or the corpus (``invented``)
    does not contain. Both lists are sorted and use ``kind:value`` strings."""

    unsupported: tuple[str, ...]
    invented: tuple[str, ...]


def score_groundedness(
    answer: str, question: str, context: Vocabulary, corpus: Vocabulary
) -> Groundedness:
    """Compare the answer's identifiers with the context and the corpus.

    Identifiers that the question itself contains are never counted: repeating them is not a
    grounding failure.
    """
    asked = vocabulary_from_texts([question])
    answer_ids = extract_identifiers(answer)
    unsupported = sorted(
        str(i) for i in answer_ids if not context.contains(i) and not asked.contains(i)
    )
    invented = sorted(
        str(i) for i in answer_ids if not corpus.contains(i) and not asked.contains(i)
    )
    return Groundedness(tuple(unsupported), tuple(invented))


def mentions_endpoint(answer: str) -> bool:
    """Diagnostic only: whether the answer contains any method and path."""
    return _ENDPOINT.search(answer) is not None


# ------------------------------------------------------------------------------ citations


def citations_valid(cited: Collection[str], context_ids: Collection[str]) -> bool:
    """Every cited id was among the chunks in the prompt."""
    return set(cited) <= set(context_ids)


def cites_relevant(cited: Collection[str], relevant_ids: Collection[str]) -> bool:
    """At least one cited id is a relevant chunk."""
    return bool(set(cited) & set(relevant_ids))


def context_hit(context_ids: Sequence[str], relevant_ids: Collection[str], k: int) -> bool:
    """Whether any of the top ``k`` context chunks is relevant."""
    relevant = set(relevant_ids)
    return any(chunk_id in relevant for chunk_id in context_ids[:k])
