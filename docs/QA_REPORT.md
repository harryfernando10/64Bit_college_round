# Refutella Exploratory QA Report

**Test date:** 2026-10-10  
**Branch:** phase-4-evaluation-demo  
**Scope:** Live browser exploration, Playwright setup, API/source-limit investigation, existing backend checks, and focused test/documentation additions. No application behavior or backend implementation was changed.

## 1. Executive summary

Refutella loaded in Chromium at http://localhost:5173/. Its Vite proxy reached the running FastAPI backend. Browser checks exercised all three scenarios, custom audits, claim selection and evidence traces, all three Evidence Stress Lab operations, the source-count boundary, validation failures, responsive layout, and recovery from an intentionally interrupted request.

The reported “Run audit disables at about four sources” behavior is **not a four-source limit defect**. A new source is created with a title and empty body. Run audit is disabled while any answer/title/body is blank or whitespace. At two sources, the blank draft disabled the button; whitespace remained disabled; entering non-whitespace text re-enabled it. The browser test populated each short source through eight total sources and successfully ran an audit. The API accepted eight sources (HTTP 200) and rejected nine (HTTP 422), matching the documented 1–8 contract. The UI gives no inline explanation for the disabled state, a minor usability issue. No source-limit code change was warranted.

Final checks: **39/39 backend tests passed; deterministic evaluation passed (12/12 fixed labels plus 3 stress cases); Playwright passed (7/7, plus a subsequent individual rerun of the punctuation-only assertion); TypeScript/production build passed; git diff --check passed.** The evaluation is a narrow rule-aligned regression set, not a general accuracy estimate. Actual NLI inference was not attempted.

**Readiness verdict: Ready with known limitations.** The deterministic demo workflows are stable in the tested environment. Optional NLI is unconfigured, visible header elements are placeholders, and several accessibility, race, long-input and alternate stress scenarios remain untested.

## 2. Environment and test setup

| Item | Observed |
|---|---|
| Git branch | phase-4-evaluation-demo; remained unchanged |
| Initial working tree | Clean. Git required a per-command safe.directory override because the checkout is owned by BUILTIN/Administrators; no Git config was changed. |
| Frontend | Existing Vite server loaded at http://localhost:5173/ and was reused by Playwright. |
| Backend | /api/health returned HTTP 200 and service refutella-api through Vite’s proxy; scenario and audit requests also succeeded. Direct PowerShell socket probes were sandbox-blocked, so browser/API observations are the health evidence. |
| Versions | Node 24.19.0; npm 11.17.0; Python 3.12.14 from .venv; @playwright/test 1.64.0; Chromium for Testing 156.0.8078.4 (Playwright build v1248). |
| NLI | REFUTELLA_NLI_MODEL_PATH unset in the test shell. No model weights or NLI packages installed; no real inference run. |
| Changes | Browser test setup/tests, test ignores, setup documentation, and this report only. No application code, fixture, or existing test changed. |

The first sandboxed pytest attempt stalled because Starlette TestClient could not create its local socket pair. Rerunning outside the network-restricted sandbox succeeded. No server was started, stopped, or killed.

Playwright was added to frontend/package.json and its lockfile; Chromium was installed using the Playwright installer. frontend/playwright.config.ts reuses or starts Vite on port 5173 and expects the real FastAPI backend on 127.0.0.1:8000. Failure screenshots/traces are enabled; frontend/test-results is Git-ignored.

## 3. Complete interactive-control inventory

Inventory is based on the rendered accessibility tree/DOM and actual clicks or changes.

