# Test Plan

## Automated checks
- Backend unit/schema: request bounds, unique IDs, response counts and exact span integrity.
- API integration: health, scenario listing, successful fixture audit and understandable 422 response.
- Evidence: exact quote equals source slice; source/sentence IDs exist; quote stays inside sentence; answer span equals claim text.
- Fixtures: expected labels and evidence sentence IDs agree; every scenario parses through API model.
- Frontend: npm run build performs TypeScript checking and production bundling.

## Manual and end-to-end acceptance
Start API and Vite, load default scenario, confirm data arrives from GET /api/scenarios, submit via POST /api/audit, inspect selected claim/evidence and fixture label. Change input and confirm insufficient fallback and warning. Stop API and confirm visible error and retry. Keyboard tab through selector, text areas and buttons; check narrow viewport.

## Edge cases
Empty answer/source, duplicate or malformed IDs, unknown fixture, stale scenario ID with edited text, multi-line source offsets, Unicode before a span, punctuation/abbreviations/decimals, compound claims, source not proving claim, quote that exists but is irrelevant, contradictory passages, overlapping claims, invalid evidence IDs, oversized inputs, API unavailable.

## Passing vs assumptions
Tests only establish implemented schema and fixture behavior. They do not establish factuality, verifier accuracy, claim segmentation quality, accessibility audit completion, or model compatibility on team hardware. Phase 1 has no automated browser E2E test. Record actual commands and results in docs/Context.md.
