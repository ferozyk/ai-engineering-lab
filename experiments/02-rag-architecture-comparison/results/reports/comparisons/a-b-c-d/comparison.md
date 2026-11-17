# Comparison: a-b-c-d

Generated from committed run summaries; no model was called.

## Retrieval

| measure | dense (20261110T204546Z-retrieval-measured-dense) | hybrid (20261113T232754Z-retrieval-measured-hybrid) | rerank (20261117T023412Z-retrieval-measured-rerank) |
|---|---|---|---|
| answerable questions | 34 | 34 | 34 |
| Hit@1 | 0.559 | 0.706 | 0.588 |
| Hit@3 | 0.941 | 0.882 | 0.765 |
| Hit@5 | 0.941 | 0.882 | 0.824 |
| Hit@10 | 1.000 | 0.941 | 0.971 |
| Recall@5 | 0.843 | 0.775 | 0.794 |
| MRR | 0.748 | 0.782 | 0.708 |
| latency p50, retrieval total (ms) | 123.27 | 130.42 | 9223.68 |
| latency p50, rerank (ms) | - | - | 7538.49 |
| relevant chunk among candidates | - | - | 33/34 (0.971) |
| Hit@1 authentication | 0.800 (n=5) | 0.800 (n=5) | 0.600 (n=5) |
| Hit@1 comparison | 0.333 (n=3) | 1.000 (n=3) | 0.667 (n=3) |
| Hit@1 endpoint_discovery | 0.600 (n=5) | 0.800 (n=5) | 0.600 (n=5) |
| Hit@1 exact_identifier | 0.667 (n=6) | 0.833 (n=6) | 1.000 (n=6) |
| Hit@1 multi_endpoint | 0.500 (n=4) | 0.750 (n=4) | 0.000 (n=4) |
| Hit@1 schema | 0.400 (n=5) | 0.400 (n=5) | 0.800 (n=5) |
| Hit@1 semantic | 0.500 (n=6) | 0.500 (n=6) | 0.333 (n=6) |
| Hit@5 authentication | 0.800 (n=5) | 1.000 (n=5) | 0.800 (n=5) |
| Hit@5 comparison | 1.000 (n=3) | 1.000 (n=3) | 1.000 (n=3) |
| Hit@5 endpoint_discovery | 1.000 (n=5) | 1.000 (n=5) | 0.800 (n=5) |
| Hit@5 exact_identifier | 1.000 (n=6) | 1.000 (n=6) | 1.000 (n=6) |
| Hit@5 multi_endpoint | 1.000 (n=4) | 1.000 (n=4) | 0.250 (n=4) |
| Hit@5 schema | 1.000 (n=5) | 0.800 (n=5) | 1.000 (n=5) |
| Hit@5 semantic | 0.833 (n=6) | 0.500 (n=6) | 0.833 (n=6) |

## Answers

| measure | dense (20261110T221134Z-answers-measured-dense) | hybrid (20261116T224508Z-answers-measured-hybrid) | rerank (20261117T090258Z-answers-measured-rerank) | agentic (20261117T173854Z-answers-measured-agentic) |
|---|---|---|---|---|
| correctness (answerable) | 77/102 (0.755) | 78/102 (0.765) | 78/102 (0.765) | 85/102 (0.833) |
| false refusal (answerable) | 9/102 (0.088) | 10/102 (0.098) | 13/102 (0.127) | 1/102 (0.010) |
| correct refusal (unanswerable) | 18/18 (1.000) | 18/18 (1.000) | 18/18 (1.000) | 17/18 (0.944) |
| made-up answer (unanswerable) | 0/18 (0.000) | 0/18 (0.000) | 0/18 (0.000) | 1/18 (0.056) |
| answers with invented identifiers | 0/120 (0.000) | 0/120 (0.000) | 0/120 (0.000) | 0/120 (0.000) |
| citation validity | 93/93 (1.000) | 92/92 (1.000) | 89/89 (1.000) | 101/101 (1.000) |
| generation p50 (ms) | 2088 | 2392 | 2578 | 3774 |
| generation p95 (ms) | 7521 | 6893 | 7608 | 12332 |
| rerank p50 (ms) | - | - | 7515 | - |
| agent p50 (ms) | - | - | - | 8469 |
| total p50 (ms) | 2230 | 2525 | 13199 | 14185 |
| model calls per attempt (mean / max) | 1.00 / 1 | 1.00 / 1 | 1.00 / 1 | 3.25 / 5 |
| searches per attempt (mean) | 1.00 | 1.00 | 1.00 | 2.18 |
| full source coverage, multi_endpoint | 3/12 attempts | 3/12 attempts | 0/12 attempts | 9/12 attempts |
| mean total tokens | 1435 | 1471 | 1479 | 4703 |
| estimated cost per 1,000 questions (USD, estimated) | 0.3313 | 0.3615 | 0.3603 | 1.1012 |

## Per question

