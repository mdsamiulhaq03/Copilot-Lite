# MCP Server - CloudlyNet Copilot

Model Context Protocol (MCP) server exposing the CloudlyNet platform to AI agents, over one
server on `:8082` and, in-process, to the backend's own agents.

Design docs live in the parent repo under `artifacts/copilot/`. This file covers how the code is
laid out and how to add to it.

## Layout

| File | Role |
| --- | --- |
| `server.py` | Composition root. Builds the FastMCP app, calls `domains.register_all`, assembles the programmatic registry. Registers **no tools of its own**. |
| `domains/` | Every tool, grouped by layer. One `register(mcp)` per module. |
| `envelope.py` | The master response envelope (`cloudlynet.mcp.response.v1`). Every tool returns one. |
| `context.py` | `resolve_context()`: tenant and bearer token, read off the inbound connection, never off an LLM argument. |
| `domains/seams.py` | The gateway seams: time normalisation, offset cursors, the 200-versus-500 fan-out, device identity. |
| `domains/shared.py` | The shared gateway client, and the adapter that wraps a pre-existing tool's payload in the envelope. |
| `domains/gate.py` | The three gates on the two mutating tools. |
| `platform_tools.py` | LangChain tool factories, shared between `:8082` and the backend's page-bound registrations. |
| `cloudlynet_client.py` | Typed gateway wrappers. Read methods only, plus the two recommendation decisions. |

## Domains

| Module | Layer | What it answers |
| --- | --- | --- |
| `ndt_tools.py` | Network Digital Twin | Which twin models exist, is training done, what did a run report |
| `data_tools.py` | Ingest and Data | Baselines, UE datasets, NybSys NanoLink PM CSV upload status, and the data-generation guidance tools |
| `optimization_tools.py` | Optimization (CCO/ES/LB/MRO) | Trained model inventory, inference reports, model comparisons |
| `policy_tools.py` | Policy and Guardrails | Guardrail decision log (ops only), TR-069 (CWMP) managed parameter catalogue |
| `observability_tools.py` | Observability and RCA | Alarms, device events, multi-source device timeline |
| `diagnostics_tools.py` | Observability | Platform service error logs |
| `actuation_tools.py` | Actuation | Device-plane reads, plus approving or rejecting a recommendation |

Two registrations are conditional, and "off" means **absent from the registry**, not present and
refusing:

- the two mutating tools, behind `MCP_ENABLE_MUTATING_TOOLS`
- `get_guardrail_decisions`, behind `MCP_COPILOT_OPS_DATABASE_URL`

## Usage

### Over the protocol (`:8082`)

Connect with `Authorization: Bearer <jwt>`. The tenant is read off the token's `custom:tenant_id`
claim and the token is forwarded verbatim on every outbound gateway call. This server is not an
auth authority: the gateway verifies and enforces.

### In Python code

```python
from app.mcp_server import mcp_server

result = await mcp_server.call_tool(
    "query_existing_baselines",
    limit=10,
    tenant_id=tenant_id,
    auth_token=auth_token,
)
```

This surface returns each tool's own payload rather than the envelope: it is the in-process
interface for agents, not the `:8082` wire.

## Adding a tool

1. Pick the domain module whose layer the tool belongs to, or add one and append it to
   `domains/__init__.register_all`.
2. Register it inside that module's `register(mcp)` with `@mcp.tool(name=...)`.
3. Take the tenant and token from `resolve_context()`. Never accept `tenant_id` or `auth_token`
   as a parameter: a registry test asserts no tool exposes either.
4. Return through `envelope.ok` / `empty` / `err` / `partial` / `preview`. Never hand-roll a dict
   and never return a bare string.
5. Report every downgrade in `query.ignored` with a typed reason. Silence is the one forbidden
   outcome.
6. Reuse `domains/seams.py` for paging, cursors and time. A second copy of the fan-out arithmetic
   is how the two drift.
7. Add the tool to `TOOL_ARGS` in `tests/test_mcp_envelope.py`. The registry conformance test
   fails if you do not, which is the point.

## Tests

```bash
cd backend && python -m pytest tests/test_mcp_envelope.py     # envelope + registry conformance
cd backend && python -m pytest -k mcp                          # every MCP suite
```

The load-bearing one walks the live registry, invokes every tool against mocked upstreams, and
validates each reply against the vendored JSON Schema.

## Tracing

The container reports its whole lifecycle to stdout. `./scripts/kafka/compose.sh logs copilot-mcp-server`
(from the parent repo) is the only view of what an external MCP client actually did — nothing
in-house connects to `:8082`, so this log is the sole evidence.