| Control / accessible name | Intended purpose | Observed behavior | Status |
|---|---|---|---|
| Brand link “refutella.” | Return to workspace/top level | Keeps the same page/path; href # does not navigate elsewhere. | Same-page link, no route navigation |
| “Evidence review” and status dot | Status display | Noninteractive text. | Presentational |
| Project menu / “Workspace” | Open workspace menu | Click caused no menu, navigation, or visible state change. | Visible placeholder |
| Avatar “R” | Profile access | Plain text, not a button or link. | Presentational placeholder |
| Sample scenario select | Load a curated scenario | All three options changed answer, source, fixture findings, label, and audit result. Switch and refresh worked. | Works |
| Answer under review textarea | Edit answer | Updated counts; edits cleared stale results; whitespace disabled Run audit. Unicode and punctuation-only inputs were accepted. | Works; punctuation-only text is one insufficient-evidence claim |
| Selected answer span | Show selected claim and offsets | Updated after claim selection; matches returned claim spans. | Presentational, correct updates |
| Source title and source text fields | Edit source metadata/evidence | Edits clear stale findings. Whitespace body keeps Run audit disabled. | Works |
| Source count and IDs | Show count and IDs | Count updates; IDs are displayed as read-only text. | Status display |
| + Add source | Add editable source | Creates title “New source” with empty body; audit stays disabled until body has non-whitespace text. Enabled to count 8; disabled at 8. | Works; missing reason text |
| Source removal in editor | Remove an input document | No source-removal control exists in the editor. Scenario switch/restore replaces input. Stress Lab removal is separate. | Not implemented |
| Run audit | Submit current answer/sources | Real API requests produced fixture/baseline results. Disabled for empty/whitespace required fields. Repeat edits/audits replaced old result. | Works |
| Claim review cards | Select claim | Selected state, answer highlight, verdict, note, and evidence trace updated. | Works |
| “Original order” and arrow | Show ordering | Text/icon only; clicking does not sort. | Presentational; sorting absent |
| Evidence trace / quote card | Show source and justification | Selected claim showed matching source, sentence ID, quote, offsets, and validation. Caveat says quote existence does not prove truth. | Works |
| Stress Lab Source select | Choose source | Listed baseline sources. | Works |
| Stress Lab Change select | Choose REMOVE_SOURCE, REMOVE_PASSAGE, EDIT_PASSAGE | Each operation exposed expected conditional controls and ran. | Works |
| Retrieved passage select | Select eligible evidence | Appeared for passage operations and listed retrieved sentences. | Works for tested evidence |
| Replacement text | Edit passage | Accepted replacement and displayed changed text. | Works |
| Run experiment | Submit stress operation | Disabled until required selection/text existed; returned comparisons and warnings. | Works for all three |
| Restore scenario | Reload canonical inputs | Appeared after edit; restored answer/source and reran fixture audit. | Works |
| Error Retry | Retry API failure | Controlled network abort showed useful error; Retry succeeded after removing abort. | Works |
| Footer and other icons | Decoration | No links or click actions exposed. | Presentational |

No profile menu, sort menu, navigation drawer, tooltip, input-source delete button, or standalone clear/reset control was found.

## 4. Feature-by-feature test matrix

Status definitions: PASS = tested and matched observed/documented behavior; FAIL = reproducible defect; BLOCKED = environment prevented verification; NOT TESTED = not exercised. Contract-expected HTTP 422 responses are not app failures.

