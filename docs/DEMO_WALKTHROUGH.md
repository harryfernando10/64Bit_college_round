# Refutella demo walkthrough

Use the README PowerShell commands to start the backend and frontend in separate terminals, then open Vite's local URL. The scenarios and expected behavior below use existing examples or short inputs entered in the workspace. The app calls the actual local API; timing and rendering depend on the machine.

## Walkthrough (about 4 minutes)

1. **Show a claim and its sources.** Select **Garden Trial** from the scenario menu. The UI loads the answer and source documents and initially displays the fixture mode label. Explain that this is a curated scenario result, not a fresh inference.
2. **Inspect an exact evidence trace.** Select a claim in the findings list. Point out the exact source excerpt, source ID/sentence ID, character offsets, verdict and verification tier. The quote check establishes provenance at offsets, not truth.
3. **Show contradiction and insufficient evidence.** Edit the answer to contain `The review was completed in 2025.` and replace/add a source sentence `The review was completed in 2024.`; use a distinct source ID. Run audit: the live baseline's narrow date rule is expected to report contradiction. Then change the claim to a detail absent from the sources, such as `The report lists the plant color.` and rerun: expected insufficient evidence. These are source-driven baseline results, not fixture results.
4. **Establish stress baseline.** Set the answer to `The garden trial ended after four weeks.` and a source with that exact sentence plus another sentence (for example, `The garden trial enrolled 48 plants.`). Run audit; expect a baseline exact-text support finding.
5. **Change evidence and compare.** In Evidence Stress Lab, select the report and remove its supporting passage, or edit it to `The garden trial lasted for a month.`. Run experiment. With the baseline verifier and no NLI configured, the changed passage should leave the claim insufficient; inspect the changed text, both evidence columns, outcome and warnings. With an NLI verifier configured, outcomes may differ and must be read with the mode/status disclosure. Repeat with source removal if time permits.
6. **State limitations.** Retrieval is lexical; it can miss relevant paraphrases or select misleading overlap. Deterministic contradiction rules are narrow, and optional local NLI is fallible and uncalibrated. The curated evaluation is small and not representative. A verdict surviving an evidence edit does not demonstrate parametric-memory leakage.

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
- Try invalid/whitespace input and stop the backend to inspect validation and connection error states.
- Check keyboard operation, screen-reader labels, reduced-motion behavior and common laptop-width layout.

This walkthrough is documentation only; no browser automation or manual browser session was performed as part of Phase 4 verification.
