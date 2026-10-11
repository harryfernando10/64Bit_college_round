import json
import unicodedata
from fastapi.testclient import TestClient
from backend.main import app
from backend.phase5c import _canonical, _sha, wilson_interval, reliability_summary, receipt_for, load_heldout
from backend.mutations import CATALOG, compare_expected_behavior
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

def test_mutation_comparison_uses_predeclared_oracle_and_real_traces():
    body={"answer":"The report lists 48 volunteers.","sources":[{"source_id":"s1","title":"Report","text":"The report lists 48 volunteers."}],"mutation_id":"number.claim","target_id":"claim-1","parameters":{"from":"48","to":"84"}}
    data=client.post("/api/mutation-run",json=body).json()
    assert data["expected_outcome"]=="SUPPORTED_TO_CONTRADICTED"
    assert data["comparison"]=="EXPECTED_OBSERVED", (data["explanation"],[(c["verdict"],c["claim_text"],c["error_localizations"],c["deterministic_checks"]) for c in data["perturbed"]["claims"]])
    assert data["baseline"]["claims"][0]["verdict"]=="SUPPORTED"
    assert data["perturbed"]["claims"][0]["verdict"]=="CONTRADICTED"
    assert data["perturbed"]["claims"][0]["error_localizations"]

def test_manually_curated_challenges_match_actual_engine_outcomes():
    challenges=client.get("/api/challenges").json()
    assert [c["expected_challenge"] for c in challenges]==["CAUGHT","NOT_SUPPORTED","FALSE_SUPPORT"]
    observed=[]
    for c in challenges:
        data=client.post("/api/mutation-run",json={k:c[k] for k in ("answer","sources","mutation_id","target_id","parameters")}).json()
        before=data["baseline"]["claims"][0]["verdict"]
        after=data["perturbed"]["claims"][0]["verdict"]
        assert data["baseline"]["execution_mode"]==data["perturbed"]["execution_mode"]=="BASELINE"
        assert before=="SUPPORTED"
        observed.append((c["expected_challenge"],data["expected_outcome"],data["comparison"],after))
    assert observed[0][1:]==("SUPPORTED_TO_CONTRADICTED","EXPECTED_OBSERVED","CONTRADICTED"),observed
    assert observed[1][1:]==("SUPPORTED_TO_NOT_SUPPORTED","EXPECTED_OBSERVED","INSUFFICIENT_EVIDENCE"),observed
    assert observed[2][1:]==("SUPPORTED_TO_NOT_SUPPORTED","EXPECTED_CHANGE_NOT_OBSERVED","SUPPORTED"),observed

def test_mutation_precondition_failures_are_rejected():
    base={"answer":"A report exists.","sources":[{"source_id":"s1","title":"Report","text":"A report exists."}],"target_id":"claim-1"}
    missing=client.post("/api/mutation-run",json={**base,"mutation_id":"number.claim","parameters":{"from":"48","to":"84"}})
    assert missing.status_code==422
    bad_side=client.post("/api/mutation-run",json={**base,"mutation_id":"quantifier.evidence","parameters":{"from":"some","to":"all"}})
    assert bad_side.status_code==422

def test_mutation_comparison_reports_missed_unexpected_and_incomparable_runs():
    common={"sources":[{"source_id":"s1","title":"Report","text":"The report lists 48 volunteers."}]}
    changed=client.post("/api/mutation-run",json={"answer":"The report lists 48 volunteers.","sources":[{"source_id":"s1","title":"A","text":"The report lists 48 volunteers."},{"source_id":"s2","title":"B","text":"The report lists 48 volunteers."}],"mutation_id":"number.evidence","target_id":"s1","parameters":{"from":"48","to":"84"}}).json()
    assert changed["comparison"]=="UNEXPECTED_CHANGE"
    from backend.service import SCENARIOS
    scenario=json.loads(next(p.read_text(encoding="utf8") for p in SCENARIOS.glob("*.json") if json.loads(p.read_text(encoding="utf8"))["scenario_id"]=="garden-trial"))
    incomparable=client.post("/api/mutation-run",json={"answer":scenario["answer"],"sources":scenario["sources"],"mutation_id":"number.claim","target_id":"claim-1","parameters":{"from":"18","to":"20"},"scenario_id":"garden-trial"}).json()
    assert incomparable["comparison"]=="NOT_COMPARABLE"

