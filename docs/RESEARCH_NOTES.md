# Research Notes

## Optional local NLI model

Selected for the optional adapter: [`cross-encoder/nli-deberta-v3-small`](https://huggingface.co/cross-encoder/nli-deberta-v3-small), pinned in code to revision `fa2804872c3b4bd748f38c0185cc85775361e735`. Its model card identifies English text classification, Apache-2.0 licensing, and training on SNLI and MultiNLI. The card documents paired premise/hypothesis inference with `AutoTokenizer` and `AutoModelForSequenceClassification`, and output classes for contradiction, entailment and neutral. The [pinned Hub file listing](https://huggingface.co/cross-encoder/nli-deberta-v3-small/tree/fa2804872c3b4bd748f38c0185cc85775361e735) reports the `model.safetensors` weight file at 568 MB; the model configuration has a 512-token maximum sequence length. These are model artifact facts, not an estimate of total installed disk use or runtime memory. The model card does not give a verified CPU RAM or latency requirement; neither was measured here.

Transformers [4.57.1 installation documentation](https://huggingface.co/docs/transformers/v4.57.1/installation) lists Python 3.9+ and PyTorch 2.2+ among its tested install requirements. Refutella keeps those dependencies outside the standard requirements and loads only local files with `local_files_only=True`. No API key is needed. For local opt-in, install `requirements-nli.txt`, then use the Hugging Face CLI to fetch the safetensors checkpoint and tokenizer/config files (avoiding the repository's optional 4.45 GB ONNX export):

```powershell
hf download cross-encoder/nli-deberta-v3-small config.json added_tokens.json model.safetensors special_tokens_map.json spm.model tokenizer.json tokenizer_config.json --revision fa2804872c3b4bd748f38c0185cc85775361e735 --local-dir models/refutella-nli
$env:REFUTELLA_NLI_MODEL_PATH = "models/refutella-nli"
```

The path is ignored by Git. The model is not loaded for exact fixtures.

Prior to Phase 5A, actual inference had not been run: the optional ML packages and weights were absent. Phase 5A added the dependencies to the ignored local `.venv`, downloaded the pinned 568 MB safetensors file into ignored `models/refutella-nli`, and ran the local CPU smoke test. Load took about 17 seconds; single-pair latency was approximately 0.08–0.29 seconds after loading. Entailment, contradiction, neutral, and a simple paraphrase produced the expected smoke labels; a separate “four weeks” / “one month” paraphrase was misclassified as contradiction. RAM was not measured. The smoke test checks raw logits are returned and explicitly described as uncalibrated. No task accuracy or Refutella-specific calibration is claimed. The card's reported SNLI/MNLI scores are publisher-reported benchmark results and are not evidence of accuracy on Refutella inputs. The previous HHEM feasibility review is superseded: HHEM was not selected or integrated.

## Implemented baseline

The baseline uses local tokenization, BM25-style lexical evidence ranking and scoped string checks. It requires no API key, model download, or network access during audits. Lexical overlap is not factual support. Without the optional local verifier, exact normalized text identity is the only support rule; quantity/date checks abstain when multiple values or incompatible units make comparison ambiguous. Polarity checks require otherwise identical unquoted wording. Ambiguity is reserved for retrieved direct conflicts and a limited causal qualification pattern. The model-assisted path adds fallible NLI output only for retrieved passages, combines it with these deterministic checks conservatively, and does not establish world truth.

## Related work

- [FActScore](https://aclanthology.org/2023.emnlp-main.741/) motivates atomic factuality assessment.
- [FactCC](https://aclanthology.org/2020.emnlp-main.750/) studies consistency and evidence localization.
- [RAGTruth](https://arxiv.org/abs/2401.00396) provides human-annotated RAG hallucination examples.

These works informed the product framing only; Refutella does not reproduce their models or benchmarks. Evaluation here consists of controlled project-authored cases, not benchmark claims.

## Phase 3 evidence stress evaluation

Reproducible API examples are encoded in `tests/test_stress.py`: removing the only supporting source while retaining an irrelevant source yielded SUPPORTED → INSUFFICIENT_EVIDENCE; removing an unrelated source left the observed verdict SUPPORTED; replacing an exact supporting sentence with a paraphrase yielded INSUFFICIENT_EVIDENCE under the lexical baseline. These examples exercise the existing rules and retrieval path; they are not representative samples, accuracy measurements, or evidence that every perturbation should change a verdict. Evidence sensitivity is not a test of parametric memory leakage. A fixture baseline is curated and therefore reported as not directly comparable with the engine's perturbed result.

## Phase 5A triage and source identity notes

The baseline now preserves all sentence spans while flagging only obvious questions, common instruction starts, short headings/labels, and explicit first-person opinion phrasing as `NOT_ASSESSED`. Each includes a reason and may be explicitly included through `assess_claim_ids`. This rule layer is intentionally narrow and transparent; borderline language remains assessed as an ordinary claim. The new count does not imply truth or falsity and is separate from insufficient evidence.

API responses map immutable source IDs to ordered human labels (`S1`, `S2`, …). Labels are recomputed from the current input ordering; IDs remain stable across removals and appear in traces. Plain summaries sit beside technical details. Quote presence, relevance retrieval, support, contradiction, insufficient/conflicting evidence, and not-assessed status are separate concepts.

Pinned-card verification: the revision-specific Hub page exposes the same commit `fa2804872c3b4bd748f38c0185cc85775361e735`, identifies text classification/NLI in English and Apache-2.0, and lists 0.1B parameters, SNLI and MultiNLI training data, and a 568 MB `model.safetensors` artifact. Its Transformers example pairs inputs to `AutoTokenizer` and `AutoModelForSequenceClassification`; Refutella uses the documented paired premise/hypothesis form locally. The pinned file listing also includes a 4.45 GB ONNX export that is not needed by the Transformers adapter. Observed locally: CPU-only PyTorch 2.14.1, Transformers 4.57.6; ~17 s model load and 0.08–0.29 s per smoke pair. RAM was not measured and no authoritative memory requirement is published. Sources: [pinned model card](https://huggingface.co/cross-encoder/nli-deberta-v3-small/tree/fa2804872c3b4bd748f38c0185cc85775361e735) and [pinned file listing](https://huggingface.co/cross-encoder/nli-deberta-v3-small/tree/fa2804872c3b4bd748f38c0185cc85775361e735).
# Phase 5B evidence intelligence notes

Search Receipts expose only candidates already selected by the lexical retrieval call. They do not expose the internal ranking score as confidence. Source similarity uses normalized exact text or a conservative sentence-level token-set Jaccard threshold; sources remain present and the result is not evidence of common authorship or independence. Review flags are narrow matching cues maintained in `backend/review_flags.py`; they are not a safety classifier or a truth score. NLI-only contradiction is an ambiguity cue because local inference is fallible and uncalibrated.
