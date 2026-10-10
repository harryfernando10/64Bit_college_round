# Phase 2B Context

Phase 2 source-driven auditing remains the default. Added an optional local NLI adapter for retrieved passages, API response statuses/raw logits, frontend disclosure, opt-in dependency requirements and mocked offline integration tests. Fixture scenarios remain exact-input curated results. No Evidence Stress Lab, database, export, history, authentication or external inference was implemented.

Verification on 2026-10-10: `.venv/Scripts/python.exe -m pytest -q` — 29 passed; `frontend/npm.cmd run build` — TypeScript and Vite production build passed; `git diff --check` — no whitespace errors. Pytest reported existing Windows cache access warnings and an AnyIO deprecation warning. Actual NLI inference was not run: optional ML packages and local weights were absent, and weights were not downloaded. Model research and limitations are in Research Notes.
