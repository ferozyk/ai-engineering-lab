"""The ownership rule that links labelled spec elements to chunks.

A question labels *spec elements* (a document id plus a JSON Pointer), not chunks. A chunk is
relevant to a labelled source when it owns the element (its ``source_reference`` is the longest
whole-segment prefix of the pointer) or when it was built from something inside the element.
"""

from collections.abc import Collection, Sequence

from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.ingestion.pointers import Source, is_prefix, split_pointer


def owner_chunks(source: Source, chunks: Sequence[Chunk]) -> list[Chunk]:
    """Chunks of the same document whose pointer is the longest prefix of the source pointer.

    Split parts of one chunk share a ``source_reference``, so all of them are returned.
    """
    candidates = [
        c
        for c in chunks
        if c.document_id == source.document_id and is_prefix(c.source_reference, source.pointer)
    ]
    if not candidates:
        return []
    longest = max(len(split_pointer(c.source_reference)) for c in candidates)
    return [c for c in candidates if len(split_pointer(c.source_reference)) == longest]


def _relevant_to(source: Source, chunks: Sequence[Chunk]) -> set[str]:
    ids = {c.chunk_id for c in owner_chunks(source, chunks)}
    ids.update(
        c.chunk_id
        for c in chunks
        if c.document_id == source.document_id and is_prefix(source.pointer, c.source_reference)
    )
    return ids


def relevant_chunk_ids(sources: Collection[Source], chunks: Sequence[Chunk]) -> frozenset[str]:
    """Ids of every chunk that is relevant to at least one labelled source."""
    ids: set[str] = set()
    for source in sources:
        ids.update(_relevant_to(source, chunks))
    return frozenset(ids)


def is_relevant(chunk: Chunk, sources: Collection[Source], chunks: Sequence[Chunk]) -> bool:
    """True if ``chunk`` is relevant to any of the sources."""
    return chunk.chunk_id in relevant_chunk_ids(sources, chunks)


def covered_sources(
    retrieved_chunk_ids: Collection[str], sources: Collection[Source], chunks: Sequence[Chunk]
) -> frozenset[Source]:
    """The labelled sources for which at least one retrieved chunk is relevant."""
    retrieved = set(retrieved_chunk_ids)
    return frozenset(s for s in sources if retrieved & _relevant_to(s, chunks))
