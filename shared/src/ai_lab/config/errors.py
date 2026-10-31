"""Configuration error types."""


class ConfigurationError(Exception):
    """Raised when application configuration is invalid or incomplete."""


class MissingCredentialError(ConfigurationError):
    """Raised when a credential is required by an operation but not configured."""
