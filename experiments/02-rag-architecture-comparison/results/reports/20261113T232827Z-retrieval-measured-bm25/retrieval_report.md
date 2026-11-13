# Retrieval report: 20261113T232827Z-retrieval-measured-bm25

## Setup

- Corpus: version 1.0.0, checksum `72063d1be60b13a9e9a5105f04b081a161fa010cb11d210d0be3589b8726c0e6`
- Question set: measured, version 1.0.0, checksum `28d846ec119f105cbb6d6b36b5b00bda0dd7b7a1b16d4b43179c359f5432cede`
- Embedding model: `none`, revision `none`, device cpu, dimension 0, normalised True
- Retriever: bm25; collection `none (in-memory BM25 index)`
- Questions: 40 (6 unanswerable, excluded from metrics)
- K values: 1, 3, 5, 10; retrieved depth 10
- Git: `9f396681eb9496496402d90a5068eb2bba707280` (dirty: False); deterministic retrieval: True

## Metrics

| group | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | MRR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| overall | 34 | 0.500 | 0.676 | 0.765 | 0.853 | 0.377 | 0.593 | 0.678 | 0.809 | 0.500 | 0.265 | 0.188 | 0.121 | 0.612 |
| authentication | 5 | 0.400 | 0.600 | 0.800 | 1.000 | 0.300 | 0.500 | 0.580 | 0.900 | 0.400 | 0.200 | 0.200 | 0.180 | 0.550 |
| comparison | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.444 | 0.722 | 0.889 | 1.000 | 1.000 | 0.556 | 0.400 | 0.233 | 1.000 |
| endpoint_discovery | 5 | 0.600 | 0.800 | 0.800 | 1.000 | 0.600 | 0.800 | 0.800 | 1.000 | 0.600 | 0.267 | 0.160 | 0.100 | 0.725 |
| exact_identifier | 6 | 0.500 | 1.000 | 1.000 | 1.000 | 0.417 | 1.000 | 1.000 | 1.000 | 0.500 | 0.389 | 0.233 | 0.117 | 0.722 |
| multi_endpoint | 4 | 0.500 | 0.750 | 0.750 | 1.000 | 0.250 | 0.375 | 0.375 | 0.750 | 0.500 | 0.250 | 0.150 | 0.150 | 0.667 |
| schema | 5 | 0.400 | 0.400 | 0.600 | 0.600 | 0.300 | 0.400 | 0.600 | 0.600 | 0.400 | 0.200 | 0.160 | 0.080 | 0.450 |
| semantic | 6 | 0.333 | 0.333 | 0.500 | 0.500 | 0.333 | 0.333 | 0.500 | 0.500 | 0.333 | 0.111 | 0.100 | 0.050 | 0.367 |

## Hypothesis verdicts (frozen criteria, computed mechanically)

diagnostic run: no pre-registered hypotheses

## Per question

