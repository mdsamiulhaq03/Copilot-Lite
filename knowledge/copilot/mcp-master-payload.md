# CloudlyNet MCP master payload contract

**Status:** AGREED with the copilot team, v1.1, 2026-08-10 (proposed 2026-07-29)
**Contract id:** `cloudlynet.mcp.response.v1`

> **v1.1 changes** (decision record: [`HANDOVER-mcp-log-rca.md`](./HANDOVER-mcp-log-rca.md) §11):
> field projection via `fields` on every list tool (§3 rule 8, §6.1.3); reply-size semantics
> clarified — ~8 KB is advisory, `limit` vs `size_cap` interplay defined (§8 note 3);
> `fetch_raw_log_window` is bounded + paged, no bulk mode (§6.6); `correlation_id` is minted by
> the copilot orchestrator, one per RCA session (§9.2, resolved). Envelope unchanged — no
> `schema` bump; `unknown_field` was added to the `query.ignored` reason enum.
**Scope:** every tool on every CloudlyNet MCP server, in every layer (Intelligence Layer: Ingest/Data,
Network Digital Twin, Optimization, Policy & Guardrails; Actuators: TR-069 (CWMP); Observability/RCA).
**Machine-readable schema:** [`mcp-envelope.schema.json`](./mcp-envelope.schema.json)
**Implements:** EPIC-8 story S0 ([`../docs/cloudlynet-rearchitecture/epics/EPIC-8-copilot-mcp-layers.md`](../docs/cloudlynet-rearchitecture/epics/EPIC-8-copilot-mcp-layers.md))

---

## 1. The rule

> One envelope, every tool, every server. The **outer body is identical everywhere**; the
> **`data` block is domain-specific**.

This is the direct answer to the copilot team's "a totally universal payload might be difficult":
correct, and the envelope does not try to universalise the payload. It universalises everything
*around* the payload, which is where the LLM-facing and ops-facing value sits: did it succeed, what
was actually queried, how much was elided, how fresh is it, what should the agent do next. The
per-domain variation lives inside `data`, discriminated by `data_type`.

**Why an envelope at all.** Today every MCP tool returns a bare `str`
(`backend/app/mcp_server/server.py`, all ten tools `-> str`). An agent cannot distinguish "no
results" from "failed", cannot tell truncated output from complete output, and cannot know whether
it is reading data from 30 seconds ago or 3 days ago. Each of those is a hallucination source.

**Why this shape.** It extends the platform envelope the gateway already returns
(`SuccessEnvelope` / `ErrorEnvelope`, `artifacts/design/openapi.yaml:2372-2436`): the
`success` / `timestamp` / `message` / `data` / `errors` spine is preserved verbatim, so an MCP
response and a gateway response are read the same way, and the gateway error-code enum is reused
rather than reinvented. The versioned `schema` discriminator follows the frozen Kafka contract
convention (`01-hld-frozen.md` A.5).

---

## 2. The envelope

