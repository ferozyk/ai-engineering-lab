# Benchmark methodology — MCP vs Code Mode

Status: design approved; runner implemented. All request counts below are planning estimates, not results. Terminology follows the [experiment README](../README.md).

## 1. Scenarios

**Scenario A — Simple lookup.** Prompt: "What is the available balance of account `<id>`?" Answer schema: `{account_id, available_balance, currency}`. Expected: one tool call (MCP mode) or one script (Code Mode).

**Scenario B — Chained aggregation.** The prompt asks, for customer `<id>` and the window 2026-07-03 to 2026-10-01 inclusive: for each account, the available balance, total debit spend per category (absolute values, 2 dp), and IDs of debits with absolute amount greater than 1,000; plus the total available balance across accounts. Answer schema:

```json
{
  "customer_id": "<string>",
  "accounts": [
    {"account_id": "<string>", "available_balance": "<number>",
     "spend_by_category": {"<category>": "<number>"},
     "large_debit_ids": ["<string>"]}
  ],
  "total_available_balance": "<number>"
}
```

The window is stated as explicit dates (no relative dates) to remove ambiguity.

The dataset contains four Scenario B volumes (transactions per account): 10, 50, 100 and 200. The measured run covers Scenario A and Scenario B at volumes 10 and 100 only (maintainer decision, see section 3). This gives 6 measured cells: A x {mcp, code} and B x {10, 100} x {mcp, code}.

## 2. Ground truth and scoring

Ground truth is computed by plain Python over the dataset, never by an LLM. A task is `correct` only if every value matches: numbers within +/-0.01, category keys exact, large-debit ID sets equal. A field-level partial score (fraction of fields correct) is also recorded for analysis.

## 3. Controls

- Same model, temperature 0, same max output tokens, same `MAX_TURNS` (8).
- Same system prompt structure (role, rules, answer schema), differing only in the tool description section.
- Same dataset and principal.
- Both runtimes warm.
- Interleaved execution: for each iteration, the 6 cells run in an order shuffled with a fixed seed, so provider-side drift affects both modes equally.

**Pre-run protocol change (canary `20261101T154924Z-canary`).** The first canary used `max_output_tokens = 4096`. In the B200 MCP task the model spent all 4,096 output tokens on reasoning over a 68,038-token prompt and was truncated (`finish_reason = length`) before writing an answer. That cap was a harness setting, not a model limit, and would have failed every B200 MCP task by construction. Before any measured run, the cap was raised to 32,768 for **both** modes (and the request timeout from 180 s to 600 s). Answers still truncated at 32,768 tokens are recorded as failures, not excluded. The canary's raw data is kept in `results/raw/20261101T154924Z-canary/`.

**Pre-run protocol change (2026-11-02, before the measured run).** Volume 100 was added (generated after the existing customers, so the dataset 1.0.0 data for volumes 10, 50 and 200 is byte-identical; dataset version 1.1.0) and iterations were reduced from 15 to 10 by maintainer decision. Canary runs used dataset 1.0.0; their volume 10 and 200 data is unchanged.

**Pre-run protocol change (2026-11-02, scope, before any measured run).** Measured run scope reduced to Scenario A and Scenario B volumes 10 and 100 (maintainer decision, before any measured run). H3 and H4 were restated relative to the largest/smallest measured volume. Volume 200 is not part of the measured run. Canary observations (single runs, not measured statistics): MCP at volume 200 was cut off at the 32,768-token output limit in canaries 20261101T155803Z (104,255 tokens) and 20261101T162525Z (106,185 tokens); Code Mode at volume 200 answered correctly with 5,441 tokens in canary 20261101T163457Z.

**Pre-run protocol change (canary `20261101T162525Z-canary`).** In the B10 Code Mode task the model reused a variable defined in an earlier `run_python` call and got `NameError`, costing an extra round trip. Each call deliberately runs in a fresh sandbox, but the Code Mode instructions did not say so — an ambiguity in the harness, not a property of Code Mode. Before any measured run, one rule was added to the Code Mode instructions: "Each run_python call starts in a fresh sandbox: variables, functions and imports from earlier calls are not kept, so each call must contain all the code it needs." The MCP instructions are unchanged. Raw data from this canary is kept in `results/raw/20261101T162525Z-canary/`.

## 4. Sample size and request budget (planning estimates)

- Iterations: 10 per cell, giving 6 cells x 10 = 60 measured tasks, plus 1 unmeasured warm-up task per mode (2 warm-up tasks). 10 is exactly the minimum measured count per cell below which hypothesis verdicts are reported as inconclusive (section 10), so any infra error that is not recovered by resume makes the affected hypotheses inconclusive.
- Planning estimate (not a result): lower bound 144 (ideal agent: 4 warm-up requests plus 14 per iteration x 10); worst case 62 x 8 = 496. The `plan` command computes and prints both figures before anything runs.
- OpenRouter free tier at this account level: 20 requests per minute, 1,000 per day. The runner throttles to 15 requests per minute and stops cleanly at a configurable daily cap (default 900). The run is resumable.

## 5. Metrics

