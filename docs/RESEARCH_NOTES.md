# Research Notes

This is a compact design survey, not a novelty claim. Prior work covers atomic claim verification, evidence attribution, span localisation, and RAG evaluation.

## Claim-level verification and grounding
- FActScore breaks long-form output into atomic facts and measures support against a knowledge source. Its framing supports granular inspection; it also motivates caution about treating each grammatical sentence as one claim. https://aclanthology.org/2023.emnlp-main.741/
- Google DeepMind's SAFE uses search-augmented factuality evaluation for long-form answers. It is an example of agent/search-based evaluation; Refutella Phase 1 does not use web search. https://deepmind.google/research/publications/85420/
- Google Cloud Check Grounding offers a claim-level grounding API over supplied facts and linked fact chunks. It shows source-linked grounding is an existing product capability. https://cloud.google.com/generative-ai-app-builder/docs/check-grounding

## Inconsistency and localisation
- FactCC jointly predicts summary consistency and extracts source/supporting and inconsistent spans, an established source-grounding and localisation approach. https://aclanthology.org/2020.emnlp-main.750/
- RAGTruth provides human annotated RAG hallucination examples with case and word-level labels, useful for evaluation design. https://arxiv.org/abs/2401.00396
- LettuceDetect formulates RAG hallucination detection as token-level classification and reports span localisation; its paper and models need their own compatibility/license review before reuse. https://arxiv.org/abs/2502.17125

## Evidence ablation and evaluation
- ContextCite is relevant prior art for ablation-based attribution: it studies which context contributes to a generated answer. A user-facing source mutation workflow could measure response to controlled edits, but it is distinct in product framing and must not be represented as unprecedented. https://papers.nips.cc/paper_files/paper/2024/file/adbea136219b64db96a9941e4249a857-Paper-Conference.pdf
- RAGAS is a framework for reference-free assessment across RAG retrieval and generation dimensions. A labelled evaluation set and explicit metrics remain necessary for Refutella's own claims. https://arxiv.org/abs/2309.15217
- Related work includes attribution, claim verification, citation matching, natural language inference, benchmark curation and mutation/ablation testing. Evaluation should measure verdict quality, evidence validity, span overlap, abstention behavior, calibration and change sensitivity separately.

## Design limits
Validating that a quotation occurs at the reported source offsets proves that the source contains that quotation. It does not prove that the quotation entails the claim, that the source is authoritative, or that the claim is true in the world. Likewise, a source edit changing a verdict does not establish parametric leakage from the answer generator. It tests only the auditor's sensitivity to that controlled context under a specified setup.

Defensible current differentiator: an integrated, user-visible workflow for inspecting evidence references and testing whether verdicts respond appropriately to controlled source changes, with explicit limitations and measured evaluation. The Evidence Stress Lab is future work. No claim is made that no other project has implemented such ideas.

## Vectara HHEM-2.1-Open preflight
Reviewed the Hugging Face model card at a fixed displayed repository commit (a3c3fe8e0f7d5672d5c054358476d588ecbda287) and Vectara's announcement during Phase 1. Card metadata says Apache-2.0, English text classification, and custom code. The card describes pair scoring from premise/context to hypothesis/claim with values from 0 (not evidenced) to 1 (fully supported), and documents AutoModelForSequenceClassification usage. It warns of breaking changes and current use instructions involving trust_remote_code=True. Do not enable that setting until the exact code at the chosen immutable revision has been inspected and pinned. The card reports <600 MB RAM at 32-bit precision and about 1.5 seconds on a modern x86 CPU for a 2k-token input; this is publisher-reported, not verified on our target.

Actual compatibility assessment: plausible as an optional English-only local support scorer, not a proven contradiction/ambiguity classifier or standalone truth checker. It can be run without a GPU per the card's stated CPU claim, but actual latency/memory and inference must be tested. Transformers, PyTorch and tokenizer/model dependencies are needed; none are added to Phase 1 requirements. We did not install them, fetch model weights, enable remote code, or test inference. Weights require a first-run download unless explicitly cached; network and disk requirements are not part of Phase 1. Sources: [pinned Hugging Face model card](https://huggingface.co/vectara/hallucination_evaluation_model/tree/a3c3fe8e0f7d5672d5c054358476d588ecbda287) and [Vectara HHEM-2.1 announcement](https://www.vectara.com/blog/hhem-2-1-a-better-hallucination-detection-model). Reassess current card and immutable code revision before adoption.
