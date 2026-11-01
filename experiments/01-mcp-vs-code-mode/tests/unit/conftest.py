"""Shared fixtures for experiment 01 unit tests.

The fixtures live in ``tests/support.py``. They are loaded by file path because the repository
root also has a ``tests`` directory, which makes ``tests.support`` ambiguous in a full run.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_support() -> ModuleType:
    name = "exp01_tests_support"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parents[1] / "support.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_support = _load_support()
anyio_backend = _support.anyio_backend
audit_log = _support.audit_log
dataset = _support.dataset
executor = _support.executor
principal = _support.principal
service = _support.service