| Metric | Type | Source |
|---|---|---|
| Input, output, reasoning, total tokens per task | Measured | Provider-reported usage, summed over all model calls in the task |
| Model calls per task, tool calls per task | Measured | Agent loop |
| End-to-end latency per task (mean, p50, p95) | Measured | Wall clock |
| Latency breakdown: model time, tool/sandbox time, overhead | Measured | Timers around each step |
| Accuracy (correct / measured tasks), partial score | Measured | Scoring vs ground truth |
| Success / failure rate by outcome | Measured | Outcome counts |
| Code-error retries (Code Mode) | Measured | Agent loop |
| Estimated cost per task and per 1,000 tasks | **Estimated** | Tokens x paid-tier price of the same model from OpenRouter's models API, snapshotted with date at run start. If no paid variant exists, a reference price from config, explicitly labelled. |
| Peak prompt size (tokens) per task | Measured | Max prompt tokens over calls |

Percentiles use linear interpolation (numpy/pandas default). With n=10, p95 is close to the sample maximum; this is stated in every chart caption that shows it. Token and latency statistics include all non-`infra_error` tasks; accuracy is reported alongside. Infra errors are counted and reported, never silently dropped.

## 6. First-run reliability protocol

The free tier allows about 1,000 requests per day, so the real run must succeed the first time.

1. **Full offline dry run.** The entire pipeline (run, analyze, charts, report, LinkedIn asset) executes end-to-end against a scripted fake LLM, writing to a gitignored `results/dry-run/` directory with charts watermarked `SIMULATED DATA`. Covered by automated tests. Zero model requests.
2. **Preflight** (at most 2 model requests). Checks:
   - config present;
   - model exists in OpenRouter's model list, supports tool calling, and has context length at least the projected peak prompt size;
   - paid-tier pricing found (or reference price configured);
   - key valid and account tier confirmed via the key-info endpoint;
   - MCP server starts and lists 4 tools;
   - Monty executes a sample script calling all 4 tools;
   - ground truth computes;
   - output directory writable;
   - git working tree clean (commit SHA recorded);
   - one minimal live tool-calling request verifies the model returns well-formed tool calls.
3. **Canary** (about 10-15 requests). One task per cell for Scenario A and Scenario B volume 10. Must produce parseable answers in both modes before the full run starts. If the canary fails, the run stops for review; there is no automatic retry loop.
4. **Checkpointing.** Each completed task is appended to JSONL immediately. `run --resume` skips completed tasks and re-attempts only `infra_error` tasks. A crash never repeats completed requests.
5. **Capture everything once.** Full transcripts, per-call usage and timings are stored raw, so all metrics, charts and reports can be recomputed offline without new requests.
6. **Budget guard.** Throttle, daily cap, and a pre-run confirmation showing estimated requests.

## 7. Recorded run metadata

The required fields from the [benchmarking standards](../../../docs/standards/benchmarking-standards.md): experiment version, git SHA, timestamp, hardware, OS, Python version, provider, model id, dataset version, configuration, iterations, failed requests. Additionally:

- package versions (`mcp`, `openai`, `pydantic-monty`)
- pricing snapshot and date
- serving providers observed
- `MAX_TURNS`
- rate-limit settings
- random seeds

## 8. Output layout

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

## 9. Planned charts

All charts are generated from `processed/` data.

| File | Type | Shows |
|---|---|---|
| `tokens_vs_volume` | Line (x: transactions per account, log scale, measured volumes only (10 and 100 for the scoped run); y: mean total tokens per task), MCP vs Code Mode, min-max band | Headline: how token use scales with chained data |
| `latency_vs_volume` | Line, p50 with p95 markers | Latency scaling |
| `cost_vs_volume` | Line, estimated USD per 1,000 tasks, labelled "Estimated" | Cost scaling |
| `model_calls_vs_volume` | Line, mean model calls per task | Round trips |
| `scenario_a_parity` | Grouped bars: tokens, p50 latency, MCP vs Code Mode | Parity on simple lookups |
| `latency_distribution` | Box plot per cell | Spread and outliers |
| `accuracy_by_cell` | Grouped bars | Correctness per mode and volume |

LinkedIn assets (in `linkedin/visual-assets/`): landscape 1200x627 (tokens and latency line charts plus one data-derived takeaway sentence) and portrait 1080x1350 (summary card). Takeaway text is generated from the processed numbers, never typed by hand.

## 10. Hypothesis evaluation criteria

Fixed before any real run. Each hypothesis is evaluated automatically from the processed data and reported as "supported", "not supported" or "inconclusive". A verdict is "inconclusive" when any cell it requires has fewer than 10 measured tasks (or a required statistic is missing).

Token and latency statistics include all tasks with outcome other than `infra_error`; accuracy uses the same denominator.

| Hypothesis | Supported if and only if |
|---|---|
| H1 | For Scenario A, both \|mean total tokens(code) - mean total tokens(mcp)\| / mean total tokens(mcp) < 0.25 and \|p50 latency(code) - p50 latency(mcp)\| / p50 latency(mcp) < 0.25. |
| H2 | For every measured Scenario B volume, mean total tokens(code) < mean total tokens(mcp), and the absolute difference (mcp - code) strictly increases with volume. |
| H3 | For Scenario B, p50 latency(code) < p50 latency(mcp) at the largest measured volume. |
| H4 | Accuracy(mcp, largest measured volume) < accuracy(mcp, smallest measured volume), and max - min of Code Mode accuracy across measured volumes is at most 0.10. |

The smallest and largest volumes are taken from the Scenario B volumes present in the run (10 and 100 for the scoped measured run); verdicts and evidence name the actual volumes. A verdict is also "inconclusive" when fewer than 2 Scenario B volumes are present (H2 and H4).
