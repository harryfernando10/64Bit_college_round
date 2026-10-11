import json
import io
import os
import re
import unicodedata
import zipfile
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from backend.models import AuditRequest, AuditResponse, StressExperimentRequest, StressExperimentResponse, MAX_SOURCE, MutationRunRequest, MutationRunResponse, BlindSpotRequest, RepairRequest, RepairApplyRequest
from backend.service import run_audit, run_stress_experiment, SCENARIOS
from backend.mutations import BY_ID, public_catalog, apply_mutation, compare_expected_behavior
from backend.phase5c import receipt_for, blindspot_report, repair_preview, bind_preview, consume_preview

app = FastAPI(title="Refutella API", version="0.2.0", description="Evidence-based claim auditing against supplied sources")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_BYTES = max(1, int(os.environ.get("REFUTELLA_MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES))))
MAX_SOURCE_CHARS = MAX_SOURCE
MAX_SOURCE_TITLE_CHARS = 160

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "refutella-api", "phase": 5, "subphase": "5C"}


def _safe_filename(filename: str | None) -> str:
    name = re.split(r"[/\\]", filename or "")[-1].strip()
    if not name or len(name) > MAX_SOURCE_TITLE_CHARS or name in {".", ".."}:
        raise HTTPException(status_code=422, detail="Provide a filename of 1 to 160 characters.")
    return name


def _extract_docx(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if sum(item.file_size for item in members) > 20 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="The expanded DOCX content exceeds the extraction safety limit.")
            if "[Content_Types].xml" not in archive.namelist() or "word/document.xml" not in archive.namelist():
                raise ValueError("This is not a valid DOCX document.")
        from docx import Document
        document = Document(io.BytesIO(content))
        parts = []
        for child in document.element.body.iterchildren():
            if isinstance(child, CT_P):
                value = Paragraph(child, document).text.strip()
                if value:
                    parts.append(value)
            elif isinstance(child, CT_Tbl):
                table = Table(child, document)
                for row in table.rows:
                    value = "\t".join(cell.text.strip() for cell in row.cells).strip()
                    if value:
                        parts.append(value)
        return "\n".join(parts)
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="The DOCX file is corrupt or unreadable.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="The DOCX file is corrupt or unreadable.") from exc


def _extract_document(filename: str, content: bytes) -> tuple[str, str]:
    extension = Path(filename).suffix.casefold()
    if extension not in {".txt", ".pdf", ".docx"}:
        raise HTTPException(status_code=415, detail="Unsupported file type. Upload a .txt, .pdf, or .docx file.")
    if not content:
        raise HTTPException(status_code=422, detail="The selected file is empty.")
    if extension == ".txt":
        if content.startswith(b"%PDF-") or content.startswith(b"PK\x03\x04"):
            raise HTTPException(status_code=422, detail="The file contents do not match the .txt extension.")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=422, detail="Text files must use UTF-8 encoding.") from exc
        if any(ord(character) < 32 and character not in "\t\n\r\f" for character in text):
            raise HTTPException(status_code=422, detail="The .txt file contains binary control characters.")
    elif extension == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=422, detail="The PDF file is corrupt or has an invalid file signature.")
        try:
            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise HTTPException(status_code=422, detail="Encrypted PDFs are not supported. Remove the password and try again.")
            if len(reader.pages) > 200:
                raise HTTPException(status_code=413, detail="PDFs are limited to 200 pages.")
            text_parts = []
            extracted_chars = 0
            for page in reader.pages:
                page_text = page.extract_text() or ""
                extracted_chars += len(page_text)
                if extracted_chars > MAX_SOURCE_CHARS:
                    raise HTTPException(status_code=413, detail=f"Extracted text exceeds the {MAX_SOURCE_CHARS:,}-character source limit.")
                text_parts.append(page_text)
            text = "\n".join(text_parts)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail="The PDF file is corrupt or unreadable.") from exc
    else:
        if not content.startswith(b"PK"):
            raise HTTPException(status_code=422, detail="The DOCX file is corrupt or has an invalid file signature.")
        text = _extract_docx(content)

    if not text.strip():
        detail = "No extractable text was found. This PDF may be scanned or image-only; OCR is not supported."
        raise HTTPException(status_code=422, detail=detail)
    if len(text) > MAX_SOURCE_CHARS:
        raise HTTPException(status_code=413, detail=f"Extracted text exceeds the {MAX_SOURCE_CHARS:,}-character source limit.")
    return text, extension[1:].upper()


