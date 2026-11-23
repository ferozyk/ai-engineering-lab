# LinkedIn post draft

Status: draft for review. Every number comes from the committed comparison report (`results/reports/comparisons/a-b-c-d/comparison.md`). Visuals: an 11-slide PDF carousel and a single cheat-sheet infographic with evidence labels, generated locally from the same data (not committed).

Link: https://github.com/ferozyk/ai-engineering-lab/tree/master/experiments/02-rag-architecture-comparison

---

## Version 1: concise (pairs with the infographic)

I built the same AI assistant four ways to see which design actually gives better answers.

The assistant answers questions about a fictional bank's API documentation. Same documents, same questions, same AI model. Only the way it finds information changed:

1. Semantic Search RAG (finds passages that mean the same as the question): 77 of 102 answers right
2. Hybrid Search RAG (adds exact-keyword search): 78 of 102
3. Hybrid + Reranker RAG (a second AI re-orders the top results): 78 of 102
4. Agentic RAG (an AI agent plans, checks what it found, and searches again): 85 of 102

What surprised me:
• Hybrid search and the reranker did not add right answers. It changed which questions were answered correctly, not how many.
• The reranker was misled by one short permissions list that mentions everything. It often looked more relevant than the real answer.
• Agentic RAG was the only clear improvement, mostly on questions asked in everyday words, and it almost never said "I don't know" when the answer was there (1 time vs 9 to 13). It also cost about 3× more per question and took about 6× longer, and once it answered a trick question it should have declined.

My takeaway: start simple, measure where it fails, and add one piece only when the failures point to it.

Small, synthetic test (40 questions, each asked 3 times) on one small, clean manual, so read it as direction, not law. Hybrid search and rerankers are built for larger, messier, code-heavy documents; that is exactly what I am testing next. Code, data and method are open: [link]

What would you have expected to win?

#AIEngineering #RAG #LLM #SoftwareEngineering

---

## Version 2: detailed (pairs with the carousel)

"Just add a reranker." "Use hybrid search." "Make it agentic."

These are common pieces of advice for AI assistants that answer from your own documents (retrieval-augmented generation, or RAG). I wanted to see what each one actually changes, so I built the same assistant four ways and measured them on the same test.

**The test**
• A fictional bank's API documentation: 5 APIs, split into 186 sections.
• 34 real questions, each asked 3 times (102 graded answers), plus 6 trick questions with no answer in the documentation.
• Graded automatically: is the answer right, does it say "I don't know" when it should, does it make anything up.
• Hypotheses written down and committed before each measurement, so I could not move the goalposts.

**The four techniques, and what happened**

1. Semantic Search RAG: find the five passages closest in meaning to the question and answer from them.
→ 77/102 right, about 2 seconds per question, never made anything up. A strong baseline.

2. Hybrid Search RAG: also search for exact keywords, and merge the two result lists.
→ 78/102. Better when people use the documentation's exact terms, worse when they use everyday words: the keyword matches crowded out good results.

3. Hybrid + Reranker RAG: a second model re-reads the top 30 passages and re-orders them.
→ 78/102, about 13 seconds per question on my laptop. It recovered some of the everyday-wording questions Hybrid lost, but a short permissions list that mentions everything ("read customers, accounts and consents… cancel payments") often looked more relevant than the real answer and pushed better passages down.

4. Agentic RAG: an AI agent plans its searches, checks whether it found enough, and searches again if not.
→ 85/102, and only 1 wrong "I don't know" (the other three: 9 to 13). The extra right answers came from questions asked in everyday words and one comparison. One question none of the others answered ("which web address do I get back for checking on a custom report?") it answered every time, by splitting it into two searches. On questions that need several steps, it gathered complete information far more often (9 of 12 tries vs 3 of 12), but it got the same ones right as Hybrid Search RAG, which it uses as its search tool.
The cost: about 3.3 model calls per question, roughly 3× the estimated cost and 6× the time of Semantic Search RAG, and one confident wrong answer to a trick question.

**What I took from it**
1. Better ranking is not the same as better answers. Hybrid and Reranker ranked differently, but the AI answered about as well whenever a relevant passage made it into the context.
2. Validate "standard upgrades" on your own content. A catch-all reference section and duplicated text worked against the reranker.
3. An agent loop earned its cost on everyday wording and on not giving up too early. More complete evidence for multi-step questions did not, by itself, add right answers. For simple lookups, the plain design is cheaper and nearly as good.

Caveats: a small synthetic test on one small, clean manual, one AI model (a free model through OpenRouter), estimated costs, and CPU-only latencies. Treat it as direction, not law. The conditions hybrid search and rerankers are designed for (large, messy, code-heavy documents) were not part of this test; the next experiment builds them on purpose.

Everything is open, including the code, data, run records and pre-registered hypotheses: [link]

If you have built RAG systems: which of these matched your experience, and which did not?

#AIEngineering #RAG #LLM #SoftwareEngineering #Evaluation
