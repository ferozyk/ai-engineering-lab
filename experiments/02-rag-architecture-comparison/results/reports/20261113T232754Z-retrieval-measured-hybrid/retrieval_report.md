# Retrieval report: 20261113T232754Z-retrieval-measured-hybrid

## Setup

- Corpus: version 1.0.0, checksum `72063d1be60b13a9e9a5105f04b081a161fa010cb11d210d0be3589b8726c0e6`
- Question set: measured, version 1.0.0, checksum `28d846ec119f105cbb6d6b36b5b00bda0dd7b7a1b16d4b43179c359f5432cede`
- Embedding model: `BAAI/bge-m3`, revision `5617a9f61b028005a4858fdac845db406aefb181`, device cpu, dimension 1024, normalised True
- Retriever: hybrid; collection `lab-bank-c1-0-0-72063d1b-bge-m3-5617a9f6-m2400`
- Questions: 40 (6 unanswerable, excluded from metrics)
- K values: 1, 3, 5, 10; retrieved depth 10
- Git: `9f396681eb9496496402d90a5068eb2bba707280` (dirty: False); deterministic retrieval: True

## Metrics

| group | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | MRR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| overall | 34 | 0.706 | 0.882 | 0.882 | 0.941 | 0.569 | 0.761 | 0.775 | 0.876 | 0.706 | 0.343 | 0.212 | 0.129 | 0.782 |
| authentication | 5 | 0.800 | 1.000 | 1.000 | 1.000 | 0.700 | 0.740 | 0.740 | 0.860 | 0.800 | 0.333 | 0.200 | 0.160 | 0.867 |
| comparison | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.444 | 0.889 | 0.889 | 1.000 | 1.000 | 0.667 | 0.400 | 0.233 | 1.000 |
| endpoint_discovery | 5 | 0.800 | 1.000 | 1.000 | 1.000 | 0.800 | 1.000 | 1.000 | 1.000 | 0.800 | 0.333 | 0.200 | 0.100 | 0.867 |
| exact_identifier | 6 | 0.833 | 1.000 | 1.000 | 1.000 | 0.750 | 1.000 | 1.000 | 1.000 | 0.833 | 0.389 | 0.233 | 0.117 | 0.917 |
| multi_endpoint | 4 | 0.750 | 1.000 | 1.000 | 1.000 | 0.375 | 0.500 | 0.625 | 0.750 | 0.750 | 0.333 | 0.250 | 0.150 | 0.833 |
| schema | 5 | 0.400 | 0.800 | 0.800 | 0.800 | 0.300 | 0.700 | 0.700 | 0.800 | 0.400 | 0.333 | 0.200 | 0.120 | 0.567 |
| semantic | 6 | 0.500 | 0.500 | 0.500 | 0.833 | 0.500 | 0.500 | 0.500 | 0.750 | 0.500 | 0.167 | 0.100 | 0.083 | 0.544 |

## Hypothesis verdicts (frozen criteria, computed mechanically)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HB1 | Hit@1 over exact_identifier + schema >= 8/11 | not supported | Hit@1 = 7/11 = 0.636; architecture A: 6/11 |
| HB2 | overall Hit@5 >= 31/34 | not supported | Hit@5 = 30/34 = 0.882; architecture A: 32/34 |
| HB3 | correctness over answerable attempts >= 0.755 | pending (needs generation) |  |

## Per question

