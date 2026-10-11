# Refutella demo walkthrough

Use the README PowerShell commands to start the backend and frontend in separate terminals, then open Vite's local URL. The scenarios and expected behavior below use existing examples or short inputs entered in the workspace. The app calls the actual local API; timing and rendering depend on the machine.

## Walkthrough (about 4 minutes)

1. **Show a claim and its sources.** Select **Garden trial summary** from the scenario menu. The UI loads the answer and source documents and initially displays the fixture mode label. Explain that this is a curated scenario result, not a fresh inference.
2. **Inspect an exact evidence trace.** Select a claim in the findings list. Point out the exact source excerpt, source ID/sentence ID, character offsets, verdict and verification tier. The quote check establishes provenance at offsets, not truth.
3. **Show contradiction and insufficient evidence.** Edit the answer to contain `The review was completed in 2025.` and replace/add a source sentence `The review was completed in 2024.`; use a distinct source ID. Run audit: the live baseline's narrow date rule is expected to report contradiction. Then change the claim to a detail absent from the sources, such as `The report lists the plant color.` and rerun: expected insufficient evidence. These are source-driven baseline results, not fixture results.
4. **Establish stress baseline.** Set the answer to `The garden trial ended after four weeks.` and a source with that exact sentence plus another sentence (for example, `The garden trial enrolled 48 plants.`). Run audit; expect a baseline exact-text support finding.
5. **Change evidence and compare.** In Evidence Stress Lab, select the report and remove its supporting passage, or edit it to `The garden trial lasted for a month.`. Run experiment. With the baseline verifier and no NLI configured, the changed passage should leave the claim insufficient; inspect the changed text, both evidence columns, outcome and warnings. With an NLI verifier configured, outcomes may differ and must be read with the mode/status disclosure. Repeat with source removal if time permits.
6. **State limitations.** Retrieval is lexical; it can miss relevant paraphrases or select misleading overlap. Deterministic contradiction rules are narrow, and optional local NLI is fallible and uncalibrated. The curated evaluation is small and not representative. A verdict surviving an evidence edit does not demonstrate parametric-memory leakage.

## Document upload (about 1 minute)

1. Select a scenario and show that supplied sources can still be edited directly. The source card also accepts multiple `.txt`, text-based `.pdf`, or `.docx` files through **Upload documents** or drag-and-drop.
2. Upload a small UTF-8 text file or text-based PDF/DOCX. Wait for extraction to finish, point out the filename and type/size marker, and inspect the extracted text in the editable source field.
3. Edit the extracted text if needed, then run the audit. The extracted text is sent as an ordinary source to the existing audit endpoint; manual and uploaded sources share the eight-source maximum.
4. Remove the uploaded source with its remove icon. A failed or unsupported upload shows an inline error and preserves other sources.
5. Explain the limits: 10 MiB per file by default, 30,000 extracted characters per source, scanned/image-only PDFs need OCR (not included), and complex PDF columns/tables may extract imperfectly. Files are processed in memory and not stored by the backend.

## Likely failure points

- If scenarios do not load, confirm the backend is listening at `127.0.0.1:8000` and refresh.
- If edited text is empty or only whitespace, the API correctly rejects the request; the UI disables the audit button for these cases.
- Fixture results and modified live results use different methods. The Evidence Stress Lab labels fixture comparisons not directly comparable.
- Removing the only source or passage may leave no source context; the API returns `NOT_COMPARABLE` because a baseline audit requires at least one source.
- Optional NLI is not required for the demo. If configured but unavailable, the UI/API report the unavailable verifier; do not present it as a successful model-assisted audit.

## Manual browser checklist

- Load each of the three scenarios; verify fixture label, answer, source text and claim details.
- Edit an answer or source and confirm old results disappear; run a new audit and inspect the baseline mode label.
- Add a source, switch scenarios, and restore the selected scenario; confirm content corresponds to the selected scenario.
- Inspect selected answer span and evidence quote offsets, including a Unicode-prefixed claim.
- Submit supported, contradicted, insufficient and conflicting source examples; verify verdict and verification tier are distinct.
- Run source removal, passage removal and passage edit; verify changed text, baseline/perturbed evidence and comparability warnings.
- Try invalid/whitespace input and upload an unsupported extension to inspect validation and recovery. Stop the backend only in a controlled local session to inspect connection error states.
- Check keyboard operation, screen-reader labels, reduced-motion behavior and common laptop-width layout.

Playwright coverage exercises the core scenario, custom audit, stress-lab, upload, and responsive flows against the local FastAPI service. See `docs/QA_REPORT.md` for exact results and remaining manual checks. The optional NLI model was not configured or run.

## Phase 5A demo: compare two sources

This is a live baseline example, separate from the curated scenario selector and fixture findings. Use answer `The garden trial ended after four weeks.` and add two sources:

- Primary report: `The garden trial ended after four weeks.`
- Context note: `The garden trial enrolled 48 plants.`

Run a custom audit, then use Evidence Stress Lab to remove either source. Removing the primary report leaves the second source in context, so the comparison remains meaningful and does not immediately become an empty-context case. The exact-text support result is a narrow text match, not source-authority or world-truth verification.

Question, command, heading and explicit opinion patterns appear as **Not assessed** with an explanation. Select **Include in audit** to run normal claim checks on that span. `S1`, `S2` labels follow current source order; API IDs remain available for traceability.
# Phase 5B review

After running an audit, inspect the claim/source evidence matrix and select a source cell to change the active claim. The selected claim's Search Receipt lists its retrieved passages and offsets. Review flags appear separately and never change verdicts. Duplicate-source labels identify similar supplied text while keeping each source visible.

## Phase 5C tools

After a live audit, use **Mutation & reliability tools** to select an evidence or claim mutation. Read its preconditions, declared expectation, ground-truth limits and warnings before running it. Compare the actual baseline and perturbed claim traces; a verdict change is not proof that the original result was wrong, and an unchanged verdict does not prove independence. The Judge Challenge panel only scores a completed comparable claim run when the catalog declares a testable expectation; inconclusive cases remain unscored. Use Reset challenge session to clear displayed session counts.

The receipt export asks for confirmation because it contains the answer and source text. It downloads locally as JSON and includes canonical hashes; hashes show canonical identity, not factual correctness. The Blind-Spot Map reports project and held-out provenance separately. Held-out evaluation is pending until 40+ independent cases are provided. Safe repair previews may refuse; if offered, inspect the one-token diff and source quote, then explicitly approve. The app clears prior findings and requires a new audit after applying.
