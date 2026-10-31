"""Tests for settings loading and validation."""

from pathlib import Path

import pytest

from ai_lab.config import (
    ConfigurationError,
    MissingCredentialError,
    load_settings,
)

pytestmark = pytest.mark.unit

SECRET = "sk-test-secret-value"


def test_defaults() -> None:
    settings = load_settings(env_file=None)
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.llm_provider == "openrouter"
    assert settings.llm_model is None
    assert settings.llm_temperature == 0.0
    assert settings.openrouter_api_key is None
    assert str(settings.openrouter_base_url).startswith("https://openrouter.ai/api/v1")


def test_env_vars_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "<your-model-id>")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    monkeypatch.setenv("APP_ENV", "test")
    settings = load_settings(env_file=None)
    assert settings.llm_model == "<your-model-id>"
    assert settings.llm_temperature == 0.7
    assert settings.app_env == "test"


def test_log_level_is_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert load_settings(env_file=None).log_level == "DEBUG"


def test_env_file_loading(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"LLM_MODEL=<your-model-id>\nAPP_ENV=production\nOPENROUTER_API_KEY={SECRET}\n",
        encoding="utf-8",
    )
    settings = load_settings(env_file=env_file)
    assert settings.llm_model == "<your-model-id>"
    assert settings.app_env == "production"
    assert settings.require_openrouter_api_key() == SECRET


def test_empty_env_file_values_are_unset(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=\nLLM_MODEL=\n", encoding="utf-8")
    settings = load_settings(env_file=env_file)
    assert settings.openrouter_api_key is None
    assert settings.llm_model is None


def test_secret_is_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    settings = load_settings(env_file=None)
    assert SECRET not in repr(settings)
    assert SECRET not in str(settings)
    assert SECRET not in settings.model_dump_json()


def test_require_api_key_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    assert load_settings(env_file=None).require_openrouter_api_key() == SECRET


def test_require_api_key_raises_when_unset() -> None:
    settings = load_settings(env_file=None)
    with pytest.raises(MissingCredentialError, match="OPENROUTER_API_KEY"):
        settings.require_openrouter_api_key()


def test_require_llm_model(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ConfigurationError, match="LLM_MODEL"):
        load_settings(env_file=None).require_llm_model()
    monkeypatch.setenv("LLM_MODEL", "<your-model-id>")
    assert load_settings(env_file=None).require_llm_model() == "<your-model-id>"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLM_TEMPERATURE", "5"),
        ("LOG_LEVEL", "LOUD"),
        ("LLM_PROVIDER", "unknown"),
        ("OPENROUTER_BASE_URL", "not-a-url"),
    ],
)
def test_invalid_values_raise_configuration_error(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError, match="Invalid configuration"):
        load_settings(env_file=None)


def test_missing_credential_is_a_configuration_error() -> None:
    assert issubclass(MissingCredentialError, ConfigurationError)


def test_validation_error_message_does_not_leak_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_BASE_URL", SECRET)
    with pytest.raises(ConfigurationError) as exc_info:
        load_settings(env_file=None)
    message = str(exc_info.value)
    assert "OPENROUTER_BASE_URL" in message
    assert SECRET not in message
