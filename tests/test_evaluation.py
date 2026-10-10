"""Small deterministic API evaluation; run with pytest -s to print its report."""
import json
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "evaluation" / "cases.json"
STRESS_CASES = ROOT / "data" / "evaluation" / "stress_cases.json"


def test_curated_api_evaluation_report(monkeypatch):
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    stress_cases = json.loads(STRESS_CASES.read_text(encoding="utf-8"))
    ids = [case["id"] for case in cases] + [case["id"] for case in stress_cases]
    assert len(ids) == len(set(ids)), "evaluation case IDs must be unique"
    observed = Counter()
    expected = Counter(case["expected"] for case in cases)
    matrix = Counter()
    from backend import service
    from backend.verifier import NliResult

    class MockEntailmentVerifier:
        available = True
        model_id = "evaluation-mock-nli"
        detail = "Deterministic evaluation mock; no real model inference."

        def verify(self, premise, hypothesis):
            return NliResult("ENTAILMENT", self.model_id, raw_logits={"ENTAILMENT": 3.0, "CONTRADICTION": -2.0, "NEUTRAL": 0.0})

    monkeypatch.setattr(service, "configured_verifier", lambda: MockEntailmentVerifier())
    with TestClient(app) as client:
        for case in cases:
            if case.get("mode") == "MODEL_MOCK":
                monkeypatch.setattr(service, "configured_verifier", lambda: MockEntailmentVerifier())
            else:
                monkeypatch.setattr(service, "configured_verifier", lambda: None)
            response = client.post("/api/audit", json={key: case[key] for key in ("answer", "sources")})
            assert response.status_code == 200, f"{case['id']}: {response.text}"
            data = response.json()
            actual = data["claims"][0]["verdict"] if len(data["claims"]) == 1 else "MULTI_CLAIM"
            if case.get("mode") == "MODEL_MOCK":
                assert data["execution_mode"] == "MODEL"
                assert data["claims"][0]["semantic_verifications"][0]["status"] == "ENTAILMENT"
            observed[actual] += 1
            matrix[(case["expected"], actual)] += 1
            assert actual == case["expected"], f"{case['id']}: expected {case['expected']}, observed {actual}"
            if case["id"] == "unicode-offset-001":
                claim = data["claims"][0]
                assert data["answer"][claim["start_offset"]:claim["end_offset"]] == claim["claim_text"]
                for evidence in claim["evidence"]:
                    source = next(item for item in data["sources"] if item["source_id"] == evidence["source_id"])
                    assert source["text"][evidence["start_offset"]:evidence["end_offset"]] == evidence["quote"]
        for case in stress_cases:
            answer = "The garden trial ended after four weeks."
            if case["operation"] == "REMOVE_SOURCE":
                sources = [{"source_id": "support", "title": "Trial report", "text": answer},
                           {"source_id": "extra", "title": "Extra", "text": "A separate garden note."}]
            else:
                sources = [{"source_id": "report", "title": "Trial report", "text": answer + " Another note about the garden."}]
            baseline_response = client.post("/api/audit", json={"answer": answer, "sources": sources})
            assert baseline_response.status_code == 200
            baseline = baseline_response.json()
            baseline_copy = json.dumps(baseline, ensure_ascii=False, sort_keys=True)
            ref = next(ref for claim in baseline["claims"] for ref in claim["evidence"] if ref["source_id"] == case["source_id"])
            body = {"baseline": baseline, "operation": case["operation"], "source_id": case["source_id"]}
            if case["operation"] != "REMOVE_SOURCE":
                body["sentence_id"] = ref["sentence_id"]
            if case["operation"] == "EDIT_PASSAGE":
                body["replacement_text"] = case["replacement_text"]
            response = client.post("/api/stress-experiment", json=body)
            assert response.status_code == 200, f"{case['id']}: {response.text}"
            result = response.json()
            comparison = result["comparisons"][0]
            assert (comparison["outcome"], comparison["perturbed"]["verdict"]) == (case["expected_outcome"], case["expected_verdict"]), case["id"]
            assert json.dumps(result["baseline"], ensure_ascii=False, sort_keys=True) == baseline_copy, case["id"]
            assert [item["text"] for item in result["baseline"]["sources"]] == [item["text"] for item in sources], case["id"]
    print(f"Curated API evaluation: {len(cases)} audit cases + {len(stress_cases)} stress cases")
    print("Observed verdict counts:", dict(sorted(observed.items())))
    print("Expected verdict counts:", dict(sorted(expected.items())))
    print("Confusion counts (expected -> observed):")
    for (want, got), count in sorted(matrix.items()):
        print(f"  {want} -> {got}: {count}")
    print(f"Exact-label accuracy: {sum(n for (want, got), n in matrix.items() if want == got)}/{sum(observed.values())}")
    print(f"Stress behavior: {len(stress_cases)} cases; unresolved outcomes and immutable inputs checked")
