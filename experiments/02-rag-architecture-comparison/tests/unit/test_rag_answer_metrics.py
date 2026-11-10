"""Unit tests for the answer metrics, with literal cases."""

from collections.abc import Callable

import pytest

from rag_experiment.corpus import Corpus
from rag_experiment.evaluation.answer_metrics import (
    Identifier,
    citations_valid,
    cites_relevant,
    context_hit,
    context_vocabulary,
    corpus_vocabulary,
    determine_outcome,
    extract_identifiers,
    mentions_endpoint,
    required_key_facts,
    score_correctness,
    score_groundedness,
)
from rag_experiment.ingestion.chunker import Chunk

pytestmark = pytest.mark.unit

ChunkFactory = Callable[..., Chunk]
HEADERS = frozenset({"Authorization", "X-Api-Key", "Retry-After"})


def _ids(text: str) -> set[tuple[str, str]]:
    return {(i.kind, i.value) for i in extract_identifiers(text)}


# ------------------------------------------------------------------------------ outcome


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {
                "infra_error": True,
                "finish_reason": "length",
                "parse_error": "x",
                "insufficient_context": True,
            },
            "infra_error",
        ),
        (
            {
                "infra_error": False,
                "finish_reason": "length",
                "parse_error": "x",
                "insufficient_context": False,
            },
            "cut_off",
        ),
        (
            {
                "infra_error": False,
                "finish_reason": "stop",
                "parse_error": "x",
                "insufficient_context": False,
            },
            "invalid_answer",
        ),
        (
            {
                "infra_error": False,
                "finish_reason": None,
                "parse_error": "x",
                "insufficient_context": True,
            },
            "invalid_answer",
        ),
        (
            {
                "infra_error": False,
                "finish_reason": "stop",
                "parse_error": None,
                "insufficient_context": True,
            },
            "refused",
        ),
        (
            {
                "infra_error": False,
                "finish_reason": "stop",
                "parse_error": None,
                "insufficient_context": False,
            },
            "answered",
        ),
        (
            # a parseable answer wins over a "length" finish reason
            {
                "infra_error": False,
                "finish_reason": "length",
                "parse_error": None,
                "insufficient_context": False,
            },
            "answered",
        ),
    ],
)
def test_outcome_precedence(kwargs: dict[str, object], expected: str) -> None:
    assert determine_outcome(**kwargs) == expected  # type: ignore[arg-type]


# ------------------------------------------------------------------------------ correctness


def test_correct_when_all_key_facts_present() -> None:
    ok, missing = score_correctness(
        "answered",
        "Call GET /v1/accounts/{id}/balances with an authorization header and scope accounts:read.",
        ["GET /v1/accounts/{accountId}/balances", "Authorization", "accounts:read"],
        HEADERS,
    )
    assert ok and missing == []


def test_missing_key_facts_are_listed() -> None:
    ok, missing = score_correctness(
        "answered", "Send X-Api-Key.", ["Authorization", "X-Api-Key"], HEADERS
    )
    assert not ok and missing == ["Authorization"]


@pytest.mark.parametrize("outcome", ["refused", "invalid_answer", "cut_off"])
def test_non_answered_outcomes_are_incorrect(outcome: str) -> None:
    ok, missing = score_correctness(outcome, "Authorization", ["Authorization"], HEADERS)  # type: ignore[arg-type]
    assert not ok and missing == ["Authorization"]


# ------------------------------------------------------------------------------ identifiers


def test_endpoint_masks_parameters_and_strips_trailing_punctuation() -> None:
    found = _ids("Use `GET /v1/customers/{customerId}/accounts`. Then POST /oauth/token.")
    assert ("endpoint", "GET /v1/customers/{}/accounts") in found
    assert ("endpoint", "POST /oauth/token") in found
    assert not any(kind == "path" for kind, _ in found)


def test_endpoint_stops_at_markdown_and_query_string() -> None:
    found = _ids("**GET /v1/accounts/{accountId}/transactions?limit=5** and (PUT /v1/x),")
    assert ("endpoint", "GET /v1/accounts/{}/transactions") in found
    assert ("endpoint", "PUT /v1/x") in found


def test_bare_path_is_a_path_but_endpoint_paths_are_not_repeated() -> None:
    found = _ids("The path /v1/accounts/{accountId}/balances and POST /v1/payments")
    assert ("path", "/v1/accounts/{}/balances") in found
    assert ("endpoint", "POST /v1/payments") in found
    assert ("path", "/v1/payments") not in found
    assert ("path", "/oauth/token") in _ids("tokens come from /oauth/token:")


def test_error_codes_scopes_and_headers() -> None:
    found = _ids(
        "RATE-001 and AUTH-001 (not rate-001 or A-1). Scopes accounts:read, customers:write; "
        "headers X-Api-Key, Retry-After, authorization, Idempotency-Key, Location."
    )
    assert ("error_code", "RATE-001") in found and ("error_code", "AUTH-001") in found
    assert not any(
        v.lower() == "rate-001" and k == "error_code" and v != "RATE-001" for k, v in found
    )
    assert ("scope", "accounts:read") in found and ("scope", "customers:write") in found
    # headers are matched as written and compared lower-case; prose "authorization" is no header
    assert ("header", "x-api-key") in found and ("header", "retry-after") in found
    assert ("header", "idempotency-key") in found and ("header", "location") in found
    assert ("header", "authorization") not in found
    assert ("header", "authorization") in _ids("Send Authorization: Bearer abc")


