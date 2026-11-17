# Comparison: a-b-c-retrieval

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

## Per question

| question | category | first relevant rank: dense | first relevant rank: hybrid | first relevant rank: rerank | candidate rank: rerank |
|---|---|---|---|---|---|
| Q101 | semantic | 3 | 10 | 4 | 10 |
| Q102 | semantic | 1 | 1 | 1 | 1 |
| Q103 | exact_identifier | 1 | 1 | 1 | 1 |
| Q104 | semantic | 8 | not in top 10 | not in top 10 | not in candidates |
| Q105 | schema | 3 | 3 | 1 | 3 |
| Q106 | schema | 2 | not in top 10 | 3 | 16 |
| Q107 | exact_identifier | 2 | 1 | 1 | 1 |
| Q108 | semantic | 2 | 6 | 1 | 6 |
| Q109 | exact_identifier | 1 | 1 | 1 | 1 |
| Q110 | semantic | 1 | 1 | 4 | 1 |
| Q111 | schema | 1 | 1 | 1 | 1 |
| Q112 | semantic | 1 | 1 | 2 | 1 |
| Q113 | schema | 1 | 1 | 1 | 1 |
| Q114 | schema | 2 | 2 | 1 | 2 |
| Q115 | exact_identifier | 2 | 2 | 1 | 2 |
| Q116 | exact_identifier | 1 | 1 | 1 | 1 |
| Q117 | exact_identifier | 1 | 1 | 1 | 1 |
| Q118 | endpoint_discovery | 2 | 1 | 1 | 1 |
| Q119 | endpoint_discovery | 1 | 3 | 1 | 3 |
| Q120 | endpoint_discovery | 2 | 1 | 7 | 1 |
| Q121 | endpoint_discovery | 1 | 1 | 1 | 1 |
| Q122 | endpoint_discovery | 1 | 1 | 2 | 1 |
| Q123 | authentication | 1 | 1 | 6 | 1 |
| Q124 | authentication | 1 | 1 | 1 | 1 |
| Q125 | authentication | 8 | 3 | 1 | 3 |
| Q126 | authentication | 1 | 1 | 1 | 1 |
| Q127 | authentication | 1 | 1 | 2 | 1 |
| Q128 | multi_endpoint | 1 | 1 | 2 | 1 |
| Q129 | multi_endpoint | 2 | 1 | 6 | 1 |
| Q130 | multi_endpoint | 1 | 3 | 6 | 3 |
| Q131 | multi_endpoint | 2 | 1 | 9 | 1 |
| Q132 | comparison | 2 | 1 | 1 | 1 |
| Q133 | comparison | 2 | 1 | 1 | 1 |
| Q134 | comparison | 1 | 1 | 2 | 1 |

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

