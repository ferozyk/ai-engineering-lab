# Answer report: 20261117T173854Z-answers-measured-agentic

## Setup

- Corpus: version 1.0.0, checksum `72063d1be60b13a9e9a5105f04b081a161fa010cb11d210d0be3589b8726c0e6`
- Question set: measured, version 1.0.0, checksum `28d846ec119f105cbb6d6b36b5b00bda0dd7b7a1b16d4b43179c359f5432cede`
- Generation model: `nvidia/nemotron-3.5-super-vl:free` via openrouter; served by models ['nvidia/nemotron-3.5-super-vl:free'], providers ['Nvidia']
- Prompt: version a-1.0, hash `bc694d3da6e02137e4df755079dc355e99a1cf29506953c90c17631ac919abfc`
- Agent: {'prompt_version': 'd-1.0', 'max_searches': 3, 'results_per_search': 5, 'max_context_chunks': 10, 'max_planned_queries': 2, 'prompt_hash': '9e8b93edc35a9fd6c48f2ee17c6417a2fffb91c2e794100247076cdaa8f92ed1', 'search_tool': {'retriever': 'hybrid', 'bm25_k1': 1.2, 'bm25_b': 0.75, 'rrf_k': 60, 'candidate_depth': 50}}
- Generation settings: {'prompt_version': 'a-1.0', 'temperature': 0.0, 'max_output_tokens': 16384, 'llm_seed': None, 'request_timeout_seconds': 300}
- Run settings: {'repetitions': 3, 'order_seed': 20261111, 'rate_limit_per_minute': 15, 'daily_request_cap': 900, 'canary_question_ids': ['Q01', 'Q05', 'Q14']}
- Retrieval: agentic, context = up to 10 chunks; embedding `BAAI/bge-m3` revision `5617a9f61b028005a4858fdac845db406aefb181` (cpu); collection `lab-bank-c1-0-0-72063d1b-bge-m3-5617a9f6-m2400`; retrieval deterministic: False
- Run timing: started 2026-11-17 17:38:53 UTC, finished 2026-11-17 18:16:08 UTC
- Git: `0b1ff66434fe17d45751334f89d5dbedbe009f01` (dirty: False); Python 3.12.12; macOS-15.0.1-arm64-arm-64bit
- Attempts: 120 planned, 120 completed, 0 unresolved infrastructure errors; halted: False

## Results

Infrastructure errors are excluded from every quality denominator below.

| group | n | answered | refused | invalid | cut off | correctness (answerable) | false refusal (answerable) | correct refusal (unanswerable) |
|---|---|---|---|---|---|---|---|---|
| overall | 120 | 102 | 18 | 0 | 0 | 85/102 = 0.833 | 1/102 = 0.010 | 17/18 = 0.944 |
| authentication | 15 | 15 | 0 | 0 | 0 | 12/15 = 0.800 | 0/15 = 0.000 | n/a (0) |
| comparison | 9 | 9 | 0 | 0 | 0 | 8/9 = 0.889 | 0/9 = 0.000 | n/a (0) |
| endpoint_discovery | 15 | 15 | 0 | 0 | 0 | 15/15 = 1.000 | 0/15 = 0.000 | n/a (0) |
| exact_identifier | 18 | 18 | 0 | 0 | 0 | 15/18 = 0.833 | 0/18 = 0.000 | n/a (0) |
| multi_endpoint | 12 | 12 | 0 | 0 | 0 | 9/12 = 0.750 | 0/12 = 0.000 | n/a (0) |
| schema | 15 | 14 | 1 | 0 | 0 | 11/15 = 0.733 | 1/15 = 0.067 | n/a (0) |
| semantic | 18 | 18 | 0 | 0 | 0 | 15/18 = 0.833 | 0/18 = 0.000 | n/a (0) |
| unanswerable | 18 | 1 | 17 | 0 | 0 | n/a (0) | n/a (0) | 17/18 = 0.944 |

## Hypotheses (frozen criteria, computed mechanically)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HD1 | multi_endpoint attempts whose collected context covers every labelled source >= 9/12 | supported | full source coverage 9/12 = 0.750; architecture B: 3/12 |
| HD2 | correct answerable attempts >= 80/102 | supported | correct 85/102 = 0.833; architecture B: 78/102 |
| HD3 | correct refusals on unanswerable attempts >= 17/18 | supported | correct refusals 17/18 = 0.944; architecture B: 18/18 |

## Guardrails

