from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from content_agent.api.schemas import CreateRunRequest, RunResponse, RunStatus

app = FastAPI(title="Content Agent API")


# Temp storage, till we have db
RUNS: dict[str, RunResponse] = {}


@app.post("/runs", response_model=RunResponse, status_code=201)
def create_run(request: CreateRunRequest):
    run = RunResponse(
        run_id=str(uuid4()),
        topic=request.topic,
        guidance=request.guidance,
        status=RunStatus.QUEUED,
        created_at=datetime.now(timezone.utc),
    )
    RUNS[run.run_id] = run

    return run

@app.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: str):
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run

@app.get("/health")
def health():
    return {"status": "ok"}