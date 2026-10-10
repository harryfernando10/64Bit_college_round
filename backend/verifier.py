"""Optional local NLI adapter. Importing this module does not import ML libraries."""
from dataclasses import dataclass
from typing import Literal, Protocol

NliLabel = Literal["ENTAILMENT", "CONTRADICTION", "NEUTRAL", "INCONCLUSIVE", "UNAVAILABLE", "ERROR"]
MODEL_ID = "cross-encoder/nli-deberta-v3-small"
MODEL_REVISION = "fa2804872c3b4bd748f38c0185cc85775361e735"
MODEL_IDENTIFIER = f"{MODEL_ID}@{MODEL_REVISION}"

@dataclass(frozen=True)
class NliResult:
    label: NliLabel
    model_id: str
    raw_logits: dict[str, float] | None = None
    detail: str = ""

class ClaimVerifier(Protocol):
    model_id: str
    available: bool
    detail: str

    def verify(self, premise: str, hypothesis: str) -> NliResult: ...

class UnavailableVerifier:
    available = False

    def __init__(self, model_id: str, detail: str):
        self.model_id = model_id
        self.detail = detail

    def verify(self, premise: str, hypothesis: str) -> NliResult:
        return NliResult("UNAVAILABLE", self.model_id, detail=self.detail)

class LocalTransformersNliVerifier:
    """CPU-only, local-files-only DeBERTa NLI inference."""
    available = True
    max_pair_tokens = 512
    minimum_top_score = 0.60
    minimum_score_margin = 0.20

    def __init__(self, local_model_path: str):
        # Lazy imports preserve baseline startup when optional packages are absent.
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.model_id = MODEL_IDENTIFIER
        self.detail = ""
        self._tokenizer = AutoTokenizer.from_pretrained(local_model_path, local_files_only=True)
        self._model = AutoModelForSequenceClassification.from_pretrained(local_model_path, local_files_only=True)
        self._model.to("cpu")
        self._model.eval()
        labels = {int(key): str(value).casefold() for key, value in self._model.config.id2label.items()}
        expected = {"contradiction", "entailment", "neutral"}
        if set(labels.values()) != expected:
            raise ValueError(f"Expected NLI labels {sorted(expected)}, received {sorted(labels.values())}")
        self._labels = labels

    def verify(self, premise: str, hypothesis: str) -> NliResult:
        encoded = self._tokenizer(premise, hypothesis, add_special_tokens=True, truncation=False)
        if len(encoded["input_ids"]) > self.max_pair_tokens:
            return NliResult("INCONCLUSIVE", self.model_id, detail="Passage and claim exceed the model's 512-token pair limit; input was not truncated.")
        features = self._tokenizer(premise, hypothesis, return_tensors="pt", truncation=False)
        with self._torch.inference_mode():
            logits = self._model(**features).logits[0].detach().cpu().tolist()
        raw = {self._labels[index]: float(value) for index, value in enumerate(logits)}
        # The model's softmax scores are only an operational margin check, not calibrated probabilities.
        exp_logits = self._torch.softmax(self._torch.tensor(logits, dtype=self._torch.float64), dim=0).tolist()
        order = sorted(range(len(exp_logits)), key=exp_logits.__getitem__, reverse=True)
        winner, runner_up = order[0], order[1]
        winning_label = self._labels[winner]
        if winning_label == "neutral":
            label: NliLabel = "NEUTRAL"
        elif exp_logits[winner] < self.minimum_top_score or exp_logits[winner] - exp_logits[runner_up] < self.minimum_score_margin:
            label = "INCONCLUSIVE"
        else:
            label = "ENTAILMENT" if winning_label == "entailment" else "CONTRADICTION"
        return NliResult(label, self.model_id, raw_logits=raw,
                         detail="Raw classifier logits; class-margin thresholds are heuristic and uncalibrated.")

def load_local_verifier(local_model_path: str) -> ClaimVerifier:
    """Load only already-cached local weights; never resolves a Hub model ID."""
    from pathlib import Path
    path = Path(local_model_path)
    if not path.is_dir():
        return UnavailableVerifier(MODEL_IDENTIFIER, f"Configured local NLI directory does not exist: {path}")
    try:
        return LocalTransformersNliVerifier(str(path))
    except Exception as exc:
        return UnavailableVerifier(MODEL_IDENTIFIER, f"Could not load optional local NLI: {type(exc).__name__}: {exc}")