```jsonc
{
  // ── identity ────────────────────────────────────────────────────────────
  "schema": "cloudlynet.mcp.response.v1",   // REQUIRED. Contract id + major version.
  "success": true,                          // REQUIRED. true => errors == []
  "timestamp": "2026-07-29T10:31:04.512Z",  // REQUIRED. UTC, RFC 3339, response generation time.
  "message": "12 of 42 matching lines returned.",  // Optional. One human/LLM sentence.

  "tool": {                                 // REQUIRED. Who answered.
    "name": "search_device_logs",
    "domain": "observability",              // ingest | ndt | optimization | policy | actuation | observability
    "server": "cloudlynet-copilot-mcp",     // logical server id; survives multi-server futures
    "contract_version": "1.0.0"             // per-tool payload version, independent of `schema`
  },

  // ── request context ─────────────────────────────────────────────────────
  "context": {                              // Optional block, present on gateway-backed tools.
    "tenant_id": "3f2a…",                   // Resolved from the JWT, never from an LLM argument.
    "request_id": "01J…",                   // Echoes X-Request-ID when the call crossed the gateway.
    "correlation_id": "rca-8c1f64-2026-06-13"  // Caller-supplied; ties a multi-tool RCA together.
  },

  // ── what was actually run ───────────────────────────────────────────────
  "query": {                                // Optional block; present whenever the tool takes params.
    "echo": {                               // Normalised params AFTER defaults were applied.
      "device_id": "8C1F64-2205609999",
      "start": "2026-06-13T17:50:00Z",
      "end":   "2026-06-13T18:05:00Z",
      "limit": 12
    },
    "applied_defaults": ["limit", "sort", "end"],  // Params the caller did NOT send.
    "ignored": [                            // Params accepted but not honoured. Never silent.
      { "param": "regex", "reason": "unsupported_by_source",
        "detail": "Source supports substring match only; treated as substring." }
    ]
  },

  // ── result framing ──────────────────────────────────────────────────────
  "result": {                               // REQUIRED. How to read `data`.
    "kind": "collection",                   // collection | object | timeseries | summary
                                            // | action_preview | empty | error
    "data_type": "device_log_lines",        // Discriminator for the `data` block's schema.
    "count": 12,                            // Items actually in `data`.
    "total_matched": 42,                    // Items that matched, before limit/truncation. null if unknown.
    "truncated": true,                      // REQUIRED whenever `data` is not the whole answer.
    "truncation_reason": "limit",           // limit | size_cap | source_cap | retention_boundary
    "page": { "limit": 12, "offset": 0, "next_cursor": "eyJzZXEiOjE2NX0=" }
  },

  // ── the domain-specific body ────────────────────────────────────────────
  "data": { },                              // REQUIRED. Shape defined by result.data_type. {} when empty.

  // ── trust ───────────────────────────────────────────────────────────────
  "provenance": [                           // Optional but STRONGLY recommended on every read tool.
    { "source": "fm_alarms", "store": "postgres", "as_of": "2026-07-29T10:31:03Z",
      "coverage": { "from": "2026-04-30T00:00:00Z", "to": "2026-07-29T10:31:03Z" } },
    { "source": "nanolink-logs/…/20260613/", "store": "object_storage",
      "as_of": "2026-06-13T18:06:00Z", "coverage": null }
  ],
  "freshness_s": 61,                        // Optional. Age of the newest datum, seconds.

  // ── agent steering ──────────────────────────────────────────────────────
  "next_actions": [                         // Optional. Machine-usable follow-ups; NOT prose.
    { "tool": "fetch_raw_log_window", "why": "Read the unparsed 60s window around the raise.",
      "args": { "device_id": "8C1F64-2205609999", "at": "2026-06-13T17:58:12Z", "window_s": 60 } }
  ],

  // ── failures ────────────────────────────────────────────────────────────
  "errors": [ ]                             // REQUIRED. [] on success. Shape in §4.
}
```

### Required vs optional

| Always present | Present when meaningful |
|---|---|
| `schema`, `success`, `timestamp`, `tool`, `result`, `data`, `errors` | `message`, `context`, `query`, `provenance`, `freshness_s`, `next_actions` |

Omit optional blocks entirely rather than sending `null` or `{}`. Envelope overhead on a typical
read is ~250 bytes, which is the cost of the agent knowing what it is looking at.

### `result.kind` semantics

| kind | `data` holds | Use for |
|---|---|---|
| `collection` | `{ "items": [...] }` | Lists: log lines, alarms, models, devices |
| `object` | the entity | A single model, device, run, config snapshot |
| `timeseries` | `{ "series": [...] }` | PM counters, KPI traces |
| `summary` | aggregates | Counts, distributions, health rollups |
| `action_preview` | the confirm-gate preview | Mutating tools before `confirm=true` (§5) |
| `empty` | `{}` | Query valid, zero matches. **`success: true`.** |
| `error` | `{}` | `success: false`; read `errors` |

