"""MCP server with one tool, fetch_error_logs.

The Debugger Agent (step 7) connects to this server as an MCP client, finds the
tool, and calls it. The tool calls the Dummy Error Log API and hands the logs back.
The agent never calls the Dummy API itself and has no log-fetching code.

Transport: Streamable HTTP. The MCP address is http://<host>:8002/mcp

Run from the mcp-server/ folder (the Dummy API must be running on port 8001):
    python server.py
"""

from __future__ import annotations

import json
import logging
import os
import re

import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# On your laptop the Dummy API is on localhost; in Docker it is http://dummy-api:8001
DUMMY_API_URL = os.environ.get("DUMMY_API_URL", "http://localhost:8001").rstrip("/")
PORT = int(os.environ.get("MCP_PORT", "8002"))
REQUEST_TIMEOUT_SECONDS = 10

# A tenant ID goes into the URL path, so allow only letters, digits, "-" and "_".
# This stops values like "../admin" from changing which address is called.
TENANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

mcp = FastMCP("Maveric Diagnostics")


@mcp.tool
async def fetch_error_logs(tenant_id: str) -> str:
    """Fetch the recent error logs of a tenant on the Maveric platform.

    Use this when the user reports a failure, crash, timeout or error and you need
    the logs to find the root cause. Each log has the failing service, error code,
    message, stack trace and a context object with the details.

    Args:
        tenant_id: The tenant whose logs to fetch, for example "demo-tenant".
    """
    # Fail gracefully: every problem becomes a message for the agent, never an
    # exception, so the Debugger can tell the user it could not fetch the logs.
    if not TENANT_ID_PATTERN.match(tenant_id):
        return f"ERROR: invalid tenant_id {tenant_id!r}. Use letters, digits, '-' or '_' only."

    url = f"{DUMMY_API_URL}/v1/tenants/{tenant_id}/baselines/logs/errors"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            logs = response.json()
    except httpx.HTTPStatusError as error:
        logger.warning("Error Log API returned %s for %s", error.response.status_code, url)
        return f"ERROR: the Error Log API answered with status {error.response.status_code}."
    except (httpx.HTTPError, ValueError) as error:
        logger.warning("Could not fetch logs from %s: %s", url, error)
        return "ERROR: could not reach the Error Log API. The logs are not available right now."

    if not logs:
        return f"No error logs found for tenant {tenant_id}."
    return json.dumps(logs, indent=2)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """For Docker to check that the server is up. Not an MCP tool."""
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # "http" is fastmcp's name for the Streamable HTTP transport.
    # 0.0.0.0 so other containers can reach it.
    mcp.run(transport="http", host="0.0.0.0", port=PORT)
