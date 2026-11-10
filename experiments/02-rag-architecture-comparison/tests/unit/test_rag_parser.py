"""Unit tests for the OpenAPI parser."""

import logging
from pathlib import Path

import pytest

from rag_experiment.ingestion.parser import (
    EmptySpecError,
    InvalidSpecError,
    SpecError,
    UnsupportedSpecError,
    parse_spec,
    schema_summary,
)

pytestmark = pytest.mark.unit


def _write(tmp_path: Path, text: str, name: str = "t.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


MINIMAL = """\
openapi: 3.1.0
info: {title: T, version: "1"}
paths:
  /a:
    get:
      responses:
        "200": {description: ok}
"""


def test_parse_tiny_spec(tiny_spec_path: Path) -> None:
    spec = parse_spec(tiny_spec_path)
    assert spec.document_id == "tiny"
    assert spec.title == "Tiny API"
    assert spec.version == "2.0.0"
    assert [(o.method, o.operation_id) for o in spec.operations] == [
        ("GET", "getThing"),
        ("PUT", "replaceThing"),
    ]
    get = spec.operations[0]
    assert get.pointer == "#/paths/~1v1~1things~1{thingId}/get"
    # Responses are ordered by status string.
    assert [r.status for r in get.responses] == ["200", "404"]
    assert get.responses[0].headers[0].name == "X-Trace"
    assert len(spec.raw_checksum) == 64


@pytest.mark.parametrize("text", ["", "   \n\n"])
def test_empty_file(tmp_path: Path, text: str) -> None:
    with pytest.raises(EmptySpecError, match=r"t\.yaml"):
        parse_spec(_write(tmp_path, text))


def test_invalid_yaml_and_non_mapping(tmp_path: Path) -> None:
    with pytest.raises(InvalidSpecError, match="mapping"):
        parse_spec(_write(tmp_path, "- a\n- b\n"))
    with pytest.raises(InvalidSpecError, match="not valid YAML"):
        parse_spec(_write(tmp_path, "a: [unclosed\n"))


def test_swagger_two_is_unsupported(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedSpecError, match="Swagger"):
        parse_spec(_write(tmp_path, 'swagger: "2.0"\ninfo: {title: T}\npaths: {}\n'))


def test_old_openapi_version_is_unsupported(tmp_path: Path) -> None:
    text = "openapi: 2.x\ninfo: {title: T}\npaths: {}\n"
    with pytest.raises(UnsupportedSpecError, match=r"2\.x"):
        parse_spec(_write(tmp_path, text))


def test_missing_paths_title_or_version(tmp_path: Path) -> None:
    with pytest.raises(InvalidSpecError, match="paths"):
        parse_spec(_write(tmp_path, "openapi: 3.1.0\ninfo: {title: T}\n"))
    with pytest.raises(InvalidSpecError, match=r"info\.title"):
        parse_spec(_write(tmp_path, "openapi: 3.1.0\ninfo: {}\npaths: {}\n"))
    with pytest.raises(InvalidSpecError, match="openapi"):
        parse_spec(_write(tmp_path, "info: {title: T}\npaths: {}\n"))
    with pytest.raises(InvalidSpecError, match="'paths' must be a mapping"):
        parse_spec(_write(tmp_path, "openapi: 3.1.0\ninfo: {title: T}\npaths: [1]\n"))


def test_operation_must_be_a_mapping(tmp_path: Path) -> None:
    text = "openapi: 3.1.0\ninfo: {title: T}\npaths:\n  /a:\n    get: nope\n"
    with pytest.raises(InvalidSpecError, match="GET /a"):
        parse_spec(_write(tmp_path, text))


def test_external_ref_is_unsupported(tmp_path: Path) -> None:
    text = MINIMAL + "components:\n  schemas:\n    X:\n      $ref: other.yaml#/Y\n"
    with pytest.raises(UnsupportedSpecError, match="non-local"):
        parse_spec(_write(tmp_path, text))


def test_unresolvable_ref(tmp_path: Path) -> None:
    text = MINIMAL.replace(
        "{description: ok}", '{description: ok, content: {a/b: {schema: {$ref: "#/components/x"}}}}'
    )
    with pytest.raises(InvalidSpecError, match="does not resolve"):
        parse_spec(_write(tmp_path, text))


def test_errors_are_spec_errors_and_carry_the_path(tmp_path: Path) -> None:
    path = _write(tmp_path, "")
    with pytest.raises(SpecError) as info:
        parse_spec(path)
    assert str(path) in str(info.value)


def test_missing_operation_id_falls_back_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        spec = parse_spec(_write(tmp_path, MINIMAL))
    assert spec.operations[0].operation_id == "get_a"
    assert "no operationId" in caplog.text


def test_missing_descriptions_are_none(tmp_path: Path) -> None:
    op = parse_spec(_write(tmp_path, MINIMAL)).operations[0]
    assert op.summary is None
    assert op.description is None
    assert op.tags == ()


def test_path_and_operation_parameters_merge(tiny_spec_path: Path, tmp_path: Path) -> None:
    spec = parse_spec(tiny_spec_path)
    params = {p.name: p for p in spec.operations[0].parameters}
    assert set(params) == {"thingId", "verbose"}
    assert params["thingId"].required  # path parameters are always required
    assert params["verbose"].schema_summary == "boolean, default false"
    assert params["verbose"].pointer == spec.operations[0].pointer + "/parameters"

    override = tiny_spec_path.read_text().replace(
        "      parameters:\n        - name: verbose",
        "      parameters:\n"
        "        - name: thingId\n          in: path\n          description: Operation level.\n"
        "          schema:\n            type: integer\n"
        "        - name: verbose",
    )
    path = tmp_path / "over.yaml"
    path.write_text(override, encoding="utf-8")
    merged = {p.name: p for p in parse_spec(path).operations[0].parameters}
    assert merged["thingId"].description == "Operation level."
    assert merged["thingId"].schema_summary == "integer"


def test_root_security_fallback_and_explicit_override(tmp_path: Path) -> None:
    text = (
        "openapi: 3.1.0\ninfo: {title: T}\n"
        "security:\n  - bearerAuth: [s:read]\n"
        "paths:\n  /a:\n    get:\n      operationId: a\n      responses: {}\n"
        "  /b:\n    get:\n      operationId: b\n      security: []\n      responses: {}\n"
    )
    ops = {o.operation_id: o for o in parse_spec(_write(tmp_path, text)).operations}
    assert ops["a"].security == ((("bearerAuth", ("s:read",)),),)
    assert ops["b"].security == ()


def test_nullable_type_summary() -> None:
    assert schema_summary({"type": ["string", "null"], "maxLength": 20}) == (
        "string, max length 20, nullable"
    )


def test_schema_summary_order_and_values() -> None:
    summary = schema_summary(
        {"type": "integer", "format": "int32", "default": 100, "minimum": 1, "maximum": 500}
    )
    assert summary == "integer, format int32, default 100, min 1, max 500"
    assert schema_summary({"type": "string", "enum": ["A", "B"], "minLength": 1}) == (
        "string, enum A|B, min length 1"
    )
    assert schema_summary({"$ref": "#/components/schemas/Amount"}) == "Amount"
    assert schema_summary({"type": "array", "items": {"$ref": "#/components/schemas/Amount"}}) == (
        "array of Amount"
    )
    assert schema_summary({"type": "boolean", "default": False}) == "boolean, default false"


def test_refs_are_resolved_one_level(tiny_spec_path: Path) -> None:
    spec = parse_spec(tiny_spec_path)
    response = spec.operations[0].responses[0]
    view = response.contents[0].schema_view
    assert view is not None
    assert view.name == "Thing"
    assert view.summary == "Thing"
    fields = {f.name: f for f in view.fields}
    # A field that is a $ref keeps the reference name instead of being expanded.
    assert fields["owner"].summary == "Owner"
    assert fields["owners"].summary == "array of Owner"
    assert fields["labels"].summary == "array of string"
    assert fields["nickname"].summary == "string, max length 20, nullable"
    assert fields["id"].required
    assert not fields["nickname"].required
    components = {c.name: c for c in spec.component_schemas}
    assert components["Thing"].view.summary == "object"
    assert components["Thing"].pointer == "#/components/schemas/Thing"


def test_ref_cycle_is_rejected(tmp_path: Path) -> None:
    text = MINIMAL + (
        "components:\n  schemas:\n"
        '    A:\n      $ref: "#/components/schemas/B"\n'
        '    B:\n      $ref: "#/components/schemas/A"\n'
    )
    with pytest.raises(InvalidSpecError, match="cycle"):
        parse_spec(_write(tmp_path, text))
