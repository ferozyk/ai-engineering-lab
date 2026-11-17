# Answer report: 20261117T100130Z-answers-dev-agentic-canary

## Setup

- Corpus: version 1.0.0, checksum `72063d1be60b13a9e9a5105f04b081a161fa010cb11d210d0be3589b8726c0e6`
- Question set: dev, version 0.1.0, checksum `9d9ab2a5a6dc6338cf0ddc1f3ff041a0da12b756a9a411f2bb4c2f11e6ca944b`; canary subset Q01, Q05, Q14
- Generation model: `nvidia/nemotron-3.5-super-vl:free` via openrouter; served by models ['nvidia/nemotron-3.5-super-vl:free'], providers ['Nvidia']
- Prompt: version a-1.0, hash `bc694d3da6e02137e4df755079dc355e99a1cf29506953c90c17631ac919abfc`
- Agent: {'prompt_version': 'd-1.0', 'max_searches': 3, 'results_per_search': 5, 'max_context_chunks': 10, 'max_planned_queries': 3, 'prompt_hash': '9e8b93edc35a9fd6c48f2ee17c6417a2fffb91c2e794100247076cdaa8f92ed1', 'search_tool': {'retriever': 'hybrid', 'bm25_k1': 1.2, 'bm25_b': 0.75, 'rrf_k': 60, 'candidate_depth': 50}}
- Generation settings: {'prompt_version': 'a-1.0', 'temperature': 0.0, 'max_output_tokens': 16384, 'llm_seed': None, 'request_timeout_seconds': 300}
- Run settings: {'repetitions': 1, 'order_seed': 20261111, 'rate_limit_per_minute': 15, 'daily_request_cap': 900, 'canary_question_ids': ['Q01', 'Q05', 'Q14']}
- Retrieval: agentic, context = up to 10 chunks; embedding `BAAI/bge-m3` revision `5617a9f61b028005a4858fdac845db406aefb181` (cpu); collection `lab-bank-c1-0-0-72063d1b-bge-m3-5617a9f6-m2400`; retrieval deterministic: False
- Run timing: started 2026-11-17 10:01:30 UTC, finished 2026-11-17 10:02:10 UTC
- Git: `83d441f5af37c9477d65d426359afecf8e142a56` (dirty: False); Python 3.12.12; macOS-15.0.1-arm64-arm-64bit
- Attempts: 3 planned, 3 completed, 0 unresolved infrastructure errors; halted: False

## Results

Infrastructure errors are excluded from every quality denominator below.

| group | n | answered | refused | invalid | cut off | correctness (answerable) | false refusal (answerable) | correct refusal (unanswerable) |
|---|---|---|---|---|---|---|---|---|
| overall | 3 | 2 | 1 | 0 | 0 | 1/2 = 0.500 | 0/2 = 0.000 | 1/1 = 1.000 |
| endpoint_discovery | 1 | 1 | 0 | 0 | 0 | 1/1 = 1.000 | 0/1 = 0.000 | n/a (0) |
| multi_endpoint | 1 | 1 | 0 | 0 | 0 | 0/1 = 0.000 | 0/1 = 0.000 | n/a (0) |
| unanswerable | 1 | 0 | 1 | 0 | 0 | n/a (0) | n/a (0) | 1/1 = 1.000 |

## Hypotheses (frozen criteria, computed mechanically)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HD1 | multi_endpoint attempts whose collected context covers every labelled source >= 9/12 | not applicable (development set) | full source coverage 0/1 = 0.000; architecture B: 3/12 |
| HD2 | correct answerable attempts >= 80/102 | not applicable (development set) | correct 1/2 = 0.500; architecture B: 78/102 |
| HD3 | correct refusals on unanswerable attempts >= 17/18 | not applicable (development set) | correct refusals 1/1 = 1.000; architecture B: 18/18 |

## Guardrails

| measure | value |
|---|---|
| correct refusal (unanswerable) | 1/1 = 1.000 |
| made-up answer (unanswerable) | 0/1 = 0.000 |
| invalid answers on unanswerable attempts | 0 |
| cut-off answers on unanswerable attempts | 0 |
| false refusal (answerable) | 0/2 = 0.000 |
| diagnostic: unanswerable answers naming an endpoint (not scored) | 0 |

## Groundedness and citations

Identifiers only (endpoints, paths, error codes, scopes, headers, names); identifiers repeated from the question are not counted.