| question | category | first relevant rank: dense | first relevant rank: hybrid | first relevant rank: rerank | candidate rank: rerank | correct: dense (20261110T221134Z-answers-measured-dense) | correct: hybrid (20261116T224508Z-answers-measured-hybrid) | correct: rerank (20261117T090258Z-answers-measured-rerank) | correct: agentic (20261117T173854Z-answers-measured-agentic) | sources covered (r1/r2/r3): agentic |
|---|---|---|---|---|---|---|---|---|---|---|
| Q101 | semantic | 3 | 10 | 4 | 10 | 2/3 | 0/3 | 2/3 | 0/3 | 1/1 / 0/1 / 1/1 |
| Q102 | semantic | 1 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q103 | exact_identifier | 1 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q104 | semantic | 8 | not in top 10 | not in top 10 | not in candidates | 0/3 | 0/3 | 0/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q105 | schema | 3 | 3 | 1 | 3 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q106 | schema | 2 | not in top 10 | 3 | 16 | 0/3 | 0/3 | 2/3 | 0/3 | 1/1 / 1/1 / 1/1 |
| Q107 | exact_identifier | 2 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 / 2/2 / 2/2 |
| Q108 | semantic | 2 | 6 | 1 | 6 | 3/3 | 0/3 | 2/3 | 3/3 | 2/2 / 2/2 / 2/2 |
| Q109 | exact_identifier | 1 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q110 | semantic | 1 | 1 | 4 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q111 | schema | 1 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q112 | semantic | 1 | 1 | 2 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q113 | schema | 1 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 / 2/2 / 2/2 |
| Q114 | schema | 2 | 2 | 1 | 2 | 3/3 | 3/3 | 3/3 | 2/3 | 2/2 / 0/2 / 2/2 |
| Q115 | exact_identifier | 2 | 2 | 1 | 2 | 0/3 | 0/3 | 0/3 | 0/3 | 1/1 / 1/1 / 1/1 |
| Q116 | exact_identifier | 1 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q117 | exact_identifier | 1 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q118 | endpoint_discovery | 2 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q119 | endpoint_discovery | 1 | 3 | 1 | 3 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q120 | endpoint_discovery | 2 | 1 | 7 | 1 | 3/3 | 3/3 | 0/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q121 | endpoint_discovery | 1 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q122 | endpoint_discovery | 1 | 1 | 2 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q123 | authentication | 1 | 1 | 6 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q124 | authentication | 1 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 / 1/2 / 2/2 |
| Q125 | authentication | 8 | 3 | 1 | 3 | 0/3 | 3/3 | 3/3 | 3/3 | 5/5 / 4/5 / 5/5 |
| Q126 | authentication | 1 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 / 1/1 / 1/1 |
| Q127 | authentication | 1 | 1 | 2 | 1 | 0/3 | 0/3 | 0/3 | 0/3 | 1/1 / 1/1 / 1/1 |
| Q128 | multi_endpoint | 1 | 1 | 2 | 1 | 0/3 | 3/3 | 3/3 | 3/3 | 2/2 / 2/2 / 2/2 |
| Q129 | multi_endpoint | 2 | 1 | 6 | 1 | 3/3 | 3/3 | 0/3 | 3/3 | 2/2 / 2/2 / 2/2 |
| Q130 | multi_endpoint | 1 | 3 | 6 | 3 | 0/3 | 0/3 | 0/3 | 0/3 | 1/2 / 1/2 / 1/2 |
| Q131 | multi_endpoint | 2 | 1 | 9 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 / 2/2 / 2/2 |
| Q132 | comparison | 2 | 1 | 1 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 / 3/3 / 3/3 |
| Q133 | comparison | 2 | 1 | 1 | 1 | 0/3 | 0/3 | 0/3 | 2/3 | 2/2 / 2/2 / 2/2 |
| Q134 | comparison | 1 | 1 | 2 | 1 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 / 2/2 / 2/2 |

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

### Retrieval: rerank (20261117T023412Z-retrieval-measured-rerank)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HC1 | MRR (top 10) over answerable questions >= 0.85 | not supported | MRR = 0.708; architecture B: 0.782 |
| HC2 | overall Hit@5 >= 32/34 | not supported | Hit@5 = 28/34 = 0.824; architecture B: 30/34 |
| HC3 | correct answerable attempts >= 80/102 | pending (needs generation) |  |

### Answers: dense (20261110T221134Z-answers-measured-dense)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HA3 | correctness >= 0.80 when the top-5 context has a relevant chunk and <= 0.20 when it has none; the 'none' half needs at least 3 attempts | supported | context hit 77/96 correct = 0.802; context miss 0/6 correct = 0.000 |
| HA4 | correct-refusal rate over unanswerable attempts >= 0.80 | supported | correct refusals 18/18 = 1.000 |

### Answers: hybrid (20261116T224508Z-answers-measured-hybrid)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HB3 | correctness over answerable attempts >= 0.755 | supported | correct 78/102 = 0.765; architecture A: 77/102 |

### Answers: rerank (20261117T090258Z-answers-measured-rerank)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HC3 | correct answerable attempts >= 80/102 | not supported | correct 78/102 = 0.765; architecture B: 78/102 |

### Answers: agentic (20261117T173854Z-answers-measured-agentic)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HD1 | multi_endpoint attempts whose collected context covers every labelled source >= 9/12 | supported | full source coverage 9/12 = 0.750; architecture B: 3/12 |
| HD2 | correct answerable attempts >= 80/102 | supported | correct 85/102 = 0.833; architecture B: 78/102 |
| HD3 | correct refusals on unanswerable attempts >= 17/18 | supported | correct refusals 17/18 = 0.944; architecture B: 18/18 |

