import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.models import AuditRequest, AuditResponse
from backend.service import run_audit, SCENARIOS

app = FastAPI(title="Refutella API", version="0.1.0", description="Fixture-backed evidence audit foundation")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "refutella-api", "phase": 1}

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
