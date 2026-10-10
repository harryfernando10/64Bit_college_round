from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal

MAX_ANSWER = 20000
MAX_SOURCE = 30000

class Verdict(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_ASSESSED = "NOT_ASSESSED"

class VerificationTier(StrEnum):
    MECHANICAL = "MECHANICAL"
    MODEL = "MODEL"
    INSUFFICIENT = "INSUFFICIENT"

class ExecutionMode(StrEnum):
    FIXTURE = "FIXTURE"
    BASELINE = "BASELINE"
    LIVE = "LIVE"
    MODEL = "MODEL"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"

class SourceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=MAX_SOURCE)

    @field_validator("title", "text")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must contain non-whitespace text")
        return value

class AuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=MAX_ANSWER)
    sources: list[SourceDocument] = Field(min_length=1, max_length=8)
    scenario_id: str | None = Field(default=None, max_length=80)
    assess_claim_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("answer")
    @classmethod
    def reject_whitespace_only_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer must contain non-whitespace text")
        return value

    @model_validator(mode="after")
    def unique_source_ids(self):
        ids = [source.source_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source_id values must be unique")
        return self

class SentenceReference(BaseModel):
    sentence_id: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=1)
    text: str

class EvidenceReference(BaseModel):
    source_id: str
    sentence_id: str
    quote: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=1)
    quotation_validated: bool

class DeterministicCheck(BaseModel):
    check_type: str
    status: Literal["MATCH", "MISMATCH", "NOT_CHECKED"]
    detail: str

class SemanticVerification(BaseModel):
    status: Literal["ENTAILMENT", "CONTRADICTION", "NEUTRAL", "INCONCLUSIVE", "UNAVAILABLE", "ERROR"]
    source_id: str
    sentence_id: str
    model_id: str
    raw_logits: dict[str, float] | None = None
    detail: str = ""

class LexicalDifference(BaseModel):
    answer_terms: list[str] = []
    source_terms: list[str] = []

class ClaimFinding(BaseModel):
    claim_id: str
    claim_text: str
    triage_reason: str | None = None
    plain_summary: str = ""
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=1)
    verdict: Verdict
    verification_tier: VerificationTier
    evidence: list[EvidenceReference] = []
    deterministic_checks: list[DeterministicCheck] = []
    semantic_verifications: list[SemanticVerification] = []
    lexical_difference: LexicalDifference | None = None
    note: str
    model_score: float | None = Field(default=None, ge=0, le=1)
    model_score_calibrated: Literal[False] | None = None
    severity: Literal["LOW", "MEDIUM", "HIGH"] | None = None

class AuditSummary(BaseModel):
    supported: int = Field(ge=0)
    contradicted: int = Field(ge=0)
    insufficient_evidence: int = Field(ge=0)
    ambiguous: int = Field(ge=0)
    not_assessed: int = Field(default=0, ge=0)
    total_claims: int = Field(ge=0)

