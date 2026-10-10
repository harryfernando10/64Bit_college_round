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

class VerificationTier(StrEnum):
    MECHANICAL = "MECHANICAL"
    MODEL = "MODEL"
    INSUFFICIENT = "INSUFFICIENT"

class ExecutionMode(StrEnum):
    FIXTURE = "FIXTURE"
    LIVE = "LIVE"
    MODEL = "MODEL"

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

class LexicalDifference(BaseModel):
    answer_terms: list[str] = []
    source_terms: list[str] = []

class ClaimFinding(BaseModel):
    claim_id: str
    claim_text: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=1)
    verdict: Verdict
    verification_tier: VerificationTier
    evidence: list[EvidenceReference] = []
    deterministic_checks: list[DeterministicCheck] = []
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
    total_claims: int = Field(ge=0)

class AuditResponse(BaseModel):
    audit_id: str
    execution_mode: ExecutionMode
    answer: str
    sources: list[SourceDocument]
    source_sentences: dict[str, list[SentenceReference]]
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
            "total_claims": len(self.claims),
        }
        if self.summary.model_dump() != expected:
            raise ValueError("summary counts must match claims")
        source_ids = {source.source_id for source in self.sources}
        if set(self.source_sentences) != source_ids:
            raise ValueError("source_sentences keys must match source IDs")
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
                if not (sentence.start_offset <= ref.start_offset < ref.end_offset <= sentence.end_offset):
                    raise ValueError("evidence offsets must be within referenced sentence")
        return self
