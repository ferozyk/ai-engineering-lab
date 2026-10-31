# Tests

Repository-level tests for the shared `ai_lab` package.

## Layout

| Directory | Purpose |
|---|---|
| `unit/` | Fast, isolated tests with no I/O beyond temporary files |
| `integration/` | Tests across components using mocked providers (none yet) |
| `evaluation/` | Model-quality evaluations, mocked unless marked `live` (none yet) |

## Markers

Markers are declared in `pyproject.toml` and enforced with `--strict-markers`:
`unit`, `integration`, `evaluation`, `live`.

## Live tests

Tests marked `live` call real model providers. They are excluded by default and run only with
`uv run pytest -m live`, which also requires credentials (see `.env.example`).
CI never calls paid APIs.

## Experiment tests

Experiment-specific tests live inside each experiment's `tests/` directory. They will be added to
`testpaths` when they exist.

## Running

```bash
uv run pytest
```
