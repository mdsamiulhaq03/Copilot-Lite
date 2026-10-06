# EPIC 8 — Copilot MCP layer coverage (`cloudlynet_ai_copilot`)

**Epic ID:** E8
**Title:** Copilot MCP: one server, per-domain tool modules — master response envelope, JWT/tenant threading fix, Network Digital Twin + Ingest/Data + Optimization + Actuation/TR-069 + Policy & Guardrails + Observability/RCA modules, placeholder retirement, docs lockstep
**Goal:** Answer the standing platform question "shall we add MCP servers for copilot in all layers/sub-layers (Intelligence Layer: Ingest, Network Digital Twin, Optimization, Policy & Guardrails; Actuators: TR-069)?" with a built decision: **one** MCP server (the existing FastMCP SSE service on :8082) whose tool registry is organized into **per-domain tool modules**, not N per-layer servers. The epic first freezes the **master response envelope** every tool in every layer returns (S0), then repairs the :8082 auth/tenant model (JWT-derived tenant binding, kill the hardcoded default tenant), fills the empty domains (Network Digital Twin, Ingest/Data, Optimization, Actuation/TR-069, Policy & Guardrails, Observability/RCA), retires the two placeholder tools, and locks the docs.

**Naming note (2026-07-29 grounding):** the platform's first layer is the **Intelligence Layer** (formerly "Core"). Domain module names and the `tool.domain` enum are unaffected (`ingest`, `ndt`, `optimization`, `policy`, `actuation`, `observability`); only prose changes.
**Depends on:** Independent of the E0–E7 merge chain — no shared migration numbers, no shared Kafka topics, no shared service code. Can start any time after E0 (E0.S4 naming commit, so new copy lands post-rebrand). Depends only on copilot submodule state: JWT forwarding (SUMMARY §22) and the guardrail middleware + decision log (SUMMARY §§ guardrails; `artifacts/copilot/guardrail-rls-decision.md`) are merged, which they are on `main`. Stories bind only to **today's** gateway contracts (`artifacts/design/openapi.yaml`); surfaces E1–E5 add later (`/ndt/**`, `/ingest/**`, loop endpoints) are explicitly out of scope and flagged as follow-ups.

**Decision (frozen for this epic):** ONE MCP server, per-domain tool MODULES.
- Every tool — whatever layer it serves — reaches the platform through the same gateway (`http://gateway:8080`) with the same per-request JWT. Per-layer servers would multiply the auth surface (N places to capture, thread, and audit tokens), the ops burden (N containers, N health checks, N compose/chart entries — violating the zero-CI/CD instinct of this re-architecture), and the registry drift risk, while buying **zero** isolation: all N would call the same gateway with the same credentials.
- Domain separation lives in the code layout (`app/mcp_server/domains/<domain>_tools.py`, one module per layer/sub-layer) and in tool naming/description conventions, not in deployment topology.
- Revisit trigger (recorded, not planned): only if a domain someday needs credentials the others must not hold (e.g. the S6 `copilot_ops` DSN growing write scope) does a second server become worth its ops cost.

