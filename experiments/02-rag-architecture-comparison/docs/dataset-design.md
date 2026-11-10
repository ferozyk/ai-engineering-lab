# Dataset design

Status: the corpus, chunker and question sets exist (Stage 2a). Everything is synthetic; "Lab Bank" is fictional.

## 1. Corpus: Lab Bank synthetic OpenAPI 3.1 specs

Five self-contained YAML files with no cross-file `$ref`, under `datasets/corpus/`.

**Conventions shared by every spec except Auth**

- Security: an OAuth2 bearer token (`Authorization: Bearer <token>`, client-credentials flow, per-operation scopes) and an `X-Api-Key` header.
- An optional `X-Correlation-Id` request header, echoed in responses.
- Errors use an `application/problem+json` `Problem` schema with fields `type`, `title`, `status`, `code`, `detail`, `correlationId`.
- Error codes:
  - `AUTH-001`: 401, missing, invalid or expired token
  - `AUTH-002`: 403, insufficient scope
  - `CUS-404`, `ACC-404`, `STM-404`, `PAY-404`: 404, resource not found
  - `VAL-001`: 400, validation error
  - `RATE-001`: 429, with a `Retry-After` response header
- Each spec carries its own copy of `Problem` and of the security schemes. That is realistic, and it deliberately creates near-duplicate chunks.
- No spec states a numeric rate limit. Unanswerable question Q15 relies on this.

| File | Operations (method path · operationId · notes) |
|---|---|
| `auth-api.yaml` | `POST /oauth/token` · issueAccessToken · form body `grant_type`, `client_id`, `client_secret`, `scope`; 200 `TokenResponse {access_token, token_type, expires_in, scope}`; 400 `AUTH-003` invalid_grant; 401 `AUTH-001`. `POST /oauth/revoke` · revokeToken. `POST /oauth/introspect` · introspectToken. Scopes defined: `customers:read`, `customers:write`, `accounts:read`, `statements:read`, `payments:write`. |
| `customers-api.yaml` | `GET /v1/customers/{customerId}` · getCustomer. `GET /v1/customers` · searchCustomers (query `email`, `lastName`, `page`, `pageSize` max 100). `GET /v1/customers/{customerId}/accounts` · listCustomerAccounts. `PATCH /v1/customers/{customerId}/contact-details` · updateContactDetails (body `ContactDetailsUpdate`; scope `customers:write`). `GET /v1/customers/{customerId}/consents` · listConsents. |
| `accounts-api.yaml` | `GET /v1/accounts/{accountId}` · getAccount (deprecated). `GET /v2/accounts/{accountId}` · getAccountV2 (adds `availableBalance` and `overdraftLimit`). `GET /v1/accounts/{accountId}/balances` · getAccountBalances. `GET /v1/accounts/{accountId}/transactions` · listTransactions (query `fromDate`, `toDate`, `cursor`, `limit` default 100, max 500). `GET /v1/accounts/{accountId}/transactions/{transactionId}` · getTransaction. All use scope `accounts:read`. |
| `statements-api.yaml` | `GET /v1/accounts/{accountId}/statements` · listStatements (monthly statements; query `year`). `GET /v1/accounts/{accountId}/statements/{statementId}` · getStatement (`Accept: application/pdf` or `application/json`). `POST /v1/accounts/{accountId}/statement-requests` · requestStatement (ad-hoc date range; body `StatementRequest` with required `fromDate`, `toDate`, `format`; returns 202 with a `Location` header). `GET /v1/statement-requests/{requestId}` · getStatementRequestStatus. Scope `statements:read`. |
| `payments-api.yaml` | `POST /v1/payments` · initiatePayment (required `Idempotency-Key` header; scope `payments:write`). `GET /v1/payments/{paymentId}` · getPayment. `POST /v1/payments/{paymentId}/cancellation` · cancelPayment (only while status is `PENDING`). |

### Deliberate look-alikes

These are hard negatives. They exist so that no architecture scores 100% for trivial reasons, and so the differences between retrieval strategies have something to show up on.