| id | category | first relevant rank | hit@5 | recall@5 | top 3 chunks |
|---|---|---|---|---|---|
| Q101 | semantic | not in top 10 | 0.000 | 0.000 | `statements-api:StatementRequest:component_schema`, `statements-api:StatementSummary:component_schema`, `statements-api:Statement:component_schema` |
| Q102 | semantic | 1 | 1.000 | 1.000 | `payments-api:initiatePayment:response:409`, `payments-api:initiatePayment:operation`, `payments-api:getPayment:operation` |
| Q103 | exact_identifier | 2 | 1.000 | 1.000 | `statements-api:requestStatement:operation`, `statements-api:requestStatement:response:202`, `statements-api:getStatementRequestStatus:operation` |
| Q104 | semantic | not in top 10 | 0.000 | 0.000 | `customers-api:Customer:component_schema`, `customers-api:ContactDetailsUpdate:component_schema`, `statements-api:requestStatement:operation` |
| Q105 | schema | 4 | 1.000 | 1.000 | `customers-api:searchCustomers:operation`, `customers-api:CustomerPage:component_schema`, `customers-api:searchCustomers:response:200` |
| Q106 | schema | not in top 10 | 0.000 | 0.000 | `payments-api:initiatePayment:operation`, `auth-api:TokenReference:component_schema`, `customers-api:searchCustomers:response:403` |
| Q107 | exact_identifier | 1 | 1.000 | 1.000 | `auth-api:TokenResponse:component_schema`, `auth-api:issueAccessToken:response:200`, `customers-api:listConsents:response:200` |
| Q108 | semantic | not in top 10 | 0.000 | 0.000 | `accounts-api:bearerAuth:security_scheme`, `customers-api:bearerAuth:security_scheme`, `payments-api:bearerAuth:security_scheme` |
| Q109 | exact_identifier | 1 | 1.000 | 1.000 | `payments-api:cancelPayment:operation`, `statements-api:StatementRequest:component_schema`, `payments-api:initiatePayment:operation` |
| Q110 | semantic | 5 | 1.000 | 1.000 | `payments-api:Payment:component_schema`, `auth-api:introspectToken:operation`, `payments-api:getPayment:operation` |
| Q111 | schema | 1 | 1.000 | 1.000 | `customers-api:Customer:component_schema`, `customers-api:getCustomer:response:200`, `customers-api:updateContactDetails:response:200` |
| Q112 | semantic | 1 | 1.000 | 1.000 | `customers-api:Customer:component_schema`, `customers-api:getCustomer:operation`, `customers-api:getCustomer:response:200` |
| Q113 | schema | 1 | 1.000 | 1.000 | `accounts-api:Transaction:component_schema`, `accounts-api:getTransaction:response:200`, `customers-api:listCustomerAccounts:operation` |
| Q114 | schema | not in top 10 | 0.000 | 0.000 |  |
| Q115 | exact_identifier | 3 | 1.000 | 1.000 | `statements-api:getStatementRequestStatus:response:404`, `statements-api:requestStatement:response:404`, `statements-api:getStatement:response:404` |
| Q116 | exact_identifier | 1 | 1.000 | 1.000 | `auth-api:introspectToken:operation`, `auth-api:introspectToken:request_body`, `auth-api:introspectToken:response:200` |
| Q117 | exact_identifier | 2 | 1.000 | 1.000 | `payments-api:initiatePayment:operation`, `payments-api:initiatePayment:parameters`, `payments-api:initiatePayment:response:409` |
| Q118 | endpoint_discovery | 1 | 1.000 | 1.000 | `accounts-api:getTransaction:operation`, `accounts-api:getAccount:operation`, `accounts-api:bearerAuth:security_scheme` |
| Q119 | endpoint_discovery | 8 | 0.000 | 0.000 | `customers-api:searchCustomers:parameters`, `customers-api:updateContactDetails:request_body`, `customers-api:ContactDetailsUpdate:component_schema` |
| Q120 | endpoint_discovery | 1 | 1.000 | 1.000 | `customers-api:listConsents:operation`, `accounts-api:Account:component_schema`, `accounts-api:bearerAuth:security_scheme` |
| Q121 | endpoint_discovery | 1 | 1.000 | 1.000 | `auth-api:revokeToken:operation`, `auth-api:TokenResponse:component_schema`, `auth-api:issueAccessToken:response:200` |
| Q122 | endpoint_discovery | 2 | 1.000 | 1.000 | `payments-api:PaymentRequest:component_schema`, `payments-api:initiatePayment:operation`, `customers-api:ContactDetailsUpdate:component_schema` |
| Q123 | authentication | 6 | 0.000 | 0.000 | `accounts-api:bearerAuth:security_scheme`, `customers-api:bearerAuth:security_scheme`, `payments-api:bearerAuth:security_scheme` |
| Q124 | authentication | 1 | 1.000 | 0.500 | `auth-api:issueAccessToken:operation`, `auth-api:issueAccessToken:request_body`, `auth-api:issueAccessToken:response:200` |
| Q125 | authentication | 4 | 1.000 | 0.400 | `auth-api:TokenRequest:component_schema`, `auth-api:issueAccessToken:request_body`, `auth-api:clientBasic:security_scheme` |
| Q126 | authentication | 3 | 1.000 | 1.000 | `customers-api:listConsents:operation`, `customers-api:listConsents:parameters`, `customers-api:listConsents:response:403` |
| Q127 | authentication | 1 | 1.000 | 1.000 | `statements-api:getStatementRequestStatus:operation`, `statements-api:getStatementRequestStatus:parameters`, `statements-api:requestStatement:operation` |
| Q128 | multi_endpoint | 1 | 1.000 | 0.500 | `payments-api:cancelPayment:operation`, `payments-api:cancelPayment:response:200`, `payments-api:Payment:component_schema` |
| Q129 | multi_endpoint | 2 | 1.000 | 0.500 | `accounts-api:getAccountBalances:response:200`, `customers-api:listCustomerAccounts:operation`, `accounts-api:bearerAuth:security_scheme` |
| Q130 | multi_endpoint | 6 | 0.000 | 0.000 | `customers-api:ContactDetailsUpdate:component_schema`, `customers-api:updateContactDetails:request_body`, `customers-api:Customer:component_schema` |
| Q131 | multi_endpoint | 1 | 1.000 | 0.500 | `customers-api:listConsents:operation`, `customers-api:Customer:component_schema`, `customers-api:getCustomer:response:200` |
| Q132 | comparison | 1 | 1.000 | 0.667 | `statements-api:requestStatement:operation`, `statements-api:listStatements:operation`, `statements-api:getStatementRequestStatus:operation` |
| Q133 | comparison | 1 | 1.000 | 1.000 | `payments-api:PaymentRequest:component_schema`, `payments-api:initiatePayment:request_body`, `payments-api:initiatePayment:operation` |
| Q134 | comparison | 1 | 1.000 | 1.000 | `payments-api:getPayment:response:404`, `payments-api:cancelPayment:response:404`, `customers-api:getCustomer:response:404` |
| Q135 | unanswerable | excluded | | | `customers-api:CustomerPage:component_schema`, `customers-api:searchCustomers:response:200`, `payments-api:initiatePayment:operation` |
| Q136 | unanswerable | excluded | | | `accounts-api:Balances:component_schema`, `statements-api:Statement:component_schema`, `accounts-api:AccountV2:component_schema` |
| Q137 | unanswerable | excluded | | | `customers-api:AccountSummary:component_schema`, `accounts-api:Account:component_schema`, `accounts-api:AccountV2:component_schema` |
| Q138 | unanswerable | excluded | | | `customers-api:listCustomerAccounts:operation`, `customers-api:listCustomerAccounts:response:200`, `accounts-api:bearerAuth:security_scheme` |
| Q139 | unanswerable | excluded | | | `auth-api:IntrospectionResponse:component_schema`, `auth-api:introspectToken:response:200`, `customers-api:searchCustomers:response:403` |
| Q140 | unanswerable | excluded | | | `accounts-api:bearerAuth:security_scheme`, `customers-api:bearerAuth:security_scheme`, `payments-api:bearerAuth:security_scheme` |

## Paraphrase pairs

| original | paraphrase | original first relevant rank | paraphrase first relevant rank |
|---|---|---|---|
| Q103 | Q104 | 2 | not in top 10 |
| Q105 | Q106 | 4 | not in top 10 |
| Q107 | Q108 | 1 | not in top 10 |
| Q109 | Q110 | 1 | 5 |
| Q111 | Q112 | 1 | 1 |
| Q113 | Q114 | 1 | not in top 10 |

## Latency

BM25 over an in-memory index in pure Python; CPU; no query embedding (0 ms).

| stage | n | p50 (ms) | p95 (ms) |
|---|---|---|---|
| query embedding | 40 | 0.00 | 0.00 |
| vector search | 40 | 0.12 | 0.25 |
| total | 40 | 0.12 | 0.25 |

## Indexing cost


The analysis of these results is in the experiment README, written by the author.
