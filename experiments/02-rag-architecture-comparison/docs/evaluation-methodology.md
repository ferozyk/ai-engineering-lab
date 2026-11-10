# Evaluation methodology

Status: architecture A hypotheses frozen (2026-11-11). Nothing in this document is a result.

## 1. Principles

- Measure retrieval and answers separately.
- Use deterministic checks first.
- Nothing is counted as good because it reads plausibly.
- Write hypotheses down before measuring.
- Report per-question results, not only averages.

## 2. Question record schema

One record per question, validated against [question.schema.json](../datasets/evaluation/question.schema.json).

| Field | Type | Meaning |
|---|---|---|
| `id` | string, `Q` plus 2 or 3 digits | Stable question id. |
| `question` | string | The question as a user would ask it. |
| `category` | enum | See below. |
| `expected_answer` | string | The reference answer, written from the spec. |
| `key_facts` | list of strings | Facts a correct answer must contain. Checked mechanically. |
| `relevant_sources` | list of sources | Spec elements containing the evidence, as `{document_id}#{JSON Pointer}`. May be empty only when `must_abstain` is true. |
| `relevant_document_ids` | list of strings | Specs containing the evidence; must match the document ids in `relevant_sources`. |
| `constraints` | object | `must_cite` (boolean) and `must_abstain` (boolean). |
| `paraphrase_of` | string or null | Id of the question this rephrases. |
| `notes` | string | Free text. |

**Categories:** `semantic`, `exact_identifier`, `endpoint_discovery`, `authentication`, `schema`, `multi_endpoint`, `comparison`, `unanswerable`.

## 3. Draft question set

Fifteen questions. Relevant pointers are described rather than listed; final pointers are fixed in Stage 2 once the specs exist.

**Development set vs measured set.** These 15 questions are the development set, used to build and debug the pipeline. With one to three questions per category they are too few to test per-category hypotheses, so measured runs use the expanded set (below), frozen and versioned before the first measured run.

| id | category | question | expected answer and key facts |
|---|---|---|---|
| Q01 | endpoint_discovery | Which endpoint lists all the accounts a customer holds? | `GET /v1/customers/{customerId}/accounts` |
| Q02 | authentication | What headers must be sent when calling `GET /v1/accounts/{accountId}/balances`? | `Authorization` (Bearer token with scope `accounts:read`), `X-Api-Key` |
| Q03 | semantic | How can I get a statement covering a custom date range rather than a calendar month? | `POST /v1/accounts/{accountId}/statement-requests`, then poll `GET /v1/statement-requests/{requestId}` |
| Q04 | comparison | What is the difference between `GET /v1/accounts/{accountId}` and `GET /v2/accounts/{accountId}`? | v1 is deprecated; v2 adds `availableBalance` and `overdraftLimit` |
| Q05 | multi_endpoint | Starting from a customer ID, which API calls are needed to download one of their account statements? | `POST /oauth/token`, `GET /v1/customers/{customerId}/accounts`, `GET /v1/accounts/{accountId}/statements`, `GET /v1/accounts/{accountId}/statements/{statementId}` |
| Q06 | authentication | What response does a consumer get when the access token is missing or expired? | HTTP 401, `application/problem+json`, code `AUTH-001` |
| Q07 | exact_identifier | Which endpoint accepts `fromDate` as a query parameter? | `GET /v1/accounts/{accountId}/transactions` (not the statement-request body) |
| Q08 | schema | What are the required fields of `StatementRequest`? | `fromDate`, `toDate`, `format` |
| Q09 | exact_identifier | What does error code `RATE-001` mean and which header says when to retry? | HTTP 429 too many requests; `Retry-After` |
| Q10 | exact_identifier | Which HTTP method and path does `updateContactDetails` use, and what scope does it need? | `PATCH /v1/customers/{customerId}/contact-details`; `customers:write` |
| Q11 | semantic | If a payment request times out and I retry it, how do I make sure the payment isn't made twice? | `Idempotency-Key` header on `POST /v1/payments` |
| Q12 | schema | What is the maximum page size when listing transactions? | `limit`, max 500 (default 100) |
| Q13 | authentication | Which OAuth scope is required to read statements? | `statements:read` |
| Q14 | unanswerable | Which endpoint closes a customer's bank account? | Must abstain; no such endpoint |
| Q15 | unanswerable | How many requests per minute does the Payments API allow? | Must abstain; the specs define `RATE-001` and `Retry-After` but no numeric limit |

**Note on Q07.** The `fromDate` look-alike is intentional: it is a query parameter on one endpoint and a body field on another.

### Expansion to 30–50 questions

- Balance the categories, with at least four questions each.
- Add paraphrase pairs: each question written once in the spec's vocabulary and once with no shared content words, linked by `paraphrase_of`. This isolates lexical from semantic retrieval.
- Add more multi-endpoint and comparison questions, which architecture D is expected to affect.
- Keep roughly 15% unanswerable, including near-miss ones like Q15.

### Bias control

The same person writes the corpus and the questions, which risks questions that are too easy for the corpus's wording. Mitigations: paraphrases are written before looking at chunk text, the maintainer reviews the set, and the set is frozen and versioned before any measured run.

## 4. Retrieval metrics

Computed from retrieved chunks and the labelled pointers, using the relevance rule in [dataset-design.md](dataset-design.md) section 3. They need no model requests. K takes the values 1, 3, 5 and 10.

- **Hit@K:** 1 if any relevant chunk is in the top K, else 0. Averaged over questions.
- **Recall@K:** covered relevant pointers divided by total relevant pointers. A pointer is covered if at least one top-K chunk is relevant to it.
- **Precision@K:** relevant chunks in the top K divided by K.
- **MRR:** the mean over questions of 1/rank of the first relevant chunk, or 0 if none appears within the top 10.

