# results

No results yet. Stage 1 is design only; nothing has been run.

## Planned layout

```text
results/
├── raw/<run_id>/          # per-request records and run metadata (JSON, JSONL)
├── processed/<run_id>/    # aggregated summaries (JSON, CSV)
├── charts/<run_id>/       # PNG and SVG charts generated from processed data
└── reports/<run_id>/      # Markdown report
```

Rules:

- Raw data is kept separate from processed summaries.
- Failed requests are recorded, not discarded.
- Charts are generated from processed data, never drawn by hand.
- Estimated values (for example cost) are labelled as estimated.

The metrics and run metadata are defined in [docs/evaluation-methodology.md](../docs/evaluation-methodology.md).
