"""Unit tests for the JSON Pointer helpers."""

import pytest

from rag_experiment.ingestion.pointers import (
    PointerError,
    Source,
    escape_segment,
    is_prefix,
    parse_source,
    pointer,
    resolve_pointer,
    split_pointer,
)

pytestmark = pytest.mark.unit


def test_escape_round_trip() -> None:
    raw = "/v1/a~b/{id}"
    assert escape_segment(raw) == "~1v1~1a~0b~1{id}"
    assert split_pointer(pointer("paths", raw)) == ("paths", raw)


def test_pointer_without_segments_is_hash() -> None:
    assert pointer() == "#"
    assert split_pointer("#") == ()


def test_pointer_keeps_braces_literal() -> None:
    assert pointer("paths", "/v1/x/{id}", "get") == "#/paths/~1v1~1x~1{id}/get"


def test_split_requires_prefix() -> None:
    with pytest.raises(ValueError):
        split_pointer("/paths/x")


def test_unescape_order() -> None:
    # "~01" must decode to "~1", not "/".
    assert split_pointer("#/~01") == ("~1",)


def test_resolve_pointer_mapping_and_list() -> None:
    doc = {"a": {"b": [{"c": 1}, {"c": 2}]}, "x/y": 5}
    assert resolve_pointer(doc, "#/a/b/1/c") == 2
    assert resolve_pointer(doc, "#/x~1y") == 5
    assert resolve_pointer(doc, "#") is doc


@pytest.mark.parametrize("bad", ["#/a/zzz", "#/a/b/7", "#/a/b/x", "#/a/b/0/c/d"])
def test_resolve_pointer_errors(bad: str) -> None:
    doc = {"a": {"b": [{"c": 1}]}}
    with pytest.raises(PointerError):
        resolve_pointer(doc, bad)


def test_is_prefix_uses_whole_segments() -> None:
    assert is_prefix("#/paths/~1v1~1accounts", "#/paths/~1v1~1accounts/get")
    assert is_prefix("#/a", "#/a")
    assert not is_prefix("#/paths/~1v1~1accounts", "#/paths/~1v1~1accounts-x/get")
    assert not is_prefix("#/a/b", "#/a")


def test_parse_source_round_trip() -> None:
    text = "accounts-api#/paths/~1v1~1accounts~1{accountId}/get/security"
    source = parse_source(text)
    assert source == Source("accounts-api", "#/paths/~1v1~1accounts~1{accountId}/get/security")
    assert str(source) == text


@pytest.mark.parametrize("bad", ["no-hash", "#/only/pointer", "doc#nopath", ""])
def test_parse_source_rejects_bad_format(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_source(bad)
