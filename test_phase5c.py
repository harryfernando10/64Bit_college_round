import json
import unicodedata
from fastapi.testclient import TestClient
from backend.main import app
from backend.phase5c import _canonical, _sha, wilson_interval, reliability_summary, receipt_for, load_heldout
from backend.mutations import CATALOG
from backend.models import AuditRequest
from backend.service import run_audit

client=TestClient(app)

def test_catalog_has_stable_ids_and_both_sides():
    assert len({m.mutation_id for m in CATALOG})==len(CATALOG)
    assert {m.side for m in CATALOG}=={"EVIDENCE","CLAIM"}
    assert {m.mutation_class for m in CATALOG}>={"NUMBER","DATE","NEGATION","ENTITY","QUANTIFIER","CAUSAL_WORDING","PARAPHRASE","NOISE","DUPLICATION","ORDER","SOURCE_REMOVAL","SOURCE_EDIT"}

def test_mutation_endpoint_is_immutable_and_returns_real_audits():
    body={"answer":"The count is 84.","sources":[{"source_id":"s1","title":"Report","text":"The count is 48."}],"mutation_id":"number.evidence","target_id":"s1","parameters":{"from":"48","to":"84"}}
    original=json.loads(json.dumps(body))
    response=client.post("/api/mutation-run",json=body)
    assert response.status_code==200,response.text
    data=response.json()
    assert data["perturbed"] and data["baseline"]
    assert body==original
    assert data["perturbed"]["sources"][0]["text"]=="The count is 84."

def test_mutation_validation_duplicate_warning_and_paraphrase_mode():
    body={"answer":"The count is 48.","sources":[{"source_id":"s1","title":"Report","text":"The count is 48."}],"mutation_id":"duplication.evidence","target_id":"s1"}
    data=client.post("/api/mutation-run",json=body).json()
    assert any("not independent corroboration" in x for x in data["warnings"])
    body["mutation_id"]="paraphrase.claim";body["target_id"]="claim-1";body["parameters"]={"replacement":"The total reached forty eight."}
    data=client.post("/api/mutation-run",json=body).json()
    assert data["comparison"]=="UNTESTABLE_IN_MODE"

def test_canonical_hash_normalization_and_exclusions():
    assert _canonical({"x":"e\u0301\r\n"})==_canonical({"x":"é\n"})
    assert _sha({"b":2,"a":1})==_sha({"a":1,"b":2})
    audit=run_audit(AuditRequest(answer="The count is 48.",sources=[{"source_id":"s1","title":"Report","text":"The count is 48."}]))
    a=receipt_for(audit);audit.audit_id="audit-random";b=receipt_for(audit)
    assert a["hashes"]["result_sha256"]==b["hashes"]["result_sha256"]
    assert a["payload"]["claims"] and a["hashes"]["answer_sha256"]

def test_wilson_interval_and_small_sample_policy():
    low,high=wilson_interval(5,10)
    assert 0<low<.5<high<1
    assert len(wilson_interval(1,1))==2
    assert reliability_summary(5,9)["interval_95"] is None
    assert reliability_summary(8,10)["interval_95"] is not None

def test_blind_spot_pending_and_heldout_provenance_validation():
    result=client.post("/api/blind-spot-run",json={}).json()
    assert result["heldout_pending"] is True
    assert result["groups"][-1]["provenance"]=="heldout"
    assert load_heldout()==[]

def test_heldout_loader_rejects_wrong_provenance_and_duplicate_ids(tmp_path,monkeypatch):
    import backend.phase5c as phase
    monkeypatch.setattr(phase,"HELDOUT",tmp_path)
    case={"case_id":"x","answer":"Claim.","sources":[{"source_id":"s1","title":"S","text":"Text."}],"provenance":"project","author":"independent-author","expected_label":"SUPPORTED"}
    (tmp_path/"bad.json").write_text(json.dumps(case),encoding="utf8")
    try: load_heldout()
    except ValueError as exc: assert "provenance" in str(exc)
    else: assert False,"wrong provenance must fail"

def test_receipt_api_and_repair_refusal():
    body={"answer":"The report lists 84 volunteers.","sources":[{"source_id":"s1","title":"Report","text":"The report lists 48 volunteers."}]}
    assert client.post("/api/audit-receipt",json=body).status_code==200
    audit=client.post("/api/audit",json=body).json()
    response=client.post("/api/repair-preview",json={**body,"claim_id":audit["claims"][0]["claim_id"]})
    assert response.status_code==200
    preview=response.json()
    assert preview["offered"] is True
    assert preview["diff"]=={"before":"84","after":"48"}
    assert preview["dry_run"]["claims"][0]["verdict"]=="SUPPORTED"
    assert client.post("/api/repair-apply",json={"answer":body["answer"],"proposed_answer":preview["proposed_answer"],"approved":False}).status_code==409
    applied=client.post("/api/repair-apply",json={"answer":body["answer"],"proposed_answer":preview["proposed_answer"],"approved":True})
    assert applied.status_code==200 and applied.json()["audit_required"] is True
    unrelated=client.post("/api/repair-apply",json={"answer":body["answer"],"proposed_answer":"A different claim says 48 volunteers.","approved":True})
    assert unrelated.status_code==422

def test_repair_refuses_multiple_values_and_conflicting_sources():
    bodies=[
      {"answer":"The report lists 84 volunteers across 3 sites.","sources":[{"source_id":"s1","title":"Report","text":"The report lists 48 volunteers across 2 sites."}]},
      {"answer":"The report lists 84 volunteers.","sources":[{"source_id":"s1","title":"A","text":"The report lists 48 volunteers."},{"source_id":"s2","title":"B","text":"The report lists 52 volunteers."}]},
    ]
    for body in bodies:
        audit=client.post("/api/audit",json=body).json()
        preview=client.post("/api/repair-preview",json={**body,"claim_id":audit["claims"][0]["claim_id"]}).json()
        assert preview["offered"] is False
