# Retrieval report: 20261117T024638Z-retrieval-dev-rerank

## Setup

- Corpus: version 1.0.0, checksum `72063d1be60b13a9e9a5105f04b081a161fa010cb11d210d0be3589b8726c0e6`
- Question set: dev, version 0.1.0, checksum `9d9ab2a5a6dc6338cf0ddc1f3ff041a0da12b756a9a411f2bb4c2f11e6ca944b`
- Embedding model: `BAAI/bge-m3`, revision `5617a9f61b028005a4858fdac845db406aefb181`, device cpu, dimension 1024, normalised True
- Reranker model: `BAAI/bge-reranker-v2-m3`, revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, device cpu, max length 1024 tokens, candidates re-ordered: 30
- Retriever: rerank; collection `lab-bank-c1-0-0-72063d1b-bge-m3-5617a9f6-m2400`
- Questions: 15 (2 unanswerable, excluded from metrics)
- K values: 1, 3, 5, 10; retrieved depth 10
- Git: `c6634741ad5d90e27764f030ed76110bedc0ef0e` (dirty: False); deterministic retrieval: True

## Metrics

| group | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | MRR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| overall | 13 | 0.692 | 0.846 | 1.000 | 1.000 | 0.406 | 0.579 | 0.717 | 0.788 | 0.692 | 0.333 | 0.277 | 0.169 | 0.804 |
| authentication | 3 | 0.333 | 0.667 | 1.000 | 1.000 | 0.067 | 0.233 | 0.511 | 0.578 | 0.333 | 0.222 | 0.267 | 0.167 | 0.583 |
| comparison | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.333 | 0.333 | 0.333 | 0.667 | 1.000 | 0.333 | 0.200 | 0.200 | 1.000 |
| endpoint_discovery | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.333 | 0.200 | 0.100 | 1.000 |
| exact_identifier | 3 | 0.333 | 0.667 | 1.000 | 1.000 | 0.333 | 0.667 | 0.733 | 0.867 | 0.333 | 0.222 | 0.200 | 0.167 | 0.567 |
| multi_endpoint | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.250 | 0.500 | 0.750 | 0.750 | 1.000 | 0.667 | 0.600 | 0.300 | 1.000 |
| schema | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 0.750 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.300 | 0.150 | 1.000 |
| semantic | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.500 | 0.750 | 0.750 | 1.000 | 0.333 | 0.300 | 0.150 | 1.000 |

Relevant chunk among the 30 candidates: 13/13 answerable questions = 1.000

## Hypothesis verdicts (frozen criteria, computed mechanically)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HC1 | MRR (top 10) over answerable questions >= 0.85 | not applicable (development set) | MRR = 0.804; architecture B: 0.782 |
| HC2 | overall Hit@5 >= 32/34 | not applicable (development set) | Hit@5 = 13/13 = 1.000; architecture B: 30/34 |
| HC3 | correct answerable attempts >= 80/102 | pending (needs generation) |  |

## Per question

| id | category | first relevant rank | hit@5 | recall@5 | top 3 chunks |
|---|---|---|---|---|---|
| Q01 | endpoint_discovery | 1 | 1.000 | 1.000 | `customers-api:listCustomerAccounts:operation`, `customers-api:listCustomerAccounts:response:200`, `customers-api:bearerAuth:security_scheme` |
| Q02 | authentication | 4 | 1.000 | 0.333 | `accounts-api:getAccountBalances:response:200`, `accounts-api:getAccountBalances:parameters`, `accounts-api:getAccount:response:200` |
| Q03 | semantic | 1 | 1.000 | 0.500 | `statements-api:requestStatement:operation`, `statements-api:StatementRequest:component_schema`, `statements-api:requestStatement:request_body` |
| Q04 | comparison | 1 | 1.000 | 0.333 | `accounts-api:getAccount:operation`, `accounts-api:getAccountBalances:parameters`, `accounts-api:getAccount:parameters` |
| Q05 | multi_endpoint | 1 | 1.000 | 0.750 | `customers-api:listCustomerAccounts:operation`, `statements-api:requestStatement:operation`, `statements-api:getStatement:operation` |
| Q06 | authentication | 1 | 1.000 | 0.200 | `customers-api:getCustomer:response:401`, `customers-api:listCustomerAccounts:response:401`, `customers-api:listConsents:response:401` |
| Q07 | exact_identifier | 2 | 1.000 | 1.000 | `accounts-api:listTransactions:operation`, `accounts-api:listTransactions:parameters`, `statements-api:requestStatement:response:400` |
| Q08 | schema | 1 | 1.000 | 1.000 | `statements-api:requestStatement:request_body`, `statements-api:StatementRequestStatus:component_schema`, `statements-api:StatementRequest:component_schema` |
| Q09 | exact_identifier | 5 | 1.000 | 0.200 | `accounts-api:getAccount:response:429`, `accounts-api:getAccountV2:response:429`, `statements-api:getStatement:response:429` |
| Q10 | exact_identifier | 1 | 1.000 | 1.000 | `customers-api:updateContactDetails:operation`, `customers-api:updateContactDetails:request_body`, `customers-api:updateContactDetails:response:403` |
| Q11 | semantic | 1 | 1.000 | 1.000 | `payments-api:initiatePayment:operation`, `payments-api:cancelPayment:response:429`, `payments-api:initiatePayment:response:429` |
| Q12 | schema | 1 | 1.000 | 1.000 | `accounts-api:listTransactions:parameters`, `customers-api:searchCustomers:parameters`, `accounts-api:listTransactions:response:200` |
| Q13 | authentication | 2 | 1.000 | 1.000 | `statements-api:getStatement:operation`, `statements-api:listStatements:operation`, `statements-api:getStatementRequestStatus:operation` |
| Q14 | unanswerable | excluded | | | `auth-api:bearerAuth:security_scheme`, `customers-api:listCustomerAccounts:response:200`, `customers-api:bearerAuth:security_scheme` |
| Q15 | unanswerable | excluded | | | `payments-api:cancelPayment:response:429`, `payments-api:getPayment:response:429`, `payments-api:initiatePayment:operation` |

## Paraphrase pairs

This question set has no paraphrase pairs.

## Latency

Qdrant local mode, in-process, exact search; CPU; not representative of a Qdrant server.

| stage | n | p50 (ms) | p95 (ms) |
|---|---|---|---|
| query embedding | 15 | 1419.79 | 2563.75 |
| vector search | 15 | 4.18 | 8.76 |
| reranking | 15 | 6973.66 | 9864.66 |
| total | 15 | 8344.79 | 12225.46 |

## Indexing cost

- Index build: 186 chunks, 186 embedded, 0 from cache, embedding 38.66 s, upsert 0.13 s
- This run: 186 chunks, 0 embedded, 186 from cache, up to date: True

The analysis of these results is in the experiment README, written by the author.
