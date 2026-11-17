"""A deterministic stand-in reranker for tests and dry runs. It is not a real model."""

import hashlib
import re
from collections.abc import Sequence

_TOKEN = re.compile(r"[a-z0-9]+")


class FakeReranker:
    """Scores by the number of shared lower-cased words, with a tiny stable tie-breaker."""

    model_id = "fake-word-overlap"
    revision = "fake"

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        """One score per text: shared word count plus a hash-derived value below 0.001."""
        query_words = set(_TOKEN.findall(query.lower()))
        scores: list[float] = []
        for text in texts:
            shared = len(query_words & set(_TOKEN.findall(text.lower())))
            digest = hashlib.blake2b(text.encode("utf-8"), digest_size=4).digest()
            tie_break = int.from_bytes(digest, "big") / 2**32 * 0.001
            scores.append(shared + tie_break)
        return scores
