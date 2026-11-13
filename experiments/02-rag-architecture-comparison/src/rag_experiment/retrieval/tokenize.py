"""Identifier-aware tokeniser for BM25.

Lexical search only matches whole tokens. API text is full of identifiers such as ``X-Api-Key``,
``accounts:read``, ``STM-404`` or ``pageSize``; a plain word splitter would either keep them
glued together (so a question about "the api key header" misses ``X-Api-Key``) or tear them apart
(so a question about the exact string ``X-Api-Key`` loses its specificity). This tokeniser emits
both the whole identifier and its parts.

Rules (deterministic, no learned components):

1. Find compounds: runs of letters and digits joined by ``-``, ``:``, ``_``, ``.`` or ``/``.
2. For each compound emit the lower-cased compound; if it contains a separator, also emit each
   part, lower-cased.
3. For every part (or the compound itself when it has no separator) that has a lower-to-upper
   camelCase boundary, also emit the camelCase pieces, lower-cased.
4. Drop tokens shorter than 2 characters and a fixed list of English stop words.
5. Keep duplicates: term frequency matters to BM25.
"""

import re

_COMPOUND = re.compile(r"[A-Za-z0-9]+(?:[-:_./][A-Za-z0-9]+)*")
_SEPARATORS = re.compile(r"[-:_./]")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

MIN_TOKEN_LENGTH = 2
STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "my",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
    }
)


def _camel_pieces(part: str) -> list[str]:
    pieces = _CAMEL_BOUNDARY.split(part)
    return [p.lower() for p in pieces] if len(pieces) > 1 else []


def tokenize(text: str) -> list[str]:
    """Split ``text`` into lower-case BM25 tokens (see the module docstring for the rules)."""
    tokens: list[str] = []
    for compound in _COMPOUND.findall(text):
        tokens.append(compound.lower())
        parts = _SEPARATORS.split(compound)
        if len(parts) > 1:
            tokens.extend(p.lower() for p in parts)
        for part in parts:
            tokens.extend(_camel_pieces(part))
    return [t for t in tokens if len(t) >= MIN_TOKEN_LENGTH and t not in STOP_WORDS]
