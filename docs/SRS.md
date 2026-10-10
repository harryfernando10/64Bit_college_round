# Software Requirements Specification

## Overview
Refutella helps a reviewer inspect whether an AI answer is supported by source text supplied for that audit. Fluent answers can mix supported, contradicted, missing, and ambiguous claims.

## Goals
Phase 1 delivers an API-driven workflow, three labelled scenarios, four verdicts, validated text spans, and explicit fixture disclosure. Later goals are measured claim precision/recall, reference validity, localisation, and mutation response against a human-labelled set. No Phase 1 accuracy claim is made.

## Roles and journey
Reviewer chooses a sample or enters answer and sources, runs audit, inspects verdicts and evidence, and interprets limitations. Team roles: backend/integration; frontend/UI; scenarios/evaluation/docs/presentation.

## Functional requirements

| ID | Requirement | Phase | Acceptance evidence |
|---|---|---|---|
| FR-01 | Load sample answer and sources from API library. | 1 | GET /api/scenarios populates selector. |
| FR-02 | Submit answer and sources. | 1 | UI calls POST /api/audit. |
| FR-03 | Return stable verdict, tier, note and optional references. | 1 | Pydantic schema and scenario tests. |
| FR-04 | Validate offsets against original text. | 1 | Schema and fixture tests. |
| FR-05 | Label fixtures in response and UI. | 1 | Response plus UI. |
| FR-06 | Report unmatched text without pretending to verify. | 1 | Insufficient fallback. |
| FR-07 | Validate references without equating quote existence with truth. | 1 | Integrity checks. |
| FR-08 | Provide loading, empty, invalid and backend-error states. | 1 | UI/manual acceptance. |
| FR-09 | Decompose text into carefully qualified claims. | Later | Claim segmentation evaluation. |
| FR-10 | Retrieve evidence and apply narrow checks plus optional verifier. | Later | Reproducible evaluation. |
| FR-11 | Add source mutations, audit diffs, export and history. | Later | Stress Lab and history tests. |
| FR-12 | Evaluate unsafe recommendation flags with stated limits. | Later | Curated safety evaluation. |

## Non-functional requirements
Reliability: malformed payloads produce 422 errors; future verifier failures degrade to insufficient evidence. Usability: statuses, evidence, fixture label and actionable errors are clear. Accessibility: semantic controls, keyboard focus, labels, responsive layout, text and icon alongside colour. Privacy: local Phase 1, no remote model or telemetry. Error handling: unavailable API and invalid input are visible. Maintainability: Pydantic and TypeScript contracts match.

## Data and evidence integrity
IDs are constrained and unique. Text lengths are bounded. Offsets are half-open [start,end) indexes in exact original strings using Python Unicode code points. Claim text must equal its answer slice. Evidence source/sentence IDs must exist; quote equals its source slice and lies within its sentence. Quote validation proves provenance only, not entailment. Missing evidence is not contradiction.

## Error and fallback behavior
Invalid payloads: FastAPI 422. Backend unavailable: UI guidance and retry. Unmatched/custom input: fixture mode, insufficient findings and warning. Future verifier failure: preserve mechanical results and mark unresolved checks insufficient.

## Out of scope
Database, accounts, deployment, OCR, internet fact checking, hosted LLM, downloaded weights, robust linguistic segmentation, safety advice, history/export, Evidence Stress Lab.

## Assumptions and acceptance
Python 3.11+, Node 20+, local use, short hackathon window, no confirmed hosted LLM. JSON is adequate for scenarios. Acceptance includes working frontend/backend, health 200, actual API sample audit rendered, fixture label, matching contracts and offsets, passing tests/build, all docs, documented model status and known limitations.

## Requirement-to-test traceability

| Requirement | Validation |
|---|---|
| FR-01/02 | scenario API and audit integration test |
| FR-03–07 | response schema and fixture span checks |
| FR-08 | manual responsive and error-state review; not automated |
| FR-09–12 | deferred; no Phase 1 pass claimed |
| reliability/data integrity | 422 validation and source/claim offset tests |
| accessibility/usability | keyboard and responsive manual review pending |
