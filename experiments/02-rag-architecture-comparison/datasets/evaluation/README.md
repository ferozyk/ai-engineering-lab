# evaluation

Questions used to evaluate every architecture. One JSON object per line in a `.jsonl` file, validated against [question.schema.json](question.schema.json).

`examples.jsonl` holds three illustrative records (Q02, Q07, Q14). They show the format only. Final pointers are fixed when the corpus is written in Stage 2.

## How questions are written

1. Write the question and the expected answer from the spec, not from retrieved chunks.
2. List the `key_facts` that a correct answer must contain. These are checked mechanically.
3. Label the spec elements that contain the evidence, as sources (`{document_id}#{RFC 6901 JSON Pointer}`) in `relevant_sources`.
4. Write paraphrase pairs before looking at chunk text, and link them with `paraphrase_of`.
5. The maintainer reviews the set. It is then frozen and versioned.

## Relevance rule: sources, not chunk IDs

Questions label **spec elements**, not chunks. A source is `{document_id}#{JSON Pointer}`, for example `accounts-api#/paths/~1v1~1accounts~1{accountId}~1transactions/get/parameters`; the document id is needed because pointers repeat across specs.

- Every spec element is owned by the chunk whose `source_reference` is its longest whole-segment prefix (so the `operation` chunk owns `.../get/security`, but the `parameters` chunk owns `.../get/parameters`).
- A chunk is relevant to a labelled source if it owns it, or if the chunk's pointer is a descendant of it.

The full rule and a worked example are in [docs/dataset-design.md](../../docs/dataset-design.md#3-ground-truth-uses-json-pointers-not-chunk-ids).

Chunk IDs change whenever chunking changes. Pointers do not, so the same questions can compare chunking strategies later.

## Unanswerable questions

Questions with `constraints.must_abstain: true` may have an empty `relevant_sources`. They are excluded from retrieval metrics and scored separately for abstention.