| measure | value |
|---|---|
| correct refusal (unanswerable) | 17/18 = 0.944 |
| made-up answer (unanswerable) | 1/18 = 0.056 |
| invalid answers on unanswerable attempts | 0 |
| cut-off answers on unanswerable attempts | 0 |
| false refusal (answerable) | 1/102 = 0.010 |
| diagnostic: unanswerable answers naming an endpoint (not scored) | 3 |

## Groundedness and citations

Identifiers only (endpoints, paths, error codes, scopes, headers, names); identifiers repeated from the question are not counted.

| measure | value |
|---|---|
| answers with at least one unsupported identifier | 0/120 = 0.000 |
| answers with at least one invented identifier | 0/120 = 0.000 |
| all cited ids were in the context (answered, must cite) | 101/101 = 1.000 |
| at least one cited id is relevant (answered, must cite) | 98/101 = 0.970 |

Most frequent unsupported identifiers: none

Most frequent invented identifiers: none

## Per question

| id | category | context hit | correct | outcomes | agree | missing key facts |
|---|---|---|---|---|---|---|
| Q101 | semantic | yes | 0/3 | answered, answered, answered | yes | `VAL-001` |
| Q102 | semantic | yes | 3/3 | answered, answered, answered | yes | - |
| Q103 | exact_identifier | yes | 3/3 | answered, answered, answered | yes | - |
| Q104 | semantic | yes | 3/3 | answered, answered, answered | yes | - |
| Q105 | schema | yes | 3/3 | answered, answered, answered | yes | - |
| Q106 | schema | yes | 0/3 | answered, answered, answered | yes | `pageSize` |
| Q107 | exact_identifier | yes | 3/3 | answered, answered, answered | yes | - |
| Q108 | semantic | yes | 3/3 | answered, answered, answered | yes | - |
| Q109 | exact_identifier | yes | 3/3 | answered, answered, answered | yes | - |
| Q110 | semantic | yes | 3/3 | answered, answered, answered | yes | - |
| Q111 | schema | yes | 3/3 | answered, answered, answered | yes | - |
| Q112 | semantic | yes | 3/3 | answered, answered, answered | yes | - |
| Q113 | schema | yes | 3/3 | answered, answered, answered | yes | - |
| Q114 | schema | yes | 2/3 | answered, refused, answered | no | `CREDIT`, `DEBIT`, `creditDebitIndicator` |
| Q115 | exact_identifier | yes | 0/3 | answered, answered, answered | yes | `404` |
| Q116 | exact_identifier | yes | 3/3 | answered, answered, answered | yes | - |
| Q117 | exact_identifier | yes | 3/3 | answered, answered, answered | yes | - |
| Q118 | endpoint_discovery | yes | 3/3 | answered, answered, answered | yes | - |
| Q119 | endpoint_discovery | yes | 3/3 | answered, answered, answered | yes | - |
| Q120 | endpoint_discovery | yes | 3/3 | answered, answered, answered | yes | - |
| Q121 | endpoint_discovery | yes | 3/3 | answered, answered, answered | yes | - |
| Q122 | endpoint_discovery | yes | 3/3 | answered, answered, answered | yes | - |
| Q123 | authentication | yes | 3/3 | answered, answered, answered | yes | - |
| Q124 | authentication | yes | 3/3 | answered, answered, answered | yes | - |
| Q125 | authentication | yes | 3/3 | answered, answered, answered | yes | - |
| Q126 | authentication | yes | 3/3 | answered, answered, answered | yes | - |
| Q127 | authentication | yes | 0/3 | answered, answered, answered | yes | `statements:read` |
| Q128 | multi_endpoint | yes | 3/3 | answered, answered, answered | yes | - |
| Q129 | multi_endpoint | yes | 3/3 | answered, answered, answered | yes | - |
| Q130 | multi_endpoint | yes | 0/3 | answered, answered, answered | yes | `GET /v1/customers/{customerId}` |
| Q131 | multi_endpoint | yes | 3/3 | answered, answered, answered | yes | - |
| Q132 | comparison | yes | 3/3 | answered, answered, answered | yes | - |
| Q133 | comparison | yes | 2/3 | answered, answered, answered | no | `currency` |
| Q134 | comparison | yes | 3/3 | answered, answered, answered | yes | - |
| Q135 | unanswerable | no | 3/3 | refused, refused, refused | yes | - |
| Q136 | unanswerable | no | 3/3 | refused, refused, refused | yes | - |
| Q137 | unanswerable | no | 3/3 | refused, refused, refused | yes | - |
| Q138 | unanswerable | no | 2/3 | refused, refused, answered | no | - |
| Q139 | unanswerable | no | 3/3 | refused, refused, refused | yes | - |
| Q140 | unanswerable | no | 3/3 | refused, refused, refused | yes | - |

