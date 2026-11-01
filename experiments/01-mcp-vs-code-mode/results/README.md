# results

No real results yet: the benchmark pipeline is verified offline and the real run is pending.

## Planned layout

```text
results/
├── raw/<run_id>/
│   ├── run_metadata.json
│   ├── tasks.jsonl          # one record per task (outcome, totals, timings)
│   ├── llm_calls.jsonl      # one record per model call
│   ├── tool_calls.jsonl     # one record per tool / sandbox execution
│   ├── audit.jsonl          # banking-service audit log
│   └── transcripts/<task_id>.json
├── processed/<run_id>/summary.json, cells.csv, comparisons.csv
├── charts/<run_id>/*.png, *.svg
└── reports/<run_id>/report.md
```

| Directory | Content | Format |
|---|---|---|
| `raw/` | Raw per-request records, never edited | JSON, JSONL |
| `processed/` | Aggregated summaries derived from raw data | JSON, CSV |
| `charts/` | Charts generated from processed data | PNG, SVG |
| `reports/` | Written benchmark reports | Markdown |

Each run has its own `<run_id>/` subdirectory under `raw/`, `processed/`, `charts/` and `reports/`. Produced per run: `summary.json`, `cells.csv` and `comparisons.csv` (processed); one PNG and one SVG per chart (charts; see `benchmarks/methodology.md` for the list); `report.md` (reports). Regenerate them from the raw data with `uv run mcp-vs-code-mode publish <run_id>`.

Dry-run output goes to a gitignored `results/dry-run/<run_id>/` directory (with `raw/`, `processed/`, `charts/`, `reports/` and `linkedin/` inside), with charts watermarked `SIMULATED DATA — NOT A RESULT`.

Never hand-edit results. Failed runs are recorded, not discarded.