- **v1 vs v2 accounts:** two nearly identical operations, one deprecated. Tests whether retrieval and generation distinguish versions.
- **Statements vs transactions:** similar vocabulary (account, date range, list), different resources.
- **`listStatements` vs `requestStatement`:** monthly statements versus an ad-hoc date range. A question about a custom range must find the second.
- **The `Problem` schema repeated in every spec:** near-duplicate chunks compete for the same top-K slots.
- **`fromDate`:** a query parameter on `listTransactions` and a body field in `StatementRequest`. An exact-identifier question must tell them apart.

### Details settled while writing the corpus

- Operations in `payments-api` all use the scope `payments:write`; the design lists no separate read scope.
- `auth-api` authenticates clients with an HTTP Basic scheme (`clientBasic`). It also carries a reference `bearerAuth` scheme, so the five scopes are documented in a chunk that can be retrieved.
- Spec-specific error responses: `AUTH-003` (token endpoint), `PAY-409` (idempotency conflict), `PAY-410` (payment not cancellable), and `VAL-001` on `requestStatement` for an invalid date range.
- No spec states a numeric rate limit, closes or removes an account, offers notification subscriptions, exports customer data, or mentions a BIC or refresh tokens. Several unanswerable questions rely on these gaps.

## 2. Normalised chunk model

| Field | Type | Example | Purpose |
|---|---|---|---|
| `document_id` | string | `accounts-api` | Which spec the chunk came from. |
| `document_name` | string | `Lab Bank Accounts API` | Human-readable spec title. |
| `chunk_id` | string | `accounts-api:listTransactions:parameters` | Deterministic id, used for citations and as the Qdrant point id source. |
| `chunk_type` | enum | `parameters` | Which structural element the chunk covers. |
| `api_path` | string or null | `/v1/accounts/{accountId}/transactions` | Path, for operation-level chunks. |
| `http_method` | string or null | `GET` | Method, for operation-level chunks. |
| `operation_id` | string or null | `listTransactions` | Operation the chunk belongs to. |
| `tags` | list of strings | `["Transactions"]` | Spec tags. |
| `content` | string | header line plus text | The text that is embedded and shown to the model. |
| `source_reference` | string | `#/paths/~1v1~1accounts~1{accountId}~1transactions/get/parameters` | RFC 6901 JSON Pointer (within `document_id`) to the element the chunk was built from. Used for relevance, see section 3. |
| `refs` | list of strings | `["Transaction"]` | Names of components referenced by this chunk. |
| `spec_version` | string | `1.0.0` | The `info.version` of the spec. |
| `content_hash` | string | SHA-256 hex | Detects changed chunks; part of the embedding cache key. |

### `chunk_type` values

- `operation`: method, path, operationId, summary, description, tags, deprecated flag, plus a digest line with parameter names, security scopes and response codes.
- `parameters`: all parameters of one operation, with name, location (`in`), required flag, type, constraints and description.
- `request_body`: media type and the resolved schema field list.
- `response`: one per status code, with the resolved schema and headers.
- `security_scheme`: one per scheme per document.
- `component_schema`: one per entry in `components.schemas`.

### Rules

- Every chunk starts with a context header, for example `[accounts-api] GET /v1/accounts/{accountId}/transactions · parameters`. Without it, a parameter table would not say which endpoint it belongs to.
- A `$ref` is resolved one level into a field list (name, type, required). The referenced component is also its own chunk, and the reference name goes in `refs`.
- `chunk_id` is deterministic: `{document_id}:{operation_id or component name}:{chunk_type}[:{status}]`.
- `source_reference` is an RFC 6901 JSON Pointer. In a pointer, `~` is written `~0` and `/` is written `~1`.
- Size: these chunks are naturally small; the measured sizes are under "Corpus statistics" below. A chunk is split only if it exceeds the configured maximum, by schema properties with the header repeated. No overlap is needed, because splits fall on structural boundaries.
- Why not fixed-size splitting: a split can cut through the middle of a parameter table and separate a field from its endpoint.
- Limitation: the operation digest duplicates some text that also appears in the parameter and response chunks.

### Worked example

Input (a short, illustrative snippet):

