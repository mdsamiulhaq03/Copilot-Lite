"""Try the MCP server the way the Debugger Agent will: as an MCP client.

It connects, asks which tools the server has, and calls fetch_error_logs.
No Groq and no agent: just the MCP connection.

Run from the mcp-server/ folder (the MCP server must be running):
    python try_client.py                     # tenant "demo-tenant"
    python try_client.py some-tenant         # another tenant
    python try_client.py http://host:8002/mcp demo-tenant
"""

from __future__ import annotations

import asyncio
import sys

from fastmcp import Client

DEFAULT_URL = "http://localhost:8002/mcp"
PREVIEW_CHARS = 600


async def main(url: str, tenant_id: str) -> None:
    async with Client(url) as client:
        print(f"Connected to {url}")

        # 1. Discovery: the client learns the tools from the server
        tools = await client.list_tools()
        for tool in tools:
            print(f"\nTool: {tool.name}")
            print(f"  inputs: {list(tool.input_schema['properties'])}")
            print(f"  description: {tool.description.splitlines()[0]}")

        # 2. Call: the server runs the tool and sends back the result
        print(f"\nCalling fetch_error_logs(tenant_id={tenant_id!r}) ...")
        result = await client.call_tool("fetch_error_logs", {"tenant_id": tenant_id})
        text = result.content[0].text
        print(f"Result ({len(text)} characters):\n{text[:PREVIEW_CHARS]}")
        if len(text) > PREVIEW_CHARS:
            print("...")


if __name__ == "__main__":
    args = sys.argv[1:]
    url = args.pop(0) if args and args[0].startswith("http") else DEFAULT_URL
    asyncio.run(main(url, args[0] if args else "demo-tenant"))
