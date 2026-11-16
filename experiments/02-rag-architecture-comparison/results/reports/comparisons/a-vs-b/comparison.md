# Comparison: a-vs-b

Generated from committed run summaries; no model was called.

## Retrieval

| measure | dense (20261110T204546Z-retrieval-measured-dense) | hybrid (20261113T232754Z-retrieval-measured-hybrid) | bm25 (20261113T232827Z-retrieval-measured-bm25) |
|---|---|---|---|
| answerable questions | 34 | 34 | 34 |
| Hit@1 | 0.559 | 0.706 | 0.500 |
| Hit@3 | 0.941 | 0.882 | 0.676 |
| Hit@5 | 0.941 | 0.882 | 0.765 |
| Hit@10 | 1.000 | 0.941 | 0.853 |
| Recall@5 | 0.843 | 0.775 | 0.678 |
| MRR | 0.748 | 0.782 | 0.612 |
| latency p50, embed + search (ms) | 123.27 | 130.42 | 0.12 |
| Hit@1 authentication | 0.800 (n=5) | 0.800 (n=5) | 0.400 (n=5) |
| Hit@1 comparison | 0.333 (n=3) | 1.000 (n=3) | 1.000 (n=3) |
| Hit@1 endpoint_discovery | 0.600 (n=5) | 0.800 (n=5) | 0.600 (n=5) |
| Hit@1 exact_identifier | 0.667 (n=6) | 0.833 (n=6) | 0.500 (n=6) |
| Hit@1 multi_endpoint | 0.500 (n=4) | 0.750 (n=4) | 0.500 (n=4) |
| Hit@1 schema | 0.400 (n=5) | 0.400 (n=5) | 0.400 (n=5) |
| Hit@1 semantic | 0.500 (n=6) | 0.500 (n=6) | 0.333 (n=6) |
| Hit@5 authentication | 0.800 (n=5) | 1.000 (n=5) | 0.800 (n=5) |
| Hit@5 comparison | 1.000 (n=3) | 1.000 (n=3) | 1.000 (n=3) |
| Hit@5 endpoint_discovery | 1.000 (n=5) | 1.000 (n=5) | 0.800 (n=5) |
| Hit@5 exact_identifier | 1.000 (n=6) | 1.000 (n=6) | 1.000 (n=6) |
| Hit@5 multi_endpoint | 1.000 (n=4) | 1.000 (n=4) | 0.750 (n=4) |
| Hit@5 schema | 1.000 (n=5) | 0.800 (n=5) | 0.600 (n=5) |
| Hit@5 semantic | 0.833 (n=6) | 0.500 (n=6) | 0.500 (n=6) |

## Answers

| measure | dense (20261110T221134Z-answers-measured-dense) | hybrid (20261116T224508Z-answers-measured-hybrid) |
|---|---|---|
| correctness (answerable) | 77/102 (0.755) | 78/102 (0.765) |
| false refusal (answerable) | 9/102 (0.088) | 10/102 (0.098) |
| correct refusal (unanswerable) | 18/18 (1.000) | 18/18 (1.000) |
| made-up answer (unanswerable) | 0/18 (0.000) | 0/18 (0.000) |
| answers with invented identifiers | 0/120 (0.000) | 0/120 (0.000) |
| citation validity | 93/93 (1.000) | 92/92 (1.000) |
| generation p50 (ms) | 2088 | 2392 |
| generation p95 (ms) | 7521 | 6893 |
| mean total tokens | 1435 | 1471 |
| estimated cost per 1,000 questions (USD, estimated) | 0.3313 | 0.3615 |

## Per question