`empty` versus `error` is the single most load-bearing distinction in this contract. "No alarms in
the window" is a finding. "The alarm store was unreachable" is a failure. Collapsing them, which a
bare-string return does, is how an agent ends up telling a customer their network is healthy when
the query simply broke.

---

## 3. Query contract rules (all layers)

These rules answer the copilot team's item A and the standing instruction that queryable
parameters be **accepted but optional, never mandatory**.

1. **Every filter parameter is optional.** A tool called with zero arguments must return a useful,
   bounded default rather than a validation error. Documented defaults per tool; the applied ones
   are listed in `query.applied_defaults` so the agent can see what it did not choose.
2. **Identity parameters are never LLM-visible.** `tenant_id` and the bearer token come from
   `ToolContext` (EPIC-8 S1). A tool that takes `tenant_id` as an argument is a defect.
3. **Unsupported parameters are accepted, not rejected.** If a caller passes `regex` and the source
   does substring only, honour what you can and record the downgrade in `query.ignored`. This keeps
   one stable tool signature while sources vary in capability, and it is why the MCP side can
   implement against this contract before every source supports every filter.
4. **Time is always UTC RFC 3339 on the wire.** Relative forms (`-2h`, `-15m`) are accepted on
   input and normalised in `query.echo`. Device-local timestamps are additionally preserved inside
   `data` where the source is device-local (§6).
5. **Every list tool paginates.** `limit` (documented default and hard cap), plus `cursor`. Cursors
   are opaque base64 and must encode a stable sort key, not an offset into a shifting result set.
6. **Truncation is never silent.** `result.truncated` plus `truncation_reason`. A tool that drops
   data without saying so is a hallucination generator.
7. **Enumerations are lowercase snake_case** on the wire, even when the source uses other casing.
8. **Every list tool accepts `fields: string[]`** (v1.1) — a projection naming the per-item fields
   to return. Omitted means the full record. Unknown names are honoured-where-possible and
   reported per name in `query.ignored` with reason `unknown_field`, never rejected.
   `query.echo.fields` always shows the projection actually applied. Projection touches
   `data.items[*]` only; the envelope itself is never projected away. Rationale and the
   recommended lean set for RCA paging: §6.1.3.

---

## 4. Error contract

```jsonc
{
  "schema": "cloudlynet.mcp.response.v1",
  "success": false,
  "timestamp": "2026-07-29T10:31:04.512Z",
  "message": "Device 8C1F64-9999999999 is not registered in this tenant.",
  "tool": { "name": "search_device_logs", "domain": "observability",
            "server": "cloudlynet-copilot-mcp", "contract_version": "1.0.0" },
  "result": { "kind": "error", "data_type": null, "count": 0, "truncated": false },
  "data": {},
  "errors": [
    { "code": "NOT_FOUND",
      "message": "Device 8C1F64-9999999999 is not registered in this tenant.",
      "details": { "device_id": "8C1F64-9999999999" },
      "retryable": false,
      "hint": "Call list_devices to enumerate registered devices for this tenant." }
  ]
}
```

**Codes.** Reuse the gateway enum verbatim (`openapi.yaml:2404-2432`): `BAD_REQUEST`,
`INVALID_REQUEST`, `VALIDATION_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`,
`RATE_LIMITED`, `INTERNAL_ERROR`, `DB_ERROR`, `DEPENDENCY_ERROR`, `TIMEOUT`, `JOB_FAILED`,
`TENANT_REQUIRED`, `TENANT_FORBIDDEN`, … plus these MCP-layer additions:

| Code | Meaning | Retryable |
|---|---|---|
| `AUTH_CONTEXT_MISSING` | No Bearer on the MCP connection | no |
| `TENANT_UNRESOLVED` | JWT carried no usable `custom:tenant_id` | no |
| `CONFIRMATION_REQUIRED` | Mutating tool called without `confirm=true` (§5) | no |
| `TOOL_DISABLED` | Tool exists but is gated off in this environment | no |
| `UPSTREAM_UNSUPPORTED` | Source cannot serve this query at all | no |
| `PARTIAL_RESULT` | Some sources answered, some failed; `data` is incomplete | yes |

