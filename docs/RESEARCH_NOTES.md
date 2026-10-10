# Research Notes

## Optional local NLI model

Selected for the optional adapter: [`cross-encoder/nli-deberta-v3-small`](https://huggingface.co/cross-encoder/nli-deberta-v3-small), pinned in code to revision `fa2804872c3b4bd748f38c0185cc85775361e735`. Its model card identifies English text classification, Apache-2.0 licensing, and training on SNLI and MultiNLI. The card documents paired premise/hypothesis inference with `AutoTokenizer` and `AutoModelForSequenceClassification`, and output classes for contradiction, entailment and neutral. The [pinned Hub file listing](https://huggingface.co/cross-encoder/nli-deberta-v3-small/tree/fa2804872c3b4bd748f38c0185cc85775361e735) reports the `model.safetensors` weight file at 568 MB; the model configuration has a 512-token maximum sequence length. These are model artifact facts, not an estimate of total installed disk use or runtime memory. The model card does not give a verified CPU RAM or latency requirement; neither was measured here.

Transformers [4.57.1 installation documentation](https://huggingface.co/docs/transformers/v4.57.1/installation) lists Python 3.9+ and PyTorch 2.2+ among its tested install requirements. Refutella keeps those dependencies outside the standard requirements and loads only local files with `local_files_only=True`. No API key is needed. For local opt-in, install `requirements-nli.txt`, then use the Hugging Face CLI to fetch the safetensors checkpoint and tokenizer/config files (avoiding the repository's optional 4.45 GB ONNX export):

```powershell
hf download cross-encoder/nli-deberta-v3-small config.json added_tokens.json model.safetensors special_tokens_map.json spm.model tokenizer.json tokenizer_config.json --revision fa2804872c3b4bd748f38c0185cc85775361e735 --local-dir models/refutella-nli
$env:REFUTELLA_NLI_MODEL_PATH = "models/refutella-nli"
```

The path is ignored by Git. The model is not loaded for exact fixtures.

Actual inference was not run: this environment had no installed `torch`, `transformers`, `sentence_transformers` or `tokenizers`, and the 568 MB weights were deliberately not downloaded during the timeboxed feasibility check. Offline mock tests cover the integration. No throughput, memory, task accuracy or Refutella-specific calibration is claimed. The card's reported SNLI/MNLI scores are publisher-reported benchmark results and are not evidence of accuracy on Refutella inputs. The previous HHEM feasibility review is superseded: HHEM was not selected or integrated.

## Implemented baseline

The baseline uses local tokenization, BM25-style lexical evidence ranking and scoped string checks. It requires no API key, model download, or network access during audits. Lexical overlap is not factual support. Without the optional local verifier, exact normalized text identity is the only support rule; quantity/date checks abstain when multiple values or incompatible units make comparison ambiguous. Polarity checks require otherwise identical unquoted wording. Ambiguity is reserved for retrieved direct conflicts and a limited causal qualification pattern. The model-assisted path adds fallible NLI output only for retrieved passages, combines it with these deterministic checks conservatively, and does not establish world truth.

## Related work

- [FActScore](https://aclanthology.org/2023.emnlp-main.741/) motivates atomic factuality assessment.
- [FactCC](https://aclanthology.org/2020.emnlp-main.750/) studies consistency and evidence localization.
- [RAGTruth](https://arxiv.org/abs/2401.00396) provides human-annotated RAG hallucination examples.

These works informed the product framing only; Refutella does not reproduce their models or benchmarks. Evaluation here consists of controlled project-authored cases, not benchmark claims.
