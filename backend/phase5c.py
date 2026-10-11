"""Canonical receipts, evaluation provenance reports and conservative repair previews."""
import hashlib, json, unicodedata, re, secrets, time, threading
from pathlib import Path
from backend.models import AuditRequest, Verdict
from backend.service import run_audit
from backend.mutations import public_catalog
from backend.mutations import CATALOG, apply_mutation, compare_expected_behavior

ROOT=Path(__file__).resolve().parents[1]
HELDOUT=ROOT/"data"/"evaluation"/"heldout"
ENGINE_VERSION="refutella-phase5c"
_preview_lock = threading.Lock()
_preview_approvals = {}
PREVIEW_TTL_SECONDS = 300

def bind_preview(answer, proposed, sources, claim_id, preview):
    binding = _sha({"answer": answer, "proposed": proposed, "sources": [s.model_dump() for s in sources], "claim_id": claim_id})
    preview_digest = _sha(preview)
    token = secrets.token_urlsafe(32)
    with _preview_lock:
        now = time.monotonic()
        for key in [k for k,v in _preview_approvals.items() if v[1] <= now]: _preview_approvals.pop(key, None)
        _preview_approvals[token] = (binding, now + PREVIEW_TTL_SECONDS, preview_digest)
    return token

def consume_preview(token, answer, proposed, sources, claim_id):
    with _preview_lock:
        item = _preview_approvals.get(token)
        if item is None: return False
        if item[1] <= time.monotonic():
            _preview_approvals.pop(token, None)
            return False
        valid = item[0] == _sha({"answer": answer, "proposed": proposed, "sources": [s.model_dump() for s in sources], "claim_id": claim_id}) and bool(item[2])
        if valid: _preview_approvals.pop(token, None)
        return valid

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
            sem.pop("raw_logits",None)
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

PROJECT_CASES=ROOT/"data"/"evaluation"/"cases.json"

def _project_cases():
    rows=json.loads(PROJECT_CASES.read_text(encoding="utf8"))
    labels={"SUPPORTED","CONTRADICTED","INSUFFICIENT_EVIDENCE","AMBIGUOUS","NOT_ASSESSED"}
    if not isinstance(rows,list): raise ValueError("Project evaluation cases must be a JSON list")
    ids=set(); cases=[]
    for row in rows:
        if not isinstance(row,dict) or not {"id","answer","sources","expected"}.issubset(row): raise ValueError("Malformed project evaluation case")
        cid=row["id"]
        if not isinstance(cid,str) or not cid.strip() or cid in ids: raise ValueError("Project evaluation case IDs must be non-empty and unique")
        if row["expected"] not in labels: raise ValueError(f"Unsupported expected label in project case {cid}")
        AuditRequest(answer=row["answer"],sources=row["sources"])
        ids.add(cid); cases.append({"case_id":cid,"answer":row["answer"],"sources":row["sources"],"expected_label":row["expected"],"provenance":"project","author":"project evaluation suite","mode":row.get("mode")})
    return cases

def _automatic_mutation(case, mutation):
    answer=case["answer"]; sources=[dict(s) for s in case["sources"]]; text=answer if mutation.side=="CLAIM" else sources[0]["text"]
    params={}; cls=mutation.mutation_class
    if cls in {"NUMBER","DATE"}:
        pat=r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{4}|\d+(?:[.,/]\d+)*)\b" if cls=="DATE" else r"(?<!\w)\d+(?!\w)"
        match=re.search(pat,text)
        if not match:return None
        old=match.group(); new=str(int(old[:4])+1)+old[4:] if cls=="DATE" and len(old)>=4 and old[:4].isdigit() else str(int(old)+1)
        params={"from":old,"to":new}
    elif cls=="NEGATION": pass
    elif cls in {"QUANTIFIER","CAUSAL_WORDING","ENTITY","SOURCE_EDIT"}:
        choices={"QUANTIFIER":(("some","all"),("all","some"),("most","few")),"CAUSAL_WORDING":(("because","although"),("caused","preceded")),"ENTITY":(("Monday","Tuesday"),("Monday","Tuesday")),"SOURCE_EDIT":((" ","  "),)}[cls]
        selected=next(((a,b) for a,b in choices if re.search(re.escape(a),text,re.I)),None)
        if selected is None:return None
        params={"from":selected[0],"to":selected[1]}
    elif cls=="PARAPHRASE": return None
    elif cls=="SOURCE_REMOVAL" and len(sources)<2:return None
    elif cls=="ORDER" and len(re.findall(r"[.!?](?:\s|$)",text))<2:return None
    try:
        _,changed,description=apply_mutation(mutation.mutation_id,text,params)
    except ValueError:return None
    if mutation.side=="CLAIM": answer=changed
    elif cls=="SOURCE_REMOVAL": sources=sources[1:]
    else:sources[0]["text"]=changed
    return answer,sources,description

