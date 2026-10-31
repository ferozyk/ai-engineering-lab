"""Shared pytest fixtures."""

import pytest

_ENV_VARS = (
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_TEMPERATURE",
    "APP_ENV",
    "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove configuration env vars so a developer's shell never influences test results."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
