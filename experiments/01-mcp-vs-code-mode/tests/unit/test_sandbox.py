"""Unit tests for CodeSandbox using the real Monty runtime."""

from collections.abc import Iterator

import pytest

from mcp_vs_code_mode.banking import AuditLog, BankingService, Dataset, benchmark_principal
from mcp_vs_code_mode.code_mode import CodeSandbox, SandboxLimits
from mcp_vs_code_mode.tools import ToolExecutor, compact_json

pytestmark = pytest.mark.unit

_LIMITS = SandboxLimits(max_duration_secs=1.0, max_memory_bytes=64 * 1024 * 1024, max_host_calls=50)


@pytest.fixture(scope="module")
def module_dataset() -> Dataset:
    from mcp_vs_code_mode.banking import generate_dataset

    return generate_dataset()


@pytest.fixture(scope="module")
def module_audit() -> AuditLog:
    return AuditLog()


@pytest.fixture(scope="module")
def module_executor(module_dataset: Dataset, module_audit: AuditLog) -> ToolExecutor:
    service = BankingService(module_dataset, module_audit)
    return ToolExecutor(service, benchmark_principal(), "code_mode")


@pytest.fixture(scope="module")
def sandbox(module_executor: ToolExecutor) -> Iterator[CodeSandbox]:
    with CodeSandbox(module_executor, _LIMITS) as box:
        yield box


_SUPPORTED_SNIPPETS = {
    "syntax": "x = 3\nif x > 2:\n    y = 'big'\nelse:\n    y = 'small'\ny",
    "function": "def f(a, b=2):\n    return a * b\nf(21)",
    "loop": "t = 0\nfor i in range(5):\n    t += i\nt",
    "while": "n = 0\nwhile n < 3:\n    n += 1\nn",
    "list_comprehension": "[x * x for x in range(4)]",
    "dict_comprehension": "{k: len(k) for k in ['a', 'bb']}",
    "set": "sorted({1, 2, 2, 3})",
    "dict": "d = {'a': 1}\nd['b'] = 2\nd",
    "list": "xs = [3, 1, 2]\nxs.append(0)\nsorted(xs)",
    "generator": "sum(x for x in [1, 2, 3])",
    "fstring": "name = 'bank'\nf'{name}-{1 + 1}'",
    "lambda_sorted": "sorted([{'a': 2}, {'a': 1}], key=lambda d: d['a'])",
    "round_abs": "round(abs(-1.2345), 2)",
    "json": "import json\njson.dumps({'a': 1})",
    "math": "import math\nmath.floor(2.7)",
    "datetime": "import datetime\nstr(datetime.date(2026, 1, 2))",
    "collections": (
        "from collections import defaultdict\nd = defaultdict(float)\nd['a'] += 1\ndict(d)"
    ),
}


@pytest.mark.parametrize("code", _SUPPORTED_SNIPPETS.values(), ids=_SUPPORTED_SNIPPETS.keys())
def test_advertised_features_run(sandbox: CodeSandbox, code: str) -> None:
    result = sandbox.run(code)
    assert result.error_type is None, result.error_message
    assert result.value is not None


def test_all_tools_match_executor(sandbox: CodeSandbox, module_executor: ToolExecutor) -> None:
    code = """\
a = get_customer("CUST-0050")
b = list_accounts(customer_id="CUST-0050")
c = get_balance("ACC-0050-1")
d = get_transactions("ACC-0050-1", start_date="2026-07-03", end_date="2026-10-01")
[a, b, c, d]
"""
    result = sandbox.run(code)
    assert result.error_type is None, result.error_message
    expected = [
        module_executor.execute("get_customer", {"customer_id": "CUST-0050"}),
        module_executor.execute("list_accounts", {"customer_id": "CUST-0050"}),
        module_executor.execute("get_balance", {"account_id": "ACC-0050-1"}),
        module_executor.execute(
            "get_transactions",
            {"account_id": "ACC-0050-1", "start_date": "2026-07-03", "end_date": "2026-10-01"},
        ),
    ]
    assert compact_json(result.value) == compact_json(expected)
    assert result.host_calls == 4


def test_audit_channel_is_code_mode(sandbox: CodeSandbox, module_audit: AuditLog) -> None:
    sandbox.run('get_balance("ACC-0050-1")')
    assert module_audit.records
    assert {r.channel for r in module_audit.records} == {"code_mode"}


def test_access_denied_is_catchable_permission_error(sandbox: CodeSandbox) -> None:
    code = """\
try:
    get_balance("ACC-9999-1")
    r = "no error"
except PermissionError as e:
    r = "denied"
r
"""
    result = sandbox.run(code)
    assert result.error_type is None, result.error_message
    assert result.value == "denied"


def test_uncaught_access_denied_is_runtime_error(sandbox: CodeSandbox) -> None:
    result = sandbox.run('get_balance("ACC-9999-1")')
    assert result.error_type == "runtime_error"
    assert result.error_message is not None
    assert "PermissionError" in result.error_message


def test_not_found_and_invalid_input_exceptions(sandbox: CodeSandbox) -> None:
    code = """\
out = []
for call in [lambda: get_balance("ACC-0050-9"), lambda: get_balance("bad")]:
    try:
        call()
    except LookupError:
        out.append("lookup")
    except ValueError:
        out.append("value")
out
"""
    result = sandbox.run(code)
    assert result.error_type is None, result.error_message
    assert result.value == ["lookup", "value"]


def test_too_many_positional_args(sandbox: CodeSandbox) -> None:
    result = sandbox.run('get_balance("ACC-0050-1", "extra")')
    assert result.error_type == "runtime_error"
    assert "TypeError" in (result.error_message or "")


def test_infinite_loop_times_out(sandbox: CodeSandbox) -> None:
    result = sandbox.run("while True:\n    pass")
    assert result.error_type is not None
    assert result.duration_ms < 10_000


def test_memory_bomb_fails(sandbox: CodeSandbox) -> None:
    result = sandbox.run("x = [0] * 10**9\nlen(x)")
    assert result.error_type is not None


def test_host_call_cap(sandbox: CodeSandbox) -> None:
    result = sandbox.run("for i in range(200):\n    get_balance('ACC-0050-1')\n1")
    assert result.error_type is not None


@pytest.mark.parametrize(
    "code", ["open('/etc/passwd').read()", "import os\nos.environ.get('HOME')"]
)
def test_filesystem_and_environment_denied(sandbox: CodeSandbox, code: str) -> None:
    result = sandbox.run(code)
    assert result.error_type is not None


def test_syntax_error(sandbox: CodeSandbox) -> None:
    result = sandbox.run("def (")
    assert result.error_type == "syntax_error"


def test_print_captured(sandbox: CodeSandbox) -> None:
    result = sandbox.run("print('hello')\n2")
    assert result.stdout == "hello\n"
    assert result.value == 2


def test_warm_up_returns_duration(sandbox: CodeSandbox) -> None:
    assert sandbox.warm_up() > 0


def test_run_requires_context_manager(module_executor: ToolExecutor) -> None:
    with pytest.raises(RuntimeError):
        CodeSandbox(module_executor).run("1")
