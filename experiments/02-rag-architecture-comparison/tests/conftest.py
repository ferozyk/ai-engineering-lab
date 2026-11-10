"""Shared fixtures for experiment 02 tests.

The fixtures live in ``rag_support.py`` and are loaded by file path, because the repository root
also has a ``tests`` directory and a second ``conftest`` module name would clash under mypy.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_support() -> ModuleType:
    name = "exp02_tests_support"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parent / "rag_support.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_support = _load_support()
chunks = _support.chunks
corpus = _support.corpus
experiment_config = _support.experiment_config
header_names = _support.header_names
tiny_spec_path = _support.tiny_spec_path
make_chunk = _support.make_chunk
make_record = _support.make_record
anyio_backend = _support.anyio_backend
