# Refutella

Refutella is an evidence-first audit workspace for inspecting AI-generated claims against user-provided source material. Its principle: **Don't blindly trust the answer. Don't blindly trust the auditor either.**

## Product direction

Intended users include readers, researchers, students, and reviewers. The long-term product includes claim verification, validated source references, precise localisation, narrow deterministic checks, reasoning consistency, uncertainty-aware reporting, safety flags, audit history/export, a labelled evaluation set, and the Evidence Stress Lab for controlled evidence edits. These are future goals, not current capabilities or novelty claims.

## Phase 2

React/TypeScript/Vite/Tailwind frontend; Python/FastAPI/Pydantic backend; version-controlled JSON fixtures; API-loaded scenario picker; validated character spans; useful errors and fixture labels. Exact unchanged fixture inputs retain their curated results. Other inputs use a local evidence-based baseline: sentence-span claims, BM25-style lexical passage retrieval and narrow number/date/polarity checks. In baseline mode, support requires normalized whole-claim textual identity; optional model mode can additionally use NLI for paraphrased passages. Lexical similarity alone never supports a claim. An optional local NLI verifier can be enabled with pre-installed dependencies and locally cached model files; it is off by default and makes no audit-time network calls. Quote validation proves presence at offsets, not truth.

## Phase 3

The Evidence Stress Lab uses the current audit as its baseline and reruns the same audit engine after removing one source, removing a retrieved passage, or editing that passage. Results are request-scoped and include claim-by-claim verdicts and evidence. Fixture baselines and differing execution modes are flagged as not directly comparable. See `POST /api/stress-experiment` in the API contract. The controlled examples are not a general evaluation or a test of parametric memory leakage.

## Structure

- frontend/src: UI, styles, API types
- backend: routes, models, fixture service
- data/scenarios: example audits and expected labels
- tests: API and fixture consistency tests
- docs: SRS, architecture, API contract, test plan, research and handoff

## Prerequisites

Python 3.11+, Node.js 20.19+ (required by Vite 8), npm, Git. Python and npm were unavailable as callable commands in the implementation environment; Node was available. See docs/Context.md for verification status.

## Windows PowerShell setup

From repository root, run:
    py -3.11 -m venv .venv
    .venv/Scripts/python.exe -m pip install -r requirements.txt
    cd frontend
    npm install
    cd ..


Start backend in terminal 1 from root:
    .venv/Scripts/python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

Optional local NLI mode (offline at audit time): install `.venv/Scripts/python.exe -m pip install -r requirements-nli.txt`, run the pinned `hf download` command in `docs/RESEARCH_NOTES.md`, then set `$env:REFUTELLA_NLI_MODEL_PATH = "models/refutella-nli"` before starting the backend. Missing dependencies or files leave the baseline available and return `MODEL_UNAVAILABLE`; no model weights are bundled or fetched by the API.


Start frontend in terminal 2:
    cd frontend
    npm run dev


Open Vite's printed URL (normally http://localhost:5173). The Vite proxy forwards /api to 127.0.0.1:8000. FastAPI docs: http://127.0.0.1:8000/docs.

## Checks

From repository root, run the backend suite:
    .venv/Scripts/python.exe -m pytest
Run only the reproducible API evaluation and print its counts:
    .venv/Scripts/python.exe -m pytest tests/test_evaluation.py -q -s -p no:cacheprovider
From `frontend/`, run the TypeScript check and production build:
    npm run build
The build command runs TypeScript checks and a production build. The evaluation uses 12 fixed single-claim API cases with defensible expected labels and three fixed Evidence Stress Lab behavior cases. One paraphrase case uses a deterministic mocked NLI entailment; it does not measure real model performance. The command prints observed and expected verdict counts, confusion counts and exact-label accuracy. These curated, rule-aligned cases are a regression set, not evidence of general real-world reliability, benchmark superiority or calibrated confidence. No model download or network is needed. See `docs/TEST_PLAN.md` and `docs/DEMO_WALKTHROUGH.md`.

## Sample data and reset

The scenario selector loads fixtures through GET /api/scenarios. Select a scenario and run an audit. Editing answer/source keeps the selected scenario visible, marks the content as modified, and returns explicit insufficient evidence unless the full answer and source set still match a fixture. Use **Restore scenario** to reload its canonical answer and sources, or select another scenario to switch fixtures. Additional sources are included in the audit request and do not receive fixture findings unless the complete input exactly matches a supported fixture.

## Limitations

The baseline cannot reliably verify paraphrases, complex claims, tables, or general reasoning. Optional NLI can also be wrong and has not had actual runtime inference tested in this environment; it is not calibrated. Retrieval may surface irrelevant passages. Numeric normalization and context matching are limited, and sentence splitting can mishandle abbreviations/punctuation. The controlled evaluation suite is not representative of general use. Phase 3 adds a request-scoped Evidence Stress Lab for source/passage removal and passage editing followed by a rerun of the existing engine. These observed outcomes are not a benchmark, reliability estimate, or test of parametric memory leakage; fixture baselines cannot be directly compared with live perturbed engine results. No history or export is included. Offsets use Python Unicode code-point indexes. Model feasibility findings are in docs/RESEARCH_NOTES.md.

## Repeatable demo

Follow [the demo walkthrough](docs/DEMO_WALKTHROUGH.md) for a short sequence using existing fixtures and custom source-driven examples. It records the expected mode labels and cautions where results depend on the current deterministic engine.

## Team workflow and Git checkpoint

Member 1: backend and integration. Member 2: frontend and UI. Member 3: scenarios, evaluation, docs, presentation. Coordinate on docs/API_CONTRACT.md before editing types. Inspect status and diff before committing. Exclude .env, credentials, environments, node_modules, weights and caches.

Recommended checkpoint commands after review:
    git status --short
    git diff --check
    git add README.md .gitignore .env.example requirements.txt backend frontend data tests docs
    git diff --cached --stat
    git commit -m "Build Refutella Phase 1 foundation"
Inspect branch and git remote -v before any push. These steps do not push.
