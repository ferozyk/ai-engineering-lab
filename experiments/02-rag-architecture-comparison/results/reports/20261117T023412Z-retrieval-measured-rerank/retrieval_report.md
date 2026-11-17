# Retrieval report: 20261117T023412Z-retrieval-measured-rerank

## Setup

- Corpus: version 1.0.0, checksum `72063d1be60b13a9e9a5105f04b081a161fa010cb11d210d0be3589b8726c0e6`
- Question set: measured, version 1.0.0, checksum `28d846ec119f105cbb6d6b36b5b00bda0dd7b7a1b16d4b43179c359f5432cede`
- Embedding model: `BAAI/bge-m3`, revision `5617a9f61b028005a4858fdac845db406aefb181`, device cpu, dimension 1024, normalised True
- Reranker model: `BAAI/bge-reranker-v2-m3`, revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, device cpu, max length 1024 tokens, candidates re-ordered: 30
- Retriever: rerank; collection `lab-bank-c1-0-0-72063d1b-bge-m3-5617a9f6-m2400`
- Questions: 40 (6 unanswerable, excluded from metrics)
- K values: 1, 3, 5, 10; retrieved depth 10
- Git: `c6634741ad5d90e27764f030ed76110bedc0ef0e` (dirty: False); deterministic retrieval: True

## Metrics

| group | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | MRR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| overall | 34 | 0.588 | 0.765 | 0.824 | 0.971 | 0.457 | 0.670 | 0.794 | 0.912 | 0.588 | 0.314 | 0.235 | 0.135 | 0.708 |
| authentication | 5 | 0.600 | 0.800 | 0.800 | 1.000 | 0.340 | 0.620 | 0.700 | 0.900 | 0.600 | 0.400 | 0.320 | 0.180 | 0.733 |
| comparison | 3 | 0.667 | 1.000 | 1.000 | 1.000 | 0.278 | 0.556 | 1.000 | 1.000 | 0.667 | 0.444 | 0.467 | 0.233 | 0.833 |
| endpoint_discovery | 5 | 0.600 | 0.800 | 0.800 | 1.000 | 0.600 | 0.800 | 0.800 | 1.000 | 0.600 | 0.267 | 0.160 | 0.100 | 0.729 |
| exact_identifier | 6 | 1.000 | 1.000 | 1.000 | 1.000 | 0.917 | 1.000 | 1.000 | 1.000 | 1.000 | 0.389 | 0.233 | 0.117 | 1.000 |
| multi_endpoint | 4 | 0.000 | 0.250 | 0.250 | 1.000 | 0.000 | 0.125 | 0.125 | 0.625 | 0.000 | 0.083 | 0.050 | 0.125 | 0.236 |
| schema | 5 | 0.800 | 1.000 | 1.000 | 1.000 | 0.600 | 1.000 | 1.000 | 1.000 | 0.800 | 0.467 | 0.280 | 0.140 | 0.867 |
| semantic | 6 | 0.333 | 0.500 | 0.833 | 0.833 | 0.250 | 0.417 | 0.833 | 0.833 | 0.333 | 0.167 | 0.200 | 0.100 | 0.500 |

Relevant chunk among the 30 candidates: 33/34 answerable questions = 0.971

## Hypothesis verdicts (frozen criteria, computed mechanically)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HC1 | MRR (top 10) over answerable questions >= 0.85 | not supported | MRR = 0.708; architecture B: 0.782 |
| HC2 | overall Hit@5 >= 32/34 | not supported | Hit@5 = 28/34 = 0.824; architecture B: 30/34 |
| HC3 | correct answerable attempts >= 80/102 | pending (needs generation) |  |

## Per question

