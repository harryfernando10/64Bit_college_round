"""Canonical receipts, evaluation provenance reports and conservative repair previews."""
import hashlib, json, unicodedata, re
from pathlib import Path
from backend.models import AuditRequest, Verdict
from backend.service import run_audit
from backend.mutations import public_catalog

ROOT=Path(__file__).resolve().parents[1]
HELDOUT=ROOT/"data"/"evaluation"/"heldout"
ENGINE_VERSION="refutella-phase5c"

def _norm(value):
    if isinstance(value,str): return unicodedata.normalize("NFC",value.replace("\r\n","\n").replace("\r","\n"))
    if isinstance(value,list): return [_norm(x) for x in value]
    if isinstance(value,dict):
        normalized={unicodedata.normalize("NFC",k):_norm(v) for k,v in value.items()}
        if len(normalized)!=len(value): raise ValueError("Canonical object keys collide after Unicode NFC normalization")
        return normalized
    return value

def _canonical(value): return json.dumps(_norm(value),ensure_ascii=False,sort_keys=True,separators=(",",":" )).encode("utf-8")
def _sha(value): return hashlib.sha256(value if isinstance(value,bytes) else _canonical(value)).hexdigest()

def receipt_for(audit):
    findings=[]
    for c in audit.claims:
        item=c.model_dump(mode="json",exclude={"model_score"})
        for sem in item.get("semantic_verifications",[]):
            if sem.get("raw_logits") is not None: sem["raw_logits"]={k:round(v,3) for k,v in sem["raw_logits"].items()}
        findings.append(item)
    payload={"answer":audit.answer,"sources":[s.model_dump() for s in audit.sources],"claims":findings,"engine_version":ENGINE_VERSION,"audit_mode":audit.execution_mode.value,"model_revision":next((v.model_id for c in audit.claims for v in c.semantic_verifications if v.status in {"ENTAILMENT","CONTRADICTION","NEUTRAL"}),None)}
    result_hash=_sha(payload)
    return {"canonicalization":"Unicode NFC; CRLF/CR to LF; UTF-8; sorted object keys; compact JSON; meaningful source/claim/evidence order preserved; audit IDs and timestamps omitted.","hashes":{"answer_sha256":_sha(payload["answer"]),"sources_sha256":_sha(payload["sources"]),"result_sha256":result_hash},"payload":payload}

def load_heldout():
    cases=[]
    if not HELDOUT.exists(): return cases
    for path in sorted(HELDOUT.glob("*.json")):
        raw=json.loads(path.read_text(encoding="utf8"))
        rows=raw if isinstance(raw,list) else [raw]
        for case in rows:
            required={"case_id","answer","sources","provenance","author","expected_label"}
            if not isinstance(case,dict) or not required.issubset(case): raise ValueError(f"Malformed evaluation case in {path.name}; required fields: {', '.join(sorted(required))}")
            if case["provenance"]!="heldout": raise ValueError(f"Heldout directory case {case.get('case_id')} must have provenance='heldout'")
            labels={"SUPPORTED","CONTRADICTED","INSUFFICIENT_EVIDENCE","AMBIGUOUS","NOT_ASSESSED"}
            if not isinstance(case["case_id"],str) or not case["case_id"].strip(): raise ValueError(f"Malformed case ID in {path.name}")
            if not isinstance(case["author"],str) or not case["author"].strip(): raise ValueError(f"Heldout case {case['case_id']} needs a non-empty author identifier")
            if case["expected_label"] not in labels: raise ValueError(f"Heldout case {case['case_id']} has unsupported expected_label")
            AuditRequest(answer=case["answer"],sources=case["sources"])
            cases.append(case)
    ids=[c["case_id"] for c in cases]
    if len(ids)!=len(set(ids)): raise ValueError("Evaluation case IDs must be unique")
    return cases

def wilson_interval(successes,n,z=1.959963984540054):
    if n<1 or successes<0 or successes>n: raise ValueError("Require 0 <= successes <= n and n > 0")
    p=successes/n; d=1+z*z/n; center=(p+z*z/(2*n))/d; margin=z*((p*(1-p)/n+z*z/(4*n*n))**0.5)/d
    return [max(0,center-margin),min(1,center+margin)]

