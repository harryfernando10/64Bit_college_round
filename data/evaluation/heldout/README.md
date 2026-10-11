# Independently authored held-out evaluation data

This directory intentionally contains no cases yet. A teammate who has not read Refutella's implementation rules must author at least 40 cases independently before the held-out evaluation can be reported.

Each JSON file may contain one case object or an array of objects. Required fields:

- `case_id`: stable unique identifier
- `answer`: answer text
- `sources`: normal `SourceDocument` objects (`source_id`, `title`, `text`)
- `provenance`: exactly `heldout`
- `author`: author identifier
- `expected_label`: one of `SUPPORTED`, `CONTRADICTED`, `INSUFFICIENT_EVIDENCE`, `AMBIGUOUS`, `NOT_ASSESSED`
- `mutation_class`: optional catalog-aligned category

Do not copy project-authored tests into this directory or describe placeholders as human-authored examples. The loader validates fields, provenance, source request constraints, and duplicate IDs. Missing data is reported as pending, not as zero failures or a score.