`retryable` and `hint` exist because the consumer is an LLM. `hint` must name a concrete recovery
action, ideally a tool name. Never return a stack trace or a raw upstream body to the model.

`PARTIAL_RESULT` is the one code that may appear with `success: true`: a multi-source read (alarms
plus events plus commands) where one source failed returns what it has, `truncated: true`, and the
failure in `errors`. Silence about the missing source would be worse than partial data.

---

## 5. Mutations ride the same envelope

The EPIC-8 S5 confirm gate is expressed in the envelope, not beside it. First call
(`confirm=false`, the default the model hits first):

```jsonc
{
  "schema": "cloudlynet.mcp.response.v1",
  "success": true,
  "timestamp": "2026-07-29T10:32:00Z",
  "message": "Preview only. Nothing has been sent to the device.",
  "tool": { "name": "approve_recommendation", "domain": "actuation",
            "server": "cloudlynet-copilot-mcp", "contract_version": "1.0.0" },
  "result": { "kind": "action_preview", "data_type": "recommendation_preview",
              "count": 1, "truncated": false },
  "data": {
    "requires_confirmation": true,
    "reco_id": "…", "device_id": "8C1F64-2205609999",
    "proposed_changes": [ { "param": "…RS.RSPower", "current": -3, "proposed": -5, "unit": "dB" } ],
    "guardrails": { "sinr_floor_db": 6.0, "predicted_sinr_db": 8.4 },
    "instruction": "Relay this preview to the human. Call again with confirm=true only after the human explicitly approves."
  },
  "errors": []
}
```

Executed call returns `result.kind: "object"`, `data.executed: true`, and the command id. A refused
call returns `success: false` with `FORBIDDEN` (trial role) or `TOOL_DISABLED` (env gate off).
Neither the preview nor the refusal may be mistaken for an execution, which is exactly why
`requires_confirmation` sits in `data` **and** the kind is `action_preview`.

---

## 6. Domain bodies (`data`, keyed by `result.data_type`)

The envelope is frozen. These bodies are versioned per tool via `tool.contract_version`.

### 6.1 `device_log_lines` (Observability/RCA)

The reference body, and the one the copilot team is blocked on. Evidence base:
[`../nanolink/femtocell_dashboard_data_contract.md`](../nanolink/femtocell_dashboard_data_contract.md)
§2 (log grammar, 15,907 Log + 4 ErrorLog files, one device, 14 days).

```jsonc
"data": {
  "items": [
    {
      // ── ordering (see §6.1.1) ───────────────────────────────────────────
      "seq": 165,                                  // Device line sequence, monotonic within a boot.
      "boot_epoch": "2026-06-13T17:56:57Z",        // seq resets to 0 at reboot; this disambiguates.
      "order_key": "2026-06-13T17:56:57Z#0000000165",

      // ── time ────────────────────────────────────────────────────────────
      "ts": "2026-06-13T17:58:12.431Z",            // UTC, normalised.
      "ts_device_local": "2026-06-13 23:28:12.431",// Verbatim from the line.
      "tz_source": "device_local",                 // device_local | utc | unknown

      // ── identity ────────────────────────────────────────────────────────
      "device_id": "8C1F64-2205609999",
      "dn": "device=8C1F64-2205609999",            // Canonical DN (single-cell femtocell).
      "module": "FM",                              // [MODULE] tag: TR69|SON|SCTP|FM|SCM|L1_L2_Wrapper|…
      "stream": "errorlog",                        // log | errorlog | contlog | devicelog

      // ── content ─────────────────────────────────────────────────────────
      "message": "Critical alarm 0x16010400 raised, system reboot will be taken to recover it after 90s.",
      "severity": "critical",                      // critical|major|minor|warning|indeterminate|cleared|info
      "class": "FAULT",                            // FAULT | STATE | STATE_CM | PM_ISH | OTHER
      "alarm_id": "0x16010400",                    // null when the line is not an alarm line.
      "source_ref": "main/informer.c:307",         // Vendor file:line from the log grammar.
      "template_hash": "t_9f21c4",                 // Drain-style template id, for aggregation.

      // ── match framing (the "neighbours" answer) ─────────────────────────
      "match": "hit",                              // hit | context
      "context_offset": 0,                         // 0 for a hit; -2/-1/+1/+2 for neighbours.
      "hit_group": 1,                              // Groups a hit with its own context lines.

      // ── provenance ──────────────────────────────────────────────────────
      "archive_file": "nanolink-logs/3f2a…/8C1F64-2205609999/20260613/ErrorLog_1758.gz"
    }
  ]
}
```

