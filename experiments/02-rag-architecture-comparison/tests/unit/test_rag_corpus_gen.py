"""The large corpus generator: determinism, size gates, change log and identifier catalogue."""

import json
from collections import Counter
from pathlib import Path

import pytest

from rag_experiment.config import ExperimentConfig
from rag_experiment.corpus import corpus_checksum, load_manifest
from rag_experiment.corpus_gen import (
    CHANGES_FILE,
    IDENTIFIERS_FILE,
    GateError,
    GeneratedCorpus,
    check_generated,
    differences,
    generate,
    write_files,
)
from rag_experiment.corpus_gen.build import v3_products
from rag_experiment.corpus_gen.vocab import PRODUCTS
from rag_experiment.ingestion.pointers import resolve_pointer

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def generated(experiment_config: ExperimentConfig) -> GeneratedCorpus:
    return generate(experiment_config.corpora["clean"])


@pytest.fixture(scope="module")
def originals(experiment_config: ExperimentConfig) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in experiment_config.corpora["clean"].glob("*.yaml")}


def test_generation_is_byte_identical_across_runs(
    experiment_config: ExperimentConfig, generated: GeneratedCorpus
) -> None:
    again = generate(experiment_config.corpora["clean"])
    assert again.files == generated.files
    assert all(b"\r" not in data for data in again.files.values())


def test_committed_corpus_matches_the_generator(
    experiment_config: ExperimentConfig, generated: GeneratedCorpus
) -> None:
    assert differences(experiment_config.corpora["large"], generated.files) == []


def test_manifest_records_the_large_corpus(experiment_config: ExperimentConfig) -> None:
    manifest = load_manifest(experiment_config.manifest_path)
    assert manifest.corpora is not None
    assert manifest.corpora["large"].version == "1.0.0"
    assert manifest.corpora["large"].checksum == corpus_checksum(experiment_config.corpora["large"])
    assert manifest.corpora["clean"].checksum == manifest.corpus_checksum
    assert manifest.stress is not None and manifest.stress.status == "draft"
    assert manifest.stress.checksum is None


def test_size_and_shape_gates_hold(
    experiment_config: ExperimentConfig,
    generated: GeneratedCorpus,
    originals: dict[str, bytes],
) -> None:
    report = check_generated(generated.files, originals, experiment_config.chunking)
    assert 1800 <= report.chunks <= 2400
    assert report.max_chunk_chars <= experiment_config.chunking.max_chunk_chars
    assert report.split_chunks == 0
    assert report.documents == len(originals) + 2 * len(PRODUCTS) + len(v3_products())
    assert sum(report.by_type.values()) == report.chunks == sum(report.by_document.values())


def test_the_five_original_specs_are_copied_verbatim(
    generated: GeneratedCorpus, originals: dict[str, bytes]
) -> None:
    assert len(originals) == 5
    for name, data in originals.items():
        assert generated.files[name] == data


def test_twenty_products_two_or_three_versions(generated: GeneratedCorpus) -> None:
    names = {n for n in generated.files if n.endswith(".yaml")}
    assert len(PRODUCTS) == 20
    with_v3 = v3_products()
    assert len(with_v3) == 8
    for product in PRODUCTS:
        assert f"{product.key}-api-v1.yaml" in names
        assert f"{product.key}-api-v2.yaml" in names
        assert (f"{product.key}-api-v3.yaml" in names) == (product.key in with_v3)
    assert not any("-api-v4" in n for n in names)


def test_every_version_step_records_two_to_four_differences(generated: GeneratedCorpus) -> None:
    steps = Counter((c["product"], c["from_version"], c["to_version"]) for c in generated.changes)
    expected = {(p.key, "v1", "v2") for p in PRODUCTS} | {
        (key, "v2", "v3") for key in v3_products()
    }
    assert set(steps) == expected
    assert all(2 <= n <= 4 for n in steps.values())
    kinds = {c["kind"] for c in generated.changes}
    assert {"field_renamed", "page_size_max_changed", "param_required", "operation_added"} <= kinds
    assert {
        "error_meaning_changed",
        "error_status_changed",
        "scope_renamed",
        "scope_split",
    } <= kinds
    assert "operation_deprecated" in kinds


def test_change_locations_resolve_in_the_newer_spec(
    experiment_config: ExperimentConfig, generated: GeneratedCorpus
) -> None:
    import yaml

    for change in generated.changes:
        doc = yaml.safe_load(generated.files[f"{change['document']}.yaml"])
        assert change["document"] == f"{change['product']}-api-{change['to_version']}"
        node = resolve_pointer(doc, change["location"])
        kind = change["kind"]
        if kind in ("page_size_max_changed", "amount_max_changed"):
            assert node == change["after"] and change["after"] == 2 * change["before"]
        elif kind == "param_required":
            assert node is True
        elif kind == "operation_deprecated":
            assert node is True and str(change["after"]).startswith("deprecated, use ")
        elif kind.startswith("error_"):
            assert isinstance(node, dict) and f"`{change['subject']}`" in node["description"]
        elif kind in ("scope_renamed", "scope_split"):
            assert isinstance(node, str) and change["after"] == change["subject"]


