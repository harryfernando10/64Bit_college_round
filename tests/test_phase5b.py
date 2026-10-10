from backend.models import AuditRequest
from backend.service import _duplicate_sources, run_audit


def test_receipt_uses_retrieved_passage_and_exact_unicode_offsets():
    answer = "The café opens in 2024."
    source_text = "Irrelevant.\nThe café opens in 2023."
    result = run_audit(AuditRequest(answer=answer, sources=[{"source_id": "one", "title": "Schedule", "text": source_text}]))
    claim = result.claims[0]
    candidate = claim.search_receipt.candidates[0]
    assert claim.search_receipt.status == "RETRIEVED"
    assert candidate.snippet == "The café opens in 2023."
    assert source_text[candidate.start_offset:candidate.end_offset] == candidate.snippet
    assert "café" in claim.search_receipt.query_terms
    assert claim.verdict.value == "CONTRADICTED"


def test_duplicate_sources_exact_near_short_and_unrelated_controls():
    sources = [
        {"source_id": "a", "title": "Same title", "text": "A detailed report describes the annual regional rainfall measurement across coastal stations."},
        {"source_id": "b", "title": "Same title", "text": "A detailed report describes the annual regional rainfall measurement across coastal stations."},
        {"source_id": "c", "title": "Copy", "text": "A detailed report describes the annual regional rainfall measurement across coastal stations recently."},
        {"source_id": "d", "title": "Short", "text": "Rainfall data."},
        {"source_id": "e", "title": "Other", "text": "Mars has two small moons named Phobos and Deimos."},
    ]
    duplicates = _duplicate_sources([type("Source", (), source) for source in sources])
    assert duplicates == {"b": "a", "c": "a"}


def test_review_flags_compare_retrieved_wording_and_keep_benign_cues_out():
    source = "The treatment may reduce symptoms in some patients."
    result = run_audit(AuditRequest(answer="The treatment will reduce symptoms in all patients.", sources=[{"source_id": "s", "title": "Study", "text": source}]))
    flags = result.claims[0].review_flags
    assert {flag.rule_id for flag in flags} >= {"CERTAINTY_MAY_WILL", "CERTAINTY_SOME_ALL"}
    assert all(flag.source_id == "s" and flag.start_offset is not None for flag in flags)
    benign = run_audit(AuditRequest(answer="The report therefore recommends a review.", sources=[{"source_id": "s", "title": "Note", "text": "The report recommends a review."}]))
    assert not any(flag.flag_type == "INFERENCE_REVIEW" for flag in benign.claims[0].review_flags)


def test_review_flags_do_not_change_verdict_and_duplicate_remains_visible():
    text = "The policy may cover all visitors at this location starting in 2024."
    result = run_audit(AuditRequest(answer="The policy will cover all visitors at this location starting in 2024.", sources=[
        {"source_id": "a", "title": "Original", "text": text}, {"source_id": "b", "title": "Renamed copy", "text": text},
    ]))
    assert result.duplicate_sources == {"b": "a"}
    assert result.claims[0].verdict.value == "INSUFFICIENT_EVIDENCE"
    assert result.claims[0].search_receipt.candidates[1].duplicate_of == "a"
    assert any(flag.flag_type == "CERTAINTY_DRIFT" for flag in result.claims[0].review_flags)
