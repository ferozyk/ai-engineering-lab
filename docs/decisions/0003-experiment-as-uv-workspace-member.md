# 0003. Experiment as uv workspace member

## Status

Accepted

## Date

2026-11-01

## Context

Experiment 01 needs `mcp`, `openai`, `pydantic-monty`, `pandas` and `matplotlib`. The root project must stay lightweight and must not carry these dependencies.

## Decision

`experiments/01-mcp-vs-code-mode` is a uv workspace member with its own `pyproject.toml`. It depends on `ai-engineering-lab` through a workspace source. A single root lockfile covers all members.

## Alternatives considered

- Root dependency groups: pollutes the root project and gives the experiment no package boundary.
- Fully separate project: requires a second lockfile and duplicates tooling configuration.

## Consequences

- The root `pyproject.toml` gains a `[tool.uv.workspace]` section.
- CI must sync all workspace members.
- Each future experiment can follow the same pattern and keep its dependencies isolated.
