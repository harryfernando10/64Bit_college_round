from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def baseline(answer, sources):
    response = client.post("/api/audit", json={"answer": answer, "sources": sources})
    assert response.status_code == 200
    return response.json()


def experiment(audit, operation, source_id, sentence_id=None, replacement_text=None):
    body = {"baseline": audit, "operation": operation, "source_id": source_id}
    if sentence_id is not None:
        body["sentence_id"] = sentence_id
    if replacement_text is not None:
        body["replacement_text"] = replacement_text
    return client.post("/api/stress-experiment", json=body)


def test_remove_supporting_source_reruns_engine_and_becomes_unresolved():
    answer = "The garden trial ended after four weeks."
    sources = [
        {"source_id": "support", "title": "Trial report", "text": answer},
        {"source_id": "extra", "title": "Extra", "text": "A separate note about gardens."},
    ]
    original = baseline(answer, sources)
    result = experiment(original, "REMOVE_SOURCE", "support").json()
    assert result["perturbed"]["execution_mode"] == "BASELINE"
    assert result["comparisons"][0]["baseline"]["verdict"] == "SUPPORTED"
    assert result["comparisons"][0]["perturbed"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert result["comparisons"][0]["outcome"] == "UNRESOLVED"


def test_remove_irrelevant_source_leaves_verdict_unchanged():
    answer = "The garden trial ended after four weeks."
    sources = [
        {"source_id": "support", "title": "Trial report", "text": answer},
        {"source_id": "extra", "title": "Extra", "text": "The river bridge opened in Paris."},
    ]
    original = baseline(answer, sources)
    result = experiment(original, "REMOVE_SOURCE", "extra").json()
    assert result["comparisons"][0]["outcome"] == "UNCHANGED"
    assert result["comparisons"][0]["perturbed"]["verdict"] == "SUPPORTED"
    assert "does not indicate evidence independence" in result["comparisons"][0]["explanation"]


def test_edit_evidence_weakens_support_and_offsets_match_changed_context():
    answer = "The garden trial ended after four weeks."
    source_text = answer + " The site was near the river."
    source = {"source_id": "report", "title": "Trial report", "text": source_text}
    original = baseline(answer, [source])
    selected = original["claims"][0]["evidence"][0]
    result = experiment(original, "EDIT_PASSAGE", "report", selected["sentence_id"],
                        "The garden trial lasted for a month.").json()
    finding = result["comparisons"][0]["perturbed"]
    assert finding["verdict"] == "INSUFFICIENT_EVIDENCE"
    for ref in finding["evidence"]:
        assert result["perturbed"]["sources"][0]["text"][ref["start_offset"]:ref["end_offset"]] == ref["quote"]
    assert source["text"] == source_text
    assert original["claims"][0]["evidence"][0]["quote"] == selected["quote"]


def test_edit_evidence_can_observe_a_contradicted_verdict():
    answer = "The office is open on Monday."
    original = baseline(answer, [
        {"source_id": "notice", "title": "Notice", "text": answer + " A visitor guide is available."},
        {"source_id": "other", "title": "Other", "text": "The museum is open on Tuesday."},
    ])
    evidence = original["claims"][0]["evidence"][0]
    result = experiment(original, "EDIT_PASSAGE", evidence["source_id"], evidence["sentence_id"],
                        "The office is not open on Monday.").json()
    assert result["comparisons"][0]["perturbed"]["verdict"] == "CONTRADICTED"
    assert result["comparisons"][0]["outcome"] == "CHANGED"


def test_remove_passage_preserves_original_baseline_and_reindexes_context():
    answer = "The garden trial ended after four weeks."
    first = answer
    second = "The garden trial enrolled 48 plants."
    original = baseline(answer, [{"source_id": "report", "title": "Report", "text": first + " " + second}])
    passage = original["claims"][0]["evidence"][0]
    result = experiment(original, "REMOVE_PASSAGE", "report", passage["sentence_id"]).json()
    assert result["perturbed"]["sources"][0]["text"] == " " + second
    assert original["sources"][0]["text"] == first + " " + second
    assert original["claims"][0]["evidence"][0]["quote"] == first


def test_invalid_ids_unchanged_edit_and_invalid_operation_are_http_422():
    answer = "The garden trial ended after four weeks."
    audit = baseline(answer, [{"source_id": "report", "title": "Report", "text": answer}])
    sentence_id = audit["claims"][0]["evidence"][0]["sentence_id"]
    assert experiment(audit, "REMOVE_SOURCE", "missing").status_code == 422
    assert experiment(audit, "REMOVE_PASSAGE", "report", "missing").status_code == 422
    assert experiment(audit, "EDIT_PASSAGE", "report", sentence_id, answer).status_code == 422
    assert client.post("/api/stress-experiment", json={"baseline": audit, "operation": "REMOVE_PASSAGE", "source_id": "report"}).status_code == 422


def test_fixture_baseline_reports_comparability_warning():
    scenario = client.get("/api/scenarios").json()[0]
    audit = client.post("/api/audit", json={"answer": scenario["answer"], "sources": scenario["sources"], "scenario_id": scenario["scenario_id"]}).json()
    source_id = scenario["sources"][0]["source_id"]
    result = experiment(audit, "REMOVE_SOURCE", source_id).json()
    assert not result["comparable"]
    assert result["comparisons"][0]["outcome"] == "NOT_COMPARABLE"
    assert any("curated fixture" in warning.lower() for warning in result["warnings"])


def test_empty_resulting_context_is_reported_without_invalid_audit():
    answer = "The garden trial ended after four weeks."
    audit = baseline(answer, [{"source_id": "report", "title": "Report", "text": answer}])
    sentence_id = audit["claims"][0]["evidence"][0]["sentence_id"]
    result = experiment(audit, "REMOVE_PASSAGE", "report", sentence_id).json()
    assert result["perturbed"] is None
    assert result["comparisons"][0]["outcome"] == "NOT_COMPARABLE"
    assert "entire source context" in result["warnings"][0]


def test_experiment_respects_unavailable_optional_nli(monkeypatch, tmp_path):
    monkeypatch.setenv("REFUTELLA_NLI_MODEL_PATH", str(tmp_path / "missing-model"))
    answer = "The garden trial ended after four weeks."
    source = {"source_id": "report", "title": "Report", "text": answer + " The site was near the river."}
    audit = baseline(answer, [source])
    ref = audit["claims"][0]["evidence"][0]
    result = experiment(audit, "EDIT_PASSAGE", "report", ref["sentence_id"],
                        "The trial took about one month.").json()
    assert result["perturbed"]["execution_mode"] == "MODEL_UNAVAILABLE"
    assert all(v["status"] == "UNAVAILABLE" for v in result["comparisons"][0]["perturbed"]["semantic_verifications"])
    assert any("unavailable" in warning.lower() for warning in result["warnings"])

