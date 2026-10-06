# MCP domain coverage

**Status:** shipped in EPIC-8 (S0–S6, S8, S9). Written from the `domains/` sources, not from the epic
text — where the two disagree, this document follows the code and says so.

Working notes for the epic live in `docs/task_docs/copilot/epic_8_copilot_mcp_layers/` (gitignored).

---

## 1. The question this epic settled

**Does the copilot need an MCP server per platform layer?**

**No. One server, per-domain tool modules.** One process, one port, one registry. Each platform layer is
a module under `app/mcp_server/domains/` that registers its own tools through `register_all(mcp)`, and
`server.py` holds zero `@mcp.tool` decorators.

**Why.** A server per layer multiplies the parts that must agree: six containers, six ports, six places
for the auth model to drift, six deploys to sequence. The benefit sought — a layer's tools being
separable and independently reviewable — is a code-layout property, and modules deliver it without any
of that cost. Domain separation is therefore code layout, not deployment topology.

**Revisit trigger.** Split only when a layer needs a genuinely different *deployment* property, not a
different code shape. Concretely: a layer that must scale independently, or run in a different trust
zone or network segment, or hold a transport the others cannot. Tool count alone is not a trigger.

## 2. Tool inventory

**34 registered by default.** Two more with `MCP_ENABLE_MUTATING_TOOLS`, one more with the ops DSN
*and* `CLOUDLYIO_ORG_UUID` — 37 with everything on. A test asserts the registry as a programmatic
tool-name set built from the domain modules, so the count cannot drift from the code.

### Observability — alarms, events, timeline, diagnostics

| Tool | Answers | Registered |
|---|---|---|
| `get_platform_error_logs` | Retrieve platform error logs for debugging and root cause analysis | by default |
| `get_observability_capabilities` | Report which observability and RCA tools have a data source behind them | by default |
| `get_active_alarms` | List the tenant's currently active FM alarms, most severe first | by default |
| `get_alarm_history` | List FM alarms raised in a window, active and cleared, for flap and recurrence analysis | by default |
| `search_device_events` | Search one device's parsed lifecycle events: reboots, module stops, IP config, uploads | by default |
| `get_device_timeline` | Build one device's interleaved incident timeline: alarms, events, writes, config, advice | by default |

### Actuation — the TR-069 (CWMP) device plane

| Tool | Answers | Registered |
|---|---|---|
| `list_edges` | List the tenant's edge agents, with status and how many devices each one manages | by default |
| `list_devices` | List the tenant's TR-069 (CWMP) devices across every edge, with identity and last inform | by default |
| `get_device_config` | Read one device's managed TR-069 (CWMP) parameter snapshot: the values, bounds and flags | by default |
| `get_device_health` | Read one TR-069 (CWMP) device's current health rollup | by default |
| `get_device_kpis` | Read one device's performance samples: the RF, throughput and load counters | by default |
| `get_command_status` | Read the state and read-back result of one TR-069 (CWMP) write the platform issued | by default |
| `list_device_recommendations` | List the optimization recommendations the platform has generated for one device | by default |
| `approve_recommendation` | Approve one platform-generated optimization recommendation, after a human approves it | only with `MCP_ENABLE_MUTATING_TOOLS` |
| `reject_recommendation` | Reject one platform-generated optimization recommendation, after a human decides to | only with `MCP_ENABLE_MUTATING_TOOLS` |

### Network Digital Twin

| Tool | Answers | Registered |
|---|---|---|
| `list_twin_models` | List the tenant's Network Digital Twin (Bayesian Digital Twin) models with training status | by default |
| `get_twin_model` | Get one Network Digital Twin (Bayesian Digital Twin) model: training status and headline metrics | by default |
| `get_twin_inference_run` | Get the status, and the result when complete, of a Network Digital Twin inference run | by default |

### Optimization (CCO / ES / LB / MRO)

