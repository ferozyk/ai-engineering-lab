"""Unit tests for Code Mode stub generation."""

import ast

import pytest

from mcp_vs_code_mode.code_mode.stubs import code_mode_prompt_section, render_stub, render_stubs
from mcp_vs_code_mode.tools import TOOL_SPECS

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("spec", TOOL_SPECS, ids=lambda s: s.name)
def test_stub_matches_spec(spec) -> None:  # type: ignore[no-untyped-def]
    func = ast.parse(render_stub(spec)).body[0]
    assert isinstance(func, ast.FunctionDef)
    assert func.name == spec.name
    assert [a.arg for a in func.args.args] == list(spec.input_model.model_fields)
    assert all(
        isinstance(a.annotation, ast.Name) and a.annotation.id == "str" for a in func.args.args
    )
    docstring = ast.get_docstring(func)
    assert docstring is not None
    assert docstring.startswith(spec.description)
    for name, field in spec.input_model.model_fields.items():
        assert f"{name}: {field.description}" in docstring
    expected = "list[dict]" if spec.returns == "list" else "dict"
    assert ast.unparse(func.returns) == expected  # type: ignore[arg-type]


def test_one_stub_per_tool() -> None:
    assert render_stubs().count("def ") == len(TOOL_SPECS)


def test_prompt_section_contains_stubs_and_rules() -> None:
    section = code_mode_prompt_section()
    for spec in TOOL_SPECS:
        assert render_stub(spec) in section
    assert "Sandbox rules:" in section
    assert "the modules json, math, datetime and collections" in section
    assert "run_python" in section
