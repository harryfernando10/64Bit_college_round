# API Contract — Phase 1 v1

Base path /api, UTF-8 JSON. Canonical models are backend/models.py and frontend/src/types.ts. Extra request fields are rejected.

## GET /api/health
200 JSON: status=ok, service=refutella-api, phase=1.

## GET /api/scenarios
200 array containing scenario_id, title, description, answer and sources. Source shape: source_id, title, text. This endpoint does not contain claim results.

## POST /api/audit request

    { "answer": "...", "sources": [{"source_id":"study-note","title":"Study note","text":"..."}], "scenario_id": "harbor-plan" }

scenario_id is optional/null. Answer length 1–20,000 characters. Sources count 1–8. Source ID matches letters, digits, underscore or hyphen and is unique. Title length 1–160. Source text length 1–30,000. Unknown request properties are forbidden.

## Response
AuditResponse contains audit_id, execution_mode, answer, sources, source_sentences, claims, summary and warnings. execution_mode is FIXTURE, LIVE or MODEL; Phase 1 returns FIXTURE only. source_sentences maps source ID to sentence objects {sentence_id,start_offset,end_offset,text}. Claim fields: claim_id, claim_text, start_offset, end_offset, verdict, verification_tier, evidence, deterministic_checks, lexical_difference, note, model_score, model_score_calibrated, severity.

Verdict: SUPPORTED, CONTRADICTED, INSUFFICIENT_EVIDENCE, AMBIGUOUS. Tier: MECHANICAL, MODEL, INSUFFICIENT. Evidence: source_id, sentence_id, quote, start_offset, end_offset, quotation_validated. Check status: MATCH, MISMATCH, NOT_CHECKED. Optional model score is 0–1 and must have model_score_calibrated=false; it is not a calibrated probability. Severity: LOW, MEDIUM, HIGH. Summary contains counts by verdict and total_claims.

## Offsets and integrity
Offsets are half-open [start,end), measured in Python Unicode code points in the exact answer/source returned in the same response. No trimming or normalization is done before validation. Claim slice must equal claim_text. Evidence source/sentence IDs must exist; quote must equal source slice and lie within the sentence. quotation_validated proves only exact text exists at those offsets, not claim truth. Missing support is not contradiction.

## Errors and modes
Invalid shape, missing data, duplicate IDs or length/format violations return HTTP 422 with FastAPI detail entries. Unknown fixture/custom text remains FIXTURE mode, with insufficient findings and warning. LIVE and MODEL are reserved and not emitted in Phase 1.
