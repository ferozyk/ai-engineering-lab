# Retrieval report: 20261110T204546Z-retrieval-measured-dense

## Setup

- Corpus: version 1.0.0, checksum `72063d1be60b13a9e9a5105f04b081a161fa010cb11d210d0be3589b8726c0e6`
- Question set: measured, version 1.0.0, checksum `28d846ec119f105cbb6d6b36b5b00bda0dd7b7a1b16d4b43179c359f5432cede`
- Embedding model: `BAAI/bge-m3`, revision `5617a9f61b028005a4858fdac845db406aefb181`, device cpu, dimension 1024, normalised True
- Retriever: dense; collection `lab-bank-c1-0-0-72063d1b-bge-m3-5617a9f6-m2400`
- Questions: 40 (6 unanswerable, excluded from metrics)
- K values: 1, 3, 5, 10; retrieved depth 10
- Git: `a293716be2c42a1f9123d7a69b0a45e1989170d7` (dirty: False); deterministic retrieval: True

## Metrics

| group | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | MRR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| overall | 34 | 0.559 | 0.941 | 0.941 | 1.000 | 0.485 | 0.804 | 0.843 | 0.944 | 0.559 | 0.343 | 0.224 | 0.135 | 0.748 |
| authentication | 5 | 0.800 | 0.800 | 0.800 | 1.000 | 0.700 | 0.700 | 0.700 | 0.820 | 0.800 | 0.267 | 0.160 | 0.140 | 0.825 |
| comparison | 3 | 0.333 | 1.000 | 1.000 | 1.000 | 0.167 | 0.611 | 0.889 | 1.000 | 0.333 | 0.444 | 0.400 | 0.233 | 0.667 |
| endpoint_discovery | 5 | 0.600 | 1.000 | 1.000 | 1.000 | 0.600 | 1.000 | 1.000 | 1.000 | 0.600 | 0.333 | 0.200 | 0.100 | 0.800 |
| exact_identifier | 6 | 0.667 | 1.000 | 1.000 | 1.000 | 0.667 | 0.917 | 1.000 | 1.000 | 0.667 | 0.333 | 0.233 | 0.117 | 0.833 |
| multi_endpoint | 4 | 0.500 | 1.000 | 1.000 | 1.000 | 0.250 | 0.625 | 0.625 | 0.750 | 0.500 | 0.417 | 0.250 | 0.150 | 0.750 |
| schema | 5 | 0.400 | 1.000 | 1.000 | 1.000 | 0.300 | 0.900 | 0.900 | 1.000 | 0.400 | 0.400 | 0.240 | 0.140 | 0.667 |
| semantic | 6 | 0.500 | 0.833 | 0.833 | 1.000 | 0.500 | 0.750 | 0.750 | 1.000 | 0.500 | 0.278 | 0.167 | 0.117 | 0.660 |

## Hypothesis verdicts (frozen criteria, computed mechanically)

| hypothesis | criterion | verdict | evidence |
|---|---|---|---|
| HA1 | Hit@5 over semantic + endpoint_discovery >= 0.80 | supported | Hit@5 = 10/11 = 0.909 |
| HA2 | Hit@5 over exact_identifier is at least 0.20 lower than HA1 | not supported | exact_identifier Hit@5 = 6/6 = 1.000; HA1 value = 0.909; gap = -0.091 |
| HA3 | see methodology section 8 | pending (needs generation, stage 2c/2d) |  |
| HA4 | see methodology section 8 | pending (needs generation, stage 2c/2d) |  |

## Per question