| id | category | first relevant rank | hit@5 | recall@5 | top 3 chunks |
|---|---|---|---|---|---|
| Q101 | semantic | 10 | 0.000 | 0.000 | `statements-api:StatementRequest:component_schema`, `statements-api:requestStatement:request_body`, `statements-api:StatementSummary:component_schema` |
| Q102 | semantic | 1 | 1.000 | 1.000 | `payments-api:initiatePayment:response:409`, `payments-api:initiatePayment:operation`, `payments-api:initiatePayment:parameters` |
| Q103 | exact_identifier | 1 | 1.000 | 1.000 | `statements-api:requestStatement:response:202`, `statements-api:getStatementRequestStatus:operation`, `statements-api:requestStatement:operation` |
| Q104 | semantic | not in top 10 | 0.000 | 0.000 | `statements-api:requestStatement:operation`, `customers-api:getCustomer:response:200`, `customers-api:Customer:component_schema` |
| Q105 | schema | 3 | 1.000 | 1.000 | `customers-api:searchCustomers:operation`, `customers-api:CustomerPage:component_schema`, `customers-api:searchCustomers:parameters` |
| Q106 | schema | not in top 10 | 0.000 | 0.000 | `customers-api:searchCustomers:operation`, `customers-api:searchCustomers:response:200`, `customers-api:getCustomer:response:200` |
| Q107 | exact_identifier | 1 | 1.000 | 1.000 | `auth-api:TokenResponse:component_schema`, `auth-api:issueAccessToken:response:200`, `auth-api:introspectToken:response:200` |
| Q108 | semantic | 6 | 0.000 | 0.000 | `customers-api:bearerAuth:security_scheme`, `accounts-api:bearerAuth:security_scheme`, `auth-api:bearerAuth:security_scheme` |
| Q109 | exact_identifier | 1 | 1.000 | 1.000 | `payments-api:cancelPayment:operation`, `payments-api:cancelPayment:response:200`, `payments-api:cancelPayment:response:409` |
| Q110 | semantic | 1 | 1.000 | 1.000 | `payments-api:cancelPayment:operation`, `payments-api:cancelPayment:response:409`, `payments-api:cancelPayment:response:200` |
| Q111 | schema | 1 | 1.000 | 1.000 | `customers-api:Customer:component_schema`, `customers-api:getCustomer:response:200`, `customers-api:updateContactDetails:response:200` |
| Q112 | semantic | 1 | 1.000 | 1.000 | `customers-api:Customer:component_schema`, `customers-api:getCustomer:response:200`, `customers-api:updateContactDetails:response:200` |
| Q113 | schema | 1 | 1.000 | 1.000 | `accounts-api:Transaction:component_schema`, `accounts-api:getTransaction:response:200`, `customers-api:listCustomerAccounts:operation` |
| Q114 | schema | 2 | 1.000 | 0.500 | `accounts-api:Balances:component_schema`, `accounts-api:Transaction:component_schema`, `payments-api:Payment:component_schema` |
| Q115 | exact_identifier | 2 | 1.000 | 1.000 | `statements-api:getStatementRequestStatus:response:404`, `statements-api:getStatement:response:404`, `statements-api:requestStatement:response:404` |
| Q116 | exact_identifier | 1 | 1.000 | 1.000 | `auth-api:introspectToken:operation`, `auth-api:introspectToken:request_body`, `auth-api:introspectToken:response:200` |
| Q117 | exact_identifier | 1 | 1.000 | 1.000 | `payments-api:initiatePayment:parameters`, `payments-api:initiatePayment:operation`, `payments-api:initiatePayment:response:409` |
| Q118 | endpoint_discovery | 1 | 1.000 | 1.000 | `accounts-api:getTransaction:operation`, `accounts-api:getAccount:operation`, `accounts-api:getTransaction:response:200` |
| Q119 | endpoint_discovery | 3 | 1.000 | 1.000 | `customers-api:searchCustomers:parameters`, `customers-api:Customer:component_schema`, `customers-api:searchCustomers:operation` |
| Q120 | endpoint_discovery | 1 | 1.000 | 1.000 | `customers-api:listConsents:operation`, `customers-api:bearerAuth:security_scheme`, `accounts-api:bearerAuth:security_scheme` |
| Q121 | endpoint_discovery | 1 | 1.000 | 1.000 | `auth-api:revokeToken:operation`, `auth-api:issueAccessToken:operation`, `auth-api:issueAccessToken:response:200` |
| Q122 | endpoint_discovery | 1 | 1.000 | 1.000 | `payments-api:initiatePayment:operation`, `payments-api:PaymentRequest:component_schema`, `payments-api:Payment:component_schema` |
| Q123 | authentication | 1 | 1.000 | 1.000 | `payments-api:cancelPayment:operation`, `payments-api:cancelPayment:response:200`, `payments-api:Payment:component_schema` |
| Q124 | authentication | 1 | 1.000 | 0.500 | `auth-api:issueAccessToken:operation`, `auth-api:issueAccessToken:request_body`, `auth-api:issueAccessToken:response:200` |
| Q125 | authentication | 3 | 1.000 | 0.200 | `auth-api:TokenRequest:component_schema`, `auth-api:issueAccessToken:request_body`, `accounts-api:bearerAuth:security_scheme` |
| Q126 | authentication | 1 | 1.000 | 1.000 | `customers-api:listConsents:response:403`, `customers-api:listConsents:operation`, `customers-api:listConsents:response:401` |
| Q127 | authentication | 1 | 1.000 | 1.000 | `statements-api:getStatementRequestStatus:operation`, `statements-api:getStatementRequestStatus:parameters`, `statements-api:requestStatement:operation` |
| Q128 | multi_endpoint | 1 | 1.000 | 0.500 | `payments-api:cancelPayment:operation`, `payments-api:cancelPayment:response:200`, `payments-api:cancelPayment:response:409` |
| Q129 | multi_endpoint | 1 | 1.000 | 1.000 | `customers-api:listCustomerAccounts:operation`, `accounts-api:getAccountBalances:response:200`, `accounts-api:Balances:component_schema` |
| Q130 | multi_endpoint | 3 | 1.000 | 0.500 | `customers-api:ContactDetailsUpdate:component_schema`, `customers-api:updateContactDetails:request_body`, `customers-api:updateContactDetails:operation` |
| Q131 | multi_endpoint | 1 | 1.000 | 0.500 | `customers-api:listConsents:operation`, `customers-api:searchCustomers:operation`, `customers-api:Customer:component_schema` |
| Q132 | comparison | 1 | 1.000 | 0.667 | `statements-api:requestStatement:operation`, `statements-api:StatementRequestStatus:component_schema`, `statements-api:listStatements:operation` |
| Q133 | comparison | 1 | 1.000 | 1.000 | `payments-api:PaymentRequest:component_schema`, `accounts-api:getTransaction:response:200`, `accounts-api:Transaction:component_schema` |
| Q134 | comparison | 1 | 1.000 | 1.000 | `payments-api:getPayment:response:404`, `payments-api:cancelPayment:response:404`, `customers-api:getCustomer:response:404` |
| Q135 | unanswerable | excluded | | | `payments-api:initiatePayment:operation`, `accounts-api:listTransactions:parameters`, `payments-api:initiatePayment:request_body` |
| Q136 | unanswerable | excluded | | | `accounts-api:Balances:component_schema`, `accounts-api:getAccountBalances:response:200`, `accounts-api:getAccountV2:response:200` |
| Q137 | unanswerable | excluded | | | `accounts-api:getAccountV2:response:200`, `accounts-api:getAccount:response:200`, `accounts-api:Account:component_schema` |
| Q138 | unanswerable | excluded | | | `customers-api:listCustomerAccounts:operation`, `customers-api:listCustomerAccounts:response:200`, `customers-api:Customer:component_schema` |
| Q139 | unanswerable | excluded | | | `auth-api:introspectToken:response:200`, `auth-api:IntrospectionResponse:component_schema`, `auth-api:TokenResponse:component_schema` |
| Q140 | unanswerable | excluded | | | `accounts-api:bearerAuth:security_scheme`, `customers-api:bearerAuth:security_scheme`, `payments-api:bearerAuth:security_scheme` |

## Paraphrase pairs

| original | paraphrase | original first relevant rank | paraphrase first relevant rank |
|---|---|---|---|
| Q103 | Q104 | 1 | not in top 10 |
| Q105 | Q106 | 3 | not in top 10 |
| Q107 | Q108 | 1 | 6 |
| Q109 | Q110 | 1 | 1 |
| Q111 | Q112 | 1 | 1 |
| Q113 | Q114 | 1 | 2 |

## Latency

Query embedding, then Qdrant local-mode search (in-process, exact) plus in-memory BM25 search and rank fusion; the 'vector search' row is the sum of those three; CPU; not representative of a Qdrant server.

| stage | n | p50 (ms) | p95 (ms) |
|---|---|---|---|
| query embedding | 40 | 128.34 | 249.12 |
| vector search | 40 | 1.90 | 2.57 |
| total | 40 | 130.42 | 250.89 |

## Indexing cost

- Index build: 186 chunks, 186 embedded, 0 from cache, embedding 38.66 s, upsert 0.13 s
- This run: 186 chunks, 0 embedded, 186 from cache, up to date: True

The analysis of these results is in the experiment README, written by the author.
