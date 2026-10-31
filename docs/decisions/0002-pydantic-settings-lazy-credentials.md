# 0002. pydantic-settings with lazy credential checks

## Status

Accepted

## Date

2026-10-31

## Context

Configuration must be validated and typed, support `.env` files, and never require an API key merely to install the project or run tests.

## Decision

- Load configuration with pydantic-settings.
- Validate credentials lazily through `require_*` methods rather than at construction.
- Hold secrets as `SecretStr` so they are masked in representations.
- Provide no default model; it must be selected explicitly.

## Alternatives considered

- Plain `os.environ`: no validation or typing.
- dynaconf: additional dependency with more features than needed.
- Failing at startup when a key is missing: forces credentials on tests and CI.

## Consequences

Callers that need a credential or a model must call the matching `require_*` method, which raises a clear error when the value is missing.
