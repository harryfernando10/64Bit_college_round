import json
from pathlib import Path
from uuid import uuid4
from backend.models import *

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "data" / "scenarios"

def split_sentences(text: str, prefix: str):
    import re
    spans = []
    for match in re.finditer(r"[^.!?\n]+(?:[.!?]+|$)", text):
        start, end = match.span()
        while start < end and text[start].isspace(): start += 1
        while end > start and text[end-1].isspace(): end -= 1
        if start < end:
            spans.append(SentenceReference(sentence_id=f"{prefix}-s{len(spans)+1}", start_offset=start, end_offset=end, text=text[start:end]))
    return spans

def _fixture(scenario_id: str):
    for path in SCENARIOS.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf8"))
        if data["scenario_id"] == scenario_id: return data
    return None

def run_audit(request: AuditRequest) -> AuditResponse:
    data = _fixture(request.scenario_id) if request.scenario_id else None
    if data and data["answer"] == request.answer and data["sources"] == [s.model_dump() for s in request.sources]:
        claims = [ClaimFinding(**c) for c in data["claims"]]
        warnings = ["Scenario-backed fixture output; this is not a live model assessment."]
    else:
        spans = split_sentences(request.answer, "claim")
        claims = [ClaimFinding(claim_id=f"claim-{i+1}", claim_text=s.text, start_offset=s.start_offset, end_offset=s.end_offset, verdict=Verdict.INSUFFICIENT_EVIDENCE, verification_tier=VerificationTier.INSUFFICIENT, note="Phase 1 does not assess arbitrary text. No fixture matches this exact input; evidence sufficiency requires later verification logic.") for i,s in enumerate(spans)]
        warnings = ["Fixture mode: custom input was not evaluated by a model.", "No evidence verification was performed for custom input."]
    sentence_map = {s.source_id: split_sentences(s.text, s.source_id) for s in request.sources}
    counts = {v: sum(c.verdict == v for c in claims) for v in Verdict}
    return AuditResponse(audit_id=f"audit-{uuid4().hex[:12]}", execution_mode=ExecutionMode.FIXTURE, answer=request.answer, sources=request.sources, source_sentences=sentence_map, claims=claims, summary=AuditSummary(supported=counts[Verdict.SUPPORTED], contradicted=counts[Verdict.CONTRADICTED], insufficient_evidence=counts[Verdict.INSUFFICIENT_EVIDENCE], ambiguous=counts[Verdict.AMBIGUOUS], total_claims=len(claims)), warnings=warnings)
