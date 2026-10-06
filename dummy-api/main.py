"""Dummy Error Log API: a stand-in for the Maveric service that stores error logs.

One endpoint returns the 3 error logs from /mock-logs as a JSON array:
    GET /v1/tenants/{tenant_id}/baselines/logs/errors

The MCP server (step 6) calls this API; the Debugger Agent never calls it directly.

Run from the dummy-api/ folder:
    uvicorn main:app --port 8001
Then open http://localhost:8001/docs to try it in the browser.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

# dummy-api/main.py -> parents[1] is the project root on your laptop.
# In Docker the file is /app/main.py, so the same rule gives /mock-logs.
DEFAULT_LOGS_DIR = Path(__file__).resolve().parents[1] / "mock-logs"
LOGS_DIR = Path(os.environ.get("LOGS_DIR", str(DEFAULT_LOGS_DIR)))


def load_logs(folder: Path) -> list[dict[str, Any]]:
    """Read every .json file in the folder, in file name order.

    Stops with a clear message if the folder is missing or has no logs
    (fail loudly at startup).
    """
    files = sorted(folder.glob("*.json"))
    if not files:
        raise RuntimeError(f"No error log files (*.json) found in {folder}")
    return [json.loads(file.read_text(encoding="utf-8")) for file in files]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Read the files once when the service starts, not on every request
    app.state.logs = load_logs(LOGS_DIR)
    yield


app = FastAPI(title="Dummy Error Log API", lifespan=lifespan)


@app.get("/v1/tenants/{tenant_id}/baselines/logs/errors")
def get_error_logs(tenant_id: str) -> list[dict[str, Any]]:
    """Return the error logs. Every tenant gets the same 3 logs: this is a dummy."""
    return app.state.logs


@app.get("/health")
def health() -> dict[str, Any]:
    """For Docker and the MCP server to check that the API is up."""
    return {"status": "ok", "logs": len(app.state.logs)}