| Tool | Answers | Registered |
|---|---|---|
| `list_rapp_models` | List the tenant's trained models for one Optimization rApp, with training status | by default |
| `get_rapp_model` | Get one trained Optimization rApp model: training status, metrics and its inputs | by default |
| `get_inference_report` | Explain one completed Optimization rApp inference run, with the numbers already worked out | by default |
| `compare_inference_models` | Compare two trained Optimization rApp models over a full evaluation day | by default |
| `compare_rapp_policies` | Compare inference outputs between two Optimization rApp models | by default |

### Ingest and data

| Tool | Answers | Registered |
|---|---|---|
| `get_baseline_detail` | Get one baseline: its topology description, asset locations and creation time | by default |
| `list_ue_datasets` | List the tenant's UE datasets, with source type and generation stats | by default |
| `get_ue_dataset` | Get one UE dataset: source type, originating baseline and generation stats | by default |
| `get_nybsys_upload_status` | Check NybSys NanoLink PM CSV uploads: one job by id, or the most recent jobs | by default |
| `validate_baseline_params` | Validate topology parameters against platform schema bounds | by default |
| `validate_dataset_params` | Validate traffic-load or mobility dataset generation parameters | by default |
| `recommend_baseline_config` | Get recommended topology configuration for a scenario | by default |
| `recommend_dataset_config` | Get recommended dataset generation parameters for a scenario | by default |
| `query_existing_baselines` | List existing baselines for the tenant | by default |
| `compare_datasets` | Compare two UE datasets by diffing their stats | by default |
| `estimate_impact` | Estimate row count for a traffic-load or mobility generation run | by default |
| `get_generation_docs` | Get API documentation and curl examples for data generation endpoints | by default |

### Policy and guardrails

| Tool | Answers | Registered |
|---|---|---|
| `get_managed_param_catalog` | List the TR-069 (CWMP) managed parameters the platform may write, with types and bounds | by default |
| `get_guardrail_decisions` | Read the input guardrail decision log: what was classified, what was blocked, how fast | only with ops DSN **and** `CLOUDLYIO_ORG_UUID` |

### Defined but deliberately unregistered

| Tool | Why |
|---|---|
| `search_device_logs` | No data source. Parsed log lines need a `device_log_lines` store, which does not exist |
| `fetch_raw_log_window` | No data source. Needs the raw `.gz` archived, which nothing writes |

They are absent from the registry rather than returning empty results, because zero rows read to a
customer as *"your network is quiet"* rather than *"this is not built."* `get_observability_capabilities`
is the machine-readable probe that says which is which. Deferred by the lead on 2026-08-19 pending the
cost decision: roughly 4.6B rows/year at 1,000 devices, for content that is ~97% CWMP chatter.

## 3. Auth and identity

**Identity is never an LLM-visible argument.** `context.py` derives it per invocation from the inbound
connection:

| Field | Source |
|---|---|
| `tenant_id` | the `custom:tenant_id` claim on the bearer token |
| `auth_token` | the `Authorization: Bearer` header, forwarded per request |
| `role` | the `custom:role` claim, passed through without mapping |
| `correlation_id` | `X-Correlation-ID`, echoed back verbatim in `context.correlation_id` |
| `request_id` | `X-Request-ID`, surfaced separately as `context.request_id` |

That is **five** fields; the epic text says four, and the fifth (`request_id`) exists because conflating
a caller's session id with the gateway's per-request id makes a correlated trace unreadable.

**`:8082` is not an authorization authority.** It decodes the JWT without verifying the signature,
purely to build tenant-scoped URLs. The gateway verifies and enforces on every call. Adding local
verification would create a second authority that drifts from the gateway on Cognito key rotation and
clock skew, so it is deliberately absent.

A missing or unusable bearer returns `AUTH_CONTEXT_MISSING` and makes **zero** outbound calls.

## 4. Mutations, and the three gates