class AuditResponse(BaseModel):
    audit_id: str
    execution_mode: ExecutionMode
    answer: str
    sources: list[SourceDocument]
    source_sentences: dict[str, list[SentenceReference]]
    source_labels: dict[str, str] = {}
    claims: list[ClaimFinding]
    summary: AuditSummary
    warnings: list[str] = []

    @model_validator(mode="after")
    def validate_integrity(self):
        counts = {v: sum(c.verdict == v for c in self.claims) for v in Verdict}
        expected = {
            "supported": counts[Verdict.SUPPORTED],
            "contradicted": counts[Verdict.CONTRADICTED],
            "insufficient_evidence": counts[Verdict.INSUFFICIENT_EVIDENCE],
            "ambiguous": counts[Verdict.AMBIGUOUS],
            "not_assessed": counts[Verdict.NOT_ASSESSED],
            "total_claims": len(self.claims),
        }
        if self.summary.model_dump() != expected:
            raise ValueError("summary counts must match claims")
        source_ids = {source.source_id for source in self.sources}
        if set(self.source_sentences) != source_ids:
            raise ValueError("source_sentences keys must match source IDs")
        if self.source_labels and (set(self.source_labels) != source_ids or set(self.source_labels.values()) != {f"S{i+1}" for i in range(len(source_ids))}):
            raise ValueError("source_labels must uniquely label sources in current order")
        for source in self.sources:
            seen_sentence_ids = set()
            for sentence in self.source_sentences[source.source_id]:
                if sentence.sentence_id in seen_sentence_ids:
                    raise ValueError("sentence IDs must be unique within a source")
                seen_sentence_ids.add(sentence.sentence_id)
                if not (0 <= sentence.start_offset < sentence.end_offset <= len(source.text)):
                    raise ValueError("sentence offsets are outside source text")
                if source.text[sentence.start_offset:sentence.end_offset] != sentence.text:
                    raise ValueError("sentence offsets do not match source text")
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim IDs must be unique")
        for claim in self.claims:
            if not (0 <= claim.start_offset < claim.end_offset <= len(self.answer)):
                raise ValueError(f"claim offsets are outside original answer: {claim.claim_id}")
            if self.answer[claim.start_offset:claim.end_offset] != claim.claim_text:
                raise ValueError(f"claim offsets do not match original answer: {claim.claim_id}")
            for ref in claim.evidence:
                source = next((s for s in self.sources if s.source_id == ref.source_id), None)
                if source is None:
                    raise ValueError(f"unknown evidence source_id: {ref.source_id}")
                sentences = self.source_sentences.get(ref.source_id, [])
                sentence = next((s for s in sentences if s.sentence_id == ref.sentence_id), None)
                if sentence is None:
                    raise ValueError(f"unknown evidence sentence_id: {ref.sentence_id}")
                if not (0 <= ref.start_offset < ref.end_offset <= len(source.text)):
                    raise ValueError("evidence offsets are outside source text")
                if source.text[ref.start_offset:ref.end_offset] != ref.quote:
                    raise ValueError("evidence quote offsets do not match source text")
                if not ref.quotation_validated:
                    raise ValueError("quotation_validated must be true for returned evidence")
                if not (sentence.start_offset <= ref.start_offset < ref.end_offset <= sentence.end_offset):
                    raise ValueError("evidence offsets must be within referenced sentence")
        return self

class StressExperimentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline: AuditResponse
    operation: Literal["REMOVE_SOURCE", "REMOVE_PASSAGE", "EDIT_PASSAGE"]
    source_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    sentence_id: str | None = Field(default=None, max_length=100)
    replacement_text: str | None = Field(default=None, max_length=MAX_SOURCE)

    @model_validator(mode="after")
    def validate_operation(self):
        if self.operation == "REMOVE_SOURCE":
            if self.sentence_id is not None or self.replacement_text is not None:
                raise ValueError("source removal does not accept a passage or replacement text")
        else:
            if not self.sentence_id:
                raise ValueError("a sentence_id is required for passage experiments")
            if self.operation == "EDIT_PASSAGE":
                if self.replacement_text is None or not self.replacement_text.strip():
                    raise ValueError("replacement_text must contain non-whitespace text")
            elif self.replacement_text is not None:
                raise ValueError("passage removal does not accept replacement text")
        return self

class StressClaimComparison(BaseModel):
    claim_id: str
    claim_text: str
    baseline: ClaimFinding
    perturbed: ClaimFinding | None
    outcome: Literal["CHANGED", "UNCHANGED", "UNRESOLVED", "NOT_COMPARABLE"]
    explanation: str
    baseline_execution_mode: ExecutionMode
    perturbed_execution_mode: ExecutionMode | None

class StressExperimentResponse(BaseModel):
    experiment_label: str
    changed_source_id: str
    changed_sentence_id: str | None
    changed_text: str
    baseline: AuditResponse
    perturbed: AuditResponse | None
    comparisons: list[StressClaimComparison]
    comparable: bool
    warnings: list[str] = []
