# results

No results yet: the experiment is not implemented.

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
├── processed/<run_id>/summary.json, summary.csv
├── charts/<run_id>/*.png, *.svg
└── reports/<run_id>/report.md
```

| Directory | Content | Format |
|---|---|---|
| `raw/` | Raw per-request records, never edited | JSON, JSONL |
| `processed/` | Aggregated summaries derived from raw data | JSON, CSV |
| `charts/` | Charts generated from processed data | PNG, SVG |
| `reports/` | Written benchmark reports | Markdown |

Dry-run output goes to a gitignored `results/dry-run/` directory, with charts watermarked `SIMULATED DATA`.

Never hand-edit results. Failed runs are recorded, not discarded.
