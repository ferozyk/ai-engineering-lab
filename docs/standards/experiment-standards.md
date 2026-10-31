# Experiment Standards

## Lifecycle

Every experiment follows these steps:

1. Research question
2. Hypothesis
3. Architecture design
4. Implementation
5. Testing
6. Benchmarking
7. Results analysis
8. Documentation
9. LinkedIn content preparation

```mermaid
flowchart LR
    A[Research question] --> B[Hypothesis] --> C[Architecture design] --> D[Implementation]
    D --> E[Testing] --> F[Benchmarking] --> G[Results analysis] --> H[Documentation]
    H --> I[LinkedIn content preparation]
```

## Definition of done

An experiment is complete only when it has technical documentation, reproducible results, charts, a Markdown report and a LinkedIn draft.

## README requirements

Every experiment README contains these sections, in order (see `templates/experiment-template/README.md`):

1. Overview
2. Research Question
3. Why This Matters
4. Hypothesis
5. Objectives
6. Scope
7. Architecture
8. Implementation Approaches
9. Technology Stack
10. Experimental Methodology
11. Evaluation Metrics
12. Results
13. Analysis
14. Limitations
15. Conclusion
16. How to Run
17. References

Before the experiment is implemented, Results, Analysis and Conclusion state that results are pending.

## Code quality

- Python type hints throughout; mypy strict.
- PEP 8, enforced by Ruff.
- Pydantic for validating external data.
- Explicit exception handling.
- Structured logging where appropriate.
- Unit tests, plus integration tests where appropriate.
- No unnecessary global state or abstractions.
- Configuration kept outside business logic.
- Async only for I/O-bound work where it gives a real benefit.

## Testing

- Tests are organised as unit, integration and evaluation.
- Providers are mocked for deterministic tests.
- Live model tests are opt-in through the `live` marker.
- CI never depends on paid APIs or model availability.

## Model selection

Models are chosen through environment variables or configuration only (`LLM_PROVIDER`, `LLM_MODEL`). Free model availability changes. If the selected model is unavailable, explain the issue, check the provider configuration and suggest an alternative. Never switch models silently.
