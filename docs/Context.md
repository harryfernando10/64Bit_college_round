# Phase 2B Context

Phase 2 source-driven auditing remains the default. Added an optional local NLI adapter for retrieved passages, API response statuses/raw logits, frontend disclosure, opt-in dependency requirements and mocked offline integration tests. Fixture scenarios remain exact-input curated results. No Evidence Stress Lab, database, export, history, authentication or external inference was implemented.

Verification on 2026-10-10: `.venv/Scripts/python.exe -m pytest -q` — 29 passed; `frontend/npm.cmd run build` — TypeScript and Vite production build passed; `git diff --check` — no whitespace errors. Pytest reported existing Windows cache access warnings and an AnyIO deprecation warning. Actual NLI inference was not run: optional ML packages and local weights were absent, and weights were not downloaded. Model research and limitations are in Research Notes.

## Phase 3 Evidence Stress Lab

Added `POST /api/stress-experiment` and a frontend section for request-scoped source/passage removal and passage edits. The endpoint receives the validated baseline response, copies its source documents, validates selected source and retrieved passage IDs, and calls the regular audit service with the original answer and modified context. It never writes fixture files. Fixture baselines are labeled not directly comparable with perturbed engine results; the all-context-removed case returns a successful not-comparable result without attempting an invalid empty-source audit. See API_CONTRACT.md, ARCHITECTURE.md, and TEST_PLAN.md.

Phase 3 verification on 2026-10-10: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` — 38 passed. The command printed one existing AnyIO deprecation warning; pytest also emitted a Windows temp-directory cleanup `PermissionError` during process exit, after reporting success. `frontend/npm.cmd run build` — TypeScript and Vite production build passed. `git diff --check` — passed. Real NLI weights were not available or used; the stress path's unavailable-verifier behavior is tested with the configured missing-model path.
