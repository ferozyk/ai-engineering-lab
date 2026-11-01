# LinkedIn post draft

Status: Draft for author review. Not published.

Source run: `20261101T203521Z-full` (60 measured tasks, 10 per row, 0 infrastructure errors).
Every number below comes from `results/processed/20261101T203521Z-full/cells.csv`.

Link: https://github.com/ferozyk/ai-engineering-lab/tree/master/experiments/01-mcp-vs-code-mode
(The repository must be pushed before posting, or the link will not resolve.)

Suggested image: `linkedin/visual-assets/20261101T203521Z-full/linkedin-landscape.png`
(1200 x 627). The portrait card works better as a second slide or a carousel.

---

## Version A — Concise

I recently read about "Code Mode": instead of an LLM calling tools one at a time, you let it write a small script that calls the tools for it. It sounded neat, but I wanted to see how it actually compares to plain MCP tool calling, so I tested both on the same tasks.

The setup: a synthetic banking API with four tools, one free model (Nemotron 3.5 Super via OpenRouter), the same prompts and the same security rules for both approaches. Ten runs per scenario.

For a simple lookup (one tool call, small result) there was no real difference. Around 2,200 vs 2,000 tokens, 1.7 seconds each, and both were always correct.

For a chained task (summarise four accounts with 100 transactions each), the gap was large:
- MCP: about 65,600 tokens per task, a bit over 2 minutes, and 0 of 10 answers correct
- Code Mode: about 7,100 tokens per task, under 9 seconds, and 10 of 10 correct

The reason is simple once you look at the transcripts. With MCP, every tool result goes back into the model's context, so the model ends up doing the arithmetic over 400 rows itself. With Code Mode, the script does the summing and the model only sees the final numbers.

So I don't see this as Code Mode replacing MCP. If your agent makes a few calls and reads small results, MCP is simpler and works just as well. Once it has to chain calls and process a lot of data, letting the model write code starts to pay off, as long as you are prepared to run that code in a proper sandbox.

This is one model and synthetic data, so I would not read too much into the exact numbers. The code, data and method are on GitHub if you want to check them or try another model:
https://github.com/ferozyk/ai-engineering-lab/tree/master/experiments/01-mcp-vs-code-mode

Has anyone seen something similar with agents in production?

#MCP #AIEngineering #LLM #AgenticAI

---

## Version B — Detailed

I recently read about "Code Mode", the idea that instead of an LLM calling tools one at a time, it writes a short script that calls the tools and does the processing itself. I was curious whether that actually makes a difference compared to standard MCP tool calling, or whether it only matters in specific cases. So I set up a small experiment to find out.

What I compared

Both approaches used exactly the same four tools against a synthetic banking API (customer, accounts, balance, transactions), the same model (Nemotron 3.5 Super, free tier on OpenRouter), the same prompt structure and the same security controls. Authorisation is enforced by the banking service, never by the model. In Code Mode the generated code runs in a sandbox with no file, network or environment access, and with time and memory limits.

Two scenarios, 10 runs each:
1. A simple lookup: "what is the balance of this account?"
2. A chained task: for one customer, report each account's balance, spend per category and large debits over a 90-day window, at 10 and at 100 transactions per account.

Every answer was checked against values computed in plain Python, not by another model.

What I found

Simple lookup: practically the same.
- MCP 2,205 tokens, Code Mode 2,022 tokens
- 1.7 seconds median for both
- 10/10 correct for both

Chained task, 10 transactions per account:
- MCP 13,555 tokens, 18.6 s median, 10/10 correct
- Code Mode 7,554 tokens, 7.6 s median, 10/10 correct

Chained task, 100 transactions per account:
- MCP 65,579 tokens, 137 s median, 0/10 correct
- Code Mode 7,117 tokens, 8.5 s median, 10/10 correct

The MCP failures were not tool errors. The model fetched the right data every time. Half of the runs ran out of output budget (32k tokens) while still reasoning through the numbers, and the other half returned a well-formed answer with arithmetic mistakes in it: category totals off by anything from a few cents to over 3,000, and the occasional large transaction missed. Code Mode's token count barely moved with more data, because the raw rows never reach the model.

At the paid list price for the same model, that is roughly $19 vs $1.70 per 1,000 tasks for the larger case. That is an estimate, since the free tier cost nothing.

When I would use which

MCP tool calling is a good fit when:
- the agent makes a few calls and the results are small
- you want a simple, standard integration with no code execution to secure
- the model mainly needs to read data, not compute over it

Code Mode is worth the extra moving parts when:
- the task chains several calls together
- results are large and need filtering or aggregation
- correctness of numbers matters more than a slightly simpler setup

It is not free, though. You need a real sandbox, the model has to write working code, and it was less consistent on the small chained task: between 2 and 5 model calls per run, because it sometimes explored the data first or fixed its own code.

Caveats: one model, synthetic data and 10 runs per scenario. A stronger model would likely do better at in-context arithmetic, so the MCP accuracy result in particular may not hold everywhere. The token trend is the part I would expect to generalise, because it follows from where the data flows.

The code, raw data, charts and full methodology are here:
https://github.com/ferozyk/ai-engineering-lab/tree/master/experiments/01-mcp-vs-code-mode

I would be interested to hear how others decide between the two, or if you have run something similar with a different model.

#MCP #AIEngineering #LLM #AgenticAI #SoftwareEngineering

---

## Fact check (every figure above, from `cells.csv`)

| Claim | Value in data |
|---|---|
| A tokens MCP / Code | 2,205 / 2,022 |
| A p50 latency | 1.66 s / 1.65 s |
| B10 tokens MCP / Code | 13,555 / 7,554 |
| B10 p50 latency | 18.62 s / 7.63 s |
| B100 tokens MCP / Code | 65,579 / 7,117 |
| B100 p50 latency | 137.29 s / 8.52 s |
| B100 accuracy | MCP 0/10 (5 cut off at 32,768 output tokens, 5 incorrect) / Code 10/10 |
| Estimated cost per 1k tasks, B100 | $19.21 / $1.66 (paid list price, estimate) |
| Code Mode B10 model calls | 2 to 5 per run (raw `tasks.jsonl`: 2,2,2,2,2,2,3,3,5,5) |
| MCP fetched the right data every time | B100 MCP: 0 tool errors; every run called get_balance and get_transactions for all 4 accounts (raw `tool_calls.jsonl`) |
| Size of MCP arithmetic errors | Per-field absolute error 0.38 to 3,259.15 across the 5 incorrect runs (raw `tasks.jsonl` field_errors) |

## Notes for the author before posting
- The experiment was built with AI coding assistance. If you want to mention that, it fits naturally after "So I set up a small experiment".
- Push the repository first so the link works.