For an unanswerable question 'correct' counts correct refusals.

## Agent behaviour

Scored attempts: 120. Retrieval is chosen by the model, so it can differ between repetitions; each attempt is scored on the context it collected.

| per attempt | mean | p50 | max |
|---|---|---|---|
| model calls | 3.25 | 3.0 | 5 |
| searches | 2.18 | 2.0 | 3 |
| context chunks | 7.78 | - | 10 |

Model calls per attempt:

| value | attempts |
|---|---|
| 3 | 92 |
| 4 | 26 |
| 5 | 2 |

Searches per attempt:

| value | attempts |
|---|---|
| 1 | 6 |
| 2 | 86 |
| 3 | 28 |

| planner and judge | value |
|---|---|
| planner reported needs_retrieval = false | 0 |
| plan replies that could not be used (fell back to the question) | 0 |
| judge replies that could not be parsed (counted as enough) | 0 |
| first judge decision was enough | 92/120 = 0.767 |

Attempts whose collected context covers every labelled source, by category (answerable attempts):

| category | full source coverage |
|---|---|
| authentication | 13/15 attempts |
| comparison | 9/9 attempts |
| endpoint_discovery | 15/15 attempts |
| exact_identifier | 18/18 attempts |
| multi_endpoint | 9/12 attempts |
| schema | 14/15 attempts |
| semantic | 17/18 attempts |

Queries run in repetition 1 for each multi_endpoint question (model output):

- Q131: `find customer by last name`, `customer consents`
- Q130: `change customer email address endpoint`, `confirm email address change endpoint`, `customers-api email confirmation endpoint`
- Q129: `list customer accounts endpoint`, `read account balance endpoint`
- Q128: `cancel payment`, `get payment status`

## Latency

Qdrant local mode, in-process, exact search; CPU. Total = embed + search + agent (planner and judge calls) + generation, without client-side throttling. With few attempts p95 rests on a handful of observations.

| stage | n | p50 (ms) | p95 (ms) |
|---|---|---|---|
| embed | 120 | 393.45 | 2406.45 |
| search | 120 | 6.53 | 22.27 |
| agent | 120 | 8468.79 | 24439.19 |
| generation | 120 | 3774.10 | 12331.97 |
| total | 120 | 14185.42 | 33912.04 |

## Tokens and cost (estimated)

Tokens as reported by the provider.

| tokens | n | mean | p50 | p95 |
|---|---|---|---|---|
| prompt | 120 | 3572.6 | 3377.0 | 6103.6 |
| completion | 120 | 1130.7 | 974.5 | 2213.1 |
| total | 120 | 4703.2 | 4404.0 | 8186.2 |
| reasoning | 120 | 971.0 | 840.5 | 1915.9 |

- Estimated cost per 1,000 questions: $1.1012 (estimated, not billed; pricing source: paid_variant). Estimated, not billed. Estimated at the paid variant's list price (nvidia/nemotron-3.5-super-vl) captured 2026-11-17
- Estimated cost of this run: $0.1321
- Requests: 390 sent, 0 failed, 0 retried; 0 infrastructure-error records

## Charts

![ha3_correctness_by_context.png](../../charts/20261117T173854Z-answers-measured-agentic/ha3_correctness_by_context.png)
![guardrails.png](../../charts/20261117T173854Z-answers-measured-agentic/guardrails.png)
![latency_by_stage.png](../../charts/20261117T173854Z-answers-measured-agentic/latency_by_stage.png)
![tokens_per_question.png](../../charts/20261117T173854Z-answers-measured-agentic/tokens_per_question.png)

## Limitations

- Small, synthetic, self-authored corpus and question set.
- A single generation model.
- Qdrant local-mode latency does not represent a Qdrant server.
- Free-model routing variance on OpenRouter.
- Deterministic groundedness covers identifiers only.
- BGE-M3 is larger than an English corpus of this size needs.
- The sample size is small, so results are per-question rather than statistically significant.
- This run: 120 attempts over 40 questions; 0 unresolved infrastructure errors; 0 invalid and 0 cut-off answers.

Author interpretation: see the experiment README.
