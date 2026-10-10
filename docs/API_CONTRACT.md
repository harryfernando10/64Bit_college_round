# API Contract — Phase 2

Base path `/api`; UTF-8 JSON. Pydantic models in `backend/models.py` and TypeScript definitions in `frontend/src/types.ts` are canonical. Extra request properties are rejected.

## Endpoints

- `GET /api/health`: status, service name and phase 2.
- `GET /api/scenarios`: curated scenario inputs; these only provide a fixture verdict when scenario ID, answer and entire source list exactly match.
- `POST /api/audit`: source-driven audit for every other valid request.

Request shape remains `{answer, sources, scenario_id?}`. Answer is 1–20,000 code points, source count 1–8, source text 1–30,000, title 1–160, and IDs match `[A-Za-z0-9_-]+` and are unique. Whitespace-only text is rejected. Invalid input returns HTTP 422.

## Response and semantics

Response retains `audit_id`, `execution_mode`, exact input echo, `source_sentences`, `claims`, `summary` and `warnings`. Mode is `FIXTURE` for an exact curated fixture and `BASELINE` otherwise. No runtime model or external network is used. Findings retain the Phase 1 claim/evidence/check shape. All custom claims have original text and half-open Python Unicode code-point offsets.

- `SUPPORTED`: only normalized textual identity with a supplied passage, a narrow string-level rule; it does not mean the source is authoritative or the statement true in the world.
- `CONTRADICTED`: one comparable numeric value with matching units or one comparable date differs, with highly overlapping content context and no competing values/dates; or narrowly scoped negation/antonym wording differs while the remaining unquoted token sequence is identical. These rules are deliberately narrow.
- `AMBIGUOUS`: baseline finds directly contradictory supplied passages, or a limited causal qualification pattern.
- `INSUFFICIENT_EVIDENCE`: everything else, including retrieved but inconclusive passages and no retrieval.

Retrieval uses deterministic BM25-style term-frequency ranking within supplied sentences. The highest eligible passage from each supplied source is reserved before adding further candidates, so a verbose source does not crowd every other document out; up to `max(3, source_count)` passages are returned (eight sources is the API maximum). The score is internal discovery ranking only and is not exposed as confidence. Quoted passages are not used by deterministic checks or the exact-text support rule because attribution is unresolved. Exact quotation and source span integrity are checked by Pydantic; a validated quote proves presence, not relevance or truth. The current lightweight sentence splitter can mishandle abbreviations and some punctuation patterns.

Summary counts must exactly match returned claims. Fixture outputs remain curated and are disclosed as fixtures. Validation, retrieval or API failures are not converted into confident findings. Empty answers and duplicate IDs return 422.