```yaml
paths:
  /v1/accounts/{accountId}/balances:
    get:
      operationId: getAccountBalances
      summary: Get account balances
      tags: [Balances]
      security:
        - bearerAuth: [accounts:read]
          apiKey: []
      parameters:
        - name: accountId
          in: path
          required: true
          schema: { type: string }
      responses:
        "200":
          description: Current balances
          content:
            application/json:
              schema: { $ref: "#/components/schemas/Balances" }
```

Chunks produced (rendered as text):

```text
chunk_id: accounts-api:getAccountBalances:operation
source_reference: #/paths/~1v1~1accounts~1{accountId}~1balances/get
content:
[accounts-api] GET /v1/accounts/{accountId}/balances · operation
operationId: getAccountBalances
Get account balances
Tags: Balances
Digest: parameters accountId; scopes accounts:read; responses 200

chunk_id: accounts-api:getAccountBalances:parameters
source_reference: #/paths/~1v1~1accounts~1{accountId}~1balances/get/parameters
content:
[accounts-api] GET /v1/accounts/{accountId}/balances · parameters
accountId (path, required, string)

chunk_id: accounts-api:getAccountBalances:response:200
source_reference: #/paths/~1v1~1accounts~1{accountId}~1balances/get/responses/200
content:
[accounts-api] GET /v1/accounts/{accountId}/balances · response 200
Current balances. application/json: Balances (fields resolved one level)
refs: Balances
```

## 3. Ground truth uses JSON Pointers, not chunk IDs

**The decision.** Questions label relevant spec elements, not chunks. Each label is a **source**: a document id plus an RFC 6901 JSON Pointer, written `{document_id}#{pointer}`, for example `accounts-api#/paths/~1v1~1accounts~1{accountId}~1balances/get/security`. The document id is needed because pointers are only unique within one spec: `#/components/securitySchemes` exists in four of them. Pointers are stored in their plain RFC 6901 string form after the `#`, without the percent-encoding a URI fragment would need (so `{accountId}` stays readable).

**Which chunk covers a labelled source.** Each chunk's `source_reference` is the pointer of the element it was built from. Coverage uses whole path segments, never character prefixes:

1. **Ownership (longest prefix).** Every element of the spec is *owned* by the chunk whose `source_reference` is the longest prefix of the element's pointer. The `operation` chunk at `.../get` therefore owns `.../get/security`, `.../get/summary` and `.../get/deprecated`, because no chunk is more specific. It does not own `.../get/parameters`, because the `parameters` chunk is more specific.
2. A chunk is **relevant to a labelled source** if it owns that source, or if its `source_reference` is a descendant of the source. Labelling `accounts-api#/components/securitySchemes` makes every security-scheme chunk in that spec relevant; labelling `.../get/parameters` makes the `parameters` chunk (and any split parts of it) relevant, but not the `operation` chunk.

Worked example: the labelled source `accounts-api#/paths/~1v1~1accounts~1{accountId}~1balances/get/security` is owned by `accounts-api:getAccountBalances:operation`, so that chunk is relevant; `accounts-api:getAccountBalances:parameters` is not.

`relevant_document_ids` in a question record must equal the set of document ids used in its sources. `validate-dataset` checks this, and checks that every labelled source resolves to an element that exists in the corpus.

**Why.** Chunk ids change whenever chunking changes, while pointers into the spec stay stable. The same questions can therefore compare chunking strategies later, without relabelling.

## 4. Versioning

- The corpus has a semantic version and a SHA-256 checksum computed over the sorted files.
- The evaluation set has its own version.
- Both are recorded in every run's metadata.

## 5. Corpus statistics

Generated by `uv run rag-experiment validate-dataset` with `max_chunk_chars: 2400`.

| Item | Value |
|---|---|
| Documents | 5 |
| Operations | 20 |
| Chunks (total) | 186 |
| `operation` | 20 |
| `parameters` | 17 |
| `request_body` | 6 |
| `response` | 103 |
| `security_scheme` | 10 |
| `component_schema` | 30 |
| Longest chunk | 953 characters |
| Chunks split at the limit | 0 |