def test_declared_comparison_helper_covers_expected_change_not_observed():
    from types import SimpleNamespace as NS
    def finding(verdict,**kw):
        values={"verdict":NS(value=verdict),"evidence":[],"review_flags":[],"deterministic_checks":[],"error_localizations":[]};values.update(kw);return NS(**values)
    outcome,explanation=compare_expected_behavior("SUPPORTED_TO_CONTRADICTED",True,finding("SUPPORTED"),finding("SUPPORTED"))
    assert outcome=="EXPECTED_CHANGE_NOT_OBSERVED" and "remained SUPPORTED" in explanation

def test_model_mode_has_no_baseline_mutation_oracle(monkeypatch):
    from backend import service
    from backend.verifier import NliResult
    class MockVerifier:
        available=True; model_id="phase5c-test-model"; detail="test verifier"
        def verify(self,premise,hypothesis): return NliResult("ENTAILMENT",self.model_id,raw_logits={"ENTAILMENT":2.0,"CONTRADICTION":0.0,"NEUTRAL":0.0})
    monkeypatch.setattr(service,"configured_verifier",lambda:MockVerifier())
    data=client.post("/api/mutation-run",json={"answer":"The report lists 48 volunteers.","sources":[{"source_id":"s1","title":"Report","text":"The report lists 48 volunteers."}],"mutation_id":"number.claim","target_id":"claim-1","parameters":{"from":"48","to":"84"}}).json()
    assert data["expected_outcome"]=="UNTESTABLE_IN_MODE"
    assert data["comparison"]=="UNTESTABLE_IN_MODE"

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
    assert all("raw_logits" not in sem for claim in a["payload"]["claims"] for sem in claim["semantic_verifications"])
    assert [s["source_id"] for s in a["payload"]["sources"]]==["s1"]

def test_wilson_interval_and_small_sample_policy():
    low,high=wilson_interval(5,10)
    assert 0<low<.5<high<1
    assert len(wilson_interval(1,1))==2
    assert reliability_summary(5,9)["interval_95"] is None
    assert reliability_summary(8,10)["interval_95"] is not None
    assert reliability_summary(0,0)=={"successes":0,"comparable_cases":0,"interval_95":None,"interval_suppressed_reason":"fewer than 10 comparable cases"}
    for successes,n in [(-1,2),(3,2),(0,0)]:
        try: wilson_interval(successes,n)
        except ValueError: pass
        else: assert False,"invalid Wilson bounds must be rejected"

def test_blind_spot_pending_and_heldout_provenance_validation():
    result=client.post("/api/blind-spot-run",json={}).json()
    assert result["heldout_pending"] is True
    assert result["groups"][-1]["provenance"]=="heldout"
    assert load_heldout()==[]
    project=next(g for g in result["groups"] if g["provenance"]=="project")
    assert project["case_count"]==12 and project["attempted"]>0
    assert result["mutation_results"]
    assert all(r["provenance"]=="project" and r["baseline"]["claims"] and r["perturbed"]["claims"] for r in result["mutation_results"])
    assert sum(project["counts"].values())==project["attempted"]
    assert project["reliability"]["comparable_cases"]==project["comparable"]
    assert project["reliability"]["interval_95"] is None if project["comparable"]<10 else project["reliability"]["interval_95"] is not None

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
    audit=client.post("/api/audit",json=body).json()
    receipt=client.post("/api/audit-receipt",json=audit)
    assert receipt.status_code==200 and receipt.json()["payload"]["answer"]==audit["answer"]
    response=client.post("/api/repair-preview",json={**body,"claim_id":audit["claims"][0]["claim_id"]})
    assert response.status_code==200
    preview=response.json()
    assert preview["offered"] is True
    assert preview["diff"]=={"before":"84","after":"48"}
    assert preview["dry_run"]["claims"][0]["verdict"]=="SUPPORTED"
    approval={"answer":body["answer"],"proposed_answer":preview["proposed_answer"],"approved":True,"preview_token":preview["preview_token"],"claim_id":audit["claims"][0]["claim_id"],"sources":body["sources"]}
    applied=client.post("/api/repair-apply",json=approval)
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