Two tools write: `approve_recommendation` and `reject_recommendation`. Both act only on recommendations
**the platform itself generated** — the copilot cannot compose a change of its own — and an approval
queues a TR-069 write to a live device.

| Gate | Behaviour |
|---|---|
| **Env** | `MCP_ENABLE_MUTATING_TOOLS` defaults false, and false means *absent from the registry*, not present-and-refusing. A model cannot try what it cannot see |
| **Role** | `trial_user` is refused before any outbound call, even with `confirm=true` |
| **Confirm** | `confirm` defaults false, and that path never writes: it reads current state and returns an `action_preview` a human must be shown |

Every attempt — previewed, refused, executed, or failed upstream — is written to the mutation audit log.
A forbidden-path test pins the routes that stay unreachable: direct device commands, optimize-mode,
key regeneration, and everything under `/v1/agent/**`. One allowlist entry exists, `/rapps/compare/infer`,
which is a compute call rather than a state change.

## 5. The one direct database read, and its guard

`get_guardrail_decisions` is the only tool that opens a database connection instead of calling the
gateway. It has to: the guardrail decision log is copilot's own table (`conversation.guardrail_decision_log`)
and the gateway serves no route to it.

That makes its gate the only authorization in front of the log, and **the log spans every tenant** — the
query carries no tenant predicate and the RLS policy keys on the database role (`current_user =
'copilot_ops'`), not on a tenant. So:

- **Two variables must both be set** or the tool does not register: `MCP_COPILOT_OPS_DATABASE_URL` and
  `CLOUDLYIO_ORG_UUID`. Missing either means absent, never gated-on-the-role-alone.
- **The DSN must name copilot's own database.** One that names anything else — the platform's `maveric`
  in particular — is refused at registration rather than failing later at query time.
- **The gate reproduces the gateway's `RequirePlatformAdmin`:** the `cloudly_admin` role *and* the
  CloudlyIO org tenant. `CLOUDLYIO_ORG_UUID` is the same variable the gateway reads, so one value
  configures both rules and they cannot drift. The uuid is not hardcoded here: S1 removed the last
  tenant literal from this package.
- The read runs as a SELECT-only role, and the projection omits `query_hash`, `session_id`,
  `reviewer_id` and `reviewer_note` — the hash cannot be reversed and would only invite trying, and the
  other three identify people rather than describing decisions.

## 6. The managed-params generation seam

`get_managed_param_catalog` serves `domains/data/managed_params.json` verbatim. That file is **generated**,
not maintained: `scripts/gen_managed_params.py` in the parent repo declares smo_sim's `managed_params.py`
the single source of truth and emits hash-stamped copies for the frontend, the edge agent and now the
copilot, behind a `--check` drift gate.

Anyone changing the catalogue changes smo_sim and regenerates. The provenance block deliberately carries
**no generation date** — a timestamp would fail `--check` on every run, and the catalogue sha256 answers
"is this current?" more precisely than a date could.

24 parameters, 23 editable, 15 optimizable, `MaxTxPower` the only non-editable entry.

## 7. What the tool schemas cannot tell you

MCP advertises each tool's parameter schema, so names, defaults and caps are discoverable at runtime.
**Semantics are not.** These are the ones that matter, and they live here and in the tool docstrings:

**`kind: "empty"` with `success: true` is a finding, not a failure.** The query was valid and the answer
is genuinely nothing, so an agent may tell the operator the device is quiet. `success: false` means it
knows nothing and must say so. Never collapse them — this is the invariant the whole envelope exists for.

**Sizing.** `limit` binds: default 50, hard cap 500. Asking beyond the cap is honoured *to* the cap and
reported in `query.ignored` as `capped`, never rejected. Replies are then fitted to a **128 KB** budget
before `size_cap` binds; the payload spec's ~8 KB figure is advisory only.

