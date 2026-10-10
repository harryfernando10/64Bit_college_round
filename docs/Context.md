# Project Context — Phase 1 handoff

## Status
Phase 1 foundation implemented. Python dependencies installed in ignored .venv. Frontend dependencies installed in ignored frontend/node_modules. No database, hosted LLM, model weights, or secrets added. Working tree is uncommitted.

## Agreed stack and architecture
React + TypeScript + Vite + Tailwind; Python 3.11+ + FastAPI + Pydantic 2; JSON scenarios; pytest. Vite proxies /api to FastAPI. API contract is shared across backend/models.py and frontend/src/types.ts. Exact fixture match is required to return sample claims; custom material is explicitly unassessed.

## Completed
Health, scenario listing, audit endpoint, request/response validation, fixture data, source and answer offsets, quote/source/sentence integrity, responsive evidence workspace, loading/empty/error states, scenario selector, clickable claim list with code-point-correct answer span highlight, API-driven results, README and six required project documents. Default demo scenario harbor-plan includes supported, contradicted and insufficient findings.

## Files created
.gitignore; .env.example; requirements.txt; README.md; backend/__init__.py; backend/models.py; backend/main.py; backend/service.py; frontend/package.json; frontend/package-lock.json; frontend/index.html; frontend/vite.config.ts; frontend/tsconfig.json; frontend/tsconfig.app.json; frontend/tsconfig.node.json; frontend/postcss.config.js; frontend/tailwind.config.js; frontend/src/App.tsx; frontend/src/main.tsx; frontend/src/style.css; frontend/src/types.ts; frontend/src/vite-env.d.ts; data/scenarios/harbor-plan.json; data/scenarios/library-hours.json; data/scenarios/garden-trial.json; tests/test_api.py; docs/SRS.md; docs/ARCHITECTURE.md; docs/API_CONTRACT.md; docs/TEST_PLAN.md; docs/RESEARCH_NOTES.md; docs/Context.md.

## Checks actually run
- Backend: .venv/Scripts/python.exe -m pytest -q — 5 passed, 1 upstream Starlette deprecation warning.
- Frontend: npm.cmd run build — TypeScript project check and Vite production build succeeded (Vite 8.3.4).
- Runtime smoke check: started local FastAPI and Vite processes; health returned 200, frontend returned 200 with Refutella title, proxied scenarios returned 200 with harbor-plan first, proxied fixture audit returned 200 in FIXTURE mode with expected counts (1 supported, 1 contradicted, 1 insufficient).
- npm install reported 7 advisories (2 moderate, 5 high). npm audit endpoint could not be reached from the sandbox, so details and remediation remain unverified. Review before production.
- HHEM-2.1-Open model card reviewed. Inference was not run; no model dependencies or weights downloaded. Details/limits in RESEARCH_NOTES.md.

## Known limitations
No arbitrary-input verifier, BM25, deterministic numeric/date/negation checker, model adapter, persistent history, export, safety evaluation, or Evidence Stress Lab. Sentence segmentation is punctuation-based and may split abbreviations/decimals incorrectly. Fixtures are demonstrations, not benchmark evidence. Frontend browser automation/accessibility audit is not automated. Custom source inputs with invalid blank source text return 422.

## Decisions not to change casually
Four verdict enums and three verification tiers are stable. Offsets are half-open Python Unicode code-point offsets into exact original text. Quote validity means source text integrity only. Missing evidence is not contradiction. Fixture output must remain labelled. UI must render API findings, not local hardcoded verdict objects. Local model support must be optional, revision-pinned, and never download weights silently.

## Git checkpoint
Current branch: main. No commits exist yet; upstream tracking says origin/main is gone. Configured origin is https://github.com/harryfernando10/64Bit_college_round (fetch/push); not changed and no push attempted. Git status also showed a pre-existing untracked %SystemDrive%/ path containing ProgramData; it was not inspected beyond listing and must not be staged. No files have been staged or committed.

## Next phase
Member 1: add tested claim segmentation, lexical/BM25 candidate retrieval, and narrow deterministic checks behind current models. Member 2: refine claim highlighting and responsive/error states against live API. Member 3: expand reviewed labelled fixtures and reproducible metrics. Keep Phase 1 fixture checks intact.

**Recommended next action:** review the tracked file list and npm advisories, then checkpoint only the Refutella files with the README's git add command; explicitly exclude the pre-existing %SystemDrive%/ path. After that, begin Phase 2 with claim segmentation and labelled evaluation examples.
