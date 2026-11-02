# LinkedIn post draft

Status: Draft for author review. Not published.

Source run: `20261101T203521Z-full` (60 measured tasks, 10 per row, 0 infrastructure errors).
Every number below comes from `results/processed/20261101T203521Z-full/cells.csv`.

Link: https://github.com/ferozyk/ai-engineering-lab/tree/master/experiments/01-mcp-vs-code-mode
(The repository must be pushed before posting, or the link will not resolve.)

Suggested image (local file, gitignored, not in the repository): `linkedin/visual-assets/20261101T203521Z-full/linkedin-landscape.png`
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

---

# Follow-up: extension 01b (aggregation baseline)

Status: Draft for author review. Not published.

Source run: `20261102T201532Z-full` (110 measured tasks, 10 per row, 0 infrastructure errors).
Every number below comes from `results/processed/20261102T201532Z-full/cells.csv`.

Suggested image (local file, gitignored): `linkedin/visual-assets/20261102T201532Z-full/linkedin-landscape.png`.
Alternative: `results/charts/20261102T201532Z-full/unanticipated_query.png`.

## Reply to the comment

Really good point, so I tried it. I added a summarise_spending tool to the MCP server that returns category totals and large debits, so the model never has to look at the 400 rows.

Turns out you were mostly right. At 100 transactions per account, MCP went from 68k tokens and 0/10 correct to about 9.2k tokens and 10/10. That's roughly 94% of the gap to Code Mode, so most of the win really was just sending less data back.

Code Mode was still about 38% cheaper (5.7k tokens), mainly from one less round trip and a smaller tool list. I'd set myself a 25% margin before running it, and it missed that, so that part didn't hold.

The interesting part was when I asked something the tool wasn't built for: top 3 merchants and how many debits fell on a weekend. The model just went back to pulling every transaction, burned 83k tokens and got 0/10. Code Mode wrote a different script and got 10/10 on about 4.2k.

My take now: if you know the questions up front, a good aggregation tool gets you most of the way and you don't need a sandbox. Code Mode makes more sense when you can't predict what will be asked.

Write-up and data are in the repo:
https://github.com/ferozyk/ai-engineering-lab/tree/master/experiments/01-mcp-vs-code-mode

## Follow-up post (optional)

After my MCP vs Code Mode post, someone asked a good question: how much of Code Mode's advantage comes from running code, and how much from simply sending less data back to the model? So I added a third baseline: MCP with one extra aggregation tool that does the summing on the server.

Same model (Nemotron 3.5 Super, free tier on OpenRouter), same data, 10 runs per setup. I wrote down what would count as "supported" before running anything.

Chained task, 100 transactions per account:
- MCP, raw tools: 68,012 tokens, 146 s median, 0/10 correct
- MCP + aggregation tool: 9,172 tokens, 12 s, 10/10 correct
- Code Mode: 5,714 tokens, 9 s, 10/10 correct

So most of the gain was data reduction. One well-designed tool closed 94% of the token gap. Code Mode was still 38% cheaper, which was outside the margin I had set in advance, so I am calling that part not supported.

Then I asked something the tool wasn't designed for: the top three merchants by spend and the number of weekend debits.
- MCP + aggregation tool: 83,132 tokens, 0/10 correct (it fell back to fetching every transaction)
- Code Mode: 4,230 tokens, 10/10 correct

I built that question so the tool couldn't answer it, so this shows what happens when a question falls outside your tools, not how often that happens.

Where I have landed:
- few calls, small results: plain MCP
- known, repeated aggregations over large data: MCP with purpose-built tools, no sandbox needed
- open-ended analysis over large data: Code Mode, with a proper sandbox

One model and synthetic data, so treat the exact numbers with care. The code, raw data and pre-registered criteria are on GitHub:
https://github.com/ferozyk/ai-engineering-lab/tree/master/experiments/01-mcp-vs-code-mode

Thanks for the push to test it properly. How do you decide when a new tool is worth building versus letting the model write the code?

#MCP #AIEngineering #LLM #AgenticAI

## Fact check (01b, from `cells.csv` and raw records)

| Claim | Value in data |
|---|---|
| B100 tokens: MCP / MCP + agg / Code | 68,012 / 9,172 / 5,714 |
| B100 p50 latency | 145.64 s / 12.27 s / 8.83 s |
| B100 accuracy | 0/10 / 10/10 / 10/10 |
| Share of gap closed by the aggregation tool | (68,012 − 9,172) / (68,012 − 5,714) = 94.4% |
| Code Mode vs MCP + agg tokens | −37.7% (ratio 1.61; H5 threshold 1.25) |
| B100 model calls MCP + agg / Code | 3.0 / 2.0 |
| Extra tool definition prompt cost | peak prompt in Scenario A 1,461 vs 1,096 tokens (+365) |
| C100 tokens MCP + agg / Code | 83,132 / 4,230 |
| C100 accuracy | 0/10 (9 cut off at output limit, 1 weekend count 98 vs 99) / 10/10 |
| MCP + agg fell back to raw rows in C | raw `tool_calls.jsonl`: 40 `get_transactions`, 0 `summarise_spending` across the 10 tasks |
| MCP + agg used the tool in B100 | 40 `summarise_spending`, 0 `get_transactions` across the 10 tasks |
