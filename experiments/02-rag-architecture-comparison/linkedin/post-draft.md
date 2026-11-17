# LinkedIn post draft

Status: draft for review. Every number comes from the committed comparison report (`results/reports/comparisons/a-b-c-d/comparison.md`). Visuals: a 9-slide PDF carousel and a single infographic, generated locally from the same data (not committed).

Link: https://github.com/ferozyk/ai-engineering-lab/tree/master/experiments/02-rag-architecture-comparison

---

## Version 1: concise (pairs with the infographic)

I built the same AI assistant four ways to see which design actually gives better answers.

The assistant answers questions about a fictional bank's API documentation. Same documents, same questions, same AI model. Only the way it finds information changed:

A. Search by meaning: 77 of 102 answers right
B. + Keyword search: 78 of 102
C. + A second model that re-ranks the results: 78 of 102
D. An agent that plans, checks what it found, and searches again: 85 of 102

What surprised me:
• Adding keyword search or a re-ranker did not add right answers. It changed which questions were answered correctly, not how many.
• The re-ranker was misled by one short permissions list that mentions everything. It looked relevant to almost every question.
• The agent was the only clear improvement, and it almost never said "I don't know" when the answer was there (1 time vs 9 to 13). It also cost about 3× more per question and took about 6× longer, and once it answered a trick question it should have declined.

My takeaway: start simple, measure where it fails, and add one piece only when the failures point to it.

Small, synthetic test (40 questions, each asked 3 times), so read it as direction, not law. Code, data and method are open: [link]

What would you have expected to win?

#AIEngineering #RAG #LLM #SoftwareEngineering

---

## Version 2: detailed (pairs with the carousel)

"Just add a re-ranker." "Use hybrid search." "Make it agentic."

These are common pieces of advice for AI assistants that answer from your own documents (retrieval-augmented generation, or RAG). I wanted to see what each one actually changes, so I built the same assistant four ways and measured them on the same test.

**The test**
• A fictional bank's API documentation: 5 APIs, split into 186 sections.
• 34 real questions, each asked 3 times (102 graded answers), plus 6 trick questions with no answer in the documentation.
• Graded automatically: is the answer right, does it say "I don't know" when it should, does it make anything up.
• Hypotheses written down and committed before each measurement, so I could not move the goalposts.

**The four designs, and what happened**

A. Search by meaning. Find the five most similar passages and answer from them.
→ 77/102 right, about 2 seconds per question, never made anything up. A strong baseline.

B. Add keyword search, and merge the two result lists.
→ 78/102. Better when people use the documentation's exact terms, worse when they use everyday words: the keyword matches crowded out good results.

C. Add a second model that re-reads the top 30 passages and re-orders them.
→ 78/102, about 13 seconds per question on my laptop. It recovered the everyday-wording questions B lost, but a short permissions list that mentions everything ("read customers, accounts and consents… cancel payments") looked relevant to almost every question and pushed better passages down.

D. An agent that plans its searches, checks whether it found enough, and searches again if not.
→ 85/102, and only 1 wrong "I don't know" (A to C: 9 to 13). On questions that need several steps, it collected everything needed in 9 of 12 tries; the single-search designs managed 3 of 12 or fewer. One question none of the others answered ("which web address do I get back for checking on a custom report?") it answered every time, by splitting it into two searches.
The cost: about 3.3 model calls per question, roughly 3× the estimated cost and 6× the time of A, and one confident wrong answer to a trick question.

**What I took from it**
1. Better ranking is not the same as better answers. B and C ranked differently, but the AI answered about as well whenever a relevant passage made it into the context.
2. Validate "standard upgrades" on your own content. A catch-all reference section and duplicated text worked against the re-ranker.
3. An agent loop earns its cost when questions span several steps or use everyday wording. For simple lookups, the plain design is cheaper and nearly as good.

Caveats: a small synthetic test, one AI model (a free model through OpenRouter), estimated costs, and CPU-only latencies. Treat it as direction, not law.

Everything is open, including the code, data, run records and pre-registered hypotheses: [link]

If you have built RAG systems: which of these matched your experience, and which did not?

#AIEngineering #RAG #LLM #SoftwareEngineering #Evaluation