def test_names_from_backticks_and_camel_case() -> None:
    found = _ids("The `fromDate` field, `limit`, `a-b`, `two words` and updateContactDetails.")
    assert ("name", "fromDate") in found and ("name", "limit") in found
    assert ("name", "updateContactDetails") in found
    assert not any(v in {"a-b", "two words"} for _, v in found)
    assert ("name", "toDate") in _ids("the toDate parameter")
    assert ("name", "limit") not in _ids("the limit parameter, unquoted lower-case words")


# ------------------------------------------------------------------------------ vocabularies


@pytest.fixture
def vocab_chunks(make_chunk: ChunkFactory) -> list[Chunk]:
    return [
        make_chunk(
            "c1",
            "GET /v1/accounts/{accountId}/balances needs scope accounts:read. Send Authorization "
            "Bearer token. Fields: availableBalance, currency. Error AUTH-001.",
        ),
        make_chunk(
            "c2", "POST /v1/payments with Idempotency-Key. Error PAY-002. Bearer is a word."
        ),
    ]


def test_vocabularies_context_versus_corpus(vocab_chunks: list[Chunk]) -> None:
    corpus = corpus_vocabulary(vocab_chunks)
    context = context_vocabulary(vocab_chunks[:1])
    assert corpus.contains(Identifier("endpoint", "POST /v1/payments"))
    assert not context.contains(Identifier("endpoint", "POST /v1/payments"))
    # an endpoint also makes its bare path known
    assert corpus.contains(Identifier("path", "/v1/payments"))
    # names count when the word appears anywhere in the text, backticked or not
    assert context.contains(Identifier("name", "availableBalance"))
    assert context.contains(Identifier("name", "Bearer"))
    assert not context.contains(Identifier("name", "overdraftLimit"))
    assert not corpus.contains(Identifier("error_code", "AUTH-999"))


def test_groundedness_lists_unsupported_and_invented(vocab_chunks: list[Chunk]) -> None:
    corpus = corpus_vocabulary(vocab_chunks)
    context = context_vocabulary(vocab_chunks[:1])
    answer = (
        "Call GET /v1/accounts/{id}/balances, then POST /v1/payments (PAY-002) and "
        "DELETE /v1/accounts/{id} with `getFoo` and scope accounts:read."
    )
    result = score_groundedness(answer, "How do I get balances?", context, corpus)
    assert result.unsupported == (
        "endpoint:DELETE /v1/accounts/{}",
        "endpoint:POST /v1/payments",
        "error_code:PAY-002",
        "name:getFoo",
    )
    assert result.invented == ("endpoint:DELETE /v1/accounts/{}", "name:getFoo")


def test_identifiers_in_the_question_are_never_flagged(vocab_chunks: list[Chunk]) -> None:
    corpus = corpus_vocabulary(vocab_chunks)
    context = context_vocabulary(vocab_chunks[:1])
    question = "Does DELETE /v1/accounts/{accountId} exist, and what is `closeAccount` or ZZZ-404?"
    answer = "There is no DELETE /v1/accounts/{id}, no closeAccount and no ZZZ-404."
    result = score_groundedness(answer, question, context, corpus)
    assert result.unsupported == () and result.invented == ()


def test_corpus_vocabulary_includes_spec_names(corpus: Corpus, chunks: list[Chunk]) -> None:
    vocab = corpus_vocabulary(chunks, corpus.specs)
    assert vocab.contains(Identifier("name", "listCustomerAccounts"))
    assert vocab.contains(Identifier("endpoint", "GET /v1/customers/{}/accounts"))
    assert not vocab.contains(Identifier("name", "closeCustomerAccount"))


# ------------------------------------------------------------------------------ misc


def test_mentions_endpoint_is_a_diagnostic() -> None:
    assert mentions_endpoint("Try POST /v1/accounts/close")
    assert not mentions_endpoint("No such endpoint exists; see /v1/accounts")


def test_citation_checks() -> None:
    assert citations_valid(["a", "b"], ["a", "b", "c"])
    assert not citations_valid(["a", "z"], ["a", "b"])
    assert citations_valid([], ["a"])
    assert cites_relevant(["z", "b"], ["b"])
    assert not cites_relevant(["z"], ["b"])
    assert not cites_relevant([], ["b"])


def test_context_hit_uses_only_the_top_k() -> None:
    ranked = ["a", "b", "c", "d", "e", "f"]
    assert context_hit(ranked, {"e"}, 5)
    assert not context_hit(ranked, {"f"}, 5)
    assert not context_hit(ranked, set(), 5)


def test_key_facts_already_in_the_question_are_not_required() -> None:
    question = "What is the maximum value of `pageSize` in `searchCustomers`?"
    ok, missing = score_correctness(
        "answered", "The maximum is 100.", ["pageSize", "100"], HEADERS, question
    )
    assert ok and missing == []
    ok, missing = score_correctness(
        "answered", "pageSize can be large.", ["pageSize", "100"], HEADERS, question
    )
    assert not ok and missing == ["100"]


def test_all_key_facts_stay_required_when_all_appear_in_the_question() -> None:
    question = "Is `X-Api-Key` required?"
    assert required_key_facts(["X-Api-Key"], question, HEADERS) == ["X-Api-Key"]
