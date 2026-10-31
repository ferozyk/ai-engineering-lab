# Agent Guidelines

## Purpose

Guidance for AI coding agents contributing to this repository. Human contributors may find it useful too; see also [CONTRIBUTING.md](CONTRIBUTING.md).

## Working method

- Work incrementally. Make small, reviewable changes.
- Explain the concept and the design decision first, then implement, then show how to test it.
- Stop for approval between phases. Do not continue into the next experiment or phase on your own.
- Prefer simple Python over frameworks. Introduce a technology only when a concrete experiment requires it.

## Hard rules

- Never fabricate benchmark numbers, results, statistics or quotes. Results stay marked as pending until real runs exist.
- Never hardcode model names. Select models through configuration (`LLM_PROVIDER`, `LLM_MODEL`).
- Never commit secrets, `.env` files or credentials, and never log them.
- Never execute generated code unrestricted on the host. Use a sandbox with filesystem and network restrictions, resource limits, timeouts and explicit tool allowlists.
- Enforce authorization in application code, never in the model.
- Use synthetic data only.
- Do not push to a remote without explicit approval from the maintainer.

## Code standards

Type hints everywhere, Ruff for linting and formatting, Pydantic for external data, explicit exception handling, configuration kept outside business logic. The full list is in [experiment standards](docs/standards/experiment-standards.md).

## Testing rules

- Tests must not call paid APIs or depend on model availability. CI never uses real credentials.
- Use mocked providers for deterministic unit and integration tests.
- Tests that call real providers carry the `live` marker and run only with `pytest -m live`.
- `make check` must pass before a change is considered done.

## Avoid overengineering

Do not introduce, unless an experiment concretely requires it:

- Kubernetes
- Complex microservices
- Unnecessary message brokers
- Multiple databases or other unneeded data stores
- Unnecessary orchestration frameworks
- Plugin systems
- Premature abstraction layers

## When a model is unavailable

1. Explain the failure to the maintainer.
2. Check the current provider configuration.
3. Suggest an available alternative.
4. Never silently switch models.
