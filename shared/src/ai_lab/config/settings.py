"""Application settings loaded from the environment and an optional .env file.

Credentials are validated lazily: constructing ``Settings`` never requires an API key.
Callers that need a credential call the matching ``require_*`` method.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_lab.config.errors import ConfigurationError, MissingCredentialError


class Settings(BaseSettings):
    """Typed application configuration.

    Environment variable names are the upper-case field names (for example ``LLM_MODEL``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # `OPENROUTER_API_KEY=` in .env is treated as unset
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # Extend this Literal when a new provider is implemented.
    llm_provider: Literal["openrouter"] = "openrouter"
    # No default model, by design: model availability changes, so it must be chosen explicitly.
    llm_model: str | None = None
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: HttpUrl = HttpUrl("https://openrouter.ai/api/v1")

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        """Accept lower-case level names such as ``info``."""
        if isinstance(value, str):
            return value.upper()
        return value

    def require_openrouter_api_key(self) -> str:
        """Return the OpenRouter API key or raise if it is not configured."""
        if self.openrouter_api_key is None:
            raise MissingCredentialError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env and set it, "
                "or export it in your shell."
            )
        return self.openrouter_api_key.get_secret_value()

    def require_llm_model(self) -> str:
        """Return the configured model identifier or raise if it is not set."""
        if self.llm_model is None:
            raise ConfigurationError(
                "LLM_MODEL is not set. Choose a model id from your provider "
                "and set LLM_MODEL in .env."
            )
        return self.llm_model


def load_settings(env_file: str | Path | None = ".env") -> Settings:
    """Load settings from the environment and an optional .env file.

    Pass ``env_file=None`` to ignore .env files (useful in tests).
    Raises ConfigurationError wrapping pydantic's ValidationError with a readable message.
    """
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']).upper()}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigurationError(f"Invalid configuration: {details}") from exc