#### 6.1.1 The order key, and why it is not the timestamp

Device timestamps have millisecond resolution and the log emits bursts inside one millisecond, so
`ts` alone does not totally order the stream. The device's own 10-digit sequence number does, and it
is the dedup key the ingest pipeline already uses. It resets to 0 on reboot (observed mid-file:
`ErrorLog_1758` runs seq 165, reboots, resumes at 79), so `seq` is only unique **within a boot**.

`order_key = "{boot_epoch}#{seq:010d}"` sorts lexicographically into true stream order across
reboots. Sort on it; never reconstruct order from `ts` alone.

#### 6.1.2 Flat list plus grouping, not nesting

`items` is flat. Hits and their context lines are siblings distinguished by `match` and grouped by
`hit_group`. This was chosen over nesting `{hit, context[]}` because context windows overlap when
two hits are three lines apart, and a nested shape would duplicate those lines. A flat list with
`hit_group` renders either way and never double-counts.

#### 6.1.3 Lean records via `fields` projection (v1.1)

A full `device_log_lines` item is ~700 B; ~85% of it is repeated metadata and ~15% is the message
text. The copilot RCA loop pages through incidents, so it asks for the lean shape:

```jsonc
// Request: search_device_logs(..., fields=["order_key","message","module","severity","alarm_id","match"])
"data": {
  "items": [
    { "order_key": "2026-06-13T17:56:57Z#0000000165",
      "message": "Critical alarm 0x16010400 raised, system reboot will be taken to recover it after 90s.",
      "module": "FM", "severity": "critical", "alarm_id": "0x16010400", "match": "hit" }
  ]
}
```

~150 B per item — roughly 50 lines in the space 10 full records took, a ~5x density gain per
round-trip. `order_key` doubles as the compact line id (unique per line, cursor-compatible, and the
argument `fetch_raw_log_window` and timeline correlation both accept). The envelope around `items`
is never projected away, and `query.echo.fields` always states the projection that was applied.

### 6.2 `fm_alarms` (Observability/RCA)

Backed by the `fm_alarms` table (femtocell contract §3.2). Lifecycle-aware, so alarms are not just
log lines: `state` (`active`/`cleared`), `occurrence_count` (the 31-line ACS backoff series collapses
to one alarm with `occurrence_count: 31`), `raised_at`/`cleared_at`/`last_seen_at`,
`probable_cause`, `specific_problem`, `clearing_mechanism`.

### 6.3 `device_timeline` (RCA, `result.kind: "collection"`)

The interleaved RCA body: alarms, lifecycle events, commands, config changes and recommendations,
each item carrying `entry_type` plus its native record. This is the body that answers "why did device
X reboot on 2026-06-13" in a single tool call.

**Ordering (corrected 2026-08-17). Sort by `ts` ascending, not by `order_key`.** Earlier revisions of
this section said the sources sit on "one `order_key` axis"; that is not achievable and the claim is
withdrawn.

Only device-plane sources have an `order_key`. Commands, config changes and recommendations are
generated by the platform, so they have no device `seq` and no boot epoch. Synthesising a key from
their timestamp does not interleave, because a device key is prefixed with **when the boot started**
rather than when the line was emitted:

```
device line   seq 165, ts 17:58:12.431, boot_epoch 17:56:57
              order_key = "2026-06-13T17:56:57Z#0000000165"
platform cmd  ts 17:58:00.000
              synthetic = "2026-06-13T17:58:00.000Z#..."
```

