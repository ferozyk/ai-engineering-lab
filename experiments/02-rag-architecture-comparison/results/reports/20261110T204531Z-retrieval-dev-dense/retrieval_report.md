# Retrieval report: 20261110T204531Z-retrieval-dev-dense

## Setup

- Corpus: version 1.0.0, checksum `72063d1be60b13a9e9a5105f04b081a161fa010cb11d210d0be3589b8726c0e6`
- Question set: dev, version 0.1.0, checksum `9d9ab2a5a6dc6338cf0ddc1f3ff041a0da12b756a9a411f2bb4c2f11e6ca944b`
- Embedding model: `BAAI/bge-m3`, revision `5617a9f61b028005a4858fdac845db406aefb181`, device cpu, dimension 1024, normalised True
- Retriever: dense; collection `lab-bank-c1-0-0-72063d1b-bge-m3-5617a9f6-m2400`
- Questions: 15 (2 unanswerable, excluded from metrics)
- K values: 1, 3, 5, 10; retrieved depth 10
- Git: `a293716be2c42a1f9123d7a69b0a45e1989170d7` (dirty: False); deterministic retrieval: True

## Metrics

| group | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | MRR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| overall | 13 | 0.615 | 0.846 | 1.000 | 1.000 | 0.355 | 0.512 | 0.668 | 0.714 | 0.615 | 0.333 | 0.262 | 0.154 | 0.765 |
| authentication | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.344 | 0.344 | 0.344 | 0.478 | 1.000 | 0.333 | 0.200 | 0.167 | 1.000 |
| comparison | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.333 | 0.667 | 1.000 | 1.000 | 1.000 | 0.667 | 0.600 | 0.300 | 1.000 |
| endpoint_discovery | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.333 | 0.200 | 0.100 | 1.000 |
| exact_identifier | 3 | 0.333 | 0.667 | 1.000 | 1.000 | 0.333 | 0.400 | 0.800 | 0.867 | 0.333 | 0.222 | 0.267 | 0.167 | 0.583 |
| multi_endpoint | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.250 | 0.250 | 0.250 | 0.250 | 1.000 | 0.333 | 0.200 | 0.100 | 1.000 |
| schema | 2 | 0.500 | 1.000 | 1.000 | 1.000 | 0.500 | 1.000 | 1.000 | 1.000 | 0.500 | 0.500 | 0.300 | 0.150 | 0.750 |
| semantic | 2 | 0.000 | 0.500 | 1.000 | 1.000 | 0.000 | 0.250 | 0.500 | 0.500 | 0.000 | 0.167 | 0.200 | 0.100 | 0.350 |

## Hypothesis verdicts (frozen criteria, computed mechanically)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HA1 | Hit@5 over semantic + endpoint_discovery >= 0.80 | not applicable (development set) | Hit@5 = 3/3 = 1.000 (computed on the development set, not the frozen set) |
| HA2 | Hit@5 over exact_identifier is at least 0.20 lower than HA1 | not applicable (development set) | exact_identifier Hit@5 = 3/3 = 1.000; HA1 value = 1.000; gap = 0.000 (computed on the development set, not the frozen set) |
| HA3 | see methodology section 8 | pending (needs generation, stage 2c/2d) |  |
| HA4 | see methodology section 8 | pending (needs generation, stage 2c/2d) |  |

## Per question

| id | category | first relevant rank | hit@5 | recall@5 | top 3 chunks |
|---|---|---|---|---|---|
| Q01 | endpoint_discovery | 1 | 1.000 | 1.000 | `customers-api:listCustomerAccounts:operation`, `customers-api:listCustomerAccounts:response:200`, `customers-api:AccountSummary:component_schema` |
| Q02 | authentication | 1 | 1.000 | 0.333 | `accounts-api:getAccountBalances:operation`, `accounts-api:getAccountBalances:response:200`, `accounts-api:getAccountBalances:parameters` |
| Q03 | semantic | 2 | 1.000 | 0.500 | `statements-api:StatementRequest:component_schema`, `statements-api:requestStatement:operation`, `statements-api:requestStatement:request_body` |
| Q04 | comparison | 1 | 1.000 | 1.000 | `accounts-api:getAccountV2:operation`, `accounts-api:getAccount:operation`, `accounts-api:getAccountV2:parameters` |
| Q05 | multi_endpoint | 1 | 1.000 | 0.250 | `customers-api:listCustomerAccounts:operation`, `accounts-api:getAccount:response:200`, `customers-api:listCustomerAccounts:response:200` |
| Q06 | authentication | 1 | 1.000 | 0.200 | `customers-api:getCustomer:response:401`, `customers-api:listCustomerAccounts:response:401`, `customers-api:listConsents:response:401` |
| Q07 | exact_identifier | 4 | 1.000 | 1.000 | `statements-api:requestStatement:response:400`, `statements-api:StatementRequest:component_schema`, `statements-api:requestStatement:request_body` |
| Q08 | schema | 2 | 1.000 | 1.000 | `statements-api:StatementRequestStatus:component_schema`, `statements-api:requestStatement:request_body`, `statements-api:StatementRequest:component_schema` |
| Q09 | exact_identifier | 2 | 1.000 | 0.400 | `auth-api:introspectToken:response:429`, `auth-api:issueAccessToken:response:429`, `customers-api:listCustomerAccounts:response:429` |
| Q10 | exact_identifier | 1 | 1.000 | 1.000 | `customers-api:updateContactDetails:operation`, `customers-api:ContactDetailsUpdate:component_schema`, `customers-api:updateContactDetails:request_body` |
| Q11 | semantic | 5 | 1.000 | 0.500 | `payments-api:cancelPayment:response:429`, `payments-api:getPayment:response:429`, `payments-api:initiatePayment:response:429` |
| Q12 | schema | 1 | 1.000 | 1.000 | `accounts-api:listTransactions:parameters`, `accounts-api:listTransactions:operation`, `accounts-api:TransactionPage:component_schema` |
| Q13 | authentication | 1 | 1.000 | 0.500 | `statements-api:bearerAuth:security_scheme`, `accounts-api:bearerAuth:security_scheme`, `customers-api:bearerAuth:security_scheme` |
| Q14 | unanswerable | excluded | | | `customers-api:listCustomerAccounts:response:200`, `customers-api:AccountSummary:component_schema`, `accounts-api:Account:component_schema` |
| Q15 | unanswerable | excluded | | | `payments-api:initiatePayment:operation`, `payments-api:getPayment:response:429`, `payments-api:getPayment:parameters` |

## Paraphrase pairs

This question set has no paraphrase pairs.

## Latency

Qdrant local mode, in-process, exact search; CPU; not representative of a Qdrant server.

| stage | n | p50 (ms) | p95 (ms) |
|---|---|---|---|
| query embedding | 15 | 124.20 | 865.56 |
| vector search | 15 | 1.02 | 1.51 |
| total | 15 | 125.19 | 866.95 |

## Indexing cost

- Index build: 186 chunks, 186 embedded, 0 from cache, embedding 38.66 s, upsert 0.13 s
- This run: 186 chunks, 0 embedded, 186 from cache, up to date: True

The analysis of these results is in the experiment README, written by the author.
