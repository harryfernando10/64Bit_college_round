import json
import io
import os
import re
import zipfile
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from backend.models import AuditRequest, AuditResponse, StressExperimentRequest, StressExperimentResponse, MAX_SOURCE
from backend.service import run_audit, run_stress_experiment, SCENARIOS

app = FastAPI(title="Refutella API", version="0.2.0", description="Evidence-based claim auditing against supplied sources")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_BYTES = max(1, int(os.environ.get("REFUTELLA_MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES))))
MAX_SOURCE_CHARS = MAX_SOURCE
MAX_SOURCE_TITLE_CHARS = 160

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "refutella-api", "phase": 3}


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
