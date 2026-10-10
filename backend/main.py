import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.models import AuditRequest, AuditResponse, StressExperimentRequest, StressExperimentResponse
from backend.service import run_audit, run_stress_experiment, SCENARIOS

app = FastAPI(title="Refutella API", version="0.2.0", description="Evidence-based claim auditing against supplied sources")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "refutella-api", "phase": 2}

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