| Test ID | Feature and actions | Expected | Actual | Status / evidence |
|---|---|---|---|---|
| QA-001 | Fresh load, select Harbor/Library/Garden, refresh, edit and restore | Canonical input and fixture result; totals match; restore returns fixture | Harbor: 3 claims (1 supported, 1 contradicted, 1 insufficient); Library: same; Garden: 2 (1 supported, 1 ambiguous). Refresh and restore worked. | PASS — Playwright scenario test |
| QA-002 | Switch scenarios and select final claim | New scenario replaces old result; evidence follows selected claim | Inputs/findings changed correctly and claim trace updated. Stress-result clearing on scenario change was not separately asserted. | PASS; stress reset NOT TESTED |
| QA-003 | Exact supported custom claim; inspect API payload/trace | BASELINE; totals and spans consistent; exact quote matches source offsets | BASELINE supported result; counts and tested claim/evidence slices matched; quote validation true. | PASS — custom audit test |
| QA-004 | Contradictory positive/negative sources | AMBIGUOUS | UI showed one ambiguous claim. | PASS — custom verdict test |
| QA-005 | Claim date 2025 vs source date 2024 | Narrow date mismatch is CONTRADICTED | UI showed one contradicted claim. | PASS |
| QA-006 | Claim asks absent reviewer favorite color | INSUFFICIENT_EVIDENCE | UI showed insufficient evidence and baseline disclosure. | PASS |
| QA-007 | Unicode, whitespace, punctuation-only answer | Unicode supported; whitespace blocked; punctuation does not crash | Unicode audited; whitespace disabled audit and cleared old results; !!! became one insufficient-evidence claim. | PASS |
| QA-008 | Add/populate sources from 1 through 8; run at 8 | Empty drafts block; populated inputs through limit accepted | Blank/whitespace disabled; filling each short source enabled; max add disabled at 8; 8-source audit succeeded. | PASS — source-boundary UI test |
| QA-009 | Direct API with 8 vs 9 sources | 8 accepted, 9 rejected | HTTP 200 for 8; HTTP 422 for 9. | PASS — live proxied API |
| QA-010 | Remove retrieved supporting passage | Baseline preserved; rerun; comparison/evidence displayed | Changed passage identified; baseline evidence remained; outcome UNRESOLVED. | PASS — stress UI test |
| QA-011 | Edit retrieved passage with non-identical replacement | Replacement reruns engine and compares output | Replacement displayed; outcome UNRESOLVED in baseline mode. | PASS |
| QA-012 | Remove only source | Empty context reported as incomparable | UI showed NOT_COMPARABLE; API tests also verify no perturbed audit when all evidence is removed. | PASS |
| QA-013 | Edit source after audit | Old result cleared | Findings disappeared; audit remained enabled. | PASS |
| QA-014 | Health, whitespace answer, duplicate IDs, 9 sources, 20,001-char answer, unknown stress source | Health 200; invalid requests return readable 422 | Health 200; invalid requests returned 422; unknown source returned “Unknown source_id” detail. | PASS — live API through proxy |
| QA-015 | Abort audit, inspect error, retry | Useful error and successful recovery | API-unavailable alert appeared; retry succeeded against live backend. | PASS — controlled Playwright abort, not backend shutdown |
| QA-016 | Workspace menu, brand link, 1280×800 and 390×844 | Controls/layout behave and remain usable | Menu inert; brand stayed on same path; no horizontal overflow at 390px; answer visible. | PASS for observed behavior; menu placeholder logged |
| QA-017 | Rapid double submit, change scenario while request pending, backend stop/start | No stale/duplicate result; recovery | Not exercised against real service. Request-sequence guard inspected but not load-tested. | NOT TESTED |
| QA-018 | 30,000-char source, title limit, duplicate IDs via UI, editor delete | Boundary and recovery | Short bodies tested. No editor delete control exists. These long input limits were not sent. | NOT TESTED except control absence |
| QA-019 | Remove irrelevant/corroborating/conflicting sources; edit to contradictory/empty/long/Unicode | Correct comparison and immutability | Existing API tests cover relevant subsets including irrelevant source, conflicting/edit behavior, invalid IDs, and unchanged edits. Not all permutations were browser-tested. | API-TESTED subset; browser NOT TESTED |
| QA-020 | Keyboard-only and screen-reader audit | Operable and announced controls | Accessible locators worked; no assistive technology or full keyboard-only review performed. | NOT TESTED |

## 5. Source-limit investigation

### Reproduction

1. Open Harbor fixture: 1 source; Run audit enabled.
2. Click + Add source. Count becomes 2; new title is “New source”; body is empty. The DOM marks Run audit disabled.
3. Enter whitespace: still disabled, with no inline explanation.
4. Enter non-whitespace source text: Run audit becomes enabled.
5. Repeat through 8 total sources. Each populated source enables audit; at 8, + Add source becomes disabled.
6. Run at 8 populated short documents: succeeds in baseline mode. Direct API request: 8 sources → HTTP 200; 9 → HTTP 422.

### Finding and cause

The trigger is **any invalid/empty source draft**, not source count four. The frontend disabled expression rejects a blank answer, no sources, blank title, or blank body. Pydantic in backend/models.py validates non-whitespace fields and source count 1–8. The API contract and UI max agree. The add-source control creates a blank body, so every new draft blocks audit until filled.

