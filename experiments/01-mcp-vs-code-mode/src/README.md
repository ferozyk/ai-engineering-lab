# src

Python package `mcp_vs_code_mode` (a uv workspace member; install with `uv sync --all-packages`).

```text
src/mcp_vs_code_mode/
├── banking/       Synthetic banking domain
│   ├── errors.py      Typed errors (authentication, authorization, not found, invalid request)
│   ├── models.py      Immutable Pydantic models and the Dataset container with checksum
│   ├── dataset.py     Deterministic seeded dataset generator and ID helpers
│   ├── auth.py        Principal, session store, token fingerprints and trusted-token authentication
│   ├── audit.py       Audit record model and JSONL-capable audit log
│   └── service.py     Read-only banking service: authorization plus one audit record per call
├── tools/         Tool interface shared by both modes
│   ├── errors.py      Tool errors with a stable error payload
│   └── registry.py    Four tool specs, input models and the allowlisting ToolExecutor
├── agent/         Shared agent loop
│   ├── records.py     Pydantic records for LLM calls, tool calls and task results
│   ├── llm.py         ChatModel protocol and OpenAI-compatible client with retries
│   ├── toolsets.py    MCPToolset and CodeModeToolset
│   ├── prompts.py     System prompt construction
│   ├── loop.py        run_task
│   └── fakes.py       Simulated models for tests and the dry run (not measurements)
├── mcp_server/    MCP mode server (MCPServer over stdio; python -m mcp_vs_code_mode.mcp_server)
├── code_mode/     Code Mode
│   ├── stubs.py       Python stubs and prompt section generated from the tool registry
│   └── sandbox.py     CodeSandbox around a Monty subprocess pool
└── scenarios/     Benchmark scenarios
    ├── definitions.py Task prompts and answer schemas
    ├── ground_truth.py Expected answers computed directly from the dataset
    └── scoring.py     JSON extraction and field-level scoring
```

The benchmark runner, preflight, analysis and CLI are not implemented yet.
