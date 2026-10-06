"""The Debugger Agent: finds the root cause of a failure from the error logs.

It is an MCP client. It has no log-fetching code of its own and no RAG:
1. It connects to the MCP server and asks which tools it has (fetch_error_logs).
2. Groq reads the user's problem and calls fetch_error_logs through MCP.
3. The MCP server calls the Dummy Error Log API and hands the logs back.
4. Groq reads the logs and writes the root cause and what to do, in plain words.
"""

from __future__ import annotations

import asyncio
import logging

import groq
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph.state import CompiledStateGraph

from app.agents.text import tidy

logger = logging.getLogger(__name__)

LOG_TOOL = "fetch_error_logs"
# The logs do not change between two calls in one question, so one fetch is
# enough; a second is allowed in case the first used the wrong tenant.
MAX_LOG_FETCHES = 2

LOGS_UNAVAILABLE = (
    "Sorry, I could not fetch the error logs right now, so I cannot check what went "
    "wrong. Please try again in a moment."
)

SYSTEM_PROMPT = """You are the Debugger Agent of NetAI Copilot Lite. A user reports a \
problem with the Maveric platform. You find the root cause from the error logs and \
say what to do. The user is not technical.

Fetching the logs:
- Always call fetch_error_logs first. Use tenant_id "{tenant_id}" unless the user \
names another tenant.
- Fetch the logs once.

Using the logs:
- Base the root cause only on what the logs show. You may use general technical \
knowledge to explain it and to suggest a fix, but never invent log details.
- The logs may hold several errors. Pick the ones that match what the user describes. \
If the user asks about the errors in general, cover each one briefly.
- If the tool result starts with "ERROR", tell the user you could not fetch the logs \
right now. Do not guess a cause.
- If the tool says no error logs were found, say that no errors were found. Do not \
invent a cause.

How to write the answer, for each problem:
What happened: 1 plain sentence.
Why: 1 or 2 plain sentences with the root cause. Mention the one clue in the log that \
proves it.
What to do: at most 3 short steps, starting with "- ".

Plain text only: no ** or backticks, no headings with #. Keep it short. Leave out \
stack traces and long IDs. End with one short line offering more detail, like: \
"Want the technical details from the log?\""""


def root_cause(error: BaseException) -> str:
    """The MCP client wraps connection errors in an ExceptionGroup; show the one inside."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return f"{type(error).__name__}: {error}"


class DebuggerAgent:
    """Connects to the MCP server on the first debug question, then keeps the agent.

    The tools are loaded lazily: the chat still starts if the MCP server is down,
    and the next debug question tries again.
    """

    def __init__(self, llm: BaseChatModel, mcp_server_url: str, tenant_id: str) -> None:
        self._llm = llm
        self._tenant_id = tenant_id
        # The MCP client: only knows the server's address, not its tools
        self._client = MultiServerMCPClient(
            {"maveric": {"transport": "streamable_http", "url": mcp_server_url}}
        )
        self._agent: CompiledStateGraph | None = None
        # One event loop for the whole chat. The MCP tools and Groq's async client
        # are async; a new loop per question would break Groq's reused connection.
        self._loop = asyncio.new_event_loop()

    async def _load_agent(self) -> CompiledStateGraph:
        if self._agent is None:
            # MCP discovery: ask the server which tools it has
            tools: list[BaseTool] = await self._client.get_tools()
            if not any(tool.name == LOG_TOOL for tool in tools):
                raise RuntimeError(f"The MCP server has no {LOG_TOOL} tool")
            self._agent = create_agent(
                model=self._llm,
                tools=tools,
                system_prompt=SYSTEM_PROMPT.format(tenant_id=self._tenant_id),
                middleware=[ToolCallLimitMiddleware(tool_name=LOG_TOOL, run_limit=MAX_LOG_FETCHES)],
            )
        return self._agent

    async def _ask(self, question: str) -> str:
        try:
            agent = await self._load_agent()
            result = await agent.ainvoke({"messages": [{"role": "user", "content": question}]})
        except groq.APIError:
            raise  # Groq problems get the friendly Groq messages in the CLI
        except Exception as error:
            # MCP server down or unreachable: fail gracefully, never make things up
            logger.warning("Debugger could not reach the MCP server: %s", root_cause(error))
            return LOGS_UNAVAILABLE
        return tidy(str(result["messages"][-1].content))

    def ask(self, question: str) -> str:
        """Diagnose one problem report and return the answer."""
        return self._loop.run_until_complete(self._ask(question))