No app fix was made because the behavior matches validation. Recommended UX improvement: explain beside the disabled button that every source needs a non-whitespace title and body. The editor also lacks a remove-draft control; restoring or switching scenario is the workaround.

## 6. Bug register

| ID | Severity | Finding | Reproduction / expected vs actual | Cause / fix | Regression / remaining risk |
|---|---|---|---|---|---|
| UX-01 | Low | Disabled audit has no reason text for incomplete source | Add blank source: button disables at count 2. Contract behavior is correct; user receives no explanation. | Empty body fails intentional validation. No fix; recommend inline hint/required state. | E2E verifies blank/whitespace disabled and populated enabled. “Four sources” report explained by accumulated empty drafts. |
| UX-02 | Low | Workspace menu appears actionable but is inert; avatar is static | Click Project menu: no effect; R is plain text. | No handler/interactive semantics; likely mock header. No fix to avoid unrelated UI work. | E2E records inert behavior; may confuse judges. |
| INFO-01 | Low metadata | Phase labels lag feature scope | Footer says Phase 02 and health returns phase 2, while project README/architecture describe Phase 3 Stress Lab. | Stale labels/metadata. No code change. | Not behavior-breaking; align if phase is presented to judges. |

No reproducible core audit, evidence-integrity, scenario, source-limit, or stress defect was found in tested flows. INFO-01 is a consistency issue, not an engine failure. No application-code fix was necessary.

## 7. Test results

| Command | Result |
|---|---|
| .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider | **39 passed**, one Starlette/AnyIO deprecation warning, 1.10s. Exit 0. Pytest then emitted a temporary-directory cleanup PermissionError (WinError 5) for AppData/Local/Temp/pytest-.../pytest-current; this was post-test environment cleanup. |
| .venv/Scripts/python.exe -m pytest tests/test_evaluation.py -q -s -p no:cacheprovider | **1 passed**; 12/12 fixed labels matched (3 supported, 3 contradicted, 5 insufficient, 1 ambiguous); 3 stress behavior cases passed. |
| npm.cmd run test:e2e -- --reporter=list | **7 passed** against live frontend/backend, 9.6s. Updated punctuation-only assertion also passed individually. |
| npm.cmd run build | **Passed** TypeScript project build and Vite production build (1,566 modules). |
| git diff --check | **Passed**; only CRLF-conversion notices. |
| npm.cmd install --save-dev @playwright/test | Added Playwright packages. npm reported 7 dependency advisories (2 moderate, 5 high). npm audit JSON could not reach registry.npmjs.org (ENOTFOUND), so advisory package details were unavailable. No automatic fix/upgrade attempted. |

Changes are limited to .gitignore, README.md, docs/TEST_PLAN.md, frontend/package.json and lockfile, frontend/tsconfig.node.json, frontend/playwright.config.ts, frontend/e2e/refutella.spec.ts, and this report. Fixtures, backend implementation, and existing tests were not changed or weakened. No commit, push, merge, or branch switch occurred.

## 8. Browser diagnostics

Playwright recorded browser console errors, uncaught page errors, failed requests, and API responses with status ≥400.

- Six normal workflow tests: no console errors, uncaught exceptions, failed requests, or unexpected API HTTP failures.
- The validation test deliberately made five invalid API requests. Each returned expected HTTP 422: whitespace-only answer, duplicate IDs, 9 sources, 20,001-character answer, and unknown stress source. Chromium logged its normal “Failed to load resource: 422” console message for each. These were expected validation outcomes, not frontend crashes.
- A controlled Playwright route aborted one audit request. One requestfailed event (net::ERR_FAILED) and its console resource error were recorded. UI showed API unavailable; Retry succeeded after the route was removed.
- No unexpected API 4xx/5xx, page exception, or other console error was observed. No sensitive request bodies were logged.

The 422 details were inspected; health returned 200 through the frontend proxy. Direct PowerShell probes were sandbox-blocked and were not treated as evidence the servers were down.

## 9. Evaluation limitations