def test_deprecation_names_the_replacement(generated: GeneratedCorpus) -> None:
    import yaml

    deprecations = [c for c in generated.changes if c["kind"] == "operation_deprecated"]
    assert len(deprecations) == len(v3_products())
    for change in deprecations:
        doc = yaml.safe_load(generated.files[f"{change['document']}.yaml"])
        parent = resolve_pointer(doc, change["location"].rsplit("/", 1)[0])
        assert isinstance(parent, dict)
        replacement = str(change["after"]).removeprefix("deprecated, use ")
        assert replacement in parent["description"]


def test_error_code_families_and_catalogue(generated: GeneratedCorpus) -> None:
    import yaml

    per_product_version: Counter[tuple[str, str]] = Counter()
    for record in generated.identifiers:
        per_product_version[(record["product"], record["version"])] += 1
        doc = yaml.safe_load(generated.files[f"{record['document']}.yaml"])
        response = resolve_pointer(doc, record["location"])
        assert isinstance(response, dict) and f"`{record['code']}`" in response["description"]
        assert record["code"].startswith("ERR-")
    assert all(8 <= n <= 14 for n in per_product_version.values())
    # Near-identical wording: every product has several codes that differ in one detail.
    clauses = {r["meaning"] for r in generated.identifiers if r["product"] == "cards"}
    assert any("is frozen" in c for c in clauses) and any("is blocked" in c for c in clauses)


def test_every_spec_has_the_duplicated_security_schemes(generated: GeneratedCorpus) -> None:
    import yaml

    for product in PRODUCTS:
        doc = yaml.safe_load(generated.files[f"{product.key}-api-v1.yaml"])
        schemes = doc["components"]["securitySchemes"]
        assert set(schemes) == {"bearerAuth", "apiKey"}
        scopes = schemes["bearerAuth"]["flows"]["clientCredentials"]["scopes"]
        assert {f"{product.key}:read", f"{product.key}:write"} <= set(scopes)


def test_json_files_are_sorted_and_end_with_a_newline(generated: GeneratedCorpus) -> None:
    for name in (CHANGES_FILE, IDENTIFIERS_FILE):
        text = generated.files[name].decode("utf-8")
        assert text.endswith("]\n")
        assert json.loads(text)


def test_write_files_replaces_stale_files(tmp_path: Path) -> None:
    (tmp_path / "old.yaml").write_text("x: 1\n", encoding="utf-8")
    files = {"a.yaml": b"a: 1\n", CHANGES_FILE: b"[]\n"}
    write_files(tmp_path, files)
    assert not (tmp_path / "old.yaml").exists()
    assert differences(tmp_path, files) == []
    (tmp_path / "a.yaml").write_bytes(b"a: 2\n")
    (tmp_path / "extra.json").write_text("[]", encoding="utf-8")
    assert differences(tmp_path, files) == ["unexpected: extra.json", "differs: a.yaml"]
    assert differences(tmp_path, {**files, "b.yaml": b""}) == [
        "missing: b.yaml",
        "unexpected: extra.json",
        "differs: a.yaml",
    ]


def test_gates_reject_bad_specs(
    experiment_config: ExperimentConfig,
    generated: GeneratedCorpus,
    originals: dict[str, bytes],
) -> None:
    chunking = experiment_config.chunking
    broken = dict(generated.files)
    name = "cards-api-v1.yaml"
    broken[name] = broken[name].replace(b"Operations on cards.", b"Operations on cards")
    with pytest.raises(GateError, match="does not end with a full stop"):
        check_generated(broken, originals, chunking)

    no_disclaimer = dict(generated.files)
    no_disclaimer[name] = no_disclaimer[name].replace(b"Nothing in it", b"Something in it")
    with pytest.raises(GateError, match="synthetic-data sentence"):
        check_generated(no_disclaimer, originals, chunking)

    altered = dict(generated.files)
    first = sorted(originals)[0]
    altered[first] = originals[first] + b"# edit\n"
    with pytest.raises(GateError, match="byte-identical"):
        check_generated(altered, originals, chunking)

    with pytest.raises(GateError, match="outside"):
        check_generated(
            {k: v for k, v in generated.files.items() if k in originals}, originals, chunking
        )


def test_no_placeholder_wording_in_generated_text(generated: GeneratedCorpus) -> None:
    for name, data in generated.files.items():
        if name.endswith(".yaml") and name not in {"accounts-api.yaml"}:
            text = data.decode("utf-8").lower()
            assert "lorem" not in text and "todo" not in text