**Worked example (illustrative numbers, not results).** A question has two labelled pointers, P1 and P2. The top 5 chunks are, in order: not relevant, relevant to P1, not relevant, relevant to P2, not relevant.

- Hit@5 = 1.
- Recall@5 = 2 / 2 = 1.0. Recall@3 = 1 / 2 = 0.5.
- Precision@5 = 2 / 5 = 0.4.
- Reciprocal rank = 1 / 2 = 0.5.

**Caveat on Precision@K.** When a question has few relevant items, Precision@K has a ceiling of (number relevant) / K. With one relevant item, Precision@5 cannot exceed 0.2. It is reported but not used to rank architectures.

Unanswerable questions are excluded from retrieval metrics.

## 5. Answer metrics

Deterministic checks first.

### Correctness

An answer is correct when all `key_facts` are present after normalisation:

- Path templates compare with parameter names masked, so `{accountId}` and `{}` are equal.
- Header names compare case-insensitively.
- Field names, error codes and scopes compare exactly.
- Other key facts (numbers such as `500`, keywords such as `deprecated`) match case-insensitively as whole words.

### Groundedness (faithfulness)

Extract identifiers from the answer: HTTP method and path, header names, error codes, scopes, and schema and field names (matched against a vocabulary built from the corpus).

- An identifier is **unsupported** if it is absent from the retrieved chunks.
- An identifier is **invented** if it is absent from the whole corpus.
- Report the rate of answers with at least one unsupported identifier and the rate with at least one invented identifier.

Limitation: prose claims, such as "v1 is deprecated", are not covered. Manual review handles those.

### Citation validity

Every cited chunk id must have been retrieved, and at least one cited chunk must be relevant.

### Abstention

For `must_abstain` questions:

- **Correct-refusal rate:** `insufficient_context` is true and no endpoint is asserted as the answer.
- **Made-up-answer rate:** the answer asserts something instead of refusing.

Reported separately from accuracy, as a guardrail metric.

### Answer relevance

At this question-set size, every answer is reviewed manually against a three-level rubric: answers the question, partially, or not. An LLM judge is added later only if needed, with its model, prompt, limitations and cost documented.

## 6. Performance metrics

- **Latency per stage:** query embedding, retrieval, rerank (architecture C), generation and total. Report p50 and p95. With a few dozen questions and three repetitions, p95 rests on a handful of observations, and the report says so.
- **Tokens:** as reported by the provider. If the provider does not report them, they are marked "unavailable", not estimated.
- **Cost:** provider-reported, or computed from a documented pricing snapshot and labelled *estimated*. A free model is billed at $0, as in experiment 01.
- **Success and failure rates:** infrastructure errors are excluded from quality metrics but counted and reported.
- **Indexing cost** is one-off and reported separately: chunk count and embedding time.

## 7. Controls and reproducibility

- Same corpus, questions, generation model, temperature 0, prompt version and top-K across architectures.
- Repetitions: three per question for generation, to see variance; one for retrieval, which is deterministic. Determinism is checked by running retrieval twice and comparing.
- Run metadata: every field in section 13 of the [benchmarking standards](../../../docs/standards/benchmarking-standards.md), plus corpus version and checksum, evaluation set version, embedding model, revision and device, chunking config, retrieval config and prompt version.
- Request budget: with a measured set of 30–50 questions, about 90–150 generation requests for architecture A (three repetitions), plus a two-question canary. The daily cap and limiter work as in experiment 01.

## 8. Hypotheses

### Architecture A (frozen 2026-11-11)

Frozen before any retrieval or answer measurement, on the frozen measured question set (Q101–Q140, version 1.0.0). The criteria will not be changed after seeing data; any later analysis that differs is reported as exploratory. All are *unverified*.

Fixed settings: dense retrieval returns the top 10 chunks for retrieval metrics; the generation context is the top 5 (K = 5); temperature 0; three generation repetitions per question.

- **HA1:** Hit@5 over the `semantic` and `endpoint_discovery` questions combined (11 questions) is at least 0.80, i.e. at least 9 of 11.
- **HA2:** Hit@5 over the `exact_identifier` questions (6 questions) is at least 0.20 lower than the HA1 value.
- **HA3:** over all answerable measured questions and repetitions, correctness is at least 0.80 for answers whose top-5 context contained a relevant chunk, and at most 0.20 for answers whose context contained none. If fewer than 3 answers fall in the "none" group, that half is reported as not testable rather than supported.
- **HA4:** over the 6 unanswerable questions × 3 repetitions, the correct-refusal rate (section 5) is at least 0.80.

Retrieval is deterministic, so HA1 and HA2 use one retrieval pass per question. With 6 to 11 questions per group, one question moves a rate by 9 to 17 points; results are reported per question as well.

Placeholders for later milestones, to be made precise before their runs:

- **HB:** hybrid retrieval improves `exact_identifier` Hit@5 without lowering `semantic` Hit@5 by more than 5 points.
- **HC:** reranking improves MRR; the added latency is reported.
- **HD:** agentic retrieval improves `multi_endpoint` recall, at the cost of more model calls per question.

## 9. Limitations

- Small, synthetic, self-authored corpus and question set.
- A single generation model.
- Qdrant local-mode latency does not represent a Qdrant server.
- Free-model routing variance on OpenRouter.
- Deterministic groundedness covers identifiers only.
- BGE-M3 is larger than an English corpus of this size needs.
- The sample size is small, so results are per-question rather than statistically significant.