| id | category | first relevant rank | hit@5 | recall@5 | top 3 chunks |
|---|---|---|---|---|---|
| Q101 | semantic | 3 | 1.000 | 1.000 | `statements-api:StatementRequest:component_schema`, `statements-api:requestStatement:request_body`, `statements-api:requestStatement:response:400` |
| Q102 | semantic | 1 | 1.000 | 1.000 | `payments-api:initiatePayment:response:409`, `payments-api:initiatePayment:parameters`, `payments-api:initiatePayment:operation` |
| Q103 | exact_identifier | 1 | 1.000 | 1.000 | `statements-api:requestStatement:response:202`, `statements-api:getStatementRequestStatus:response:200`, `statements-api:getStatementRequestStatus:operation` |
| Q104 | semantic | 8 | 0.000 | 0.000 | `customers-api:listCustomerAccounts:response:200`, `statements-api:requestStatement:operation`, `accounts-api:getAccountV2:response:200` |
| Q105 | schema | 3 | 1.000 | 1.000 | `customers-api:searchCustomers:operation`, `customers-api:CustomerPage:component_schema`, `customers-api:searchCustomers:parameters` |
| Q106 | schema | 2 | 1.000 | 1.000 | `customers-api:searchCustomers:operation`, `customers-api:searchCustomers:parameters`, `customers-api:searchCustomers:response:200` |
| Q107 | exact_identifier | 2 | 1.000 | 1.000 | `auth-api:introspectToken:response:200`, `auth-api:TokenResponse:component_schema`, `auth-api:IntrospectionResponse:component_schema` |
| Q108 | semantic | 2 | 1.000 | 0.500 | `auth-api:introspectToken:response:200`, `auth-api:TokenResponse:component_schema`, `auth-api:IntrospectionResponse:component_schema` |
| Q109 | exact_identifier | 1 | 1.000 | 1.000 | `payments-api:cancelPayment:operation`, `payments-api:cancelPayment:response:409`, `payments-api:cancelPayment:response:200` |
| Q110 | semantic | 1 | 1.000 | 1.000 | `payments-api:cancelPayment:operation`, `payments-api:cancelPayment:response:409`, `payments-api:cancelPayment:response:200` |
| Q111 | schema | 1 | 1.000 | 1.000 | `customers-api:Customer:component_schema`, `customers-api:CustomerPage:component_schema`, `customers-api:Consent:component_schema` |
| Q112 | semantic | 1 | 1.000 | 1.000 | `customers-api:Customer:component_schema`, `customers-api:searchCustomers:operation`, `customers-api:getCustomer:response:200` |
| Q113 | schema | 1 | 1.000 | 1.000 | `accounts-api:getTransaction:response:200`, `accounts-api:Transaction:component_schema`, `payments-api:PaymentRequest:component_schema` |
| Q114 | schema | 2 | 1.000 | 0.500 | `accounts-api:Balances:component_schema`, `accounts-api:Transaction:component_schema`, `payments-api:Payment:component_schema` |
| Q115 | exact_identifier | 2 | 1.000 | 1.000 | `statements-api:getStatementRequestStatus:response:404`, `statements-api:getStatement:response:404`, `statements-api:requestStatement:response:404` |
| Q116 | exact_identifier | 1 | 1.000 | 1.000 | `auth-api:introspectToken:operation`, `auth-api:introspectToken:request_body`, `accounts-api:bearerAuth:security_scheme` |
| Q117 | exact_identifier | 1 | 1.000 | 1.000 | `payments-api:initiatePayment:parameters`, `payments-api:initiatePayment:response:409`, `payments-api:initiatePayment:operation` |
| Q118 | endpoint_discovery | 2 | 1.000 | 1.000 | `accounts-api:listTransactions:operation`, `accounts-api:getTransaction:operation`, `accounts-api:getTransaction:response:200` |
| Q119 | endpoint_discovery | 1 | 1.000 | 1.000 | `customers-api:searchCustomers:operation`, `customers-api:updateContactDetails:operation`, `customers-api:Customer:component_schema` |
| Q120 | endpoint_discovery | 2 | 1.000 | 1.000 | `customers-api:Consent:component_schema`, `customers-api:listConsents:operation`, `customers-api:listConsents:response:200` |
| Q121 | endpoint_discovery | 1 | 1.000 | 1.000 | `auth-api:revokeToken:operation`, `customers-api:listCustomerAccounts:response:401`, `payments-api:cancelPayment:response:401` |
| Q122 | endpoint_discovery | 1 | 1.000 | 1.000 | `payments-api:initiatePayment:operation`, `payments-api:initiatePayment:response:201`, `payments-api:Payment:component_schema` |
| Q123 | authentication | 1 | 1.000 | 1.000 | `payments-api:cancelPayment:operation`, `payments-api:cancelPayment:response:200`, `payments-api:cancelPayment:response:409` |
| Q124 | authentication | 1 | 1.000 | 0.500 | `auth-api:issueAccessToken:operation`, `customers-api:bearerAuth:security_scheme`, `payments-api:bearerAuth:security_scheme` |
| Q125 | authentication | 8 | 0.000 | 0.000 | `auth-api:TokenRequest:component_schema`, `auth-api:IntrospectionResponse:component_schema`, `auth-api:TokenResponse:component_schema` |
| Q126 | authentication | 1 | 1.000 | 1.000 | `customers-api:listConsents:response:403`, `customers-api:searchCustomers:response:403`, `customers-api:getCustomer:response:403` |
| Q127 | authentication | 1 | 1.000 | 1.000 | `statements-api:getStatementRequestStatus:operation`, `statements-api:getStatementRequestStatus:parameters`, `statements-api:getStatement:operation` |
| Q128 | multi_endpoint | 1 | 1.000 | 0.500 | `payments-api:cancelPayment:operation`, `payments-api:cancelPayment:response:200`, `payments-api:cancelPayment:response:409` |
| Q129 | multi_endpoint | 2 | 1.000 | 1.000 | `accounts-api:Balances:component_schema`, `customers-api:listCustomerAccounts:operation`, `accounts-api:getAccountBalances:operation` |
| Q130 | multi_endpoint | 1 | 1.000 | 0.500 | `customers-api:updateContactDetails:operation`, `customers-api:ContactDetailsUpdate:component_schema`, `customers-api:updateContactDetails:request_body` |
| Q131 | multi_endpoint | 2 | 1.000 | 0.500 | `customers-api:searchCustomers:operation`, `customers-api:listConsents:operation`, `customers-api:listConsents:response:200` |
| Q132 | comparison | 2 | 1.000 | 0.667 | `statements-api:StatementRequestStatus:component_schema`, `statements-api:requestStatement:operation`, `statements-api:getStatementRequestStatus:response:200` |
| Q133 | comparison | 2 | 1.000 | 1.000 | `accounts-api:getTransaction:response:200`, `payments-api:PaymentRequest:component_schema`, `accounts-api:Transaction:component_schema` |
| Q134 | comparison | 1 | 1.000 | 1.000 | `payments-api:getPayment:response:404`, `payments-api:cancelPayment:response:404`, `payments-api:cancelPayment:response:403` |
| Q135 | unanswerable | excluded | | | `payments-api:initiatePayment:operation`, `accounts-api:listTransactions:parameters`, `payments-api:getPayment:response:200` |
| Q136 | unanswerable | excluded | | | `accounts-api:getAccountBalances:response:200`, `accounts-api:getAccountV2:response:200`, `accounts-api:getAccountBalances:operation` |
| Q137 | unanswerable | excluded | | | `accounts-api:getAccountV2:response:200`, `accounts-api:getAccount:response:200`, `accounts-api:getTransaction:response:404` |
| Q138 | unanswerable | excluded | | | `customers-api:listCustomerAccounts:operation`, `customers-api:Customer:component_schema`, `customers-api:searchCustomers:operation` |
| Q139 | unanswerable | excluded | | | `auth-api:TokenResponse:component_schema`, `auth-api:issueAccessToken:response:200`, `customers-api:listConsents:response:401` |
| Q140 | unanswerable | excluded | | | `customers-api:bearerAuth:security_scheme`, `accounts-api:bearerAuth:security_scheme`, `statements-api:bearerAuth:security_scheme` |

## Paraphrase pairs

| original | paraphrase | original first relevant rank | paraphrase first relevant rank |
|---|---|---|---|
| Q103 | Q104 | 1 | 8 |
| Q105 | Q106 | 3 | 2 |
| Q107 | Q108 | 2 | 2 |
| Q109 | Q110 | 1 | 1 |
| Q111 | Q112 | 1 | 1 |
| Q113 | Q114 | 1 | 2 |

## Latency

Qdrant local mode, in-process, exact search; CPU; not representative of a Qdrant server.

| stage | n | p50 (ms) | p95 (ms) |
|---|---|---|---|
| query embedding | 40 | 122.16 | 265.18 |
| vector search | 40 | 1.04 | 1.97 |
| total | 40 | 123.27 | 266.18 |

## Indexing cost

- Index build: 186 chunks, 186 embedded, 0 from cache, embedding 38.66 s, upsert 0.13 s
- This run: 186 chunks, 0 embedded, 186 from cache, up to date: True

The analysis of these results is in the experiment README, written by the author.
