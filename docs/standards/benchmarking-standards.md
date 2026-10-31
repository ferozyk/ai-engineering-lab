# Benchmarking Standards

## Philosophy

The goal is to understand engineering trade-offs, not to declare winners. Every comparison uses a documented methodology.

## Metric catalogue

Not every metric applies to every experiment. The percentile method used is documented per experiment.

| Metric | Unit | Definition |
|---|---|---|
| Average latency | ms | Mean end-to-end time per request |
| p50 latency | ms | Median end-to-end time per request |
| p95 latency | ms | 95th percentile end-to-end time per request |
| Success rate | % | Share of requests that completed successfully |
| Failure rate | % | Share of requests that failed |
| Input tokens | tokens | Tokens sent to the model |
| Output tokens | tokens | Tokens produced by the model |
| Total tokens | tokens | Input plus output tokens |
| Estimated cost | USD | Token counts multiplied by a published price; always an estimate |
| Accuracy | % or score | Agreement with the expected answer, as defined by the experiment |
| Retrieval quality | score | Relevance of retrieved material, as defined by the experiment |
| Resource utilisation | varies | CPU, memory or similar, as defined by the experiment |

## Measured versus estimated

Values derived rather than observed (for example cost computed from token counts and a published price) are labelled "estimated" everywhere they appear. Estimated values are never presented as measured.

## Integrity

- Never manufacture or manually alter results.
- Failed runs are recorded, not discarded.

## Required run metadata

1. Experiment version
2. Git commit SHA
3. Execution timestamp
4. Hardware
5. Operating system
6. Python version
7. Model provider
8. Model identifier
9. Dataset version
10. Configuration
11. Number of iterations
12. Number of failed requests

Warm-up runs, iteration counts and concurrency are stated in the experiment methodology.

## Output formats

| Location | Content | Format |
|---|---|---|
| `results/raw/` | Raw per-request records | JSONL |
| `results/processed/` | Aggregated summaries | JSON |
| `results/charts/` | Charts | PNG, SVG |
| `results/reports/` | Written reports | Markdown |

Illustrative schema of one raw record (placeholders, not real values):

```json
{
  "run_id": "<string>",
  "approach": "<string>",
  "iteration": "<int>",
  "success": "<bool>",
  "latency_ms": "<float>",
  "input_tokens": "<int>",
  "output_tokens": "<int>",
  "error": "<string or null>"
}
```

## Report structure

1. Executive summary
2. Research question
3. Experimental setup
4. Environment
5. Methodology
6. Results table
7. Graphical comparisons
8. Key observations
9. Engineering trade-offs
10. Limitations
11. Conclusion