Lexicographically the device line sorts first, though it happened twelve seconds later. The error is
not a rounding artifact: it scales with boot duration, so a device up for three hours puts every one
of its lines before every platform record in that window, which inverts the one question an RCA
timeline exists to answer.

Therefore:

- Items are ordered by **`ts` ascending**; `query.echo.sort` reports `"ts_asc"`.
- The tie-break is `(ts, order_key, source)`, so ordering is total and stable, and two device lines
  inside the same millisecond still order correctly against each other. That preserves the exact
  property `order_key` was introduced for.
- Each item carries `order_key` **when it genuinely has one**, and `null` otherwise. Nothing is
  synthesised.
- A collapsed alarm carries `order_key` only when `occurrence_count == 1`. A row with
  `occurrence_count: 22` stores one `(boot_epoch, seq)` for a fault seen 22 times and cannot say which
  occurrence that key came from, so claiming one would be unfounded.

`order_key` remains the sole sort key on single-source device-line tools, where every record has one:
`search_device_logs` and `fetch_raw_log_window` (§6.1, §6.6). No envelope change is required for any
of this — `sort` lives in `query.echo` and the item shape lives in `data`, both already open.

Worked example: `artifacts/copilot/fixtures/get_device_timeline/01-incident.json`.

### 6.4 `pm_series` (Intelligence Layer / Ingest)

`result.kind: "timeseries"`. `{ series: [ { dn, metric, unit, granularity_s, points: [[ts, value]] } ] }`.
Values are numeric, never stringified (today's `device_kpis` stores strings, which is why five
dashboard charts are broken; the canonical `pm_measurements.value double precision` fixes it).

### 6.5 Intelligence Layer and Actuator bodies

`twin_models`, `twin_inference_run`, `rapp_models`, `inference_report`, `baseline_detail`,
`ue_datasets`, `upload_status`, `device_config`, `device_health`, `command_status`,
`guardrail_decisions`, `managed_param_catalog`. Each is defined in its EPIC-8 story; all ride this
envelope unchanged.

### 6.6 `raw_log_lines` — `fetch_raw_log_window`, bounded and paged (v1.1)

**Decided 2026-08-10 (copilot-requested): capped window + `next_cursor`, same envelope, same
`fields` projection, NO bulk mode.** The copilot team dropped an entire compression /
reference-tag / trace-back layer on the strength of this guarantee — do not reintroduce an
unbounded variant.

- Signature: `device_id` (required), `at` (required), `window_s?` (server-capped; asking beyond
  the cap is honoured to the cap and reported in `query.ignored` with reason `capped`),
  `limit?`, `cursor?`, `fields?[]`.
- `result.data_type: "raw_log_lines"`, `result.kind: "collection"`. Items reuse the
  `device_log_lines` shape where the line parses; a line the parser cannot structure is carried
  as `{ "order_key": …?, "raw": "<verbatim line>" }` so the escape hatch never hides content.
- Paging walks the window in `order_key` order; `page.next_cursor` resumes exactly where the
  reply stopped, whether the stop came from `limit` or `size_cap`.
- Source is the archived `.gz` in object storage (re-parse on demand), which is what lets this
  tool answer past the 90-day Postgres row floor.

---

## 7. Worked example: one hit with neighbours

Request: `search_device_logs(device_id="8C1F64-2205609999", q="alarm", start="2026-06-13T17:57:00Z",
end="2026-06-13T18:00:00Z", context_lines=1, limit=3)`

