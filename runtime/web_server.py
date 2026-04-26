from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn

# Import core logic from opentower_cli
import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / "runtime"))

from opentower_cli.runtime_service import load_runtime_bundle, dispatch_and_maybe_execute
from opentower_cli.auth_config import load_auth_profile, auth_env_overrides

app = FastAPI(title="OpenTower Linux Ops Dashboard")

# Serve static files (HTML/CSS)
STATIC_DIR = REPO_ROOT / "production" / "web"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

class CommandRequest(BaseModel):
    objective: str

@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return "<h1>Index.html not found</h1>"
    return index_path.read_text(encoding="utf-8")

@app.post("/execute")
async def execute_command(req: CommandRequest):
    try:
        root = REPO_ROOT
        runtime = load_runtime_bundle(root=root)
        
        # Load auth and apply environment overrides for the current process
        auth_profile = load_auth_profile(root)
        overrides = auth_env_overrides(auth_profile)
        for k, v in overrides.items():
            os.environ[k] = v
            
        bundle = dispatch_and_maybe_execute(
            root=root,
            objective=req.objective,
            runtime=runtime,
            execute=True
        )
        
        result = bundle.execution_result
        if not result:
            return {"status": "dispatched", "details": bundle.dispatch_result.__dict__}
            
        return {
            "status": result.status,
            "run_id": bundle.dispatch_result.run_id,
            "final_output": result.final_output,
            "transcript_path": str(result.transcript_file),
            "confirmation_id": result.confirmation_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcripts/{run_id}")
async def get_transcript(run_id: str):
    path = REPO_ROOT / "production" / "session-transcripts" / f"{run_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    return FileResponse(path)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