@app.post("/api/extract-document")
async def extract_document(file: UploadFile = File(...)):
    filename = _safe_filename(file.filename)
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB upload limit.")
    text, file_type = _extract_document(filename, content)
    return {"filename": filename, "file_type": file_type, "size_bytes": len(content), "text": text}

@app.get("/api/scenarios")
def scenarios():
    result = []
    for path in sorted(SCENARIOS.glob("*.json"), key=lambda p: {"harbor-plan": 0, "library-hours": 1, "garden-trial": 2}.get(json.loads(p.read_text(encoding="utf8"))["scenario_id"], 99)):
        item = json.loads(path.read_text(encoding="utf8"))
        result.append({"scenario_id": item["scenario_id"], "title": item["title"], "description": item["description"], "answer": item["answer"], "sources": item["sources"]})
    return result

@app.post("/api/audit", response_model=AuditResponse)
def audit(request: AuditRequest):
    return run_audit(request)

@app.post("/api/stress-experiment", response_model=StressExperimentResponse)
def stress_experiment(request: StressExperimentRequest):
    try:
        return run_stress_experiment(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@app.get("/api/mutations")
def mutations():
    return public_catalog()

@app.get("/api/challenges")
def curated_challenges():
    return [
        {"id":"caught-number","label":"CAUGHT · numeric contradiction","answer":"The report lists 48 volunteers.","sources":[{"source_id":"s1","title":"Study report","text":"The report lists 48 volunteers."}],"mutation_id":"number.claim","target_id":"claim-1","parameters":{"from":"48","to":"84"},"expected_behavior":"SUPPORTED_TO_CONTRADICTED","expected_challenge":"CAUGHT","limitations":"Narrow numeric contradiction; the baseline deterministic number check is expected to catch it."},
        {"id":"not-supported-quantifier","label":"NOT_SUPPORTED · quantifier change","answer":"Some participants completed the study.","sources":[{"source_id":"s1","title":"Study report","text":"Some participants completed the study."}],"mutation_id":"quantifier.claim","target_id":"claim-1","parameters":{"from":"Some","to":"All"},"expected_behavior":"SUPPORTED_TO_NOT_SUPPORTED","expected_challenge":"NOT_SUPPORTED","limitations":"The baseline has no quantifier entailment rule; loss of exact text support is expected to yield INSUFFICIENT_EVIDENCE, not a contradiction."},
        {"id":"false-support-vocative","label":"FALSE_SUPPORT · vocative comma","answer":"We will eat, Grandma.","sources":[{"source_id":"s1","title":"Example sentence","text":"We will eat, Grandma."}],"mutation_id":"vocative-comma.claim","target_id":"claim-1","parameters":{},"expected_behavior":"SUPPORTED_TO_NOT_SUPPORTED","expected_challenge":"FALSE_SUPPORT","limitations":"Curated English direct-address example. Removing the comma changes the conventional meaning, but punctuation-insensitive normalization may still call it SUPPORTED; this is a narrow documented engine blind spot."}
    ]

@app.post("/api/mutation-run", response_model=MutationRunResponse)
def mutation_run(request: MutationRunRequest):
    try:
        mutation = BY_ID.get(request.mutation_id)
        if mutation is None: raise ValueError(f"Unknown mutation_id: {request.mutation_id}")
        if mutation.side == "EVIDENCE":
            target = next((s for s in request.sources if s.source_id == request.target_id), None)
            if target is None: raise ValueError("A valid target_id source is required for an evidence mutation")
            m, changed, actual = apply_mutation(request.mutation_id, target.text, request.parameters)
            sources = [s.model_copy(deep=True) for s in request.sources]
            if m.mutation_class == "SOURCE_REMOVAL":
                if len(sources) < 2: raise ValueError("At least one source must remain after removal")
                sources = [s for s in sources if s.source_id != target.source_id]
            else:
                next(s for s in sources if s.source_id == target.source_id).text = changed
            original_text, perturbed_text = target.text, changed
            perturbed_answer = request.answer
        else:
            if not request.target_id: raise ValueError("A target_id claim index such as claim-1 is required")
            claims = __import__("backend.service", fromlist=["split_sentences"]).split_sentences(request.answer,"claim")
            index = int(request.target_id.removeprefix("claim-"))-1
            if index < 0 or index >= len(claims): raise ValueError("Unknown claim target_id")
            span=claims[index]
            m, changed, actual=apply_mutation(request.mutation_id, span.text, request.parameters)
            original_text, perturbed_text=span.text, changed
            perturbed_answer=request.answer[:span.start_offset]+changed+request.answer[span.end_offset:]
            sources=[s.model_copy(deep=True) for s in request.sources]
        baseline=run_audit(AuditRequest(answer=request.answer,sources=[s.model_copy(deep=True) for s in request.sources],scenario_id=request.scenario_id))
        perturbed=run_audit(AuditRequest(answer=perturbed_answer,sources=sources,scenario_id=None))
        expected=m.expected_model if baseline.execution_mode.value in {"MODEL","LIVE","MODEL_UNAVAILABLE"} or perturbed.execution_mode.value in {"MODEL","LIVE","MODEL_UNAVAILABLE"} else m.expected_baseline
        comparable=baseline.execution_mode==perturbed.execution_mode and baseline.execution_mode!="FIXTURE"
        before=next((c for c in baseline.claims if c.claim_id==request.target_id),None) if m.side=="CLAIM" else next((c for c in baseline.claims if c.claim_id=="claim-1"),None)
        after=next((c for c in perturbed.claims if c.claim_id==request.target_id),None) if m.side=="CLAIM" else next((c for c in perturbed.claims if c.claim_id=="claim-1"),None)
        comparison,why=compare_expected_behavior(expected,comparable,before,after)
        warnings=[m.limitations]
        if m.mutation_class=="DUPLICATION": warnings.append("Duplicated text is not independent corroboration.")
        if m.side=="EVIDENCE" and m.mutation_class in {"SOURCE_EDIT","SOURCE_REMOVAL","NUMBER","DATE","NEGATION","ENTITY","NOISE","ORDER"}:
            warnings.append("Offsets in each audit result refer to that result's own text; edited-source offsets are not transferable to the original text.")
        if m.mutation_class=="PARAPHRASE" and expected=="UNTESTABLE_IN_MODE": comparison="UNTESTABLE_IN_MODE"; why="Baseline mode has no semantic-preservation oracle for arbitrary paraphrases."
        return MutationRunResponse(mutation=public_catalog()[[x.mutation_id for x in BY_ID.values()].index(m.mutation_id)],target_id=request.target_id or "",changed_text=actual,original_text=original_text,perturbed_text=perturbed_text,expected_outcome=expected,comparison=comparison,explanation=why,applicable=True,warnings=warnings,baseline=baseline,perturbed=perturbed)
    except (ValueError, TypeError) as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc

@app.post("/api/blind-spot-run")
def blind_spot_run(request: BlindSpotRequest):
    return blindspot_report(request.include_project, request.include_heldout)

@app.post("/api/audit-receipt")
def audit_receipt(audit: AuditResponse):
    return receipt_for(audit)

@app.post("/api/repair-preview")
def repair_preview_route(request: RepairRequest):
    try:
        result=repair_preview(request)
        if result.get("offered"):
            result["preview_token"]=bind_preview(request.answer,result["proposed_answer"],request.sources,request.claim_id,result)
        return result
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc

@app.post("/api/repair-apply")
def repair_apply(request: RepairApplyRequest):
    if not request.approved:
        consume_preview(request.preview_token,request.answer,request.proposed_answer,request.sources,request.claim_id)
        raise HTTPException(status_code=409,detail="Repair declined; preview approval was invalidated")
    if not consume_preview(request.preview_token,request.answer,request.proposed_answer,request.sources,request.claim_id):
        raise HTTPException(status_code=409,detail="Preview approval is invalid, expired, already used, or does not match this answer, proposal, claim, and source set")
    token=re.compile(r"(?<!\w)(?:\d{4}-\d{1,2}-\d{1,2}|\d+(?:[.,/]\d+)*)(?!\w)")
    before=list(token.finditer(request.answer));after=list(token.finditer(request.proposed_answer))
    if len(before)!=len(after) or len(before)==0:
        raise HTTPException(status_code=422,detail="A repair must change exactly one existing numeric/date token.")
    changed=[i for i,(left,right) in enumerate(zip(before,after)) if left.group()!=right.group()]
    if len(changed)!=1:
        raise HTTPException(status_code=422,detail="A repair must make exactly one numeric/date token change.")
    i=changed[0]
    reconstructed=request.answer[:before[i].start()]+after[i].group()+request.answer[before[i].end():]
    if unicodedata.normalize("NFC",reconstructed.replace("\r\n","\n"))!=unicodedata.normalize("NFC",request.proposed_answer.replace("\r\n","\n")):
        raise HTTPException(status_code=422,detail="Repair may not modify unrelated answer text.")
    return {"answer":request.proposed_answer,"audit_required":True,"message":"Repair applied to the supplied answer. Run a new audit before presenting findings."}
