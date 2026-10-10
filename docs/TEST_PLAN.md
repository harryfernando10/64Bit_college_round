# Test Plan and Controlled Evaluation

`python -m pytest` runs API, schema, curated fixture and deterministic baseline cases offline. The controlled examples in `tests/test_api.py` cover supported exact text, quantity/date mismatch and unrelated-value abstentions, scoped and quoted polarity, paraphrased support, irrelevant evidence, missing detail, conflicting sources, Unicode offsets, multi-document retrieval, quote integrity, duplicate IDs and modified fixtures. They are constructed test cases, not a representative benchmark of real-world hallucinations.

Evaluation status: controlled suite measures contract behavior and includes all four verdict paths (fourth via conflicting sources and the curated fixture set). It is too small and intentionally rule-aligned to report meaningful per-verdict precision, recall, F1, confusion matrix or macro-F1; those metrics are therefore excluded rather than presented as general performance. Count is the number of passing automated tests at execution time, reported in the delivery summary. No cases are claimed as a benchmark.

The frontend production build runs `npm run build` and performs TypeScript checks. Manual browser checks: load each scenario; edit an answer and confirm old results clear; run a custom audit; verify exact spans and source quotes; add a source; restore the selected scenario; inspect baseline/fixture disclosures; submit invalid empty material; stop backend and confirm API error state.

Known edge cases include abbreviations, decimal/punctuation segmentation, paraphrase verification, tables or structured source text, and ambiguous numeric context. Quote validity does not imply entailment. No frontend browser automation is configured.
