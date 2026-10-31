# 0001. uv, hatchling and a src layout

## Status

Accepted

## Date

2026-10-31

## Context

The repository needs reproducible dependency management, an installable shared package and a layout that works for many independent experiments.

## Decision

- Use uv for dependency management, the lockfile and Python installation.
- Use hatchling as the build backend.
- Place the shared package under `shared/src/ai_lab`. The src layout prevents accidentally importing code that has not been installed.

## Alternatives considered

- Poetry: heavier, and uv covers the same needs with less tooling.
- pip-tools: does not manage Python installs or environments.
- uv_build backend: newer; hatchling is widely understood and sufficient.
- Flat layout: allows importing un-installed code by accident.

## Consequences

- One root lockfile (`uv.lock`) for the repository.
- Experiments import `ai_lab` after `uv sync`.