Two knobs, both read from the environment: `MCP_TRACE_DETAIL` (`off` | `basic` | `full`, default
`basic`) and `MCP_LOG_LEVEL` (default `INFO`). The trace and audit loggers are pinned to INFO
independently, so raising `MCP_LOG_LEVEL` quiets the server without silencing either.
**Response bodies are never logged at any level.**

| Event | When | Carries |
| --- | --- | --- |
| `mcp_boot` | once, before accepting connections | registry size and every tool name, plus one `gated_off` line per withheld tool **with the reason** |
| `mcp_session_open` | `GET /sse` | `conn`, peer, user-agent, `auth=present\|absent`, `xcorr` |
| `mcp_handshake` | `initialize` | client name/version, protocol version, declared capabilities |
| `mcp_list` | `tools/list` | `rid`, `sid`, `tsid`, tool count |
| `mcp_call` | every `tools/call` | identity, envelope facts, upstream calls — see below |
| `mcp_session_close` | the SSE stream ends | session duration, reason, sessions still open |
| `mcp_http_error` | 4xx/5xx on `/messages/` | the unknown-or-expired-session case, otherwise invisible |
| `mcp_shutdown` | SIGTERM/SIGINT | uptime and process totals |

A real run:

```
mcp_boot server=netai-copilot-mcp version=0.1.0 transport=sse bind=0.0.0.0:8080 sse_path=/sse
         msg_path=/messages/ tools=34 upstream=http://maveric_gateway:8080 timeout_s=30.0
         org_tenant=set mutating=False log_level=INFO trace=basic fastmcp=2.14.4
         mcp_sdk=1.26.0 pid=29
    tools compare_datasets,compare_inference_models,...
    gated_off approve_recommendation,reject_recommendation reason=MCP_ENABLE_MUTATING_TOOLS=false
    gated_off get_guardrail_decisions reason=ops_dsn_unset
mcp_session_open conn=4f498d55 peer=<host-ip>:52470 ua=python-httpx/0.28.1 auth=present
                 xcorr=sse-probe-1 sessions_open=1
mcp_handshake tsid=- client=mcp/0.1.0 proto=2025-11-25 caps=- ms=1.8
mcp_list rid=1 sid=1683a6ad tsid=c926940b tools=34 ms=2.9
mcp_call tool=get_observability_capabilities outcome=ok ms=0.8 rid=2 sid=1683a6ad tsid=c926940b
         tenant=- role=- xcorr=- args=- kind=summary n=6 bytes=2302
mcp_call tool=get_active_alarms outcome=ok ms=290.6 rid=3 sid=1683a6ad tsid=c926940b
         tenant=00000000 role=cloudly_admin xcorr=sse-probe-1 args=limit
         kind=collection n=5 trunc=limit cursor=yes ign=1 bytes=2923
         up=1 up_att=1 up_ms=274.7 up_status=200
mcp_session_close conn=4f498d55 peer=<host-ip>:52470 s=0.4 reason=disconnect sessions_open=0
mcp_shutdown s=13.5 reason=SIGTERM sessions_total=1 sessions_cut=0 calls=2 calls_failed=0
             up_attempts=1
```

Read the two `mcp_call` lines together. The first never left the process: no `tenant`, no `up=`.
The second went to the gateway, came back capped, and had one parameter it could not honour.

`outcome` is one of `ok` `empty` `error` `preview` `partial` `raised`. `up_att > up` means the
client retried upstream — that is how "our tool is slow" is told apart from "the gateway is flaky".
An `outcome=error code=AUTH_CONTEXT_MISSING` line with **no `up=` fields at all** is the proof that
an unauthenticated call emits zero outbound HTTP.

Drive it yourself, beside a log tail:

```bash
python scripts/test_mcp_sse_client.py            # initialize -> list -> two calls -> disconnect
python scripts/test_mcp_sse_client.py --no-auth  # expect AUTH_CONTEXT_MISSING, no up= fields
```

### Three things that are not what you would guess

- **`on_notification` never fires.** Every `MiddlewareContext` in fastmcp 2.14.4 hardcodes
  `type="request"`, and notifications are consumed inside the MCP SDK before fastmcp sees them.
  Observing them needs `mcp.server.lowlevel.server` at DEBUG, which also logs full request bodies —
  so it stays an escape hatch, not a wiring.
- **There is no session-teardown hook**, which is why `SessionTraceMiddleware` is ASGI: it brackets
  the long-lived `GET /sse` call, whose entry and exit *are* the session lifetime.
- **`mcp_handshake` shows `tsid=-`.** The transport session id is not in scope during
  `on_initialize` under SSE. Sessions still correlate — `conn` brackets open/close and `sid`/`tsid`
  join every call — but no single line carries both `conn` and `tsid`, so joining the bracket to
  the calls means using the timestamp and `peer`.