```json
{
  "schema": "cloudlynet.mcp.response.v1",
  "success": true,
  "timestamp": "2026-07-29T10:31:04.512Z",
  "message": "3 of 47 matching lines returned, with 1 line of context on each side.",
  "tool": {
    "name": "search_device_logs",
    "domain": "observability",
    "server": "cloudlynet-copilot-mcp",
    "contract_version": "1.0.0"
  },
  "context": {
    "tenant_id": "3f2a1c88-0e44-4a1b-9d21-77bb0c5e9f10",
    "request_id": "01JZQK7M4S8YB3N2VQ0X1C6TDA"
  },
  "query": {
    "echo": {
      "device_id": "8C1F64-2205609999",
      "q": "alarm",
      "start": "2026-06-13T17:57:00Z",
      "end": "2026-06-13T18:00:00Z",
      "context_lines": 1,
      "limit": 3,
      "sort": "order_key_asc",
      "streams": ["log", "errorlog"]
    },
    "applied_defaults": ["sort", "streams"],
    "ignored": []
  },
  "result": {
    "kind": "collection",
    "data_type": "device_log_lines",
    "count": 5,
    "total_matched": 47,
    "truncated": true,
    "truncation_reason": "limit",
    "page": { "limit": 3, "offset": 0, "next_cursor": "eyJib290IjoiMjAyNi0wNi0xM1QxNzo1Njo1N1oiLCJzZXEiOjE2Nn0=" }
  },
  "data": {
    "items": [
      {
        "seq": 163,
        "boot_epoch": "2026-06-13T17:56:57Z",
        "order_key": "2026-06-13T17:56:57Z#0000000163",
        "ts": "2026-06-13T17:57:33.118Z",
        "ts_device_local": "2026-06-13 23:27:33.118",
        "tz_source": "device_local",
        "device_id": "8C1F64-2205609999",
        "dn": "device=8C1F64-2205609999",
        "module": "SCTP",
        "stream": "errorlog",
        "message": "sctp connect to peer 10.20.0.4 failed, retry 4",
        "severity": "major",
        "class": "STATE",
        "alarm_id": null,
        "source_ref": "src/sctp_app.c:1588",
        "template_hash": "t_4b7e10",
        "match": "context",
        "context_offset": -1,
        "hit_group": 1,
        "archive_file": "nanolink-logs/3f2a1c88/8C1F64-2205609999/20260613/ErrorLog_1758.gz"
      },
      {
        "seq": 164,
        "boot_epoch": "2026-06-13T17:56:57Z",
        "order_key": "2026-06-13T17:56:57Z#0000000164",
        "ts": "2026-06-13T17:57:34.402Z",
        "ts_device_local": "2026-06-13 23:27:34.402",
        "tz_source": "device_local",
        "device_id": "8C1F64-2205609999",
        "dn": "device=8C1F64-2205609999",
        "module": "SCTP",
        "stream": "errorlog",
        "message": "Alarm Logged, id: 0x02120400 file: src/sctp_app.c line: 1588 detail: SCTP Connect Peer Failed!",
        "severity": "major",
        "class": "FAULT",
        "alarm_id": "0x02120400",
        "source_ref": "src/sctp_app.c:1588",
        "template_hash": "t_1a0cc9",
        "match": "hit",
        "context_offset": 0,
        "hit_group": 1,
        "archive_file": "nanolink-logs/3f2a1c88/8C1F64-2205609999/20260613/ErrorLog_1758.gz"
      },
      {
        "seq": 165,
        "boot_epoch": "2026-06-13T17:56:57Z",
        "order_key": "2026-06-13T17:56:57Z#0000000165",
        "ts": "2026-06-13T17:58:12.431Z",
        "ts_device_local": "2026-06-13 23:28:12.431",
        "tz_source": "device_local",
        "device_id": "8C1F64-2205609999",
        "dn": "device=8C1F64-2205609999",
        "module": "FM",
        "stream": "errorlog",
        "message": "Critical alarm 0x16010400 raised, system reboot will be taken to recover it after 90s.",
        "severity": "critical",
        "class": "FAULT",
        "alarm_id": "0x16010400",
        "source_ref": "main/informer.c:307",
        "template_hash": "t_9f21c4",
        "match": "hit",
        "context_offset": 0,
        "hit_group": 2,
        "archive_file": "nanolink-logs/3f2a1c88/8C1F64-2205609999/20260613/ErrorLog_1758.gz"
      }
    ]
  },
  "provenance": [
    {
      "source": "device_log_index",
      "store": "postgres",
      "as_of": "2026-07-29T10:31:03Z",
      "coverage": { "from": "2026-04-30T00:00:00Z", "to": "2026-07-29T10:30:00Z" }
    },
    {
      "source": "nanolink-logs/3f2a1c88/8C1F64-2205609999/20260613/",
      "store": "object_storage",
      "as_of": "2026-06-13T18:06:00Z",
      "coverage": null
    }
  ],
  "freshness_s": 64,
  "next_actions": [
    {
      "tool": "get_active_alarms",
      "why": "0x16010400 declares RecoveryMechanism = System Reboot; check whether it is still active.",
      "args": { "device_id": "8C1F64-2205609999" }
    },
    {
      "tool": "get_device_timeline",
      "why": "Interleave these alarms with commands and config changes to rule out an actuation regression.",
      "args": { "device_id": "8C1F64-2205609999", "start": "2026-06-13T17:50:00Z", "end": "2026-06-13T18:10:00Z" }
    }
  ],
  "errors": []
}
```

