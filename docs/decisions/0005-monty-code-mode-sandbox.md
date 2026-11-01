# 0005. Monty as Code Mode sandbox

## Status

Accepted

## Date

2026-11-01

## Context

Model-generated code must never run unrestricted on the host. The sandbox needs no filesystem, network or environment access, and should not dominate latency.

## Decision

Use `pydantic-monty` with execution-time and host-call limits. The registry tools are injected as external functions bound host-side to the principal.

## Alternatives considered

- Docker container per execution: heavier operations and a startup time of about 1.5 s as cited by the Monty documentation.
- Deno with Pyodide (WASM): slower startup.
- RestrictedPython: not a security boundary, rejected.

## Consequences

- The model must write code in a Python subset.
- A memory limit is supported (`max_memory`), alongside `max_feed_duration_secs` and `max_suspensions`.
- The first feed on a fresh pool takes about 0.76 s, so pools are warmed before measurement.
