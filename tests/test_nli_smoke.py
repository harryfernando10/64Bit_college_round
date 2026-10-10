"""Opt-in real NLI smoke test; requires explicitly cached local pinned weights."""
import os
from pathlib import Path
import pytest

MODEL_PATH = os.getenv("REFUTELLA_NLI_MODEL_PATH", "").strip()
pytestmark = pytest.mark.skipif(
    not MODEL_PATH or not Path(MODEL_PATH).is_dir(),
    reason="Set REFUTELLA_NLI_MODEL_PATH to a cached local model to run real inference.",
)


def test_local_nli_entailment_contradiction_neutral_and_paraphrase():
    from backend.verifier import load_local_verifier

    verifier = load_local_verifier(MODEL_PATH)
    assert verifier.available, verifier.detail
    pairs = [
        ("entailment", "The museum opens at 9 AM on Monday.", "The museum opens at 9 AM on Monday.", "ENTAILMENT"),
        ("contradiction", "The museum is closed on Monday.", "The museum is open on Monday.", "CONTRADICTION"),
        ("neutral", "A visitor guide is available at the front desk.", "The museum is open on Monday.", "NEUTRAL"),
        ("paraphrase", "A person is eating a pizza.", "Someone is eating pizza.", "ENTAILMENT"),
    ]
    for _, premise, hypothesis, expected in pairs:
        result = verifier.verify(premise, hypothesis)
        assert result.label == expected
        assert result.raw_logits and set(result.raw_logits) == {"entailment", "contradiction", "neutral"}
        assert "uncalibrated" in result.detail.casefold()
