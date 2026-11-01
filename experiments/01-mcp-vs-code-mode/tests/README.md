# tests

Tests for experiment 01. No test calls an LLM or the network.

- `unit/`: fast, isolated tests (`pytest.mark.unit`) for the dataset generator, authentication, banking service and audit log, tool registry, ground truth, scoring and scenario definitions.
- `integration/`: tests across components using a scripted fake LLM (added with the agent loop in a later phase).
- `unit/conftest.py`: shared fixtures (`dataset`, `audit_log`, `service`, `principal`, `executor`).

Run with `make test` from the repository root. Tests that call real providers must carry the `live` marker.