| measure | value |
|---|---|
| answers with at least one unsupported identifier | 0/3 = 0.000 |
| answers with at least one invented identifier | 0/3 = 0.000 |
| all cited ids were in the context (answered, must cite) | 2/2 = 1.000 |
| at least one cited id is relevant (answered, must cite) | 2/2 = 1.000 |

Most frequent unsupported identifiers: none

Most frequent invented identifiers: none

## Per question

| id | category | context hit | correct | outcomes | agree | missing key facts |
|---|---|---|---|---|---|---|
| Q01 | endpoint_discovery | yes | 1/1 | answered | yes | - |
| Q05 | multi_endpoint | yes | 0/1 | answered | yes | `POST /oauth/token` |
| Q14 | unanswerable | no | 1/1 | refused | yes | - |

For an unanswerable question 'correct' counts correct refusals.

## Agent behaviour

Scored attempts: 3. Retrieval is chosen by the model, so it can differ between repetitions; each attempt is scored on the context it collected.

| per attempt | mean | p50 | max |
|---|---|---|---|
| model calls | 3.00 | 3.0 | 3 |
| searches | 3.00 | 3.0 | 3 |
| context chunks | 10.00 | - | 10 |

Model calls per attempt:

| value | attempts |
|---|---|
| 3 | 3 |
| 4 | 0 |
| 5 | 0 |

Searches per attempt:

| value | attempts |
|---|---|
| 1 | 0 |
| 2 | 0 |
| 3 | 3 |

| planner and judge | value |
|---|---|
| planner reported needs_retrieval = false | 0 |
| plan replies that could not be used (fell back to the question) | 0 |
| judge replies that could not be parsed (counted as enough) | 0 |
| first judge decision was enough | 2/3 = 0.667 |

Attempts whose collected context covers every labelled source, by category (answerable attempts):

| category | full source coverage |
|---|---|
| endpoint_discovery | 1/1 attempts |
| multi_endpoint | 0/1 attempts |

Queries run in repetition 1 for each multi_endpoint question (model output):

- Q05: `customer accounts endpoint`, `account statements endpoint`, `download statement endpoint`

## Latency

Qdrant local mode, in-process, exact search; CPU. Total = embed + search + agent (planner and judge calls) + generation, without client-side throttling. With few attempts p95 rests on a handful of observations.

| stage | n | p50 (ms) | p95 (ms) |
|---|---|---|---|
| embed | 3 | 417.56 | 2361.06 |
| search | 3 | 7.40 | 10.78 |
| agent | 3 | 5868.78 | 8272.56 |
| generation | 3 | 2377.74 | 4848.92 |
| total | 3 | 8650.79 | 15491.26 |

## Tokens and cost (estimated)

Tokens as reported by the provider.

| tokens | n | mean | p50 | p95 |
|---|---|---|---|---|
| prompt | 3 | 4120.3 | 4050.0 | 4240.8 |
| completion | 3 | 1159.0 | 1301.0 | 1551.2 |
| total | 3 | 5279.3 | 5563.0 | 5621.5 |
| reasoning | 3 | 994.3 | 1140.0 | 1337.1 |

- Estimated cost per 1,000 questions: $1.1975 (estimated, not billed; pricing source: paid_variant). Estimated, not billed. Estimated at the paid variant's list price (nvidia/nemotron-3.5-super-vl) captured 2026-11-17
- Estimated cost of this run: $0.0036
- Requests: 9 sent, 0 failed, 0 retried; 0 infrastructure-error records

## Charts

![ha3_correctness_by_context.png](../../charts/20261117T100130Z-answers-dev-agentic-canary/ha3_correctness_by_context.png)
![guardrails.png](../../charts/20261117T100130Z-answers-dev-agentic-canary/guardrails.png)
![latency_by_stage.png](../../charts/20261117T100130Z-answers-dev-agentic-canary/latency_by_stage.png)
![tokens_per_question.png](../../charts/20261117T100130Z-answers-dev-agentic-canary/tokens_per_question.png)

## Limitations

- Small, synthetic, self-authored corpus and question set.
- A single generation model.
- Qdrant local-mode latency does not represent a Qdrant server.
- Free-model routing variance on OpenRouter.
- Deterministic groundedness covers identifiers only.
- BGE-M3 is larger than an English corpus of this size needs.
- The sample size is small, so results are per-question rather than statistically significant.
- This run: 3 attempts over 3 questions; 0 unresolved infrastructure errors; 0 invalid and 0 cut-off answers.

Author interpretation: see the experiment README.