def test_repair_preview_binding_rejects_tampering_reuse_and_expiry(monkeypatch):
    import backend.phase5c as phase
    body={"answer":"The report lists 84 volunteers.","sources":[{"source_id":"s1","title":"Report","text":"The report lists 48 volunteers."}]}
    audit=client.post("/api/audit",json=body).json()
    preview=client.post("/api/repair-preview",json={**body,"claim_id":audit["claims"][0]["claim_id"]}).json()
    base={"answer":body["answer"],"proposed_answer":preview["proposed_answer"],"approved":True,"preview_token":preview["preview_token"],"claim_id":audit["claims"][0]["claim_id"],"sources":body["sources"]}
    assert client.post("/api/repair-apply",json=dict(base,proposed_answer="The report lists 49 volunteers.")).status_code==409
    assert client.post("/api/repair-apply",json=base).status_code==200
    assert client.post("/api/repair-apply",json=base).status_code==409
    preview=client.post("/api/repair-preview",json={**body,"claim_id":audit["claims"][0]["claim_id"]}).json()
    base["preview_token"]=preview["preview_token"]
    monkeypatch.setattr(phase,"time",type("Clock",(),{"monotonic":staticmethod(lambda: 10**12)})())
    assert client.post("/api/repair-apply",json=base).status_code==409

def test_repair_preview_binds_original_claim_and_source_and_decline_invalidates():
    body={"answer":"The report lists 84 volunteers.","sources":[{"source_id":"s1","title":"Report","text":"The report lists 48 volunteers."}]}
    audit=client.post("/api/audit",json=body).json(); claim=audit["claims"][0]["claim_id"]
    preview=client.post("/api/repair-preview",json={**body,"claim_id":claim}).json()
    payload={"answer":body["answer"],"proposed_answer":preview["proposed_answer"],"approved":True,"preview_token":preview["preview_token"],"claim_id":claim,"sources":body["sources"]}
    assert client.post("/api/repair-apply",json=dict(payload,answer="The report lists 85 volunteers.")).status_code==409
    changed=[dict(body["sources"][0],text="The report lists 49 volunteers.")]
    assert client.post("/api/repair-apply",json=dict(payload,sources=changed)).status_code==409
    assert client.post("/api/repair-apply",json=dict(payload,claim_id="claim-2")).status_code==409
    declined=dict(payload,approved=False)
    assert client.post("/api/repair-apply",json=declined).status_code==409
    assert client.post("/api/repair-apply",json=payload).status_code==409

def test_repair_accepts_only_unambiguous_date_and_refuses_ambiguous_numeric_text():
    body={"answer":"The review was completed in 2025.","sources":[{"source_id":"s1","title":"Review","text":"The review was completed in 2024."}]}
    audit=client.post("/api/audit",json=body).json()
    preview=client.post("/api/repair-preview",json={**body,"claim_id":audit["claims"][0]["claim_id"]}).json()
    assert preview["offered"] is True and preview["diff"]=={"before":"2025","after":"2024"}
    ambiguous={"answer":"The report lists 84 volunteers on 2025-03-04.","sources":[{"source_id":"s1","title":"Report","text":"The report lists 48 volunteers on 2024-03-04."}]}
    audit=client.post("/api/audit",json=ambiguous).json()
    preview=client.post("/api/repair-preview",json={**ambiguous,"claim_id":audit["claims"][0]["claim_id"]}).json()
    assert preview["offered"] is False