**Definition of done (epic):**
- [ ] **Every** tool on :8082 returns the master envelope `cloudlynet.mcp.response.v1` (`artifacts/copilot/mcp-master-payload.md`, JSON Schema `artifacts/copilot/mcp-envelope.schema.json`). Zero tools return a bare string. A registry-wide parametrised test validates every tool's output against the schema, so a non-conforming tool cannot ship.
- [ ] Every filter parameter on every tool is **optional**: a tool invoked with no arguments returns a bounded default result, never a validation error. `query.applied_defaults` reports what the caller did not choose; `query.ignored` reports every accepted-but-not-honoured parameter (no silent downgrades).
- [ ] The Observability/RCA domain exists (`domains/observability_tools.py`): device log search with neighbour context, FM alarm state, device timeline, raw log window fetch. `result.kind: "empty"` is distinguishable from `success: false` on every one of them.
- [ ] No tool on :8082 carries a hardcoded `tenant_id` default (the literal `00000000-0000-0000-3029-000000000000` appears nowhere in `backend/app/mcp_server/`); tenant identity is derived from the per-connection JWT and is never an LLM-visible parameter on gateway-calling tools.
- [ ] Every gateway-calling tool on :8082 sends `Authorization: Bearer <jwt>` captured from the inbound MCP connection; an unauthenticated connection gets structured tool errors, never a malformed `/v1/tenants//…` path (SUMMARY §9 known issue closed).
- [ ] `app/mcp_server/domains/` exists with one module per domain — `ndt_tools.py` (Network Digital Twin, read-only), `data_tools.py` (Ingest/Data), `optimization_tools.py` (Optimization incl. the two inference tools registered with explicit context params), `actuation_tools.py` (TR-069 (CWMP) device plane, mutations confirm-gated), `policy_tools.py` (Policy & Guardrails), `diagnostics_tools.py` (cross-service error logs) — and `server.py` is a thin composition root (`register_all(mcp)`).
- [ ] The two placeholder tools (`get_model_accuracy`, `list_available_models`) are deleted from `server.py`, `tools.py`, and tests.
- [ ] Mutating tools exist ONLY in the actuation module, are limited to recommendation approve/reject, and are triple-gated: `confirm` parameter (default false → preview, never execute), `MCP_ENABLE_MUTATING_TOOLS` env (default false), and JWT role check (trial users always refused). No tool can create arbitrary device commands.
- [ ] The guardrail decision log is readable through exactly one tool, SELECT-only, over a dedicated `copilot_ops` connection per `artifacts/copilot/guardrail-rls-decision.md` (D2/D3); the tool is absent/refusing when the ops DSN is not configured; the app-role connection is never used to read the log.
- [ ] `COPILOT_IMPLEMENTATION_SUMMARY.md` documents the domain-module layout and tool inventory (updated via the submodule's PR-driven protocol), `artifacts/copilot/mcp-domain-coverage.md` records the one-server decision, and all new user-visible copy passes `artifacts/marketing/claims-guardrails.md` (naming: "Network Digital Twin", "TR-069 (CWMP)", "Optimization"; no O-RAN/RIC/SMO compliance claims; no em dash in marketing-bound text).
- [ ] Zero CI/CD change: no new container, image, port, or compose/chart service. :8082 (container port 8080, SSE) stays the only MCP listener. New env vars ride the existing service definitions.

**Binding constraints (all stories):**
1. **Copilot PR protocol.** All submodule work follows `submodule/cloudlynet_ai_copilot/CLAUDE.md`: read `COPILOT_IMPLEMENTATION_SUMMARY.md` before starting; never push without explicit user consent; `python -m black` / `python -m ruff` once at the end of a change set; SUMMARY/HISTORY updates only from a user-confirmed final PR description (ask first — the intent is non-negotiable).
2. **Gateway-mediated access only.** MCP tools reach the platform exclusively through the gateway with the per-request user JWT. Never a service API key, never a direct call to a backend service port, never a direct connection to a platform database. Sole exception, scoped in E8.S6: a SELECT-only `copilot_ops` connection to copilot's **own** `netai_copilot` DB per the RLS decision record.
3. **:8082 is not an auth authority.** It forwards tokens and reads claims for URL construction only; the gateway remains the single enforcement point. A forged tenant claim still dies at the gateway.
4. **Human-in-the-loop for mutations.** No mutating tool executes without an explicit confirm handshake relayed to the human; guidance-only agents (SUMMARY §20) stay guidance-only.
5. **Claims guardrails.** Any user-visible copy (tool descriptions, README text, docs) obeys `artifacts/marketing/claims-guardrails.md`: solution term "Network Digital Twin" (never bare "Digital Twin"; proper nouns Maveric BDT / Bayesian Digital Twin stay), "TR-069 (CWMP)" for the device plane, "Optimization" for the rApp layer, product name CloudlyNet, never "NetAI" in new copy (lowercase `netai` infra identifiers like `server_name: netai-copilot-mcp` are out of scope — not-yet-migrated infra, per parent CLAUDE.md).
6. **Do not break the backend page-bound path.** The in-chat factories (`platform_tools.py`) keep working exactly as SUMMARY §§20/22/24 describe; :8082 registration is additive.

---

## Context refresh (2026-08-10) — read before executing any story

Written after E0–E6 merged to every repo's main and the prod charts were made re-architecture-ready.
Four things changed since this epic was authored (2026-07-23); the stories below are unchanged, but
their binding surface and two rollout assumptions moved.

1. **The "later" surfaces exist now.** The "Depends on" note above ("surfaces E1–E5 add later …
   are explicitly out of scope") is overtaken: `artifacts/design/openapi.yaml` is at **v0.6.0**
   and carries `/ndt/**` (evaluate, kpis, feature-builds, loop policy/proposals/actions with
   :approve/:reject), `/ingest/**`, and `/data/{pm,fm,cm}` — all gateway-routed and live. E8
   stories bind to v0.6.0, not to the older file this epic quoted. The risk-8 follow-ups
   (`evaluate_twin_scenario`, loop action/feedback visibility) are now *buildable* the moment
   their domain module lands; they remain out of this epic's scope but are no longer blocked.
   S8 tranche A's `/data/fm` backing surface is no longer a future: E1.S5 is merged and
   documented.
2. **The MCP payload contract is AGREED, v1.1 (2026-08-10).** The copilot team confirmed the
   envelope and the platform accepted three deltas — field projection (`fields`) on every list
   tool, advisory reply sizing with defined `limit`/`size_cap` interplay, and a bounded+paged
   `fetch_raw_log_window` with **no bulk mode**. `correlation_id` is minted by the copilot
   orchestrator (one per RCA session); `next_actions` is load-bearing (their agent loop executes
   its `args` verbatim); the Postgres raw-line row floor is a confirmed **90-day requirement**.
   Decision record: `artifacts/copilot/HANDOVER-mcp-log-rca.md` §9/§11; normative spec:
   `mcp-master-payload.md` v1.1. **S0 and S8 implement the v1.1 contract**, and S8 gains the
   inline deltas below; a new **S9** ships the RCA incident fixture pack the copilot team asked
   for on 2026-08-10.
3. **Sizing basis for :8082.** From the copilot side: an RCA session is bounded at ~8 tool calls
   and 6 reasoning turns; expect a few concurrent sessions per tenant, asking for
   larger-but-bounded replies (a few hundred lean projected lines each, self-sized to the model's
   input budget). A firm p95 target arrives after they time their fixture (S9 feeds this).
4. **There is no staging environment.** Staging infra was deleted 2026-08-10 (charts preserved
   unmaintained in maveric-deployment `backup/`). The env-rollout note below ("staging first,
   watch the audit lines" for `MCP_ENABLE_MUTATING_TOOLS`) is overtaken: rehearse the mutation
   gate in the local compose stack instead, then enable in prod default-off with the audit lines
   watched from day one. Orientation for agents: the `.context` graph now has current pages for
   `ndt-decision-hub`, `data-platform`, `ric-integration`, and `actuator-framework`, and the
   claims bundle was re-verified 2026-08-10 — tool descriptions must keep passing the E6.S5 grep
   (`backend/app/mcp_server/domains/` is in its sweep).

---

## E8.S0 — Master response envelope (`cloudlynet.mcp.response.v1`)

**Why:** Every one of the ten tools on :8082 returns a bare `str` (`server.py`, all `-> str`). An
agent consuming them cannot distinguish "no results" from "the call failed", cannot tell a truncated
list from a complete one, and cannot tell whether a value is 30 seconds or 3 days old. Each of those
is a direct hallucination source, and each gets worse as the registry grows from 12 tools to roughly
30 in this epic. The copilot team asked for exactly this ("design the mcp payload, like a master
payload structure, we will follow the same across all mcp servers") and correctly flagged that a
*universal payload* is not achievable. The resolution is the one recorded in
`artifacts/copilot/mcp-master-payload.md`: universalise the envelope, keep the body per-domain,
discriminate it with `result.data_type`. This story lands the envelope and the builders first, so
every later story is written against it instead of retrofitted.

**Size:** M

**Scope:**
- In: `app/mcp_server/envelope.py` with the response builders (`ok`, `empty`, `err`, `preview`) and
  the `ToolDomain` enum; adoption by all ten existing tools (mechanical: wrap the current return
  value as the `data` body, add `result.data_type`, keep the tool names and LLM-visible schemas
  byte-identical); the shared registry-wide conformance test; a copy of the JSON Schema vendored
  into the submodule for test use with a provenance header pointing at the parent artifact.
- Out: any new tool (S2 onward); any change to the *content* of what existing tools return beyond
  wrapping it (a content change is a later story's business); the query-parameter optionality sweep
  on pre-existing tools where a parameter is genuinely required today (record those in the PR; S1
  removes `tenant_id`, later stories relax the rest).

**Files:**
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/envelope.py`
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/schemas/mcp_response_v1.json` (vendored copy, provenance header)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/server.py` (all ten tools return the envelope)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/schemas.py` (`RappComparisonResponse.to_markdown` becomes the `data` body producer, not the tool return)
- Create: `submodule/cloudlynet_ai_copilot/backend/tests/test_mcp_envelope.py`

**Contract:** frozen in [`artifacts/copilot/mcp-master-payload.md`](../../../copilot/mcp-master-payload.md).
Required keys `schema`, `success`, `timestamp`, `tool`, `result`, `data`, `errors`; optional
`message`, `context`, `query`, `provenance`, `freshness_s`, `next_actions`. Load-bearing invariants:

1. `result.kind: "empty"` with `success: true` is a **finding** (query valid, zero matches).
   `success: false` is a **failure**. Never collapse them.
2. `result.truncated: true` requires `truncation_reason`. Silent truncation is a defect.
3. `errors[].hint` names a concrete recovery action, ideally another tool. Never a stack trace,
   never a raw upstream body.
4. `PARTIAL_RESULT` is the only code permitted alongside `success: true`.
5. Serialise with `json.dumps(..., separators=(",", ":"))`; target under ~8 KB per response.

**Key snippets:**

```python
# app/mcp_server/envelope.py
SCHEMA_ID = "cloudlynet.mcp.response.v1"


def ok(tool: ToolIdentity, *, data_type: str, data: dict[str, Any],
       count: int, total_matched: int | None = None, truncated: bool = False,
       truncation_reason: str | None = None, message: str | None = None,
       query: dict[str, Any] | None = None, provenance: list[dict] | None = None,
       next_actions: list[dict] | None = None, kind: str = "collection") -> str:
    """Build and serialise a success envelope. The ONLY way a tool returns data."""


def err(tool: ToolIdentity, code: str, message: str, *,
        details: dict | None = None, retryable: bool = False,
        hint: str | None = None) -> str:
    """Build and serialise an error envelope (result.kind == 'error')."""
```

**Acceptance criteria:**
- `grep -n '\-> str:' app/mcp_server/server.py` still matches every tool (MCP returns text), but no
  tool body constructs its return by string concatenation or bare `json.dumps` of a payload: every
  return path goes through `envelope.ok/empty/err/preview`.
- A parametrised test walks the FastMCP registry, invokes every tool against mocked upstreams, and
  validates each response against `mcp_response_v1.json`. Adding a non-conforming tool fails it.
- Tool names and LLM-visible parameter schemas are byte-identical to pre-change (golden snapshot).
- The vendored schema file is identical to `artifacts/copilot/mcp-envelope.schema.json` (asserted by
  a hash comparison test or a documented sync step in the PR).
- Negative tests: `truncated: true` without `truncation_reason` is rejected; `success: false` with
  an empty `errors` array is rejected.
- `cd submodule/cloudlynet_ai_copilot/backend && python -m pytest` passes.

**Test plan:**
- Unit: `tests/test_mcp_envelope.py` — builder output shape; the two negative controls above; empty
  vs error distinction; ~8 KB size guard on a synthetic large result.
- Regression: existing tool tests updated once (they now assert on `data`, not the raw string); any
  test needing more than a `["data"]` unwrap indicates a content change, which is out of scope.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai), submodule
submodule/cloudlynet_ai_copilot. FIRST read COPILOT_IMPLEMENTATION_SUMMARY.md at the
submodule root (mandatory per its CLAUDE.md), then read the parent repo's
artifacts/copilot/mcp-master-payload.md (the frozen envelope contract) and
artifacts/copilot/mcp-envelope.schema.json (its JSON Schema). Git rule: cd into the
submodule for git ops; never push without explicit user consent.

Task: give every MCP tool on :8082 the master response envelope. Today all ten tools
in backend/app/mcp_server/server.py return a bare str, so an agent cannot tell "no
results" from "failed", cannot see truncation, and cannot judge freshness.

Build:
1. backend/app/mcp_server/envelope.py: SCHEMA_ID constant, a ToolIdentity dataclass
   {name, domain, server, contract_version}, a ToolDomain enum (ingest, ndt,
   optimization, policy, actuation, observability), and builders ok(), empty(), err(),
   preview() that construct the envelope and return json.dumps(..., separators=(",",
   ":")). Enforce in code: truncated=True requires truncation_reason; success=False
   requires at least one error and result.kind == "error"; PARTIAL_RESULT is the only
   code allowed with success=True.
2. Vendor the schema to backend/app/mcp_server/schemas/mcp_response_v1.json with a
   provenance header comment naming artifacts/copilot/mcp-envelope.schema.json as the
   source of truth, plus a test asserting the two files match.
3. Convert all ten existing tools to return envelope.ok/empty/err. This is a WRAPPING
   change: today's return value becomes the `data` body under a `result.data_type`
   name; do NOT change what each tool computes, and do NOT change any tool name or
   LLM-visible parameter schema (golden snapshot test proves it).
4. Tests backend/tests/test_mcp_envelope.py: a parametrised test over the FastMCP tool
   registry that invokes every tool against mocked upstreams and validates the output
   against the vendored JSON Schema (use the jsonschema package; add it to the dev
   dependencies if absent). Include the two negative controls. Update existing tool
   tests to unwrap ["data"] - if a test needs more than that unwrap, you have changed
   content, which is out of scope: revert that part.

Constraints: zero CI/CD change; no new tool; gateway-mediated access only; follow the
submodule CLAUDE.md working preferences (python -m pytest, black+ruff ONCE at the end,
never push without consent, ask before updating SUMMARY from the PR). Naming in any
new doc or comment text: "Intelligence Layer", "Network Digital Twin", "TR-069 (CWMP)";
never "NetAI" in new copy; no em dash.

Definition of done: every registry tool validates against the schema in the
parametrised test; tool names and schemas unchanged; cd backend && python -m pytest
passes.
```

---

## E8.S1 — Tenant/JWT threading on :8082 (kill the hardcoded tenant default)

**Why:** The standalone MCP server is broken and unsafe in two ways. (1) Its module-level client is built with no token — `server.py` constructs `_api_client = CloudlyNetAPIClient()` and calls every tool factory **without** `auth_token`, so every outbound gateway call carries no `Authorization` header and 401s against the post-§22 gateway (`CLOUDLYNET_API_KEY` was deleted; Bearer is mandatory). (2) The four gateway-calling tools (`compare_rapp_policies` server.py:84, `get_platform_error_logs` server.py:122, `query_existing_baselines` server.py:285, `compare_datasets` server.py:312) expose `tenant_id` as an LLM-visible parameter defaulting to the hardcoded literal `00000000-0000-0000-3029-000000000000` — an invitation to cross-tenant confusion, plus the known §9 issue that an empty `tenant_id` builds a malformed `/v1/tenants//…` path returning a silent 404. This story makes :8082 derive both token and tenant from the inbound connection, exactly mirroring the backend's §22 threading model. Every later story builds on this context helper.

**Size:** M

**Scope:**
- In: per-invocation capture of the inbound `Authorization: Bearer <jwt>` header on the SSE/HTTP MCP connection; tenant derivation from the token payload's `custom:tenant_id` claim — the gateway's JWT contract (`maveric_platform_gateway/internal/auth/jwt.go`); note `app/core/auth.py` `get_current_user()` maps only `custom:role` today because backend tenant is URL-path-only (SUMMARY §9 Phase 11 resolution), so this story adds shared claim-name constants to `auth.py` and imports them (never duplicate claim-name literals); a `ToolContext` helper module all domain modules will import; removal of all four hardcoded `tenant_id` defaults and of `tenant_id` as an LLM-visible parameter on gateway-calling tools; factory-level guard raising a structured error on empty/None tenant (closes SUMMARY §9); deletion of the dead `MCPConfig.cloudlynet_api_key` remnant (`MCP_CLOUDLYNET_API_KEY`) from `config.py`; tests.
- Out: any new tool (S2–S6), any change to the backend page-bound factories' behavior (they already thread `auth_token` correctly per §22 — only the shared empty-tenant guard touches them), any change to transport/port/container (`server_docker.py` stays SSE on container port 8080 → host 8082), token *verification* (gateway's job; :8082 decodes without verifying, constraint 3).

**Files:**
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/context.py`
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/server.py` (four tools lose the `tenant_id` param + default; resolve `ToolContext` per invocation; pass `auth_token` through)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/platform_tools.py` (empty-tenant guard in the gateway-calling factories: raise a clear error instead of building `/v1/tenants//…`)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/config.py` (delete `cloudlynet_api_key`; add nothing else here)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/core/auth.py` (extract `CLAIM_ROLE = "custom:role"` and add `CLAIM_TENANT_ID = "custom:tenant_id"` as module-level constants; `get_current_user()` behavior unchanged)
- Modify: `submodule/cloudlynet_ai_copilot/backend/tests/test_mcp_tools.py` (empty-tenant guard cases)
- Create: `submodule/cloudlynet_ai_copilot/backend/tests/test_mcp_context.py`
- Modify: `submodule/cloudlynet_ai_copilot/backend/.env.example` (document that :8082 needs no tenant env — tenant comes from the JWT; note `MCP_CLOUDLYNET_API_KEY` removal)
- Modify: `submodule/cloudlynet_ai_copilot/backend/README.md` (drop the `MCP_CLOUDLYNET_API_KEY` row from the env-var table)
- Modify: `submodule/cloudlynet_ai_copilot/backend/scripts/run_mcp_server.py` (remove the `MCP_CLOUDLYNET_API_KEY` line from the usage docstring)

**Contract:**

`ToolContext` — the epic-wide seam every domain module consumes (S2–S6 import it; freeze the shape here):

- `resolve_context() -> ToolContext{tenant_id: str, auth_token: str, role: str | None}` — reads the inbound request of the current MCP invocation. Raises `ToolContextError` (mapped to a structured tool error payload `{"error": "auth_context_missing" | "tenant_unresolved", "hint": …}`) when the header is absent or the tenant claim is empty/invalid-UUID.
- Gateway-calling tools call it first; they never accept `tenant_id` from the LLM.
- Transport mechanics: prefer FastMCP's request-context accessor (e.g. `get_http_request()` in fastmcp ≥2); if the pinned FastMCP version lacks it, wrap the SSE app in a Starlette middleware that stashes headers in a `ContextVar`. Either implementation satisfies this contract; pick at build time and record which in the PR.

**Key snippets:**

`app/mcp_server/context.py`:

```python
"""Per-invocation auth context for the standalone MCP server (:8082).

The server is NOT an auth authority: the JWT is decoded WITHOUT verification,
solely to build tenant-scoped gateway URLs; the gateway verifies and enforces
on every call. Claim names are shared constants in app/core/auth: CLAIM_ROLE
("custom:role", already mapped by get_current_user) and CLAIM_TENANT_ID
("custom:tenant_id", the gateway's JWT contract — not previously mapped in the
backend because its tenant is URL-path-only). Import the constants, never
duplicate the literals.
"""
from __future__ import annotations

from dataclasses import dataclass


class ToolContextError(Exception):
    """Raised when the inbound MCP request lacks a usable Bearer/tenant."""

    def __init__(self, code: str, hint: str) -> None: ...


@dataclass(frozen=True)
class ToolContext:
    tenant_id: str
    auth_token: str
    role: str | None = None


def resolve_context() -> ToolContext:
    """Read Authorization from the current MCP invocation's HTTP request,
    decode the tenant claim, validate UUID shape. Raises ToolContextError."""
```

Tool shape after the change (`server.py`, all four gateway tools follow this pattern):

```python
@mcp.tool(name="get_platform_error_logs")
async def get_platform_error_logs(service: str = "baselines",
                                  severity: str | None = None,
                                  page: int = 1, page_size: int = 50) -> str:
    ctx = resolve_context()          # ToolContextError -> structured error JSON
    return await _error_logs_tool.ainvoke({..., "tenant_id": ctx.tenant_id,
                                           "auth_token": ctx.auth_token})
```

**Acceptance criteria:**
- `grep -rn "00000000-0000-0000-3029-000000000000" submodule/cloudlynet_ai_copilot/backend/app/mcp_server/` returns nothing.
- No `@mcp.tool` on :8082 exposes `tenant_id` as a parameter (LLM-visible schema inspected in a test via the FastMCP tool registry).
- With a Bearer header on the SSE connection, `get_platform_error_logs` reaches the gateway with that exact token and the JWT-derived tenant in the path (asserted against a mocked httpx transport).
- Without a Bearer header, each gateway tool returns the structured `auth_context_missing` error; no HTTP call leaves the process; nothing builds `/v1/tenants//`.
- Empty-string/None tenant reaching a factory raises the new guard error (SUMMARY §9 case), covered by tests for both the :8082 path and the backend factory path.
- `MCP_CLOUDLYNET_API_KEY` / `cloudlynet_api_key` no longer exist in the submodule (`grep -ri cloudlynet_api_key` empty).
- `cd submodule/cloudlynet_ai_copilot/backend && python -m pytest` passes; backend in-chat tool flows (debugger/data-gen/inference tests) pass unmodified.

**Test plan:**
- Unit: `tests/test_mcp_context.py` — header present/absent/malformed, tenant claim missing/invalid UUID, ContextVar isolation across concurrent invocations. `tests/test_mcp_tools.py` — extend with guard cases; assert outbound Authorization via a recording httpx mock.
- Integration (compose): `./scripts/kafka/compose.sh up`; connect an MCP client to `localhost:8082/sse` with a real Cognito JWT; call `get_platform_error_logs`; verify a 200 through the gateway and the tenant path matches the token's tenant.
- Lint tail: `python -m black backend/ && python -m ruff check --fix backend/` once, at the end.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai), submodule
submodule/cloudlynet_ai_copilot. FIRST read COPILOT_IMPLEMENTATION_SUMMARY.md at the
submodule root (mandatory per its CLAUDE.md), especially §9 (known issue: no guard for
empty tenant_id in MCP tool factories) and §22 (JWT forwarding). Git rule: cd into the
submodule for git ops; never push without explicit user consent.

Task: fix tenant/JWT threading on the standalone MCP server (FastMCP SSE, container
copilot-mcp-server, host port 8082; entrypoint backend/app/mcp_server/server_docker.py).

Current defects (verified against backend/app/mcp_server/):
- server.py builds a module-level CloudlyNetAPIClient() and invokes
  create_rapp_comparison_tool/create_error_logs_tool/get_data_generation_tools WITHOUT
  auth_token, so outbound gateway calls carry no Authorization header and 401
  (the gateway requires Bearer since the §22 work deleted CLOUDLYNET_API_KEY).
- Four tools expose tenant_id as an LLM-visible param defaulting to the hardcoded
  literal 00000000-0000-0000-3029-000000000000: compare_rapp_policies (server.py:84),
  get_platform_error_logs (:122), query_existing_baselines (:285), compare_datasets
  (:312).
- Empty tenant_id builds a malformed /v1/tenants//... path (silent 404).
- config.py still declares cloudlynet_api_key (MCP_CLOUDLYNET_API_KEY) — dead remnant.

Build:
1. backend/app/mcp_server/context.py: ToolContext dataclass {tenant_id, auth_token,
   role|None}, ToolContextError(code, hint), resolve_context(). resolve_context reads
   the inbound Authorization: Bearer header of the CURRENT MCP invocation — use
   FastMCP's request accessor if the pinned version has one, else a Starlette
   middleware on the SSE app stashing headers in a ContextVar — and decodes the JWT
   WITHOUT signature verification (the gateway is the sole enforcement point; :8082
   only needs the tenant claim for URL construction). Claim names: role is
   custom:role, exactly as app/core/auth.get_current_user already maps it; tenant is
   custom:tenant_id — the gateway's JWT contract
   (maveric_platform_gateway/internal/auth/jwt.go) — which auth.py does NOT map today
   (backend tenant is URL-path-only, SUMMARY §9 Phase 11 resolution). Add
   CLAIM_ROLE/CLAIM_TENANT_ID constants to app/core/auth.py (get_current_user
   switches to CLAIM_ROLE, zero behavior change) and import them in context.py — do
   not duplicate string literals. Validate tenant is a UUID; raise ToolContextError
   ("auth_context_missing" for no/invalid header, "tenant_unresolved" for a missing or
   non-UUID tenant claim).
2. server.py: remove the tenant_id parameter AND its hardcoded default from all four
   gateway-calling tools; each now calls resolve_context() first and passes
   ctx.tenant_id + ctx.auth_token into the underlying LangChain tool invocation
   (the factories already accept auth_token per §22). Map ToolContextError to a
   structured JSON error return {"error": code, "hint": hint} — never raise raw.
3. platform_tools.py: in every gateway-calling factory, guard tenant_id — if None or
   "" or non-UUID, raise a clear ValueError BEFORE building any URL (closes SUMMARY §9
   for both the :8082 and backend page-bound paths). Do not change any other factory
   behavior; backend in-chat flows must pass unmodified.
4. config.py: delete cloudlynet_api_key. Also purge the MCP_CLOUDLYNET_API_KEY
   mentions from backend/README.md (env-var table row) and
   backend/scripts/run_mcp_server.py (usage docstring) so the submodule-wide grep is
   empty. Update backend/.env.example: note that :8082 derives tenant from the JWT
   (no tenant env var) and that MCP_CLOUDLYNET_API_KEY is gone.
5. Tests: backend/tests/test_mcp_context.py (header present/absent/malformed, bad
   tenant claim, ContextVar isolation under concurrent invocations) and extend
   backend/tests/test_mcp_tools.py (no tool schema exposes tenant_id; outbound
   Authorization asserted via a recording httpx mock; empty-tenant guard).

Constraints: zero CI/CD change (no new port/container/transport; server_docker.py
stays SSE on container port 8080). :8082 must never verify tokens or make authz
decisions — forward and derive only. Do not touch agents/, rag/, guardrails/. Follow
the submodule CLAUDE.md working preferences: python -m pytest (uv may be absent),
black+ruff ONCE at the end. Naming in any new doc/comment text: "Network Digital
Twin", "TR-069 (CWMP)"; never "NetAI" in new copy; no em dash.

Definition of done: grep for the 3029 literal in app/mcp_server/ is empty; no MCP tool
schema contains tenant_id; unauthenticated invocation yields structured errors with
zero outbound HTTP; cd backend && python -m pytest passes.

After the PR is drafted, follow the submodule's PR-driven update protocol for
COPILOT_IMPLEMENTATION_SUMMARY.md: ask the user before updating it from the PR.
```

---

## E8.S2 — Network Digital Twin domain module (read-only)

**Why:** The copilot has zero tools for the platform's core layer: the Network Digital Twin. Users ask "which twin models exist / is training done / what did the twin predict" and today the copilot can only RAG-guess. The gateway already serves the read surfaces (`/v1/tenants/{t}/bdt`, `/bdt/models/{bdt_id}`, `/bdt/models/{bdt_id}/infer/{run_id}` — `artifacts/design/openapi.yaml:1605/1669/1738`). This story adds a read-only NDT module — the first consumer of the S1 `ToolContext` seam and the template every later domain module copies.

**Size:** M

**Scope:**
- In: `domains/` package scaffold (`domains/__init__.py` with `register_all(mcp)`; `server.py` becomes a composition root that calls it — existing tools keep registering exactly as before, relocation happens in S3/S4/S6); `domains/ndt_tools.py` with three read-only tools (below); `CloudlyNetAPIClient` gains the matching GET methods; response-shaping helpers that summarize (models list → id/status/created; run detail → KPI summary) so tool output stays LLM-sized; tests.
- Out: any POST (no `bdt/train`, no `infer` trigger — read-only module by design); the E2 re-architecture surfaces (`/ndt/evaluate`, decision hub, loop endpoints) — follow-up flagged in the epic risks, NOT stubbed here; any twin math (tools report, never compute).

**Files:**
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/__init__.py`
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/ndt_tools.py`
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/server.py` (import + `register_all(mcp)`)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/cloudlynet_client.py` (add `list_bdt_models`, `get_bdt_model`, `get_bdt_inference_run` GETs, all with `auth_token` passthrough)
- Create: `submodule/cloudlynet_ai_copilot/backend/tests/test_mcp_ndt_tools.py`

**Contract (tool inventory — names frozen; descriptions must use "Network Digital Twin"):**

| Tool | Method + gateway path | LLM-visible params |
|---|---|---|
| `list_twin_models` | `GET /v1/tenants/{t}/bdt` | `status_filter?` |
| `get_twin_model` | `GET /v1/tenants/{t}/bdt/models/{bdt_id}` | `bdt_id` |
| `get_twin_inference_run` | `GET /v1/tenants/{t}/bdt/models/{bdt_id}/infer/{run_id}` | `bdt_id`, `run_id` |

`tenant_id` and `auth_token` come from `resolve_context()` — never LLM-visible. All three return compact JSON summaries (not raw passthrough): the run tool reports run status, scope, and headline KPI aggregates present in the response, with a `truncated: true` marker when it elides bulk arrays.

**Key snippets:**

`domains/__init__.py` — the registration pattern every domain story extends:

```python
"""Per-domain MCP tool modules. ONE server (:8082), one registry —
frozen E8 decision: domain separation is code layout, not deployment topology."""
from fastmcp import FastMCP

from app.mcp_server.domains import ndt_tools  # S3..S6 append their modules here


def register_all(mcp: FastMCP) -> None:
    ndt_tools.register(mcp)
```

Tool description discipline (claims-guardrails — the twin descends from Maveric; never claim we built it, never overclaim):

```python
@mcp.tool(name="list_twin_models")
async def list_twin_models(status_filter: str | None = None) -> str:
    """List the tenant's Network Digital Twin (Bayesian Digital Twin) models
    with training status. Read-only."""
```

**Acceptance criteria:**
- `domains/` exists; `server.py` calls `register_all(mcp)`; all 12 pre-existing tools still register (count asserted in a test).
- The three NDT tools appear in the :8082 registry, none exposing `tenant_id`; each 401s → structured error when the connection lacks a Bearer (S1 behavior inherited, tested once here).
- Against mocked gateway responses, each tool returns the compact summary shape; bulk arrays are elided with `truncated: true`.
- Gateway error passthrough is structured: 404 → `{"error": "not_found", …}`, 403 → `{"error": "forbidden", …}` (no raw tracebacks to the LLM).
- Tool descriptions say "Network Digital Twin"; no description claims twin authorship, O-RAN/RIC/SMO compliance, or prediction accuracy; no em dash.
- `cd submodule/cloudlynet_ai_copilot/backend && python -m pytest` passes.

**Test plan:**
- Unit: `tests/test_mcp_ndt_tools.py` — mocked `CloudlyNetAPIClient` per tool: happy path, 404/403 mapping, summary shaping, truncation marker. Registry test: tool count and schemas.
- Integration (compose): with a seeded tenant, call `list_twin_models` via an MCP client on :8082 with a real JWT; verify parity with `curl` of the same gateway endpoint.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai), submodule
submodule/cloudlynet_ai_copilot. FIRST read COPILOT_IMPLEMENTATION_SUMMARY.md
(mandatory). Prerequisite: EPIC-8 story S1 (app/mcp_server/context.py ToolContext +
JWT threading on :8082) is merged — build on resolve_context(), do not reimplement it.

Task: add the Network Digital Twin domain module to the standalone MCP server.

Build:
1. backend/app/mcp_server/domains/__init__.py: register_all(mcp) calling each domain
   module's register(mcp). Rewire server.py to import and call register_all after the
   existing inline registrations (pre-existing 12 tools keep registering exactly as
   today; relocation into modules is later stories' work, NOT yours).
2. backend/app/mcp_server/domains/ndt_tools.py with a register(mcp) function adding
   three READ-ONLY tools (names frozen):
   - list_twin_models(status_filter?) -> GET /v1/tenants/{t}/bdt
   - get_twin_model(bdt_id) -> GET /v1/tenants/{t}/bdt/models/{bdt_id}
   - get_twin_inference_run(bdt_id, run_id)
       -> GET /v1/tenants/{t}/bdt/models/{bdt_id}/infer/{run_id}
   Each resolves ToolContext first (tenant/auth never LLM-visible), calls new
   cloudlynet_client.py methods (list_bdt_models/get_bdt_model/get_bdt_inference_run,
   auth_token passthrough like the existing methods), and returns a COMPACT JSON
   summary: ids, statuses, timestamps, headline KPI aggregates; elide bulk arrays and
   set "truncated": true. Map gateway 404 -> {"error":"not_found"}, 403 ->
   {"error":"forbidden"}, other non-2xx -> {"error":"gateway_error", "status": N}.
   No POST endpoints anywhere in this module (no train, no infer trigger).
3. Tests backend/tests/test_mcp_ndt_tools.py: mocked client per tool (happy, 404,
   403, truncation), plus a registry test asserting total tool count = 12 + 3 and
   that no registered tool schema exposes tenant_id.

Copy rules (claims-guardrails, artifacts/marketing/claims-guardrails.md): tool
descriptions and any docs say "Network Digital Twin" (bare "Digital Twin" forbidden;
proper noun "Bayesian Digital Twin" allowed); never claim we built the twin (it
descends from Maveric, LF Connectivity); no O-RAN/RIC/SMO compliance wording; no em
dash. Constraints: read-only module; gateway-mediated only; zero CI/CD change; follow
submodule CLAUDE.md (python -m pytest; black+ruff once at the end; never push without
consent; ask before updating SUMMARY from the PR).

Definition of done: cd backend && python -m pytest passes; the three tools work
end-to-end on the compose stack with a real JWT; descriptions pass the copy rules.
```

---

## E8.S3 — Ingest/Data domain module (baselines, UE datasets, NybSys upload status)

**Why:** The Ingest/Data layer is half-covered: `query_existing_baselines` exists, but there is no baseline detail, no UE dataset visibility, and no way to answer "did my NybSys PM upload process?" — the single most common data-ops question. The gateway serves all of it today (`/baselines/{id}` openapi:983, `/ue-data/datasets` :1059, `/custom/nybsys/uploads` :1125, `/uploads/{upload_id}` :1177). This story completes the read surface and performs the first module relocation: the 8 data-generation tool registrations (`query_existing_baselines` among them — SUMMARY §20's tool table) move into `domains/data_tools.py` unchanged.

**Size:** M

**Scope:**
- In: `domains/data_tools.py` with four new read-only tools (below); mechanical relocation of the 8 data-gen tool registrations (including `query_existing_baselines`) from `server.py` into the module (zero behavior change — same names, same schemas, same underlying factories from `platform_tools.py`); client GETs for the new endpoints; tests.
- Out: any upload/create/delete mutation (uploads are file transfers — not MCP material); the in-memory data-gen tool logic (`platform_tools.py` factories untouched); E1's future `/ingest/**`/`/data/**` surfaces (flagged follow-up, not stubbed).

**Files:**
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/data_tools.py`
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/__init__.py` (append module)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/server.py` (remove the relocated registrations)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/cloudlynet_client.py` (add `get_ue_dataset`, `list_nybsys_uploads`, `get_nybsys_upload`; `get_baseline` and `list_ue_datasets` already exist — reuse them, do not duplicate)
- Create: `submodule/cloudlynet_ai_copilot/backend/tests/test_mcp_data_tools.py`

**Contract (tool inventory — new tools; relocated tools keep their existing names/schemas byte-identically):**

| Tool | Method + gateway path | LLM-visible params |
|---|---|---|
| `get_baseline_detail` | `GET /v1/tenants/{t}/baselines/{baseline_id}` | `baseline_id` |
| `list_ue_datasets` | `GET /v1/tenants/{t}/ue-data/datasets` | — |
| `get_ue_dataset` | `GET /v1/tenants/{t}/ue-data/datasets/{dataset_id}` | `dataset_id` |
| `get_nybsys_upload_status` | `GET /v1/tenants/{t}/custom/nybsys/uploads` + `/{upload_id}` | `upload_id?` (absent → recent list with statuses) |

Relocated unchanged: `validate_baseline_params`, `validate_dataset_params`, `recommend_baseline_config`, `recommend_dataset_config`, `query_existing_baselines`, `compare_datasets`, `estimate_impact`, `get_generation_docs`.

**Key snippets:** none load-bearing beyond the S2 module pattern; `get_nybsys_upload_status` without `upload_id` returns the most recent uploads (id, filename, status, row counts if present, timestamps), capped at 20, `truncated: true` beyond that.

**Acceptance criteria:**
- Registry count after this story: 12 + 3 (S2) + 4 = 19; every relocated tool's name and LLM-visible schema is byte-identical to pre-relocation (golden schema snapshot test).
- `server.py` no longer registers any data-gen tool inline; `domains/data_tools.py` is their only registration site.
- The four new tools follow S1/S2 discipline: no `tenant_id` param, ToolContext-first, structured error mapping, compact summaries.
- `get_nybsys_upload_status` answers both forms: specific `upload_id` detail and the capped recent list.
- Descriptions mention NybSys/NanoLink only as "NybSys NanoLink PM CSV uploads" (hardware partner naming per positioning); no em dash; no O-RAN wording.
- `cd submodule/cloudlynet_ai_copilot/backend && python -m pytest` passes, including all pre-existing data-gen tool tests unmodified.

**Test plan:**
- Unit: `tests/test_mcp_data_tools.py` — mocked client for the four new tools; golden snapshot of relocated tool schemas captured pre-change and asserted post-change; upload-status list capping.
- Regression: existing `test_mcp_tools.py` data-gen cases pass without edits (relocation proof).
- Integration (compose): upload a small PM CSV via the gateway, then `get_nybsys_upload_status` through :8082 and verify status parity.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai), submodule
submodule/cloudlynet_ai_copilot. FIRST read COPILOT_IMPLEMENTATION_SUMMARY.md
(mandatory), especially §20 (Data Generation Agent tools). Prerequisites: EPIC-8 S1
(ToolContext) and S2 (domains/ package) are merged.

Task: complete the Ingest/Data domain module on the standalone MCP server (:8082).

Build:
1. backend/app/mcp_server/domains/data_tools.py with register(mcp):
   a. RELOCATE, byte-identical in name and LLM-visible schema, the 8 existing
      data-gen registrations from server.py: validate_baseline_params,
      validate_dataset_params, recommend_baseline_config, recommend_dataset_config,
      query_existing_baselines, compare_datasets, estimate_impact,
      get_generation_docs — and nothing else (compare_rapp_policies and
      get_platform_error_logs stay in server.py; later stories move them). They keep
      delegating to the SAME platform_tools.py factories — zero behavior change.
      BEFORE moving, capture a golden snapshot of each tool's schema in a test;
      assert equality after.
   b. ADD four read-only tools (ToolContext-first, no tenant_id param, compact
      summaries, structured 404/403/gateway_error mapping — copy the S2 pattern):
      - get_baseline_detail(baseline_id) -> GET /v1/tenants/{t}/baselines/{id}
      - list_ue_datasets() -> GET /v1/tenants/{t}/ue-data/datasets
      - get_ue_dataset(dataset_id) -> GET /v1/tenants/{t}/ue-data/datasets/{id}
      - get_nybsys_upload_status(upload_id?) -> with upload_id: GET
        /v1/tenants/{t}/custom/nybsys/uploads/{upload_id}; without: GET
        /v1/tenants/{t}/custom/nybsys/uploads, most recent 20, truncated marker.
   Add the missing auth_token-threaded GET methods to cloudlynet_client.py
   (get_ue_dataset, list_nybsys_uploads, get_nybsys_upload); get_baseline and
   list_ue_datasets already exist there — reuse, do not duplicate.
2. Remove the relocated inline registrations from server.py; append data_tools to
   domains/__init__.register_all.
3. Tests: backend/tests/test_mcp_data_tools.py (four new tools mocked happy/404/403;
   golden schema equality for the 8 relocated tools; registry total = 19). Existing
   data-gen tests must pass WITHOUT modification — treat any needed edit as a
   relocation bug.

Copy rules: "NybSys NanoLink PM CSV uploads" phrasing; never claim the device plane
is more than a TR-069 (CWMP) EMS integration; no em dash. Constraints: no mutating
tool in this module (uploads/creates/deletes stay UI/API-only); gateway-mediated
only; zero CI/CD change; submodule CLAUDE.md protocol (python -m pytest, black+ruff
once at the end, never push without consent, ask before updating SUMMARY from the PR).

Definition of done: cd backend && python -m pytest passes with zero edits to
pre-existing data-gen tests; registry count 19; compose-stack upload-status round trip
works with a real JWT.
```

---

## E8.S4 — Optimization domain module + register the two inference tools on :8082

**Why:** The Optimization layer (rApps: CCO/ES/LB/MRO) has exactly one tool on :8082 (`compare_rapp_policies`) and none for model inventory or training status. Worse, the two richest tools the copilot owns — `get_inference_report` and `compare_inference_models` (SUMMARY §24), with their deterministic in-tool math layers — exist ONLY as backend page-bound factories keyed to frontend `page_context`; an MCP client on :8082 cannot reach them at all. This story builds the Optimization module and registers both inference tools on :8082 with **explicit context parameters** replacing the page binding, reusing the §24 factories so the deterministic layers stay single-sourced.

**Size:** L

**Scope:**
- In: `domains/optimization_tools.py`; relocation of `compare_rapp_policies` into it (byte-identical schema); three new read tools (models list/detail, training status via detail); :8082 registration of `get_inference_report` / `compare_inference_models` with explicit params — implemented by calling the existing §24 factories with `page_context=None` and passing identifiers through (extend factory signatures additively if needed: new keyword-only params with defaults preserving today's behavior); MRO refusal behavior preserved (`mro_not_supported` — SUMMARY §24 known limitation); tests.
- Out: any training/inference **trigger** (no `POST /train`, no `POST /infer` — §24's resolution rule "no fallback to POST /infer without a run_id" is binding here too); any change to the backend page-bound registration or `page_context` schema; prompt work on `InferenceExplanationAgent`.

**Files:**
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/optimization_tools.py`
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/__init__.py`
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/server.py` (remove relocated registration)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/platform_tools.py` (ONLY if additive keyword-only params are needed for the explicit-context path; defaults must preserve page-bound behavior)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/cloudlynet_client.py` (add `list_rapp_models`, `get_rapp_model` if absent — `get_inference_run`, `compare_models` exist per §24)
- Create: `submodule/cloudlynet_ai_copilot/backend/tests/test_mcp_optimization_tools.py`

**Contract (tool inventory):**

| Tool | Method + gateway path | LLM-visible params |
|---|---|---|
| `list_rapp_models` | `GET /v1/tenants/{t}/rapps/{rapp_id}/models` | `rapp_id` (mro/cco/es/lb) |
| `get_rapp_model` | `GET /v1/tenants/{t}/rapps/{rapp_id}/models/{rapp_model_id}` | `rapp_id`, `rapp_model_id` (training status + MRO detail live in this response) |
| `compare_rapp_policies` | (relocated, unchanged) | unchanged minus `tenant_id` (S1 already removed it) |
| `get_inference_report` | `GET /v1/tenants/{t}/rapps/{r}/models/{m}/infer/{run_id}` | `rapp_id`, `rapp_model_id`, `run_id`, `scope?`, `tick?` — **all explicit**; no page_context on :8082 |
| `compare_inference_models` | `POST /v1/tenants/{t}/rapps/compare/infer` (read-style compare of existing models) | `base_rapp_id`, `base_rapp_model_id`, `compare_rapp_model_id`, `baseline_id`, `bdt_id`, `ue_dataset_id`, `day?` — **all explicit** |

Resolution rule for `get_inference_report` on :8082 (adapted from §24): explicit `run_id` is REQUIRED — there is no page context to fall back to; a missing/unknown `run_id` returns the structured refusal with the recovery hint ("list models, then pick a completed run"), never a `POST /infer`.

**Key snippets:**

Single-sourcing the deterministic layers (factories are the only implementation; :8082 passes explicit IDs where the page context would have been):

```python
# domains/optimization_tools.py
_report_tool = create_inference_report_tool(_api_client)   # page_context=None path

@mcp.tool(name="get_inference_report")
async def get_inference_report(rapp_id: str, rapp_model_id: str, run_id: str,
                               scope: str = "day", tick: int | None = None) -> str:
    ctx = resolve_context()
    return await _report_tool.ainvoke({
        "rapp_id": rapp_id, "rapp_model_id": rapp_model_id, "run_id": run_id,
        "scope": scope, "tick": tick,
        "tenant_id": ctx.tenant_id, "auth_token": ctx.auth_token,
    })
```

**Acceptance criteria:**
- Registry count after this story: 19 + 4 = 23 (`compare_rapp_policies` relocated, not duplicated — golden schema equality asserted).
- `get_inference_report` on :8082 with a valid completed `run_id` returns the same deterministic report content (threshold pass/fail, worst-hour scan, hotspot derivation) as the backend page-bound tool for the same run — parity asserted against the same mocked gateway responses.
- `get_inference_report` with `rapp_id="mro"` returns the structured `mro_not_supported` refusal (behavior preserved, not reimplemented).
- Missing `run_id` → structured refusal with recovery hint; the tool NEVER issues `POST /infer`.
- `compare_inference_models` on :8082 requires all IDs explicitly and matches the page-bound tool's output for identical inputs.
- Backend page-bound registration and behavior are unchanged (existing §24 tests pass unmodified); any `platform_tools.py` signature change is keyword-only with behavior-preserving defaults.
- Descriptions use "Optimization" for the layer, name rApps as CCO/ES/LB/MRO, contain no autonomy/zero-touch claims, no em dash.
- `cd submodule/cloudlynet_ai_copilot/backend && python -m pytest` passes.

**Test plan:**
- Unit: `tests/test_mcp_optimization_tools.py` — mocked gateway: list/detail happy+404; report parity page-bound vs :8082; MRO refusal; missing-run_id refusal; compare parity; golden schema for the relocated tool.
- Regression: §24 inference tests + existing debugger tool tests pass unmodified.
- Integration (compose): with a completed CCO inference run seeded, pull the report via an MCP client on :8082 and diff against the backend tool's output for the same run.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai), submodule
submodule/cloudlynet_ai_copilot. FIRST read COPILOT_IMPLEMENTATION_SUMMARY.md
(mandatory), especially §24 (Inference Explanation Agent + page context: the two
page-bound tools, their deterministic in-tool math layers, the MRO refusal, and the
"no POST /infer without run_id" resolution rule). Prerequisites: EPIC-8 S1 and S2
merged; S3 preferably merged (registry counts assume it).

Task: build the Optimization domain module and register the two inference tools on
the standalone :8082 server with explicit context params.

Build:
1. backend/app/mcp_server/domains/optimization_tools.py with register(mcp):
   a. RELOCATE compare_rapp_policies from server.py byte-identically (schema golden
      test; it delegates to the same create_rapp_comparison_tool factory).
   b. ADD read tools (ToolContext-first, S2 pattern):
      - list_rapp_models(rapp_id) -> GET /v1/tenants/{t}/rapps/{rapp_id}/models
      - get_rapp_model(rapp_id, rapp_model_id) -> GET
        /v1/tenants/{t}/rapps/{rapp_id}/models/{rapp_model_id} (training status and
        MRO detail are fields of this response — summarize, don't recompute)
   c. REGISTER get_inference_report(rapp_id, rapp_model_id, run_id, scope?, tick?)
      and compare_inference_models(base_rapp_id, base_rapp_model_id,
      compare_rapp_model_id, baseline_id, bdt_id, ue_dataset_id, day?) on :8082 by
      invoking the EXISTING §24 factories (create_inference_report_tool,
      create_inference_compare_tool) with page_context=None and explicit IDs. The
      deterministic layers (threshold pass/fail, worst-hour scan, hotspot/congested
      cell derivation, side-by-side guardrail compliance) must stay single-sourced in
      platform_tools.py — if the factories need to accept explicit IDs, extend them
      with KEYWORD-ONLY params whose defaults preserve the page-bound path exactly.
      Preserve: mro_not_supported refusal for rapp_id=="mro"; structured refusal with
      recovery hint when run_id is missing/unknown; NEVER call POST /infer.
2. Remove the relocated registration from server.py; append the module to
   domains/__init__.register_all.
3. Tests backend/tests/test_mcp_optimization_tools.py: parity tests proving the
   :8082 tools and the backend page-bound tools produce identical output for
   identical mocked gateway responses; MRO refusal; missing-run_id refusal; golden
   schema for compare_rapp_policies; registry total = 23. All §24 backend tests must
   pass WITHOUT modification.

Copy rules: layer name "Optimization"; rApps CCO/ES/LB/MRO; no zero-touch/autonomous
claims; no em dash. Constraints: no training or inference triggers (read + existing
§24 compare POST only); gateway-mediated only; zero CI/CD change; submodule CLAUDE.md
protocol (python -m pytest, black+ruff once at the end, never push without consent,
ask before updating SUMMARY from the PR).

Definition of done: cd backend && python -m pytest passes with zero edits to §24
tests; report parity holds; compose-stack report retrieval works with a real JWT.
```

---

## E8.S5 — Actuation/TR-069 domain module (reads free, mutations confirm-gated)

**Why:** The Actuators layer is invisible to the copilot: no edge inventory, no device status, no config snapshots, no command tracking — and operators must leave chat to approve or reject an optimization recommendation. The gateway serves the whole device plane today (`/custom/nybsys/edge-devices*` openapi:1228+, `/devices*` :1296+, `/devices/{id}/config` :1315, `/commands/{command_id}` :1375, `/devices/{id}/recommendations` :1422, `:approve`/`:reject` :1432/:1443). This story adds the read surface plus the epic's ONLY mutating tools — recommendation approve/reject — behind a triple gate, because an LLM-invoked write to live TR-069 (CWMP) devices is the highest-blast-radius action in the copilot.

**Size:** L

**Scope:**
- In: `domains/actuation_tools.py` with seven read tools + two gated mutating tools (below); the confirm-gate helper (`domains/gate.py`) usable by any future mutating tool; `MCP_ENABLE_MUTATING_TOOLS` setting (default false → mutating tools are not even registered); JWT role check via `ToolContext.role` (trial users always refused); audit logging of every mutation attempt (structured log line with tenant, user-role, reco_id, decision — the platform's own audit trail records the actor server-side); tests.
- Out: ANY tool that creates device commands directly (`POST /devices/{id}/commands` is deliberately not exposed — approve/reject of platform-generated recommendations is the only write path, keeping the human+platform in the loop twice); edge enrollment/key rotation; `/v1/agent/**` (field-frozen agent plane, never copilot-facing); E4's actuator framework and loop topics (different epic, different service).

**Files:**
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/actuation_tools.py`
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/gate.py`
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/__init__.py`
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/config.py` (add `enable_mutating_tools: bool = False` → env `MCP_ENABLE_MUTATING_TOOLS`)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/cloudlynet_client.py` (add the seven GETs + two POSTs)
- Modify: `submodule/cloudlynet_ai_copilot/backend/.env.example` (document the gate)
- Create: `submodule/cloudlynet_ai_copilot/backend/tests/test_mcp_actuation_tools.py`

**Contract (tool inventory):**

Read (ToolContext-first, compact summaries, S2 error mapping):

| Tool | Method + gateway path |
|---|---|
| `list_edges` | `GET /v1/tenants/{t}/custom/nybsys/edge-devices` |
| `list_devices` | `GET /v1/tenants/{t}/custom/nybsys/devices` |
| `get_device_config` | `GET /v1/tenants/{t}/custom/nybsys/devices/{device_id}/config` (latest curated snapshot) |
| `get_device_health` | `GET /v1/tenants/{t}/custom/nybsys/devices/{device_id}/health` |
| `get_device_kpis` | `GET /v1/tenants/{t}/custom/nybsys/devices/{device_id}/kpis` |
| `get_command_status` | `GET /v1/tenants/{t}/custom/nybsys/commands/{command_id}` |
| `list_device_recommendations` | `GET /v1/tenants/{t}/custom/nybsys/devices/{device_id}/recommendations` |

Mutating (registered ONLY when `MCP_ENABLE_MUTATING_TOOLS=true`):

| Tool | Method + gateway path | Gate |
|---|---|---|
| `approve_recommendation` | `POST /v1/tenants/{t}/custom/nybsys/recommendations/{reco_id}:approve` | see below |
| `reject_recommendation` | `POST /v1/tenants/{t}/custom/nybsys/recommendations/{reco_id}:reject` | see below |

The triple gate (all three must pass, in order):
1. **Env**: `MCP_ENABLE_MUTATING_TOOLS=true`, else the tools are never registered (absent from the registry, not merely refusing).
2. **Role**: `ToolContext.role` must be a non-trial operator role (reuse the `get_current_user` role mapping; `trial_user` → structured `forbidden_trial` refusal).
3. **Confirm handshake**: `confirm: bool = False` LLM-visible param. `confirm=False` (the default the LLM hits first) NEVER executes: the tool fetches the recommendation via GET, returns a structured **preview** `{"requires_confirmation": true, "reco_id": …, "device_id": …, "proposed_changes": …, "instruction": "Relay this preview to the human and call again with confirm=true only after the human explicitly approves."}`. Only a second call with `confirm=true` executes the POST. The tool result of an executed mutation echoes the gateway response plus `{"executed": true}`.

**Key snippets:**

`domains/gate.py`:

```python
"""Confirm-gate for mutating MCP tools. E8 policy: mutations are preview-first;
the LLM must relay the preview to the human and re-call with confirm=true.
This gate does not replace platform-side authz — the gateway enforces the JWT
on the POST exactly as it does for the frontend."""
from __future__ import annotations
from typing import Any

TRIAL_REFUSAL = {"error": "forbidden_trial",
                 "hint": "Trial users cannot apply device changes."}


def confirmation_preview(summary: dict[str, Any]) -> dict[str, Any]:
    return {"requires_confirmation": True, **summary,
            "instruction": ("Relay this preview to the human and call again with "
                            "confirm=true only after the human explicitly approves.")}
```

**Acceptance criteria:**
- With `MCP_ENABLE_MUTATING_TOOLS` unset (default), the registry contains the 7 read tools and NEITHER mutating tool (registry snapshot test); reads work as in S2.
- With the flag true: `approve_recommendation(reco_id)` (default `confirm=False`) performs the GET, returns the preview with `requires_confirmation: true`, and issues NO POST (asserted via recording mock); the follow-up call with `confirm=true` issues exactly one POST and returns `executed: true`.
- A `trial_user` JWT gets `forbidden_trial` on both mutating tools even with `confirm=true` and the flag on; no POST leaves the process.
- Every mutation attempt (preview, refusal, execution) emits one structured audit log line with tenant, role, reco_id, and outcome.
- No tool in the module can reach `POST /devices/{id}/commands` or any `/v1/agent/**` path (grep-level assertion in tests on the client methods used).
- Descriptions say "TR-069 (CWMP) device plane via NybSys NanoLink"; nothing claims autonomous/zero-touch actuation; no em dash.
- `cd submodule/cloudlynet_ai_copilot/backend && python -m pytest` passes.

**Test plan:**
- Unit: `tests/test_mcp_actuation_tools.py` — flag-off registry; flag-on preview/execute sequence with recording mock (exactly zero POSTs before confirm, exactly one after); trial refusal matrix; read tools happy/404; audit log capture via caplog.
- Integration (compose): seed a pending recommendation (device-level optimizer), walk the preview→confirm→approve flow through an MCP client on :8082, verify the recommendation state flips via the gateway and a `commands` row appears exactly as a frontend approval would produce.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai), submodule
submodule/cloudlynet_ai_copilot. FIRST read COPILOT_IMPLEMENTATION_SUMMARY.md
(mandatory). Prerequisites: EPIC-8 S1 (ToolContext with role) and S2 (domains/
package) merged.

Task: build the Actuation/TR-069 domain module on :8082 — reads free, the two
recommendation mutations triple-gated. This is the highest-blast-radius story in the
epic: an LLM-invoked write reaches live TR-069 (CWMP) devices. Treat the gate as the
deliverable.

Build:
1. backend/app/mcp_server/domains/gate.py: confirmation_preview(summary) helper and
   TRIAL_REFUSAL constant (shapes in the EPIC-8 S5 contract; reusable by any future
   mutating tool).
2. backend/app/mcp_server/domains/actuation_tools.py with register(mcp):
   READ tools (ToolContext-first, compact summaries, structured 404/403 mapping,
   S2 pattern): list_edges, list_devices, get_device_config, get_device_health,
   get_device_kpis, get_command_status, list_device_recommendations — gateway paths
   per the EPIC-8 S5 contract table (all under /v1/tenants/{t}/custom/nybsys/...).
   MUTATING tools approve_recommendation(reco_id, confirm=False) and
   reject_recommendation(reco_id, reason?, confirm=False):
   - Registered ONLY when the new MCPConfig.enable_mutating_tools
     (env MCP_ENABLE_MUTATING_TOOLS, default false) is true — flag off means absent
     from the registry, not refusing.
   - Role gate: ToolContext.role trial_user -> return TRIAL_REFUSAL, zero HTTP.
   - Confirm handshake: confirm=False -> GET the recommendation, return
     confirmation_preview({reco_id, device_id, proposed_changes, current_values})
     and DO NOT POST. confirm=True -> POST
     /v1/tenants/{t}/custom/nybsys/recommendations/{reco_id}:approve (or :reject),
     return gateway response + {"executed": true}.
   - Audit: one structured log line (platform logger) per attempt with tenant_id,
     role, reco_id, outcome in {previewed, refused_trial, executed, gateway_error}.
   Add the client methods to cloudlynet_client.py (auth_token threaded). FORBIDDEN:
   any method or tool touching POST /devices/{id}/commands or /v1/agent/** — the
   only write path is recommendation approve/reject (human+platform stay in the loop
   twice: the platform generated the recommendation; the human confirms in chat).
3. config.py: enable_mutating_tools: bool = False. Document in .env.example.
4. Tests backend/tests/test_mcp_actuation_tools.py per the story's test plan:
   flag-off registry snapshot; preview issues zero POSTs; confirm issues exactly one;
   trial refusal even with confirm=true; audit lines; read tools happy/404.

Copy rules: "TR-069 (CWMP) device plane via NybSys NanoLink"; CloudlyNet is an
intelligence layer above an EMS, not an NMS — never imply autonomous or zero-touch
actuation; no em dash. Constraints: gateway-mediated only; zero CI/CD change;
submodule CLAUDE.md protocol (python -m pytest, black+ruff once at the end, never
push without consent, ask before updating SUMMARY from the PR).

Definition of done: cd backend && python -m pytest passes; flag-off registry has no
mutating tool; compose-stack preview->confirm->approve flow flips a seeded
recommendation exactly as a frontend approval would.
```

---

## E8.S6 — Policy & Guardrails domain module + retire the two placeholder tools

**Why:** Guardrails went enforce-mode in prod (`artifacts/copilot/guardrail-rls-decision.md`, D6) — which makes "what did the guardrail block and why" an operator question the copilot cannot answer: the decision log is RLS-locked ops-only (D3: app role INSERT-only; reads require the `copilot_ops` role). Separately, the managed-parameter catalogue (the 24 TR-069 (CWMP) paths the platform may write) is invisible in chat, and two dead placeholder tools (`get_model_accuracy`, `list_available_models` — registered at server.py:60/66 from `tools.py`) still pollute the registry with fake-looking capabilities. This story adds the Policy & Guardrails module (SELECT-only ops read + catalogue exposure) and deletes the placeholders.

**Size:** M

**Scope:**
- In: `domains/policy_tools.py` with `get_guardrail_decisions` (SELECT-only over `conversation.guardrail_decision_log` via a dedicated `copilot_ops` DSN, admin-gated, absent when unconfigured) and `get_managed_param_catalog` (bundled read-only snapshot of the 24-path catalogue with provenance); `domains/diagnostics_tools.py` absorbing `get_platform_error_logs` (relocation, byte-identical schema — finishing the server.py cleanup so it becomes a pure composition root); deletion of the two placeholders from `server.py` and `tools.py` (and `MCP_TOOLS` registry + their tests); new settings `MCP_COPILOT_OPS_DATABASE_URL` (default unset); tests.
- Out: any UPDATE on the decision log (reviewer labeling stays with the D4 review CLI, which connects as `copilot_ops` with SELECT+UPDATE — the MCP tool takes SELECT only); guardrail configuration mutation (the 7 `GUARDRAIL_*` env vars are chart-owned, D6); any change to the guardrail middleware itself; platform-DB access of any kind (the ops DSN targets copilot's OWN `netai_copilot` DB only).

**Files:**
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/policy_tools.py`
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/diagnostics_tools.py`
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/data/managed_params.json` (bundled snapshot + provenance header)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/server.py` (delete placeholder registrations at lines 60–72; remove relocated `get_platform_error_logs`; end state: FastMCP app + `register_all` only)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/tools.py` (delete `get_model_accuracy`, `list_available_models`, and their `MCP_TOOLS` entries; delete the file if nothing remains)
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/config.py` (add `copilot_ops_database_url: str | None = None`)
- Modify: `submodule/cloudlynet_ai_copilot/backend/.env.example`
- Create: `submodule/cloudlynet_ai_copilot/backend/tests/test_mcp_policy_tools.py`

**Contract:**

`get_guardrail_decisions(since_hours: int = 24, blocked_only: bool = False, guardrail_name: str | None = None, limit: int = 50) -> str`
- Gates, in order: (1) `MCP_COPILOT_OPS_DATABASE_URL` unset → tool not registered; (2) `ToolContext.role` must map to platform-admin per `get_current_user`'s role mapping, else structured `forbidden` refusal (this is an ops/audit surface, not a tenant feature — tenant users never see other tenants' rows AND never see this tool's output).
- Connects as `copilot_ops` (decision record D2: CONNECT on `netai_copilot`, USAGE on schema `conversation`, SELECT+UPDATE on the log; this tool exercises SELECT only — D4 keeps UPDATE for the review CLI). Read-only enforced client-side too: the connection is opened with `default_transaction_read_only = on`.
- Query shape (columns per `artifacts/copilot/copilot_schemas.sql` Version B; queries are never stored in plaintext — the tool returns `query_redacted`, never attempts to recover originals):

```sql
SELECT id, created_at, tenant_id, user_id, guardrail_name, would_block,
       actually_blocked, latency_ms, query_redacted, verdict,
       reviewer_label, reviewed_at
  FROM conversation.guardrail_decision_log
 WHERE created_at >= now() - make_interval(hours => :since_hours)
   AND (:blocked_only = false OR actually_blocked)
   AND (:guardrail_name::varchar IS NULL OR guardrail_name = :guardrail_name)
 ORDER BY created_at DESC
 LIMIT LEAST(:limit, 200);
```

`get_managed_param_catalog(optimizable_only: bool = False) -> str`
- Returns the bundled `domains/data/managed_params.json`: the 24 managed TR-069 (CWMP) parameter paths with type/bounds/optimizable flags and a provenance block `{source, verified_against, verified_on}`.
- **Cross-epic seam (flagged):** the canonical catalogue contract file is E4.S7's deliverable (`artifacts/contracts/`). Until E4.S7 lands, this snapshot is hand-verified against `submodule/maveric_platform_smo_sim/app/services/nybsys/managed_params.py` (24 entries) and the provenance block records that. When E4.S7 lands, copilot becomes a fourth generated copy of the canonical file (hash-stamped like smo_sim/frontend/agent) — record this as a one-line follow-up in the E4.S7 contract doc AND in `artifacts/copilot/mcp-domain-coverage.md`. Neither epic blocks the other.

Placeholder retirement: `get_model_accuracy` and `list_available_models` return hardcoded fakes; a registry that advertises fake capabilities poisons agent tool-choice. Delete, don't deprecate.

**Key snippets:** none beyond the SQL above; `diagnostics_tools.py` is a pure relocation following the S3 golden-schema pattern.

**Acceptance criteria:**
- `grep -rn "get_model_accuracy\|list_available_models" submodule/cloudlynet_ai_copilot/backend/` returns only HISTORY/SUMMARY prose (no code, no tests, no registry entries).
- `server.py` contains no `@mcp.tool` decorators — only the FastMCP app construction and `register_all(mcp)` (composition-root end state asserted by grep in a test or CI-less check).
- With the ops DSN unset (default), `get_guardrail_decisions` is absent from the registry; with it set, a platform-admin JWT gets rows and a non-admin JWT gets the structured `forbidden` refusal with zero DB queries.
- The ops connection cannot write: an UPDATE attempted through the tool's connection fails (read-only transaction test against a throwaway Postgres with the D3 policies applied).
- Tool output contains `query_redacted` and never a plaintext query; `verdict` passes through as-is (it is already sanitized jsonb).
- `get_managed_param_catalog` returns 24 entries with a provenance block whose `verified_against` names the smo_sim source file (or the E4.S7 canonical file if that landed first); `optimizable_only=true` filters correctly.
- `get_platform_error_logs` relocated byte-identically (golden schema). Registry end state is conditional (mutating tools only when `MCP_ENABLE_MUTATING_TOOLS=true`; `get_guardrail_decisions` only when the ops DSN is set), so the test asserts the exact expected tool-name SET built programmatically from the domain modules under each flag combination — never a hand-counted total.
- `cd submodule/cloudlynet_ai_copilot/backend && python -m pytest` passes.

**Test plan:**
- Unit: `tests/test_mcp_policy_tools.py` — DSN-unset absence; admin/non-admin gating (role mocked on ToolContext); SQL filter matrix (since/blocked_only/guardrail_name/limit cap) against a seeded throwaway Postgres (or sqlite-incompatible parts mocked — prefer the compose Postgres with D3 policies applied via `artifacts/copilot/guardrail-rls-decision.md` SQL); read-only enforcement; catalogue content + filter + provenance.
- Regression: full backend suite; deleted-placeholder tests removed in the same PR.
- Integration (compose): apply the D3 RLS block + `copilot_ops` role to the compose Postgres, set `MCP_COPILOT_OPS_DATABASE_URL`, trigger a guardrail block in chat, then read it back through the tool with an admin JWT.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai), submodule
submodule/cloudlynet_ai_copilot. FIRST read COPILOT_IMPLEMENTATION_SUMMARY.md
(mandatory) AND the parent repo's artifacts/copilot/guardrail-rls-decision.md (the
RLS decision record: D1 no BYPASSRLS, D2 copilot_ops role, D3 ops-only read policies,
D4 review-CLI contract). Prerequisites: EPIC-8 S1 and S2 merged.

Task: build the Policy & Guardrails domain module, finish the server.py composition
root, and retire the two placeholder tools.

Build:
1. backend/app/mcp_server/domains/policy_tools.py with register(mcp):
   a. get_guardrail_decisions(since_hours=24, blocked_only=False,
      guardrail_name=None, limit=50):
      - NOT registered unless new MCPConfig.copilot_ops_database_url
        (env MCP_COPILOT_OPS_DATABASE_URL) is set.
      - Role gate: ToolContext.role must be platform-admin per the
        app/core/auth.get_current_user role mapping; otherwise return a structured
        {"error": "forbidden"} with ZERO DB access.
      - Opens a dedicated asyncpg/SQLAlchemy connection AS copilot_ops with
        default_transaction_read_only=on and runs the SELECT from the EPIC-8 S6
        contract (conversation.guardrail_decision_log; columns per
        artifacts/copilot/copilot_schemas.sql Version B; LIMIT capped at 200).
        SELECT only — reviewer labeling belongs to the D4 review CLI, never this
        tool. Return query_redacted, never plaintext queries.
      - This is the ONLY direct-DB access in the entire MCP server, it targets
        copilot's OWN netai_copilot DB, and it must be impossible to point at a
        platform DB silently: validate the DSN's database name is netai_copilot at
        startup and refuse to register otherwise.
   b. get_managed_param_catalog(optimizable_only=False): serve the bundled
      domains/data/managed_params.json — 24 managed TR-069 (CWMP) parameter paths
      with type/bounds/optimizable and a provenance block {source, verified_against,
      verified_on}. Build the snapshot by hand-verifying against
      submodule/maveric_platform_smo_sim/app/services/nybsys/managed_params.py
      (24 entries) unless artifacts/contracts/ already carries E4.S7's canonical
      managed-params file — then generate from that and say so in provenance.
2. backend/app/mcp_server/domains/diagnostics_tools.py: relocate
   get_platform_error_logs from server.py byte-identically (golden schema test,
   same create_error_logs_tool factory).
3. Retire placeholders: delete get_model_accuracy and list_available_models from
   server.py (registrations at ~lines 60-72), tools.py (functions + MCP_TOOLS
   entries; delete tools.py entirely if empty), and their tests. Delete, don't
   deprecate — fake capabilities poison tool choice.
4. End state: server.py has ZERO @mcp.tool decorators — FastMCP app + domains
   register_all only. config.py gains copilot_ops_database_url. Document both new
   envs in .env.example.
5. Tests backend/tests/test_mcp_policy_tools.py per the story's test plan; build the
   expected registry tool-name set programmatically from the domain modules.

Copy rules: "Policy & Guardrails" for the domain; guardrail descriptions state input
guardrails (PII + Safeguard classification) factually — no "unbypassable"/absolute
safety claims; catalogue descriptions say "TR-069 (CWMP) managed parameters"; no em
dash. Constraints: gateway-mediated for everything except the scoped copilot_ops
SELECT; zero CI/CD change; submodule CLAUDE.md protocol (python -m pytest, black+ruff
once at the end, never push without consent, ask before updating SUMMARY from the
PR).

Definition of done: cd backend && python -m pytest passes; grep for the placeholder
names finds no code; server.py is a pure composition root; the compose-stack
round-trip (guardrail block in chat -> read via tool with admin JWT + copilot_ops
DSN) works with the D3 policies applied.
```

---

## E8.S7 — Docs and context lockstep (SUMMARY via PR protocol, artifacts/copilot bundle, roadmap alignment)

**Why:** The epic changes the copilot's externally observable capability surface (tool inventory quadruples, mutations appear, an ops audit surface opens). Three doc layers must land in lockstep or drift immediately: the submodule's canonical SUMMARY (whose update path is contractually PR-driven), the parent `artifacts/copilot/` design bundle, and the marketing/roadmap layer that claims-guardrails polices. This story is the epic's closing gate, mirroring E6's role for the platform epics.

**Size:** M

**Scope:**
- In: verify S1–S6 SUMMARY updates landed via the PR protocol and close any gaps with one consolidated section ("MCP domain coverage") + §2 timeline rows — with the user's explicit consent per the protocol; new `artifacts/copilot/mcp-domain-coverage.md` (the one-server decision record + full tool inventory + auth model + gates); `artifacts/copilot/copilot_LLD.md` / `copilot_openapi.yaml` touched ONLY where they document the MCP surface; roadmap alignment (`artifacts/marketing/roadmap.md` and generated pages: copilot rung wording may now say "the copilot reads the Network Digital Twin, Ingest/Data, Optimization, and TR-069 (CWMP) device layers, and lets an operator approve or reject optimization recommendations in chat with an explicit confirmation step" — Today rung, because it ships; keep the operator as the approver per claims-guardrails §5, "the copilot proposes; an operator approves"); claims re-check of every tool description string against `claims-guardrails.md`; `.context/` copilot page refreshed only if it enumerates MCP tools (check; full graph refresh stays E6's).
- Out: any code change; any SUMMARY rewrite of pre-E8 sections (append, never rewrite — submodule CLAUDE.md); marketing site regeneration beyond the roadmap files actually touched; renaming `server_name: netai-copilot-mcp` (not-yet-migrated infra identifier, parent CLAUDE.md).

**Files:**
- Modify: `submodule/cloudlynet_ai_copilot/COPILOT_IMPLEMENTATION_SUMMARY.md` (append section + timeline rows; PR-protocol consent required)
- Create: `artifacts/copilot/mcp-domain-coverage.md`
- Modify: `artifacts/copilot/copilot_LLD.md` (MCP server section: domains layout, auth model, gates)
- Modify: `artifacts/copilot/copilot_openapi.yaml` (only if it documents MCP tool schemas today — verify first; skip if not)
- Modify: `artifacts/marketing/roadmap.md` (+ regenerate affected pages via the marketing build if the rung text changes)
- Check: `.context/` copilot page (refresh tool inventory if present); `python .claude/skills/context-agent/tools/graph_check.py .context` still clean

**Contract (structure of `artifacts/copilot/mcp-domain-coverage.md`):** the question ("MCP servers in all layers?"), the frozen answer (one server, per-domain modules, with the rationale from the epic header verbatim), the revisit trigger, the tool inventory table (name, domain, method+path or local source, read/mutating, gates), the auth model (ToolContext, gateway-enforced, :8082 never an authority), the `copilot_ops` exception scope, and the E4.S7 catalogue-generation seam.

**Key snippets:** none — this is a docs story; the inventory table is generated by reading `domains/` module sources, not memory.

**Acceptance criteria:**
- SUMMARY has an appended "MCP domain coverage" section + §2 timeline rows for the epic's PRs, produced through the PR-driven protocol (explicit user consent recorded in the conversation; no auto-update).
- `artifacts/copilot/mcp-domain-coverage.md` exists with all seven contract elements; its tool inventory matches the actual registry (spot-check: every tool name greps to a `domains/` module).
- `copilot_LLD.md` MCP section describes the domains layout and gates; no stale reference to the placeholder tools or the hardcoded tenant remains anywhere in `artifacts/copilot/`.
- Roadmap copy: any new copilot capability line sits on the correct rung (shipped = Today), uses "Network Digital Twin" / "TR-069 (CWMP)" / "Optimization", contains no em dash (U+2014), no "O-RAN compliant", no "zero-touch", no "NetAI".
- `grep -rn "00000000-0000-0000-3029" artifacts/ submodule/cloudlynet_ai_copilot/ --include="*.md"` finds no doc still presenting the hardcoded tenant as current behavior.
- `.context` graph check passes if any `.context` page was touched.

**Test plan:**
- Doc verification is grep-driven per the acceptance criteria; roadmap regeneration (if any) via the existing `artifacts/marketing/` build script; no code tests.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai). Prerequisites: EPIC-8
stories S1-S6 are merged in submodule/cloudlynet_ai_copilot. Read, in order:
submodule/cloudlynet_ai_copilot/CLAUDE.md (the PR-driven update protocol — its
ask-before-updating intent is non-negotiable), COPILOT_IMPLEMENTATION_SUMMARY.md,
artifacts/marketing/claims-guardrails.md, and the EPIC-8 file's header decision
block.

Task: docs lockstep for the copilot MCP epic.

1. SUMMARY (submodule): check which S1-S6 PRs already updated it via the protocol.
   For gaps, draft ONE appended section "MCP domain coverage" (domains layout, tool
   inventory, ToolContext auth model, mutation gates, copilot_ops read path,
   placeholder retirement) plus one-line §2 timeline rows — then ASK THE USER for
   consent to apply, citing the finalized PRs as source. Append only; never rewrite
   existing numbered sections; preserve the ToC structure.
2. Create artifacts/copilot/mcp-domain-coverage.md with: the layers question, the
   frozen one-server/per-domain-modules answer + rationale + revisit trigger, the
   full tool inventory table BUILT BY READING backend/app/mcp_server/domains/
   sources (never from memory), the auth model (:8082 forwards JWT, gateway is the
   sole enforcement point), the copilot_ops SELECT-only exception and its DSN guard,
   and the E4.S7 managed-params generation seam (copilot becomes a fourth generated
   copy when the canonical contract file lands).
3. Update artifacts/copilot/copilot_LLD.md's MCP server section to the domains
   layout; purge stale mentions of get_model_accuracy / list_available_models and of
   the hardcoded tenant default across artifacts/copilot/. Touch
   copilot_openapi.yaml only if it documents MCP tool schemas today (verify first).
4. Roadmap: if adding the copilot capability line to artifacts/marketing/roadmap.md,
   place shipped capabilities on the Today rung, then regenerate affected marketing
   pages with the existing build script. Language rules (claims-guardrails, hard):
   "Network Digital Twin" (never bare "Digital Twin"), "TR-069 (CWMP)",
   "Optimization", product CloudlyNet, no em dash (U+2014), no "O-RAN compliant" /
   "zero-touch" / "carrier grade" / "NetAI". Do NOT rename infra identifiers
   (server_name netai-copilot-mcp stays; note it as not-yet-migrated infra).
5. If a .context page enumerates MCP tools, refresh it and run
   python .claude/skills/context-agent/tools/graph_check.py .context (must stay
   clean). Full graph refresh belongs to E6 — do not expand scope.

Constraints: docs only — zero code change; commit conventions per parent CLAUDE.md
(no Claude signature, concise one-liners, never stage submodule pointer bumps).

Definition of done: all EPIC-8 S7 acceptance-criteria greps pass; the SUMMARY update
went through the consent flow; the inventory table matches the real registry.
```

---

## E8.S8 — Observability/RCA domain (device logs, FM alarms, timeline, raw window)

**Why:** This is the domain the copilot team is actually blocked on, and the only one in the epic
whose backing store is not fully built. Operators ask "why did device X reboot", and answering it
needs four things the copilot has none of today: searchable device log lines with neighbour context,
FM alarms as lifecycle records rather than log text, an interleaved timeline that puts alarms next to
the commands and config changes that might have caused them, and an escape hatch to the unparsed raw
window when the extract lost the detail. The data contract for all four is already written and
evidence-backed (`artifacts/nanolink/femtocell_dashboard_data_contract.md`, §2 log grammar and §4
"MCP / RCA readiness (EPIC-8 domains)", which sketches these exact tools). This story builds the MCP
surface against it and, critically, **states honestly which parts have no producer yet**.

**Hard dependency, and the gap it exposes:** `fm_alarms` is created by E1.S1 and queryable via
E1.S5 (`GET /v1/tenants/{t}/data/fm`), so the alarm tools have a real path. **The device log
pipeline has no owning story in any epic.** The femtocell contract §2 specifies the parser
(dedup key `(device, boot_epoch, seq)`, parse both `Log_*.gz` and `ErrorLog_*.gz` through one
pipeline, raw `.gz` to object storage, extracted rows to Postgres) and §5 records that today's
watcher is broken for real devices: it consumes only `*.tgz` while real uploads are single-gzip
`Log_*.gz`/`ErrorLog_*.gz` (`collector.go:210`), and it stamps events with parse time rather than
line time. **Until that pipeline is owned and built, `search_device_logs` and
`fetch_raw_log_window` have no data source.** This story therefore ships in two tranches and must
not pretend otherwise. See the audit note in `artifacts/upgrade_plans/AUDIT-2026-07-29.md` §4.

**Size:** L (tranche A: M; tranche B: M, gated)

**Scope:**
- In, tranche A (buildable today, no new producer): `domains/observability_tools.py`;
  `get_active_alarms` and `get_alarm_history` over `GET /v1/tenants/{t}/data/fm` (E1.S5);
  `get_device_timeline` interleaving `fm_alarms` + `device_events` + `commands` +
  `device_config_snapshots` + `optimization_recommendations` on one `order_key` axis;
  `search_device_events` over the existing `device_events` table (the honest subset of log search
  available now); relocation of `get_platform_error_logs` here from `diagnostics_tools.py` if S6
  already created it (cross-service platform errors are the same domain).
- In, tranche B (gated on the log pipeline existing): `search_device_logs` with the full §3 query
  contract including `context_lines` neighbours; `fetch_raw_log_window` re-reading the archived
  `.gz` from object storage for a given `(device, ts, window_s)`.
- Out: building the log parser itself (that is an ingest-side story, flagged above and in the audit,
  not copilot work); any write to alarms or events; alarm correlation or ML clustering (report the
  records, do not infer); replacing the dashboard's own queries.

**Files:**
- Create: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/observability_tools.py`
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/domains/__init__.py`
- Modify: `submodule/cloudlynet_ai_copilot/backend/app/mcp_server/cloudlynet_client.py` (add the `/data/fm` and device-event GETs, `auth_token` threaded)
- Create: `submodule/cloudlynet_ai_copilot/backend/tests/test_mcp_observability_tools.py`

**Contract (tool inventory):**

| Tool | Tranche | Backing surface | LLM-visible params (all optional unless noted) |
|---|---|---|---|
| `get_active_alarms` | A | `GET /v1/tenants/{t}/data/fm?state=active` | `device_id?`, `dn?`, `severity?[]`, `limit?`, `fields?[]` |
| `get_alarm_history` | A | `GET /v1/tenants/{t}/data/fm` | `device_id?`, `alarm_id?`, `start?`, `end?`, `state?`, `limit?`, `cursor?`, `fields?[]` |
| `get_device_timeline` | A | multi-source join | `device_id` (**required**), `start?`, `end?`, `entry_types?[]`, `limit?`, `cursor?`, `fields?[]` |
| `search_device_events` | A | `device_events` | `device_id?`, `q?`, `event_type?[]`, `severity?[]`, `start?`, `end?`, `limit?`, `cursor?`, `fields?[]` |
| `search_device_logs` | B | `device_log_index` + object storage | `device_id?`, `q?`, `regex?`, `module?[]`, `severity?[]`, `alarm_id?[]`, `stream?[]`, `start?`, `end?`, `context_lines?`, `limit?`, `cursor?`, `sort?`, `fields?[]` |
| `fetch_raw_log_window` | B | object storage `.gz` | `device_id` (**required**), `at` (**required**), `window_s?` (server-capped), `limit?`, `cursor?`, `fields?[]` |

Response bodies: `fm_alarms`, `device_timeline`, `device_log_lines`, `raw_log_lines` per
`artifacts/copilot/mcp-master-payload.md` §6. `device_id` is the only ever-required parameter, and
only where a tenant-wide answer would be meaningless or unbounded (timeline, raw window).

**Copilot-agreed contract deltas (2026-08-10) — binding for this story** (decision record:
`artifacts/copilot/HANDOVER-mcp-log-rca.md` §11; the copilot RCA loop is already designed against
these):

1. **`fields` projection on every list tool** (tranche A included, not just log search). Omitted →
   full record. Unknown names → honoured-where-possible, each reported in `query.ignored` with
   reason `unknown_field`, never a rejection. `query.echo.fields` states what was applied. The
   RCA lean set is `["order_key","message","module","severity","alarm_id","match"]` (~150 B/item
   vs ~700 B full → ~5x lines per reply). Projection filters `data.items[*]` only — never the
   envelope.
2. **Reply sizing.** ~8 KB is an advisory target, not a hard cap. `limit` bounds count (default
   50 / hard cap 500); an additional server-side size guard may stop a reply early with
   `truncation_reason: "size_cap"` and a **resumable** `page.next_cursor`. Whichever binds first
   governs; both are always reported. The copilot self-sizes larger-but-bounded requests (a few
   hundred lean lines) — do not clamp to 8 KB.
3. **`fetch_raw_log_window` is bounded and paged — no bulk mode, ever.** Capped `window_s`
   (over-asks honoured to the cap, reported via `query.ignored` reason `capped`), pages in
   `order_key` order, same envelope, same projection. The copilot deleted their
   compression/trace-back layer on this guarantee; an unbounded variant is a regression, not a
   feature.
4. **`correlation_id`** is minted by the copilot orchestrator, one per RCA session, present on
   every call of that session: echo it verbatim in `context.correlation_id`, never mint when
   supplied. **`next_actions.args` must be executable verbatim** against the named tool — the
   copilot agent loop passes them through unmodified.
5. **Retention:** the 90-day Postgres raw-line row floor is a confirmed requirement; past it,
   `retention_boundary` + the real floor in `provenance[].coverage.from`, with
   `fetch_raw_log_window` as the archive path.

Projection belongs in the shared envelope helper, not per-tool (S0's `envelope.py`):

```python
# app/mcp_server/envelope.py (S0) — v1.1 projection support, one implementation for all tools
def project_items(items: list[dict], fields: list[str] | None,
                  ignored: list[dict]) -> list[dict]:
    """Apply a `fields` projection to data.items. Unknown names are reported, never fatal."""
    if not fields:
        return items
    known = set().union(*(item.keys() for item in items)) if items else set()
    for name in fields:
        if name not in known:
            ignored.append({"param": f"fields[{name}]", "reason": "unknown_field",
                            "detail": f"No such per-item field: {name}"})
    keep = [f for f in fields if f in known] or fields  # empty items: echo the ask
    return [{k: item[k] for k in keep if k in item} for item in items]
```

```python
# Size guard sketch (tools call this instead of len(items) checks). The cursor must
# resume at the first item NOT included, so truncation is lossless.
def fit_to_budget(items, encode, budget_bytes):
    kept, size = [], 0
    for it in items:
        size += len(encode(it))
        if size > budget_bytes:
            return kept, True   # truncated=True, reason="size_cap", cursor -> items[len(kept)]
        kept.append(it)
    return kept, False
```

**Load-bearing details (do not re-derive; they come from the evidence base):**

1. **Order key.** `order_key = "{boot_epoch}#{seq:010d}"`, not the timestamp. The device's 10-digit
   sequence totally orders the stream but resets to 0 at reboot (observed mid-file: `ErrorLog_1758`
   runs seq 165, reboots, resumes at 79), so `boot_epoch` disambiguates. Sorting on `ts` alone gives
   wrong order inside sub-millisecond bursts.
2. **Neighbours are flat, not nested.** Hits and context lines are siblings with `match`
   (`hit`/`context`), `context_offset`, and `hit_group`. Nesting duplicates lines when two hits fall
   within one context window.
3. **Alarms are not log lines.** `fm_alarms` collapses flap and backoff series: the 31-line
   `0x18020400` ACS backoff series is ONE active alarm with `occurrence_count: 31`. A tool that
   returns 31 alarms is wrong.
4. **`empty` is a finding.** "No active alarms" is `result.kind: "empty"`, `success: true`. Only a
   broken query or unreachable store is `success: false`.
5. **Retention is two-tier.** Extracted rows live in Postgres under the partition policy; raw `.gz`
   archives live in object storage and are re-parseable on demand. When a query's `start` precedes
   the Postgres floor, return `truncation_reason: "retention_boundary"` and report the real floor in
   `provenance[].coverage.from` rather than silently returning less.

**Acceptance criteria:**
- Tranche A tools ship and conform to the S0 envelope; `get_device_timeline` returns entries from at
  least three source types on a seeded device, ordered by `order_key`, with per-source `provenance`.
- A source that fails inside `get_device_timeline` yields `success: true` plus a `PARTIAL_RESULT`
  error entry and `truncated: true`, never a silent hole.
- Every tranche A tool invoked with zero optional arguments returns a bounded default rather than a
  validation error (`query.applied_defaults` lists what was defaulted).
- Tranche B tools are **not registered** while the log pipeline is absent; the module exposes a
  documented capability probe so the copilot can tell "not built yet" from "no data".
- Alarm dedup is respected: a seeded 31-line backoff series returns one alarm with
  `occurrence_count: 31`.
- No tool in this module writes anything; grep-level assertion on the client methods used.
- `cd submodule/cloudlynet_ai_copilot/backend && python -m pytest` passes.

**Test plan:**
- Unit: mocked `/data/fm` and event responses; timeline ordering across reboot boundaries (seq
  reset); `PARTIAL_RESULT` on one failed source; empty vs error; retention-boundary reporting;
  zero-argument defaults for every tool.
- Integration (compose): seed `fm_alarms` with the femtocell contract's worked example (the
  2026-06-13 SCTP to S1-setup to critical-raise to reboot chain) and assert `get_device_timeline`
  reproduces the causal sequence in order.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai), submodule
submodule/cloudlynet_ai_copilot. FIRST read COPILOT_IMPLEMENTATION_SUMMARY.md
(mandatory), then the parent repo's artifacts/copilot/mcp-master-payload.md (envelope,
especially section 6.1 device_log_lines and 6.1.1 the order key) and
artifacts/nanolink/femtocell_dashboard_data_contract.md (sections 2, 3.2 and 4 - the
evidence base: log grammar, fm_alarms DDL and lifecycle, the RCA tool sketches).
Prerequisites: EPIC-8 S0 (envelope) and S1 (ToolContext) merged; E1.S1 (fm_alarms) and
E1.S5 (GET /data/fm) merged for tranche A.

Task: build the Observability/RCA domain module, TRANCHE A ONLY.

Read this before you start: the device log pipeline (parsing Log_*.gz and
ErrorLog_*.gz) does NOT exist yet and is not your job. Today's watcher consumes only
*.tgz while real devices upload single-gzip files (collector.go:210). So
search_device_logs and fetch_raw_log_window are TRANCHE B: define their signatures and
response bodies in the module, but DO NOT register them; expose a capability probe so
a caller can distinguish "not built yet" from "no data". Do not stub them with fake
data.

Build (tranche A):
1. backend/app/mcp_server/domains/observability_tools.py with register(mcp):
   - get_active_alarms(device_id?, dn?, severity?, limit?) -> GET
     /v1/tenants/{t}/data/fm?state=active
   - get_alarm_history(device_id?, alarm_id?, start?, end?, state?, limit?, cursor?)
     -> GET /v1/tenants/{t}/data/fm
   - search_device_events(device_id?, q?, event_type?, severity?, start?, end?,
     limit?, cursor?) -> the existing device_events surface
   - get_device_timeline(device_id REQUIRED, start?, end?, entry_types?, limit?,
     cursor?) -> interleave fm_alarms + device_events + commands +
     device_config_snapshots + optimization_recommendations on one order_key axis,
     each item carrying entry_type plus its native record.
   Every tool: ToolContext first (tenant and token never LLM-visible), envelope.ok /
   empty / err from S0, per-source provenance entries, and EVERY filter parameter
   optional - a zero-argument call must return a bounded default, never a validation
   error, with query.applied_defaults listing what you defaulted.
   v1.1 contract deltas (binding; see the story's "Copilot-agreed contract deltas"):
   - every list tool above also takes fields?: list[str] - apply via the shared
     project_items() helper in envelope.py (S0), report unknown names in
     query.ignored with reason "unknown_field", echo the applied set in
     query.echo.fields; never project the envelope itself.
   - reply sizing: honour limit (default 50, cap 500) AND a byte-budget guard; a
     size-stopped reply sets truncation_reason="size_cap" with a next_cursor that
     resumes at the first EXCLUDED item. ~8 KB is advisory; callers may ask bigger.
   - echo context.correlation_id verbatim when supplied (the copilot orchestrator
     mints one per RCA session); never mint your own when one is present.
   - next_actions args must be executable verbatim against the named tool - the
     copilot agent loop passes them through unmodified; test one round-trip.
2. Ordering: order_key = f"{boot_epoch.isoformat()}#{seq:010d}". Do NOT order by
   timestamp alone: device seq resets to 0 at reboot and sub-millisecond bursts share
   a timestamp. For sources without a seq (commands, config snapshots), synthesise
   order_key from the record timestamp and document the tie-break rule in the module
   docstring.
3. Alarm semantics: fm_alarms rows are lifecycle records, already deduped
   (occurrence_count collapses flap and backoff series). Pass occurrence_count,
   state, raised_at, cleared_at, last_seen_at through. Never expand one alarm row
   into N items.
4. Partial failure: if one source in get_device_timeline fails, return success=true
   with truncated=true and a PARTIAL_RESULT entry in errors naming the failed source.
   A silent hole in an RCA timeline is the worst possible failure mode here.
5. Retention: when start precedes the queryable floor, set truncation_reason=
   "retention_boundary" and report the real floor in provenance[].coverage.from.
6. Tests backend/tests/test_mcp_observability_tools.py per the story test plan,
   including timeline ordering across a reboot (seq reset) and the seeded
   2026-06-13 SCTP -> S1 setup -> critical raise -> reboot chain from the femtocell
   contract section 4.

Constraints: read-only module, no writes of any kind; gateway-mediated only; zero
CI/CD change; submodule CLAUDE.md protocol (python -m pytest, black+ruff once at the
end, never push without consent, ask before updating SUMMARY from the PR). Copy rules:
"TR-069 (CWMP) device plane via NybSys NanoLink", "Intelligence Layer" for the
platform layer, no O-RAN/RIC/SMO claims, no em dash.

Definition of done: tranche A tools conform to the envelope schema in the S0
parametrised registry test; zero-argument calls succeed for all of them; the seeded
reboot chain reproduces in causal order; tranche B tools are absent from the registry
with a working capability probe; cd backend && python -m pytest passes.
```

---

## E8.S9 — RCA incident fixture pack (unblocks copilot local testing; requested 2026-08-10)

**Why:** The log pipeline (risk 10) blocks end-to-end testing of the copilot's LLM RCA loop, but it
does not have to block their *local* testing. The copilot team asked (2026-08-10) for a fixture:
the complete raw log set for one device over one real incident window, a handful of hand-built
contract-envelope replies over that incident, and the incident's device context. With those they
build their fixture parser, rebuild golden-set labels with accurate counts, and validate their
envelope adapters against the real thing instead of a guess — and their timing runs against this
fixture produce the firm p95 target the platform is waiting on for rate-limit sizing (§9.4 of the
handover). This is a platform deliverable: data curation plus hand-authoring, no service code.

**Size:** S

**Scope:**
- In: the three-item fixture pack below; an `artifacts/copilot/fixtures/README.md` documenting
  provenance, anonymization applied, and how the samples were derived; schema validation of every
  committed envelope sample.
- Out: the log parser (still risk 10, still not this epic); any change to MCP server code; any
  commitment that the fixture's hand-built envelopes are byte-exact previews of the future
  implementation (they are contract-exact, which is the point).

**Contract (what the copilot team receives):**

| # | Item | Contents | Confidentiality handling |
|---|---|---|---|
| 1 | Complete raw logs, one device, one real incident window | ALL streams, unfiltered: `Log_*.gz`, `ErrorLog_*.gz`, the continuous-logging ring — not the edge-forwarded subset. Window: the worked-example reboot incident (SCTP peer failure → S1 setup failure → FM critical `0x16010400` → self-reboot). | Source lives under `artifacts/real-data/` (gitignored — NEVER committed). Deliver in place read-only, or as an anonymized copy (serial → `2205609999`, MAC host parts synthetic) if it leaves that directory. Anonymization sign-off is the user's, per parent CLAUDE.md. |
| 2 | Hand-built envelope JSON replies | 2–3 samples each: `search_device_logs` (one with `context_lines`, one with the lean `fields` projection), `get_device_timeline`, `get_active_alarms`, `get_device_config`, `get_command_status`. Real `order_key` / `template_hash` / `class` / `match` / `hit_group` values derived from item 1. | Committed under `artifacts/copilot/fixtures/` in anonymized form only; every sample MUST validate against `mcp-envelope.schema.json` (add the validation loop to the fixture README). |
| 3 | Incident context | The device's 15-entry supported-alarm catalogue, one 24-parameter config snapshot, the command history for the window. | Catalogue/snapshot shapes are already public in `artifacts/nanolink/`; the window's command history follows item 1's anonymization rule. |

**Acceptance criteria:**
- `artifacts/copilot/fixtures/` exists with the item-2 samples and README; a
  `python3 -c "import json, jsonschema, pathlib; …"` loop in the README validates every sample
  against `mcp-envelope.schema.json` and passes.
- At least one `search_device_logs` sample demonstrates the v1.1 lean projection (its
  `query.echo.fields` names the projected set) and one demonstrates `size_cap` truncation with a
  resumable cursor.
- No committed file carries the real device serial or real MAC host parts (grep gate: the real
  serial appears nowhere under `artifacts/copilot/`).
- Item 1 and item 3's command history are delivered via `artifacts/real-data/` in place (or an
  explicitly user-approved anonymized copy) — the PR carries pointers, never the data.
- The handover doc's §12 table is updated from "requested" to "delivered" with the delivery paths.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai). FIRST read
artifacts/copilot/HANDOVER-mcp-log-rca.md (sections 2, 6.1, 11, 12) and
artifacts/copilot/mcp-master-payload.md (sections 6.1, 6.6, 7), then
artifacts/nanolink/femtocell_dashboard_data_contract.md section 2 (log grammar)
and section 4 (RCA tool sketches).

Task: build the RCA incident fixture pack (EPIC-8 S9), items 2 and 3 shapes only.
Item 1 (raw logs) and the real command history are USER-delivered via
artifacts/real-data/ - you produce pointers and README scaffolding for them, never
copy their contents.

1. Create artifacts/copilot/fixtures/ with 2-3 hand-built envelope JSON replies each
   for search_device_logs, get_device_timeline, get_active_alarms, get_device_config,
   get_command_status, over the worked-example reboot incident (SCTP 0x02120400 ->
   S1 setup failure -> FM critical 0x16010400 -> reboot; the incident chain and line
   grammar are in the femtocell contract section 2 and the master payload section 7).
   Derive order_key values with the real algorithm ("{boot_epoch}#{seq:010d}"),
   consistent across samples so the timeline interleaves the same events the log
   search returns. Use the anonymized device id 8C1F64-2205609999 everywhere.
2. Include: one sample with context_lines neighbours (flat items, match/hit_group),
   one with the lean fields projection (query.echo.fields set, ~150 B items), one
   size_cap truncation with a next_cursor that resumes at the first excluded item,
   one empty result (result.kind "empty", success true), and one error
   (NOT_FOUND with a hint naming list_devices).
3. Validate every sample against artifacts/copilot/mcp-envelope.schema.json
   (jsonschema, draft 2020-12); put the validation one-liner in the fixtures README.
4. fixtures/README.md: provenance (which incident, which capture), anonymization
   applied, the item-1/item-3 delivery pointers into artifacts/real-data/ (paths only),
   and the validation loop.
5. Update HANDOVER-mcp-log-rca.md section 12: items delivered, paths, date.

Constraints: NEVER read or copy artifacts/real-data/ contents into a tracked file;
the real serial 22056xxxxx must appear nowhere in your output (grep before finishing);
claims rules apply to README prose (TR-069 (CWMP), no O-RAN claims, no em dash).
```

---

## Rollout / migration notes

**Order within the epic:** S0 (the envelope every later story returns; land it first so nothing is retrofitted — v1.1 contract, projection helper included) → S1 → S2 (the `domains/` scaffold every later story imports) → {S3, S4, S6} in any order or parallel (all consume S1's `ToolContext` and S2's module pattern; S3 before S4 keeps registry-count tests simple) → S5 (needs S1's `role` + S2's module pattern; sequence it after at least one read module has proven the pattern) → S8 tranche A (E1.S1 + E1.S5 are merged as of 2026-08-10, so it is unblocked; tranche B waits on the log pipeline having an owner) → S7 last (docs reflect the merged end state). **S9 (fixture pack) is independent of every code story and can run first** — it needs only the contract docs and the real-data capture; running it early hands the copilot team their local-testing basis and produces the p95 number rate-limit sizing waits on.

S0 and S1 can be one PR if the agent prefers; they touch the same ten tools. Do not invert them:
adding the envelope after the domain modules exist means rewriting every module.

**Migrations:** none in the dev-repo numbering (Appendix A.6 untouched — no platform schema change). S6's prerequisite SQL (the D3 RLS block + `copilot_ops` role) is owned by the RLS decision record's platform TODO (`03-copilot-rls.sql`, `copilot-bootstrap-job.yaml` in maveric-deployment), NOT by this epic; E8.S6 consumes the role, it does not create it. For local compose, S6's test plan applies the D3 block manually.

**Env rollout (all default-off, per environment):**
1. S1 needs nothing new — JWT threading works with existing traffic.
2. `MCP_ENABLE_MUTATING_TOOLS=true` only in envs where operator-in-chat approval is wanted. (2026-08-10: there is no staging environment any more — rehearse the gate in the local compose stack, then enable in prod default-off and watch the audit lines from day one.)
3. `MCP_COPILOT_OPS_DATABASE_URL` only after the D2 `copilot_ops` role exists in that env's bootstrap; the DSN-name guard refuses non-`netai_copilot` databases.

**Backward compatibility:** existing MCP clients that passed `tenant_id` explicitly will break at S1 — by design (the parameter was the vulnerability). This is an internal surface (no external MCP consumers are known; the backend agents use the in-process factories, not :8082); announce in the S1 PR description regardless. The backend page-bound path is untouched throughout. Relocations (S3/S4/S6) are schema-frozen by golden tests, so tool-name-keyed clients see no change.

**Deployment:** zero CI/CD change end to end — same container, same image build, same port. Every story rides the existing `copilot-mcp-server` service; env vars are values-file edits.

## Epic-level risks

1. **PR-protocol friction.** Every submodule story ends with an ask-the-user consent step for SUMMARY updates (submodule CLAUDE.md, non-negotiable). Batching S1–S6 SUMMARY updates into S7 without consent is a protocol violation; the S7 prompt encodes the consent flow explicitly.
2. **FastMCP request-context API drift.** S1's header capture depends on the pinned FastMCP version's request accessor; the fallback (Starlette middleware + ContextVar) is specified in-story. Whichever lands, record it in the PR — later stories import `resolve_context()` and must not care.
3. **Unverified-decode misunderstanding.** :8082 decodes JWTs without verification (constraint 3). Anyone later "hardening" it into local verification creates a second auth authority that will drift from the gateway (Cognito rotation, clock skew). The context.py docstring and `mcp-domain-coverage.md` both state the invariant; treat local verification PRs as design regressions.
4. **Mutation-gate erosion.** The S5 triple gate is only as strong as its weakest future edit: a new mutating tool that skips `gate.py`, a default flipped to `confirm=True`, or registry-when-flag-off creep. The programmatic registry test (expected tool-name set built from modules) plus the "mutations only in actuation_tools.py" DoD line are the tripwires; reviewers should reject any mutating tool outside that module.
5. **`copilot_ops` scope creep.** D4 grants the role SELECT+UPDATE for the review CLI; the MCP tool must stay SELECT-only. If someone wires reviewer labeling into chat, the epic's revisit trigger fires (per-domain server discussion reopens, because the ops credential's blast radius grew). The client-side read-only transaction is the guard; the RLS policies are the backstop.
6. **Managed-params snapshot drift (cross-epic seam with E4.S7).** Until E4.S7's canonical contract file lands, S6's bundled catalogue is a hand-verified copy of smo_sim's 24 entries; if smo_sim's catalogue changes first, the copilot snapshot lies. Mitigation: provenance block with `verified_on` date surfaces staleness; the E4.S7 story's contract doc gains a one-line note adding copilot as a fourth generated copy; whichever epic merges second executes the wiring.
7. **Registry growth vs. tool-choice quality.** The registry grows ~12 → ~30 tools; LLM tool-choice accuracy can degrade with large flat registries. Domain-prefixed descriptions and compact schemas mitigate; if routing quality drops, the follow-up is description tuning or client-side tool filtering — NOT splitting servers (the frozen decision's revisit trigger is credential isolation, not registry size).
8. **Re-architecture surface lag.** ~~E1/E2/E5 add surfaces that do not exist yet~~ **OVERTAKEN
   2026-08-10:** the surfaces exist (openapi v0.6.0, gateway-routed `/ndt/**`, `/ingest/**`,
   `/data/**`, loop endpoints). The follow-up stories (`evaluate_twin_scenario`, loop
   action/feedback visibility) named in `mcp-domain-coverage.md` are now buildable; they stay out
   of this epic's scope but the "does not exist" excuse is gone — pull them in as fast-follows
   once S2/S8 land.
9. **Claims exposure via tool descriptions.** Tool descriptions are user-visible strings an LLM will paraphrase to customers. S2/S4/S5 prompts embed the exact naming rules ("Network Digital Twin", "TR-069 (CWMP)", "Optimization", no compliance claims); E6.S5's claims re-verification pass should include `backend/app/mcp_server/domains/` grep in its sweep (one-line addition to that story's checklist when both epics are active).
10. **Device log pipeline has no owning story (the epic's one external blocker).** S8 tranche B
   (`search_device_logs`, `fetch_raw_log_window`) needs a producer that does not exist: the
   `Log_*.gz` / `ErrorLog_*.gz` parser specified in `artifacts/nanolink/femtocell_dashboard_data_contract.md`
   §2, plus the fix to today's watcher, which consumes only `*.tgz` while real NanoLink devices upload
   single-gzip files (`collector.go:210`) and stamps events with parse time rather than line time.
   E1 builds the `fm_alarms` table and the `/data/fm` query API but no epic builds the log parser that
   fills them from device logs. Mitigation: S8 ships in two tranches with tranche B unregistered and a
   capability probe, so the copilot degrades honestly instead of returning empty results that read as
   "your network is quiet". Resolution belongs in an ingest-side story (proposed E1.S9); tracked in
   `artifacts/upgrade_plans/AUDIT-2026-07-29.md` §4.
11. **Envelope drift between the parent artifact and the vendored copy.** S0 vendors
   `mcp-envelope.schema.json` into the submodule for test use. Two copies drift. The hash-equality
   test is the tripwire; when the schema changes, both move in the same PR.