def reliability_summary(successes,n):
    if n<0 or successes<0 or successes>n: raise ValueError("Require 0 <= successes <= n")
    return {"successes":successes,"comparable_cases":n,"interval_95":wilson_interval(successes,n) if n>=10 else None,"interval_suppressed_reason":"fewer than 10 comparable cases" if n<10 else None}

def blindspot_report(include_project=True,include_heldout=True):
    heldout=load_heldout()
    # Existing project evaluation remains separately labeled; it is not rebranded as heldout.
    groups=[]
    if include_project: groups.append({"provenance":"project","case_count":12,"status":"Project-authored regression suite; run via tests/test_evaluation.py; no mutations implied by those cases."})
    if include_heldout: groups.append({"provenance":"heldout","case_count":len(heldout),"status":"Pending independently authored data" if not heldout else "Validated heldout cases available"})
    return {"groups":groups,"catalog":public_catalog(),"mutation_results":[],"nli":{"available":False,"detail":"Model availability is determined only when audits run; no model runs were created by this empty-data report."},"definitions":{"attempted":"case and applicable mutation scheduled","comparable":"both audits completed in the same non-fixture mode","expected_observed":"declared expectation matched observation","miss":"declared expected change was not observed","inconclusive":"no defensible expected verdict behavior","untestable":"expectation lacks an oracle in that mode","not_comparable":"different modes or fixture comparison"},"heldout_pending":len(heldout)==0}

def repair_preview(request):
    baseline=run_audit(AuditRequest(answer=request.answer,sources=request.sources))
    claim=next((c for c in baseline.claims if c.claim_id==request.claim_id),None)
    if claim is None: raise ValueError("Unknown claim_id")
    if claim.verdict!=Verdict.CONTRADICTED or not claim.error_localizations: return {"offered":False,"reason":"The engine did not establish a localized numeric/date contradiction.","baseline":baseline.model_dump(mode="json")}
    loc=claim.error_localizations
    if len(loc)!=1 or loc[0].rule_id not in {"QUANTITY_OR_DURATION_MISMATCH","DATE_MISMATCH"}: return {"offered":False,"reason":"The contradiction is not a single unambiguous numeric/date localization.","baseline":baseline.model_dump(mode="json")}
    item=loc[0]; old=item.claim_text; new=item.source_text; claim_start=claim.start_offset
    nums=lambda s: re.findall(r"(?<!\w)\d+(?:[.,/]\d+)*(?!\w)",s)
    oldnums,newnums=nums(old),nums(new)
    if len(oldnums)!=1 or len(newnums)!=1:return {"offered":False,"reason":"The claim or source contains multiple numeric values; safe minimal repair cannot be established."}
    proposed=request.answer[:item.claim_start_offset]+old.replace(oldnums[0],newnums[0],1)+request.answer[item.claim_end_offset:]
    dry=run_audit(AuditRequest(answer=proposed,sources=request.sources))
    repaired=next((c for c in dry.claims if c.start_offset==claim_start),None)
    if not repaired or repaired.verdict!=Verdict.SUPPORTED or not any(e.source_id==item.source_id and e.quote for e in repaired.evidence):return {"offered":False,"reason":"Dry-run did not classify the repaired claim as SUPPORTED with relevant evidence.","dry_run":dry.model_dump(mode="json")}
    return {"offered":True,"reason":"A single localized value change produced SUPPORTED in a dry-run with the cited source.","original_answer":request.answer,"proposed_answer":proposed,"diff":{"before":old,"after":old.replace(oldnums[0],newnums[0],1)},"supporting_source":{"source_id":item.source_id,"quote":item.source_text,"start_offset":item.source_start_offset,"end_offset":item.source_end_offset},"baseline":baseline.model_dump(mode="json"),"dry_run":dry.model_dump(mode="json"),"requires_explicit_approval":True}