| id | category | first relevant rank | hit@5 | recall@5 | top 3 chunks |
|---|---|---|---|---|---|
| Q101 | semantic | 4 | 1.000 | 1.000 | `statements-api:StatementRequest:component_schema`, `statements-api:requestStatement:request_body`, `statements-api:requestStatement:operation` |
| Q102 | semantic | 1 | 1.000 | 1.000 | `payments-api:initiatePayment:response:409`, `payments-api:initiatePayment:parameters`, `payments-api:initiatePayment:operation` |
| Q103 | exact_identifier | 1 | 1.000 | 1.000 | `statements-api:requestStatement:response:202`, `statements-api:requestStatement:operation`, `statements-api:getStatementRequestStatus:response:200` |
| Q104 | semantic | not in top 10 | 0.000 | 0.000 | `statements-api:requestStatement:operation`, `accounts-api:getAccountV2:response:429`, `customers-api:listCustomerAccounts:response:429` |
| Q105 | schema | 1 | 1.000 | 1.000 | `customers-api:searchCustomers:parameters`, `customers-api:searchCustomers:operation`, `customers-api:searchCustomers:response:200` |
| Q106 | schema | 3 | 1.000 | 1.000 | `customers-api:searchCustomers:operation`, `customers-api:searchCustomers:response:200`, `customers-api:searchCustomers:parameters` |
| Q107 | exact_identifier | 1 | 1.000 | 1.000 | `auth-api:issueAccessToken:response:200`, `auth-api:TokenResponse:component_schema`, `auth-api:introspectToken:response:200` |
| Q108 | semantic | 1 | 1.000 | 1.000 | `auth-api:TokenResponse:component_schema`, `auth-api:introspectToken:response:200`, `auth-api:IntrospectionResponse:component_schema` |
| Q109 | exact_identifier | 1 | 1.000 | 1.000 | `payments-api:cancelPayment:operation`, `payments-api:cancelPayment:response:200`, `payments-api:cancelPayment:response:409` |
| Q110 | semantic | 4 | 1.000 | 1.000 | `payments-api:cancelPayment:response:409`, `payments-api:cancelPayment:response:200`, `payments-api:cancelPayment:response:429` |
| Q111 | schema | 1 | 1.000 | 1.000 | `customers-api:Customer:component_schema`, `customers-api:getCustomer:response:200`, `customers-api:updateContactDetails:response:200` |
| Q112 | semantic | 2 | 1.000 | 1.000 | `customers-api:getCustomer:response:200`, `customers-api:Customer:component_schema`, `customers-api:updateContactDetails:response:200` |
| Q113 | schema | 1 | 1.000 | 1.000 | `accounts-api:Transaction:component_schema`, `accounts-api:getTransaction:response:200`, `payments-api:Payment:component_schema` |
| Q114 | schema | 1 | 1.000 | 1.000 | `accounts-api:Transaction:component_schema`, `accounts-api:getTransaction:response:200`, `statements-api:getStatement:response:200` |
| Q115 | exact_identifier | 1 | 1.000 | 1.000 | `statements-api:getStatement:response:404`, `statements-api:requestStatement:response:404`, `statements-api:getStatementRequestStatus:response:404` |
| Q116 | exact_identifier | 1 | 1.000 | 1.000 | `auth-api:introspectToken:operation`, `auth-api:issueAccessToken:operation`, `payments-api:initiatePayment:operation` |
| Q117 | exact_identifier | 1 | 1.000 | 1.000 | `payments-api:initiatePayment:parameters`, `payments-api:initiatePayment:response:409`, `payments-api:initiatePayment:operation` |
| Q118 | endpoint_discovery | 1 | 1.000 | 1.000 | `accounts-api:getTransaction:operation`, `payments-api:getPayment:operation`, `auth-api:bearerAuth:security_scheme` |
| Q119 | endpoint_discovery | 1 | 1.000 | 1.000 | `customers-api:searchCustomers:operation`, `customers-api:searchCustomers:parameters`, `statements-api:bearerAuth:security_scheme` |
| Q120 | endpoint_discovery | 7 | 0.000 | 0.000 | `auth-api:bearerAuth:security_scheme`, `statements-api:bearerAuth:security_scheme`, `accounts-api:bearerAuth:security_scheme` |
| Q121 | endpoint_discovery | 1 | 1.000 | 1.000 | `auth-api:revokeToken:operation`, `accounts-api:getTransaction:response:401`, `auth-api:revokeToken:response:401` |
| Q122 | endpoint_discovery | 2 | 1.000 | 1.000 | `payments-api:PaymentRequest:component_schema`, `payments-api:initiatePayment:operation`, `payments-api:bearerAuth:security_scheme` |
| Q123 | authentication | 6 | 0.000 | 0.000 | `payments-api:bearerAuth:security_scheme`, `statements-api:bearerAuth:security_scheme`, `auth-api:bearerAuth:security_scheme` |
| Q124 | authentication | 1 | 1.000 | 0.500 | `auth-api:issueAccessToken:operation`, `auth-api:issueAccessToken:request_body`, `auth-api:introspectToken:operation` |
| Q125 | authentication | 1 | 1.000 | 1.000 | `accounts-api:bearerAuth:security_scheme`, `statements-api:bearerAuth:security_scheme`, `payments-api:bearerAuth:security_scheme` |
| Q126 | authentication | 1 | 1.000 | 1.000 | `customers-api:listConsents:response:403`, `customers-api:getCustomer:response:403`, `customers-api:listCustomerAccounts:response:403` |
| Q127 | authentication | 2 | 1.000 | 1.000 | `statements-api:apiKey:security_scheme`, `statements-api:getStatementRequestStatus:operation`, `customers-api:apiKey:security_scheme` |
| Q128 | multi_endpoint | 2 | 1.000 | 0.500 | `payments-api:cancelPayment:response:200`, `payments-api:cancelPayment:operation`, `payments-api:cancelPayment:response:409` |
| Q129 | multi_endpoint | 6 | 0.000 | 0.000 | `statements-api:bearerAuth:security_scheme`, `payments-api:bearerAuth:security_scheme`, `accounts-api:bearerAuth:security_scheme` |
| Q130 | multi_endpoint | 6 | 0.000 | 0.000 | `accounts-api:bearerAuth:security_scheme`, `statements-api:bearerAuth:security_scheme`, `payments-api:bearerAuth:security_scheme` |
| Q131 | multi_endpoint | 9 | 0.000 | 0.000 | `customers-api:searchCustomers:operation`, `auth-api:bearerAuth:security_scheme`, `customers-api:listConsents:response:200` |
| Q132 | comparison | 1 | 1.000 | 1.000 | `statements-api:requestStatement:operation`, `statements-api:listStatements:operation`, `statements-api:StatementRequestStatus:component_schema` |
| Q133 | comparison | 1 | 1.000 | 1.000 | `payments-api:PaymentRequest:component_schema`, `payments-api:initiatePayment:request_body`, `accounts-api:getTransaction:response:200` |
| Q134 | comparison | 2 | 1.000 | 1.000 | `payments-api:cancelPayment:response:404`, `payments-api:getPayment:response:404`, `customers-api:listConsents:response:404` |
| Q135 | unanswerable | excluded | | | `accounts-api:listTransactions:parameters`, `payments-api:initiatePayment:parameters`, `customers-api:searchCustomers:response:200` |
| Q136 | unanswerable | excluded | | | `accounts-api:getAccountBalances:response:200`, `accounts-api:AccountV2:component_schema`, `accounts-api:getAccountBalances:operation` |
| Q137 | unanswerable | excluded | | | `customers-api:listCustomerAccounts:response:200`, `customers-api:AccountSummary:component_schema`, `accounts-api:Account:component_schema` |
| Q138 | unanswerable | excluded | | | `customers-api:bearerAuth:security_scheme`, `statements-api:bearerAuth:security_scheme`, `auth-api:bearerAuth:security_scheme` |
| Q139 | unanswerable | excluded | | | `auth-api:introspectToken:response:200`, `auth-api:IntrospectionResponse:component_schema`, `auth-api:issueAccessToken:response:200` |
| Q140 | unanswerable | excluded | | | `auth-api:clientBasic:security_scheme`, `customers-api:bearerAuth:security_scheme`, `accounts-api:bearerAuth:security_scheme` |

## Paraphrase pairs

| original | paraphrase | original first relevant rank | paraphrase first relevant rank |
|---|---|---|---|
| Q103 | Q104 | 1 | not in top 10 |
| Q105 | Q106 | 1 | 3 |
| Q107 | Q108 | 1 | 1 |
| Q109 | Q110 | 1 | 4 |
| Q111 | Q112 | 1 | 2 |
| Q113 | Q114 | 1 | 1 |

## Latency

Qdrant local mode, in-process, exact search; CPU; not representative of a Qdrant server.

| stage | n | p50 (ms) | p95 (ms) |
|---|---|---|---|
| query embedding | 40 | 1725.60 | 2627.91 |
| vector search | 40 | 4.51 | 11.43 |
| reranking | 40 | 7538.49 | 10072.78 |
| total | 40 | 9223.68 | 12283.52 |

## Indexing cost

- Index build: 186 chunks, 186 embedded, 0 from cache, embedding 38.66 s, upsert 0.13 s
- This run: 186 chunks, 0 embedded, 186 from cache, up to date: True

The analysis of these results is in the experiment README, written by the author.
