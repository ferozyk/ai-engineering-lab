# Retrieval report: 20261113T232833Z-retrieval-dev-hybrid

## Setup

- Corpus: version 1.0.0, checksum `72063d1be60b13a9e9a5105f04b081a161fa010cb11d210d0be3589b8726c0e6`
- Question set: dev, version 0.1.0, checksum `9d9ab2a5a6dc6338cf0ddc1f3ff041a0da12b756a9a411f2bb4c2f11e6ca944b`
- Embedding model: `BAAI/bge-m3`, revision `5617a9f61b028005a4858fdac845db406aefb181`, device cpu, dimension 1024, normalised True
- Retriever: hybrid; collection `lab-bank-c1-0-0-72063d1b-bge-m3-5617a9f6-m2400`
- Questions: 15 (2 unanswerable, excluded from metrics)
- K values: 1, 3, 5, 10; retrieved depth 10
- Git: `9f396681eb9496496402d90a5068eb2bba707280` (dirty: False); deterministic retrieval: True

## Metrics

| group | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | MRR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| overall | 13 | 0.615 | 1.000 | 1.000 | 1.000 | 0.374 | 0.627 | 0.683 | 0.733 | 0.615 | 0.385 | 0.277 | 0.162 | 0.795 |
| authentication | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.344 | 0.344 | 0.411 | 0.478 | 1.000 | 0.333 | 0.267 | 0.167 | 1.000 |
| comparison | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.333 | 0.667 | 1.000 | 1.000 | 1.000 | 0.667 | 0.600 | 0.300 | 1.000 |
| endpoint_discovery | 1 | 0.000 | 1.000 | 1.000 | 1.000 | 0.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.333 | 0.200 | 0.100 | 0.500 |
| exact_identifier | 3 | 0.667 | 1.000 | 1.000 | 1.000 | 0.667 | 0.733 | 0.800 | 0.867 | 0.667 | 0.333 | 0.267 | 0.167 | 0.833 |
| multi_endpoint | 1 | 0.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.250 | 0.250 | 0.500 | 0.000 | 0.333 | 0.200 | 0.200 | 0.333 |
| schema | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 0.750 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.300 | 0.150 | 1.000 |
| semantic | 2 | 0.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.500 | 0.500 | 0.500 | 0.000 | 0.333 | 0.200 | 0.100 | 0.500 |

## Hypothesis verdicts (frozen criteria, computed mechanically)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HB1 | Hit@1 over exact_identifier + schema >= 8/11 | not applicable (development set) | Hit@1 = 4/5 = 0.800; architecture A: 6/11 |
| HB2 | overall Hit@5 >= 31/34 | not applicable (development set) | Hit@5 = 13/13 = 1.000; architecture A: 32/34 |
| HB3 | correctness over answerable attempts >= 0.755 | pending (needs generation) |  |

## Per question

| id | category | first relevant rank | hit@5 | recall@5 | top 3 chunks |
|---|---|---|---|---|---|
| Q01 | endpoint_discovery | 2 | 1.000 | 1.000 | `accounts-api:Account:component_schema`, `customers-api:listCustomerAccounts:operation`, `accounts-api:getAccountV2:response:200` |
| Q02 | authentication | 1 | 1.000 | 0.333 | `accounts-api:getAccountBalances:operation`, `accounts-api:getAccountBalances:response:200`, `accounts-api:getAccountBalances:parameters` |
| Q03 | semantic | 2 | 1.000 | 0.500 | `statements-api:StatementRequest:component_schema`, `statements-api:requestStatement:operation`, `statements-api:requestStatement:request_body` |
| Q04 | comparison | 1 | 1.000 | 1.000 | `accounts-api:getAccount:operation`, `accounts-api:getAccountV2:operation`, `accounts-api:getAccountV2:parameters` |
| Q05 | multi_endpoint | 3 | 1.000 | 0.250 | `accounts-api:getAccount:response:200`, `customers-api:listCustomerAccounts:response:200`, `customers-api:listCustomerAccounts:operation` |
| Q06 | authentication | 1 | 1.000 | 0.400 | `customers-api:getCustomer:response:401`, `customers-api:searchCustomers:response:401`, `customers-api:listCustomerAccounts:response:401` |
| Q07 | exact_identifier | 1 | 1.000 | 1.000 | `accounts-api:listTransactions:parameters`, `statements-api:StatementRequest:component_schema`, `statements-api:requestStatement:response:400` |
| Q08 | schema | 1 | 1.000 | 1.000 | `statements-api:StatementRequest:component_schema`, `statements-api:requestStatement:request_body`, `statements-api:StatementRequestStatus:component_schema` |
| Q09 | exact_identifier | 2 | 1.000 | 0.400 | `auth-api:introspectToken:response:429`, `auth-api:issueAccessToken:response:429`, `auth-api:revokeToken:response:429` |
| Q10 | exact_identifier | 1 | 1.000 | 1.000 | `customers-api:updateContactDetails:operation`, `customers-api:ContactDetailsUpdate:component_schema`, `customers-api:updateContactDetails:request_body` |
| Q11 | semantic | 2 | 1.000 | 0.500 | `payments-api:cancelPayment:response:429`, `payments-api:initiatePayment:operation`, `payments-api:getPayment:response:429` |
| Q12 | schema | 1 | 1.000 | 1.000 | `accounts-api:listTransactions:parameters`, `customers-api:CustomerPage:component_schema`, `accounts-api:TransactionPage:component_schema` |
| Q13 | authentication | 1 | 1.000 | 0.500 | `statements-api:bearerAuth:security_scheme`, `accounts-api:bearerAuth:security_scheme`, `customers-api:bearerAuth:security_scheme` |
| Q14 | unanswerable | excluded | | | `accounts-api:Account:component_schema`, `customers-api:listCustomerAccounts:response:200`, `accounts-api:AccountV2:component_schema` |
| Q15 | unanswerable | excluded | | | `payments-api:getPayment:response:429`, `payments-api:initiatePayment:response:429`, `payments-api:cancelPayment:response:429` |

## Paraphrase pairs

This question set has no paraphrase pairs.

## Latency

Query embedding, then Qdrant local-mode search (in-process, exact) plus in-memory BM25 search and rank fusion; the 'vector search' row is the sum of those three; CPU; not representative of a Qdrant server.

| stage | n | p50 (ms) | p95 (ms) |
|---|---|---|---|
| query embedding | 15 | 127.07 | 939.80 |
| vector search | 15 | 1.96 | 3.79 |
| total | 15 | 129.03 | 943.41 |

## Indexing cost

- Index build: 186 chunks, 186 embedded, 0 from cache, embedding 38.66 s, upsert 0.13 s
- This run: 186 chunks, 0 embedded, 186 from cache, up to date: True

The analysis of these results is in the experiment README, written by the author.
