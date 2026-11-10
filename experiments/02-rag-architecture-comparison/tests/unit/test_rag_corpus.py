"""Unit tests for the real corpus: golden checksum and lint rules."""

import hashlib
import re
from pathlib import Path

import pytest

from rag_experiment.config import ExperimentConfig
from rag_experiment.corpus import Corpus, corpus_checksum, load_manifest

pytestmark = pytest.mark.unit

EXPECTED_OPERATIONS = {
    "auth-api": {"issueAccessToken", "revokeToken", "introspectToken"},
    "customers-api": {
        "getCustomer",
        "searchCustomers",
        "listCustomerAccounts",
        "updateContactDetails",
        "listConsents",
    },
    "accounts-api": {
        "getAccount",
        "getAccountV2",
        "getAccountBalances",
        "listTransactions",
        "getTransaction",
    },
    "statements-api": {
        "listStatements",
        "getStatement",
        "requestStatement",
        "getStatementRequestStatus",
    },
    "payments-api": {"initiatePayment", "getPayment", "cancelPayment"},
}
FORBIDDEN_TEXT = [r"per\s+(minute|second|hour)", r"rate limit of"]
FORBIDDEN_IN_IDS = re.compile(r"close|closure|delete|terminate|webhook|subscription|export", re.I)


def test_manifest_checksum_matches_the_corpus(experiment_config: ExperimentConfig) -> None:
    manifest = load_manifest(experiment_config.manifest_path)
    assert corpus_checksum(experiment_config.corpus_dir) == manifest.corpus_checksum


def test_frozen_measured_questions_match_the_manifest(experiment_config: ExperimentConfig) -> None:
    """Once frozen, the measured question set must not change without a new version."""
    manifest = load_manifest(experiment_config.manifest_path)
    assert manifest.eval_measured_status == "frozen"
    data = experiment_config.questions_measured.read_bytes()
    assert hashlib.sha256(data).hexdigest() == manifest.eval_measured_checksum


def test_corpus_version_comes_from_the_manifest(corpus: Corpus) -> None:
    assert corpus.version == "1.0.0"
    assert len(corpus.checksum) == 64


def test_checksum_changes_with_content(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("a: 1\n", encoding="utf-8")
    before = corpus_checksum(tmp_path)
    (tmp_path / "a.yaml").write_text("a: 2\n", encoding="utf-8")
    assert corpus_checksum(tmp_path) != before


def test_operations_match_the_design(corpus: Corpus) -> None:
    found = {spec.document_id: {op.operation_id for op in spec.operations} for spec in corpus.specs}
    assert found == EXPECTED_OPERATIONS
    assert sum(len(spec.operations) for spec in corpus.specs) == 20


def test_every_operation_is_fully_described(corpus: Corpus) -> None:
    for spec in corpus.specs:
        assert spec.openapi_version == "3.1.0"
        assert spec.version == "1.0.0"
        assert spec.title.startswith("Lab Bank ")
        assert spec.description is not None
        assert "synthetic" in spec.description
        for op in spec.operations:
            assert op.summary
            assert op.description
            assert op.tags
            assert op.security, f"{op.operation_id} has no operation-level security"
            assert any(r.status == "200" or r.status.startswith("2") for r in op.responses)
            assert "429" in {r.status for r in op.responses}


def test_security_matches_the_conventions(corpus: Corpus) -> None:
    for spec in corpus.specs:
        for op in spec.operations:
            names = {name for alternative in op.security for name, _ in alternative}
            if spec.document_id == "auth-api":
                assert names == {"clientBasic"}
            else:
                assert names == {"bearerAuth", "apiKey"}
                assert len(op.security) == 1  # both are required together
                assert "403" in {r.status for r in op.responses}
                assert "401" in {r.status for r in op.responses}


def test_every_ref_resolves_locally(experiment_config: ExperimentConfig, corpus: Corpus) -> None:
    from rag_experiment.ingestion.pointers import resolve_pointer

    def walk(node: object, document_id: str) -> int:
        count = 0
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref" and isinstance(value, str):
                    assert value.startswith("#/"), value
                    resolve_pointer(corpus.documents[document_id], value)
                    count += 1
                else:
                    count += walk(value, document_id)
        elif isinstance(node, list):
            count += sum(walk(item, document_id) for item in node)
        return count

    total = sum(walk(doc, doc_id) for doc_id, doc in corpus.documents.items())
    assert total > 100


def test_forbidden_content_is_absent(experiment_config: ExperimentConfig, corpus: Corpus) -> None:
    for path in sorted(experiment_config.corpus_dir.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_TEXT:
            assert not re.search(pattern, text, re.I), f"{path.name}: {pattern}"
    for spec in corpus.specs:
        for op in spec.operations:
            assert not FORBIDDEN_IN_IDS.search(op.operation_id), op.operation_id
            assert not FORBIDDEN_IN_IDS.search(op.path), op.path


def test_problem_codes_are_named_in_response_descriptions(corpus: Corpus) -> None:
    expected = {"400": "VAL-001", "401": "AUTH-001", "403": "AUTH-002", "429": "RATE-001"}
    for spec in corpus.specs:
        for op in spec.operations:
            for response in op.responses:
                code = expected.get(response.status)
                if code and response.description and spec.document_id != "auth-api":
                    if response.status == "400" and "AUTH-003" in response.description:
                        continue
                    assert code in response.description, (op.operation_id, response.status)
