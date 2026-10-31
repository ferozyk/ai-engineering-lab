"""Smoke tests for package importability."""

import importlib

import pytest

import ai_lab

pytestmark = pytest.mark.unit


def test_version_is_non_empty_string() -> None:
    assert isinstance(ai_lab.__version__, str)
    assert ai_lab.__version__


@pytest.mark.parametrize(
    "module",
    [
        "ai_lab.config",
        "ai_lab.llm",
        "ai_lab.benchmarking",
        "ai_lab.evaluation",
        "ai_lab.utils",
    ],
)
def test_subpackages_import(module: str) -> None:
    assert importlib.import_module(module) is not None