- Exact unchanged scenario inputs return curated FIXTURE findings, visibly distinguished from custom audits.
- Custom input without an optional model uses deterministic BASELINE: lexical retrieval, narrow identity/value/date/polarity rules, and conservative abstention. Retrieval relevance is not proof; quote offsets establish provenance, not truth.
- The 12-case evaluation and 3 stress workflows are deliberately rule-aligned regression cases, not a general reliability estimate, benchmark, calibration measure, or semantic-understanding test.
- Backend mocked NLI tests exist, but no model weights/dependencies were installed, REFUTELLA_NLI_MODEL_PATH was unset, and no real inference was attempted. Keep NLI disabled for demo unless local inference is installed and smoke-tested.
- Known limitations include abbreviations/punctuation segmentation, paraphrase support, structured tables, unrelated numeric context, and general reasoning. Punctuation-only answer !!! becomes a claim marked insufficient evidence; it did not crash.
- Browser coverage is not screen-reader, race/load, or backend shutdown testing. Transport failure used a controlled Playwright abort, not a stopped backend.

## 10. Recommendations

### Must fix before the hackathon

- No confirmed functional blocker from this pass. Keep NLI disabled unless real local inference is installed and verified.
- Do not describe the 12-case evaluation as general accuracy or the Stress Lab as testing memory leakage.

### Recommended if time permits

- Explain why Run audit is disabled when a source title/body is blank; add a remove-source control if editing multi-source input is part of the demo.
- Implement the Workspace menu or render it as noninteractive text; clarify whether the R avatar is decorative.
- Align Phase 02 footer/health metadata with the Phase 3 product description if those labels are user-facing.
- Investigate the 7 dependency advisories with working npm advisory access; review compatibility before any upgrade.
- Add browser coverage for double submission, scenario switches while pending, long field limits, editor deletion, irrelevant/conflicting source removal, contradictory/empty/Unicode passage edits, and actual backend restart recovery.
- Perform keyboard-only and screen-reader checks. Playwright accessible locators are not a full accessibility audit.

### Out of scope

- Do not expand into a general truth checker, broad online research, semantic claim decomposition, history/export, or persistence as part of this QA pass.
- Do not add uncalibrated confidence claims or present fixtures as a representative benchmark.

## 11. Demo walkthrough

1. Start FastAPI as documented and open http://localhost:5173/. Harbor loads in Fixture mode; explain it is curated.
2. Select the contradicted 84-volunteer claim and point out the source excerpt saying 48, source ID, quote offsets and exact-quote validation. State that quote presence is not truth.
3. Select Garden trial summary and inspect its supported and ambiguous fixture claims. Use Restore scenario after edits.
4. For live custom behavior, enter “The review was completed in 2025.” and source “The review was completed in 2024.” Run audit and show Evidence-based baseline and narrow date check. Try an absent detail for insufficient evidence or conflicting sources for ambiguous output.
5. Establish a supported exact-text baseline with a second irrelevant sentence. In Stress Lab remove the retrieved support passage and compare baseline/perturbed evidence and UNRESOLVED result. Repeat with Edit passage and a replacement.
6. Optionally remove the only source to demonstrate NOT_COMPARABLE when no context remains.
7. Explain NLI was not exercised and keep baseline mode for reproducibility. Do not present Stress Lab as evidence of memory leakage.

Avoid leaving an empty source draft: audit is disabled until its body has non-whitespace text. The editor has no source-delete button; restore or switch scenarios to return to a clean set.

## 12. Final readiness verdict

**Ready with known limitations.** Tested demo workflows passed against the real local frontend and FastAPI backend; regression tests/build passed. No confirmed core defect requires an application-code fix. Remaining risks: incomplete header controls, no explanation for required source fields, no editor source deletion, unverified real NLI, dependency advisories with unavailable detail, and untested accessibility/race/long-input/backend-restart scenarios.

---

## Follow-up: UX polish and document uploads (2026-10-10)

This follow-up supersedes the relevant UX findings above and preserves the original QA record. It adds local document extraction and focused browser coverage. The working branch remains `phase-4-evaluation-demo`; no commit, push, or branch switch was made.

### Changes and observed behavior

