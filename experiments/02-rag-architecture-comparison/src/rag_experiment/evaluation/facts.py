"""Key-fact matching: decide whether a fact appears in a piece of text.

The same rules are used to check that the labelled evidence contains the answer (dataset
validation) and, in a later phase, to score generated answers.
"""

import re
from collections.abc import Iterable

from rag_experiment.corpus import Corpus

_METHOD_PATH = re.compile(r"^(GET|POST|PUT|PATCH|DELETE)\s+/\S*$")
_PATH = re.compile(r"^/\S*$")
_PLAIN = re.compile(r"^[a-z0-9]+$")
_PARAM_NAME = re.compile(r"\{[^}]*\}")
_SPACES = re.compile(r"\s+")

# A "whole token" is not glued to identifier characters. A trailing ``.``, ``:`` or ``-`` only
# glues when another identifier character follows it, so "max 500." still contains ``500``.
_TOKEN_BEFORE = r"(?<![A-Za-z0-9_:\-.])"
_TOKEN_AFTER = r"(?![A-Za-z0-9_])(?![:\-.][A-Za-z0-9_])"


def _mask(text: str) -> str:
    return _SPACES.sub(" ", _PARAM_NAME.sub("{}", text)).strip()


def _token_search(fact: str, text: str, flags: int = 0) -> bool:
    pattern = _TOKEN_BEFORE + re.escape(fact) + _TOKEN_AFTER
    return re.search(pattern, text, flags) is not None


def fact_present(fact: str, text: str, header_names: frozenset[str]) -> bool:
    """Whether ``fact`` appears in ``text``. The first matching rule decides how.

    1. Path facts (``/v1/x`` or ``GET /v1/x``): parameter names are masked, whitespace collapsed,
       and the match must not continue into a longer path.
    2. Header names: case-insensitive whole token.
    3. Plain lowercase words and numbers (``deprecated``, ``500``): case-insensitive whole token.
    4. Anything else (field names, codes, scopes): exact, case-sensitive whole token.
    """
    if _METHOD_PATH.match(fact) or _PATH.match(fact):
        masked_fact = _mask(fact)
        pattern = r"(?<![A-Za-z0-9_{}\-])" + re.escape(masked_fact) + r"(?![A-Za-z0-9_/{}\-])"
        return re.search(pattern, _mask(text)) is not None
    if fact.lower() in {h.lower() for h in header_names}:
        return _token_search(fact, text, re.IGNORECASE)
    if _PLAIN.match(fact):
        return _token_search(fact, text, re.IGNORECASE)
    return _token_search(fact, text)


def corpus_header_names(corpus: Corpus) -> frozenset[str]:
    """Every header name that appears in the corpus, plus ``Authorization``."""
    names: set[str] = {"Authorization"}
    for spec in corpus.specs:
        for scheme in spec.security_schemes:
            if scheme.type == "apiKey" and scheme.location == "header" and scheme.header_name:
                names.add(scheme.header_name)
        for op in spec.operations:
            names.update(p.name for p in op.parameters if p.location == "header")
            for response in op.responses:
                names.update(h.name for h in response.headers)
    return frozenset(names)


def all_present(facts: Iterable[str], text: str, header_names: frozenset[str]) -> list[str]:
    """Return the facts that are missing from ``text`` (empty when all are present)."""
    return [f for f in facts if not fact_present(f, text, header_names)]
