# benchmarks

Benchmark design is documented in [methodology.md](methodology.md). It defines two scenarios (simple lookup and chained aggregation), four data volumes, 10 iterations per cell, interleaved execution, a first-run reliability protocol (offline dry run, preflight, canary, checkpointing) and the recorded run metadata. Runs must also record the metadata listed in `docs/standards/benchmarking-standards.md`.

The runner, preflight checks and CLI are implemented (see the experiment README, section 16). All settings are in [`../configs/benchmark.yaml`](../configs/benchmark.yaml); the model id comes only from `LLM_MODEL`.

## Raw output files

Each run writes to `results/raw/<run_id>/` (dry runs to `results/dry-run/<run_id>/raw/`). Row models are defined in `src/mcp_vs_code_mode/bench/records.py`.

| File | Content |
|---|---|
| `run_metadata.json` | Environment, git SHA, config, pricing snapshot, counters, halt status. Written at start, rewritten at the end. |
| `tasks.jsonl` | One line per executed task: outcome, token totals, timings, `cell`, `iteration`, `warmup`, `estimated_cost_usd`, `simulated`. No transcript. |
| `llm_calls.jsonl` | One line per model call with flattened usage, attempts, provider and model served. |
| `tool_calls.jsonl` | One line per tool or sandbox execution. |
| `audit.jsonl` | Banking-service audit log for both channels. |
| `transcripts/<task_id>.json` | Full message history for one task. |

After a resume, a retried task has more than one line in `tasks.jsonl`; the last line per `task_id` is the one to use. `llm_calls.jsonl` and `tool_calls.jsonl` keep the rows of the failed earlier attempt, because those requests were really sent.
