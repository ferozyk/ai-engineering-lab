# src

Python package `mcp_vs_code_mode` (a uv workspace member; install with `uv sync --all-packages`).

```text
src/mcp_vs_code_mode/
├── banking/       Synthetic banking domain
│   ├── errors.py      Typed errors (authentication, authorization, not found, invalid request)
│   ├── models.py      Immutable Pydantic models and the Dataset container with checksum
│   ├── dataset.py     Deterministic seeded dataset generator and ID helpers
│   ├── auth.py        Principal, in-memory session store, benchmark principal
│   ├── audit.py       Audit record model and JSONL-capable audit log
│   └── service.py     Read-only banking service: authorization plus one audit record per call
├── tools/         Tool interface shared by both modes
│   ├── errors.py      Tool errors with a stable error payload
│   └── registry.py    Four tool specs, input models and the allowlisting ToolExecutor
└── scenarios/     Benchmark scenarios
    ├── definitions.py Task prompts and answer schemas
    ├── ground_truth.py Expected answers computed directly from the dataset
    └── scoring.py     JSON extraction and field-level scoring
```

The MCP server, Code Mode runtime, agent loop, LLM client and runner are not implemented yet.