**The `fields` projection** trims `data.items` and nothing else — the envelope is never projected away.
A **floor** always comes back and it differs per tool: each keeps its own identity field, and the two
line-shaped tools also keep `order_key` (`search_device_events`: `order_key`, `event_type`;
`get_device_timeline`: `entry_type`, `ts`, `order_key`; `get_active_alarms`: `alarm_id`). An unknown
field name degrades — one `query.ignored` entry per name, reason `unknown_field` — and if *every*
requested name is unknown you get full records rather than empty ones, because `{}` per item would read
as "this device has no data". The projection is applied at the MCP boundary, not pushed upstream:
`/data/**` has no `fields` parameter, and the requestable names are not columns.

**Ordering.** `order_key` is `"{boot_epoch}#{seq:010d}"`, the device's own stream position, and it is
never fabricated — a record carries a real one, or one derived from a real `boot_epoch` and `seq`, or
the field is absent. Results are ordered by `ts` ascending with `order_key` as the tie-break, because
most records have no stream position at all. Consumers must not re-sort: `seq` restarts at 0 on every
reboot.

**`query.ignored` reasons**, the closed set: `unsupported_by_source`, `capped`, `conflicting_param`,
`insufficient_permission`, `retention_boundary`, `unknown_field`.

**`PARTIAL_RESULT` is the one error code that rides `success: true`.** On `get_device_timeline` it means
one source did not answer, so a write in that window may be missing. A partial timeline is not a
complete one.

**`next_actions[].args` are executable verbatim** against the named tool. Tests assert they run as given
and that no action names an unregistered tool.

## 8. Deviations from the epic text, and why

| Epic said | Shipped | Why |
|---|---|---|
| A retention floor, with `retention_boundary` truncation | **No retention reporting at all.** `MCP_ROW_RETENTION_DAYS` is deleted and no code path sets that reason | Nothing in the platform deletes these rows, so the 90 days was a *requirement* being reported as a *fact*. It stamped complete replies as truncated, and `retention_boundary` is the one reason with no cursor — an agent read it as "that is everything" and stopped paging a full answer. `provenance[].coverage.from` is now looked up from the store, or `null` when unknown |
| Truncation precedence between the floor and `limit` | Void | With no floor, there is nothing to order against `limit` |
| A four-field `ToolContext` | Five | `request_id` is separate from `correlation_id`; see §3 |
| `GET /ue-data/datasets/{dataset_id}` exists | It did not, and now does | Built inside this epic at the lead's direction, in smo_sim, with the spec at 0.7.0. The tool previously matched an id inside a bounded list scan |
| Hand-verify a 24-entry managed-param snapshot | Generated as a third target of an existing generator | `artifacts/contracts/` does not exist, but E4.S7's generator does — see §6 |
| `platform-admin per its role mapping` | There is no role mapping | Copilot's `get_current_user` passes the raw claim through |
| Tranche B log tools registered | Defined, unregistered, behind a probe | No data source; deferred by the lead |
| The 34/37 registry count is verifiable only from this document | The container states it at boot | `mcp_boot` reports `tools=34` with every name, plus one `gated_off … reason=` line per withheld tool. Registration banners had been discarded since the package began re-exporting from `server` — the count was documented but unobservable |

## 9. Related

- [`mcp-master-payload.md`](mcp-master-payload.md) — the response contract this implements
- [`mcp-envelope.schema.json`](mcp-envelope.schema.json) — the schema, vendored into the backend with a digest test
- [`HANDOVER-mcp-log-rca.md`](HANDOVER-mcp-log-rca.md) — the RCA agreement, including tranche A/B
- [`fixtures/`](fixtures/) — 14 contract-exact sample envelopes over one real incident
- [`copilot_LLD.md`](copilot_LLD.md) §8 — the module layout in the service's own design doc
- [`guardrail-rls-decision.md`](guardrail-rls-decision.md) — D2/D3, the `copilot_ops` role and its policies
