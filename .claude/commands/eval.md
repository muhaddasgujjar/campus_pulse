---
description: Run the golden-set evaluation and summarize the results
---

Run `make eval` and then:

1. Show the metrics table (metric, target, result) exactly as printed.
2. Compare each result with its target from docs/PRD.md Section 3 and flag every miss.
3. List the worst failing questions (up to 10): question, expected tool and facts, what happened, and the likely cause (data missing, retrieval, routing, composer, fallback).
4. Suggest the top 3 fixes. Do not change code unless asked.
5. Update the golden set size and latest eval score in docs/Memory.md Section 7.