Two lines are worth reading twice. `total_matched: 47` with `count: 5` and `truncated: true` tells
the agent it is looking at a sample, not the incident. And `next_actions` turns a log search into
the first step of a root-cause chain instead of a dead end.

The empty case is the same envelope with `result.kind: "empty"`, `count: 0`, `total_matched: 0`,
`data: {}`, `success: true`, `errors: []`, and a `message` saying so.

---

## 8. Implementation notes for the MCP side

1. **Build the envelope once.** One `envelope.py` module with `ok(...)` / `err(...)` / `preview(...)`
   builders. No tool hand-rolls a dict. A tool returning a bare string is a review rejection.
2. **Validate in tests, not at runtime.** Assert every tool's output against
   `mcp-envelope.schema.json` in a shared parametrised test over the tool registry, so a new tool
   cannot ship non-conforming.
3. **Return a JSON string.** MCP tools return text; serialise the envelope with `json.dumps` and no
   indentation. **Reply sizing (v1.1):** the ~8 KB figure is an advisory target, not a hard cap.
   `limit` bounds record count (default 50, hard cap 500); the server MAY additionally stop early
   on reply size, and when it does it sets `truncated: true`, `truncation_reason: "size_cap"`, and
   a valid `page.next_cursor` resuming exactly where the reply stopped. Whichever bound binds
   first governs; both are always reported, never silent. Expect the copilot orchestrator to
   request larger-but-bounded replies (a few hundred lean projected lines, sized to its model
   input budget) — honour `limit`, keep your own size guard, and let the cursor do the rest.
4. **`schema` bumps only on a breaking envelope change.** Adding an optional field is not breaking.
   Per-tool body changes bump `tool.contract_version`, not `schema`.
5. **Never put a raw upstream error body in `data`.** Map it to an error code plus a `hint`.

---

## 9. Open points — status as of 2026-08-10

1. **Retention boundary reporting. RESOLVED.** `truncation_reason: "retention_boundary"` with the
   real floor in `provenance[].coverage.from` is sufficient; no dedicated warning wanted. The
   copilot team confirmed the row floor requirement as **90 days** (matching the specced raw-line
   table), with older windows served from the re-parseable archive via `fetch_raw_log_window`.
2. **`correlation_id` minting. RESOLVED.** The **copilot orchestrator** mints it — one id per RCA
   session, sent on every tool call in that session. The MCP side echoes it verbatim and never
   mints its own when one is supplied. Related confirmation: `next_actions` stays, and its `args`
   must be machine-usable (directly passable to the named tool), never prose — the copilot agent
   loop executes them.
3. **Cursor stability across ingest. OPEN (accepted risk).** Cursors encode `(boot_epoch, seq)`; a
   late-arriving backlog file can insert lines *behind* an issued cursor. Acceptable for the
   current request/response RCA loop (a re-query picks them up); revisit only if the copilot ever
   streams.