| question | category | first relevant rank: dense | first relevant rank: hybrid | first relevant rank: bm25 | correct: dense (20261110T221134Z-answers-measured-dense) | correct: hybrid (20261116T224508Z-answers-measured-hybrid) |
|---|---|---|---|---|---|---|
| Q101 | semantic | 3 | 10 | not in top 10 | 2/3 | 0/3 |
| Q102 | semantic | 1 | 1 | 1 | 3/3 | 3/3 |
| Q103 | exact_identifier | 1 | 1 | 2 | 3/3 | 3/3 |
| Q104 | semantic | 8 | not in top 10 | not in top 10 | 0/3 | 0/3 |
| Q105 | schema | 3 | 3 | 4 | 3/3 | 3/3 |
| Q106 | schema | 2 | not in top 10 | not in top 10 | 0/3 | 0/3 |
| Q107 | exact_identifier | 2 | 1 | 1 | 3/3 | 3/3 |
| Q108 | semantic | 2 | 6 | not in top 10 | 3/3 | 0/3 |
| Q109 | exact_identifier | 1 | 1 | 1 | 3/3 | 3/3 |
| Q110 | semantic | 1 | 1 | 5 | 3/3 | 3/3 |
| Q111 | schema | 1 | 1 | 1 | 3/3 | 3/3 |
| Q112 | semantic | 1 | 1 | 1 | 3/3 | 3/3 |
| Q113 | schema | 1 | 1 | 1 | 3/3 | 3/3 |
| Q114 | schema | 2 | 2 | not in top 10 | 3/3 | 3/3 |
| Q115 | exact_identifier | 2 | 2 | 3 | 0/3 | 0/3 |
| Q116 | exact_identifier | 1 | 1 | 1 | 3/3 | 3/3 |
| Q117 | exact_identifier | 1 | 1 | 2 | 3/3 | 3/3 |
| Q118 | endpoint_discovery | 2 | 1 | 1 | 3/3 | 3/3 |
| Q119 | endpoint_discovery | 1 | 3 | 8 | 3/3 | 3/3 |
| Q120 | endpoint_discovery | 2 | 1 | 1 | 3/3 | 3/3 |
| Q121 | endpoint_discovery | 1 | 1 | 1 | 3/3 | 3/3 |
| Q122 | endpoint_discovery | 1 | 1 | 2 | 3/3 | 3/3 |
| Q123 | authentication | 1 | 1 | 6 | 3/3 | 3/3 |
| Q124 | authentication | 1 | 1 | 1 | 3/3 | 3/3 |
| Q125 | authentication | 8 | 3 | 4 | 0/3 | 3/3 |
| Q126 | authentication | 1 | 1 | 3 | 3/3 | 3/3 |
| Q127 | authentication | 1 | 1 | 1 | 0/3 | 0/3 |
| Q128 | multi_endpoint | 1 | 1 | 1 | 0/3 | 3/3 |
| Q129 | multi_endpoint | 2 | 1 | 2 | 3/3 | 3/3 |
| Q130 | multi_endpoint | 1 | 3 | 6 | 0/3 | 0/3 |
| Q131 | multi_endpoint | 2 | 1 | 1 | 3/3 | 3/3 |
| Q132 | comparison | 2 | 1 | 1 | 3/3 | 3/3 |
| Q133 | comparison | 2 | 1 | 1 | 0/3 | 0/3 |
| Q134 | comparison | 1 | 1 | 1 | 3/3 | 3/3 |

## Verdicts

### Retrieval: dense (20261110T204546Z-retrieval-measured-dense)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HA1 | Hit@5 over semantic + endpoint_discovery >= 0.80 | supported | Hit@5 = 10/11 = 0.909 |
| HA2 | Hit@5 over exact_identifier is at least 0.20 lower than HA1 | not supported | exact_identifier Hit@5 = 6/6 = 1.000; HA1 value = 0.909; gap = -0.091 |
| HA3 | see methodology section 8 | pending (needs generation, stage 2c/2d) |  |
| HA4 | see methodology section 8 | pending (needs generation, stage 2c/2d) |  |

### Retrieval: hybrid (20261113T232754Z-retrieval-measured-hybrid)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HB1 | Hit@1 over exact_identifier + schema >= 8/11 | not supported | Hit@1 = 7/11 = 0.636; architecture A: 6/11 |
| HB2 | overall Hit@5 >= 31/34 | not supported | Hit@5 = 30/34 = 0.882; architecture A: 32/34 |
| HB3 | correctness over answerable attempts >= 0.755 | pending (needs generation) |  |

### Retrieval: bm25 (20261113T232827Z-retrieval-measured-bm25)

diagnostic run: no pre-registered hypotheses

### Answers: dense (20261110T221134Z-answers-measured-dense)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HA3 | correctness >= 0.80 when the top-5 context has a relevant chunk and <= 0.20 when it has none; the 'none' half needs at least 3 attempts | supported | context hit 77/96 correct = 0.802; context miss 0/6 correct = 0.000 |
| HA4 | correct-refusal rate over unanswerable attempts >= 0.80 | supported | correct refusals 18/18 = 1.000 |

### Answers: hybrid (20261116T224508Z-answers-measured-hybrid)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HB3 | correctness over answerable attempts >= 0.755 | supported | correct 78/102 = 0.765; architecture A: 77/102 |

