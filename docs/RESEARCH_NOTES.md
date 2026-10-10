# Research Notes

## Optional local verifier preflight

Phase 1 notes reviewed Vectara HHEM-2.1-Open as a possible English-language local support scorer. Its model card describes pair scoring and custom remote code, and publisher-reported CPU resource estimates; it is not a general contradiction classifier or truth checker. Transformers/PyTorch and model weights require installation and a first-run download unless cached. We did not install dependencies, download weights, inspect executable remote code, or test inference during Phase 2. It is not part of application startup or runtime. No model identifier or model score is emitted.

## Implemented baseline

The baseline uses local tokenization, BM25-style lexical evidence ranking and scoped string checks. It requires no API key, model download, or network access during audits. Lexical overlap is not factual support. Exact normalized text identity is the only support rule; quantity/date checks abstain when multiple values or incompatible units make comparison ambiguous. Polarity checks require otherwise identical unquoted wording. Ambiguity is reserved for retrieved direct conflicts and a limited causal qualification pattern. These choices trade recall for a simpler, inspectable baseline and do not establish world truth.

## Related work

- [FActScore](https://aclanthology.org/2023.emnlp-main.741/) motivates atomic factuality assessment.
- [FactCC](https://aclanthology.org/2020.emnlp-main.750/) studies consistency and evidence localization.
- [RAGTruth](https://arxiv.org/abs/2401.00396) provides human-annotated RAG hallucination examples.

These works informed the product framing only; Refutella does not reproduce their models or benchmarks. Evaluation here consists of controlled project-authored cases, not benchmark claims.
