"""Try the Debugger Agent from the terminal, without the chat.

Needs the Dummy API (port 8001) and the MCP server (port 8002) running.

Run from the backend/ folder:
    python -m scripts.debug "The BDT worker keeps crashing"   # one problem
    python -m scripts.debug                                   # type problems one by one
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.agents.debugger import DebuggerAgent
from app.core.config import ConfigError, load_settings
from app.core.llm import friendly_error, load_llm


def show(debugger: DebuggerAgent, question: str) -> None:
    print(f"\n=== {question}")
    try:
        print(debugger.ask(question))
    except Exception as error:
        print(friendly_error(error))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the Debugger Agent about a problem.")
    parser.add_argument("question", nargs="?", help="leave out to type problems one by one")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    settings = load_settings()
    try:
        llm = load_llm(settings)
    except ConfigError as error:
        print(f"ERROR {error}")
        sys.exit(1)
    debugger = DebuggerAgent(llm, settings.mcp_server_url, settings.default_tenant_id)
    print(f"MCP server: {settings.mcp_server_url} | tenant: {settings.default_tenant_id}")

    if args.question:
        show(debugger, args.question)
        return
    while question := input("\nProblem (press Enter to quit): ").strip():
        show(debugger, question)


if __name__ == "__main__":
    main()
