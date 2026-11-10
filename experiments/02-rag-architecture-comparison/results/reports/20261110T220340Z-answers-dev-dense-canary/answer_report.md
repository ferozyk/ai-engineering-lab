# Answer report: 20261110T220340Z-answers-dev-dense-canary

## Setup

- Corpus: version 1.0.0, checksum `72063d1be60b13a9e9a5105f04b081a161fa010cb11d210d0be3589b8726c0e6`
- Question set: dev, version 0.1.0, checksum `9d9ab2a5a6dc6338cf0ddc1f3ff041a0da12b756a9a411f2bb4c2f11e6ca944b`; canary subset Q01, Q05, Q14
- Generation model: `nvidia/nemotron-3.5-super-vl:free` via openrouter; served by models ['nvidia/nemotron-3.5-super-vl:free'], providers ['Nvidia']
- Prompt: version a-1.0, hash `bc694d3da6e02137e4df755079dc355e99a1cf29506953c90c17631ac919abfc`
- Generation settings: {'prompt_version': 'a-1.0', 'temperature': 0.0, 'max_output_tokens': 16384, 'llm_seed': None, 'request_timeout_seconds': 300}
- Run settings: {'repetitions': 1, 'order_seed': 20261111, 'rate_limit_per_minute': 15, 'daily_request_cap': 900, 'canary_question_ids': ['Q01', 'Q05', 'Q14']}
- Retrieval: dense, context = top 5 chunks; embedding `BAAI/bge-m3` revision `5617a9f61b028005a4858fdac845db406aefb181` (cpu); collection `lab-bank-c1-0-0-72063d1b-bge-m3-5617a9f6-m2400`; retrieval deterministic: True
- Run timing: started 2026-11-10 22:03:40 UTC, finished 2026-11-10 22:05:15 UTC
- Git: `f3d88834e054d5d13fb5bf925f910b949f6f2892` (dirty: False); Python 3.12.12; macOS-15.0.1-arm64-arm-64bit
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
| HA3 | correctness >= 0.80 when the top-5 context has a relevant chunk and <= 0.20 when it has none; the 'none' half needs at least 3 attempts | not applicable (development set) | context hit 1/2 correct; context miss 0/0 correct |
| HA4 | correct-refusal rate over unanswerable attempts >= 0.80 | not applicable (development set) | correct refusals 1/1 |

## Guardrails

| measure | value |
|---|---|
| correct refusal (unanswerable) | 1/1 = 1.000 |
| made-up answer (unanswerable) | 0/1 = 0.000 |
| invalid answers on unanswerable attempts | 0 |
| cut-off answers on unanswerable attempts | 0 |
| false refusal (answerable) | 0/2 = 0.000 |
| diagnostic: unanswerable answers naming an endpoint (not scored) | 1 |

## Groundedness and citations

Identifiers only (endpoints, paths, error codes, scopes, headers, names); identifiers repeated from the question are not counted.

| measure | value |
|---|---|
| answers with at least one unsupported identifier | 1/3 = 0.333 |
| answers with at least one invented identifier | 0/3 = 0.000 |
| all cited ids were in the context (answered, must cite) | 2/2 = 1.000 |
| at least one cited id is relevant (answered, must cite) | 2/2 = 1.000 |

Most frequent unsupported identifiers: `name:getStatement` x1

Most frequent invented identifiers: none

## Per question

| id | category | context hit | correct | outcomes | agree | missing key facts |
|---|---|---|---|---|---|---|
| Q01 | endpoint_discovery | yes | 1/1 | answered | yes | - |
| Q05 | multi_endpoint | yes | 0/1 | answered | yes | `GET /v1/accounts/{accountId}/statements`, `POST /oauth/token` |
| Q14 | unanswerable | no | 1/1 | refused | yes | - |

For an unanswerable question 'correct' counts correct refusals.

## Latency

Qdrant local mode, in-process, exact search; CPU. Total = embed + search + generation, without client-side throttling. With few attempts p95 rests on a handful of observations.

| stage | n | p50 (ms) | p95 (ms) |
|---|---|---|---|
| embed | 3 | 120.90 | 9285.61 |
| search | 3 | 0.93 | 2.28 |
| generation | 3 | 2597.44 | 79367.38 |
| total | 3 | 12049.58 | 80413.91 |

## Tokens and cost (estimated)

Tokens as reported by the provider.

| tokens | n | mean | p50 | p95 |
|---|---|---|---|---|
| prompt | 3 | 1090.3 | 1088.0 | 1108.7 |
| completion | 3 | 749.3 | 353.0 | 1566.2 |
| total | 3 | 1839.7 | 1441.0 | 2639.8 |
| reasoning | 3 | 617.7 | 226.0 | 1367.2 |

- Estimated cost per 1,000 questions: $0.5157 (estimated, not billed; pricing source: paid_variant). Estimated, not billed. Estimated at the paid variant's list price (nvidia/nemotron-3.5-super-vl) captured 2026-11-10
- Estimated cost of this run: $0.0015
- Requests: 3 sent, 0 failed, 0 retried; 0 infrastructure-error records

## Charts

![retrieval_hit_at_k.png](../../charts/20261110T220340Z-answers-dev-dense-canary/retrieval_hit_at_k.png)
![ha3_correctness_by_context.png](../../charts/20261110T220340Z-answers-dev-dense-canary/ha3_correctness_by_context.png)
![guardrails.png](../../charts/20261110T220340Z-answers-dev-dense-canary/guardrails.png)
![latency_by_stage.png](../../charts/20261110T220340Z-answers-dev-dense-canary/latency_by_stage.png)
![tokens_per_question.png](../../charts/20261110T220340Z-answers-dev-dense-canary/tokens_per_question.png)

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
