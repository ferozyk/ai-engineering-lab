"""Python stubs advertised to the model in Code Mode, generated from ``TOOL_SPECS``."""

from datetime import date
from typing import Any, get_args

from mcp_vs_code_mode.tools.registry import TOOL_SPECS, ToolSpec


def _annotation_name(annotation: Any) -> str:
    if annotation is date:
        return "str"
    if annotation is str:
        return "str"
    # Annotated[...] metadata wrappers expose the base type as the first argument.
    args = get_args(annotation)
    if args:
        return _annotation_name(args[0])
    return str(getattr(annotation, "__name__", annotation))


def render_stub(spec: ToolSpec) -> str:
    """Render one tool as a Python function stub with a docstring."""
    fields = spec.input_model.model_fields
    params = ", ".join(f"{name}: {_annotation_name(f.annotation)}" for name, f in fields.items())
    returns = "dict" if spec.returns == "object" else "list[dict]"
    lines = [f"def {spec.name}({params}) -> {returns}:", f'    """{spec.description}', ""]
    lines.extend(f"    {name}: {f.description}" for name, f in fields.items())
    lines.append('    """')
    return "\n".join(lines)


def render_stubs() -> str:
    """Render every tool stub, separated by blank lines."""
    return "\n\n".join(render_stub(spec) for spec in TOOL_SPECS)


_RULES = """\
Sandbox rules:
- The value of the code's final expression is returned to you as JSON; printed output is returned too.
- Do the data processing inside the code and return only the values the answer needs.
- Supported: standard Python syntax, functions, loops, comprehensions, dict/list/set, and the modules json, math, datetime and collections.
- There is no file, network or environment access.
- If the code raises an error, you receive the error; fix the code and call run_python again."""  # noqa: E501

_INTRO = (
    "Call the run_python tool with Python code. The code runs in a sandbox where these "
    "functions are already defined (call them directly; do not import or redefine them):"
)


def code_mode_prompt_section() -> str:
    """The Code Mode part of the system prompt."""
    return f"{_INTRO}\n\n{render_stubs()}\n\n{_RULES}"