- **Disabled audit feedback:** the input panel now reports the first blocking field in an accessible live status (for example, “Source 2 is missing its text.”). Browser assertions verify the message appears for blank/whitespace source content and clears when text is entered. The existing 1–8 source and text-length rules are unchanged.
- **Header controls:** the Workspace label, R avatar, and brand are now noninteractive presentation. The “Original order” pseudo-control is now a static “Claim order · original answer” label; no unsupported sorting behavior is implied.
- **Phase label:** the footer and `/api/health` now report Phase 03/3, consistent with the implemented workspace and Evidence Stress Lab.
- **Source removal:** each editable source has a named remove button. It removes the corresponding uploaded or manual document and clears the affected audit/stress results.
- **Document upload:** the source card accepts `.txt`, text-based `.pdf`, and `.docx` via the native chooser, multi-selection, or drag-and-drop. Backend extraction runs in memory and returns the safe basename, type, byte count, and extracted text. The frontend appends it as a normal editable source with a fresh ID; the existing `/api/audit` path processes it alongside manually entered sources. Failed files produce per-file errors and do not discard valid sources. Uploads are sequential, and the UI caps their combined count with manual sources at eight.
- **Server validation:** default file size is 10 MiB (`REFUTELLA_MAX_UPLOAD_BYTES`), extracted text must fit the existing 30,000-character source limit, and DOCX uncompressed content is capped at 20 MiB. UTF-8 text, PDF signature/encryption/readability, DOCX ZIP/OOXML structure, nonempty extraction, and unsupported extensions are checked. TXT/PDF/DOCX are never written to permanent storage. The API returns 413 for size/expanded text limits, 415 for unsupported extensions, and readable 422 details for malformed or empty input.
- **Extraction limitations:** OCR is not implemented. A PDF with no extractable text explains that it may be scanned/image-only. Complex PDF columns/tables can have imperfect reading order. DOCX table cells and paragraphs are included; formatting and macros are not interpreted.

### Browser and screenshots

The actual Playwright suite ran Chromium against the live Vite frontend and FastAPI backend through the Vite `/api` proxy. It verified native file chooser use for TXT/PDF/DOCX, extracted text in editable fields, a regular source-driven audit (`BASELINE`, one `SUPPORTED` claim), manual/uploaded source composition, source removal, drag-and-drop, multi-file selection, the eight-source limit, invalid-upload recovery, scenario switching after upload, the original scenarios, evidence traces, and the three Stress Lab operations. No mocks were used for upload or audit.

Reviewed screenshots (1440×900, 1280×800 and 390×844) are saved in `docs/qa-screenshots/`. Before captures use the unchanged Git baseline; after captures use the updated app.

Before captures:

- `before-initial-workspace-1440.png`
- `before-custom-evidence-trace-1440.png`

After captures:

- `after-initial-workspace-1440.png`
- `after-custom-evidence-trace-1440.png`
- `after-source-management-1280.png`
- `after-uploaded-document-1280.png`
- `after-stress-lab-1280.png`
- `after-mobile-workspace-390.png`

The paired initial and custom-evidence screenshots were visually reviewed. The 390-pixel screenshot showed no horizontal overflow; the updated upload state, source editor, finding trace and Stress Lab were also reviewed. The temporary baseline server timed out during later capture steps, so before images for the multi-source and Stress Lab states are unavailable. These are visual reviews, not automated pixel-diff assertions. The Git baseline files were not restored over the working tree.

### Regression results

- Backend: `& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` — **49 passed**, 1 Starlette/AnyIO deprecation warning. Pytest also emitted the pre-existing Windows temp-directory permission warning during its exit cleanup; the process exit code was 0.
- Upload API subset: `& .\.venv\Scripts\python.exe -m pytest tests\test_uploads.py -q -p no:cacheprovider` — **10 passed**. Coverage includes TXT/PDF/DOCX, paragraphs and tables, encrypted PDF, malformed/corrupt and empty files, upload size, filename sanitization, mislabelled/binary TXT, eight-source boundary, and flow into the normal audit.
- Evaluation: `& .\.venv\Scripts\python.exe -m pytest tests\test_evaluation.py -q -s -p no:cacheprovider` — **1 passed**, exact expected label counts **12/12**, plus 3 stress behavior cases. This remains a small fixed regression set; the paraphrase NLI case is mocked.
- Browser: from `frontend/`, `npm.cmd run test:e2e -- --reporter=list` — **13 passed** against Chromium and the real local services.
- Frontend: from `frontend/`, `npm.cmd run build` — TypeScript and Vite production build passed (1,566 modules).
- `git diff --check` passed after the final implementation and documentation edits (Git printed only its usual line-ending normalization warnings).

