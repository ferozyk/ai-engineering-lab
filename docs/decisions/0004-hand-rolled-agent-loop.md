# 0004. Hand-rolled agent loop

## Status

Accepted

## Date

2026-11-01

## Context

Token and latency measurements must be attributable to the approach under test. Agent frameworks may inject prompts, retries or tool-handling logic that would confound the comparison.

## Decision

Use one loop of roughly 150 lines, built on the `openai` SDK, shared by both modes. Only the toolset differs between MCP mode and Code Mode.

## Alternatives considered

- Pydantic AI (including its Code Mode support): hides prompt construction and tool handling behind framework behaviour.
- LangGraph: adds orchestration abstractions that are not needed for a single bounded loop.

## Consequences

- Every token and every request is visible and attributable.
- We own the retry and answer-parsing logic, and its tests.