def blindspot_report(include_project=True,include_heldout=True):
    heldout=load_heldout()
    project=_project_cases() if include_project else []
    datasets=[("project",project),("heldout",heldout)]
    results=[]; groups=[]; nli_modes=set()
    for provenance,cases in datasets:
        if provenance=="heldout" and not include_heldout: continue
        attempted=0
        for case in cases:
            base_req=AuditRequest(answer=case["answer"],sources=case["sources"])
            baseline=run_audit(base_req)
            if baseline.execution_mode.value in {"MODEL","LIVE"}: nli_modes.add(baseline.execution_mode.value)
            for mutation in CATALOG:
                generated=_automatic_mutation(case,mutation)
                if generated is None: continue
                answer,sources,change=generated; attempted+=1
                perturbed=run_audit(AuditRequest(answer=answer,sources=sources))
                comparable=baseline.execution_mode==perturbed.execution_mode and baseline.execution_mode.value!="FIXTURE"
                expectation=mutation.expected_model if {baseline.execution_mode.value,perturbed.execution_mode.value}&{"MODEL","LIVE","MODEL_UNAVAILABLE"} else mutation.expected_baseline
                before=next((c for c in baseline.claims if c.claim_id=="claim-1"),None); after=next((c for c in perturbed.claims if c.claim_id=="claim-1"),None)
                category,explanation=compare_expected_behavior(expectation,comparable,before,after)
                results.append({"provenance":provenance,"case_id":case["case_id"],"mutation_id":mutation.mutation_id,"mutation_class":mutation.mutation_class,"mode":baseline.execution_mode.value,"attempted":True,"comparison":category,"expected":expectation,"explanation":explanation,"changed_text":change,"baseline":baseline.model_dump(mode="json"),"perturbed":perturbed.model_dump(mode="json")})
        counts={k:sum(r["provenance"]==provenance and r["comparison"]==k for r in results) for k in ("EXPECTED_OBSERVED","EXPECTED_CHANGE_NOT_OBSERVED","UNEXPECTED_CHANGE","INCONCLUSIVE","UNTESTABLE_IN_MODE","NOT_COMPARABLE")}
        verdict_counts={v:sum(c["verdict"]==v for r in results if r["provenance"]==provenance for audit in (r["baseline"],r["perturbed"]) for c in audit["claims"]) for v in ("SUPPORTED","CONTRADICTED","INSUFFICIENT_EVIDENCE","AMBIGUOUS","NOT_ASSESSED")}
        comparable_count=counts["EXPECTED_OBSERVED"]+counts["EXPECTED_CHANGE_NOT_OBSERVED"]+counts["UNEXPECTED_CHANGE"]
        summary=reliability_summary(counts["EXPECTED_OBSERVED"],comparable_count)
        groups.append({"provenance":provenance,"case_count":len(cases),"attempted":attempted,"counts":counts,"verdict_counts":verdict_counts,"comparable":comparable_count,"reliability":summary,"status":"Project-authored cases; mutation observations are not a representative benchmark." if provenance=="project" else "Pending independently authored data" if not cases else "Validated heldout cases available"})
    by_class={}; by_mode={}
    for key in ("mutation_class","mode"):
        bucket={}
        for row in results:
            name=row[key]; item=bucket.setdefault(name,{"attempted":0,"inconclusive":0,"untestable":0,"not_comparable":0,"expected_observed":0,"missed":0,"unexpected_change":0})
            item["attempted"]+=1
            field={"INCONCLUSIVE":"inconclusive","UNTESTABLE_IN_MODE":"untestable","NOT_COMPARABLE":"not_comparable","EXPECTED_OBSERVED":"expected_observed","EXPECTED_CHANGE_NOT_OBSERVED":"missed","UNEXPECTED_CHANGE":"unexpected_change"}[row["comparison"]]
            item[field]+=1
        if key=="mutation_class":by_class=bucket
        else:by_mode=bucket
    return {"groups":groups,"catalog":public_catalog(),"mutation_results":results,"by_mutation_class":by_class,"by_mode":by_mode,"nli":{"available":bool(nli_modes),"modes":sorted(nli_modes),"detail":"NLI was observed during live engine runs." if nli_modes else "NLI unavailable: no configured model-backed audit completed."},"definitions":{"attempted":"Applicable catalog entry was applied and both baseline and perturbed audits ran.","expected_observed":"A declared, pre-execution expectation matched the observed behavior.","missed":"A declared expected change did not occur.","inconclusive":"Actual runs completed but the catalog declares no valid oracle.","untestable":"The selected mode has no valid oracle for this transformation.","not_comparable":"Modes differ or a fixture was involved; excluded from scoring."},"heldout_pending":len(heldout)==0}

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