### Diagnostics and limits

Successful browser tests produced no unexpected console errors, uncaught exceptions, failed requests, or API failures. The unsupported `.rtf` upload correctly returned HTTP 415; existing invalid API scenarios produced their expected HTTP 422 responses; the transport-failure test intentionally aborts an audit and records `net::ERR_FAILED`, then verifies the UI error/retry behavior. Chromium logs the expected HTTP/resource error lines for these deliberate failures.

The optional NLI environment variable remains unset; no model weights or real NLI inference were used. No real backend stop/restart, assistive-technology audit, rapid concurrent upload stress, maximum-size valid document, malicious-document security test, or OCR test was performed. This upload route has bounded in-memory processing but is not a full document security scanner.

### Updated readiness

**Ready with known limitations.** Scenario, custom audit, evidence trace, Stress Lab and new TXT/PDF/DOCX source workflows passed the tested browser/API checks. Uploads reach the existing audit engine, and manual entry still works. Keep OCR and real NLI out of the demo claims. The multi-source and Stress Lab before screenshots and full keyboard/screen-reader audit remain outstanding; none was silently counted as passed.

## Phase 5A verification (2026-10-10)

Initial Git inspection: branch `phase-5-evidence-intelligence`; working tree clean before edits. No branch switch, commit, push, or merge was performed.

- Backend: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` — **53 passed, 1 skipped** (the opt-in local NLI smoke test), one existing AnyIO deprecation warning. Pytest also printed a Windows temp-directory cleanup `PermissionError` in its atexit cleanup after the successful exit; it did not change the test result.
- Evaluation: `tests/test_evaluation.py` — **12/12 curated labels**, plus all **3 stress cases** passed. The label counts are a controlled project regression set, not a reliability estimate.
- Browser: `npm.cmd run test:e2e -- --reporter=list` — **14 passed**, including triage display/override, readable source labels, all prior app flows, and regenerated presentation screenshots. Browser diagnostics found no unexpected console/API failures; intentionally invalid requests are part of the suite.
- Frontend: `npm.cmd run build` — TypeScript and Vite production build passed.
- `git diff --check` — passed.
- NLI: actual local CPU inference **ran** against the pinned weights downloaded to ignored `models/refutella-nli`. Optional runtime versions: PyTorch 2.14.1 CPU, Transformers 4.57.6, SentencePiece 0.2.2, Safetensors 0.8.0, Tokenizers 0.22.2. Model loading took about 17 seconds. Warm pair latencies were approximately 0.08–0.29 seconds. The focused test passed for direct entailment, contradiction, neutral, and a simple paraphrase. A separate “four weeks” / “one month” paraphrase was classified as contradiction. No RAM measurement was available; no general accuracy claim is made. Raw logits are exposed as uncalibrated classifier outputs, not truth probabilities. Default app mode remains baseline unless explicitly configured.

The model-card verification at the pinned revision is documented in `docs/RESEARCH_NOTES.md`. Captured screenshots in `docs/qa-screenshots/` reflect the updated finding presentation.
# Phase 5B verification

Phase 5B verification on 2026-10-11: backend suite **60 passed, 1 skipped**; curated evaluation **12/12** plus **3 stress cases**; Playwright **15/15**; TypeScript/production build passed; `git diff --check` passed. Pytest reported the existing AnyIO deprecation and Windows temporary-directory cleanup `PermissionError` after test completion. Browser E2E included screenshot capture and matrix/receipt selection at Unicode source offsets. Duration checks cover fixed week/day conversion and abstention on month/week comparisons, including the observed NLI conflict case. Localization tests verify exact Unicode quantity, date and antonym spans and abstention on multi-value ambiguity. Root `QA_REPORT.md` and untracked root `RESEARCH_NOTES.md` are pre-existing user work and were preserved unchanged.
