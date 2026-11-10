"""Importing the core package must not pull in the optional LLM dependencies."""

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = "import sys; import ai_lab, ai_lab.config; sys.exit(1 if 'openai' in sys.modules else 0)"


def test_importing_core_does_not_import_openai() -> None:
    result = subprocess.run([sys.executable, "-c", _SCRIPT], check=False)
    assert result.returncode == 0
