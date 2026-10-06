# Handover: MCP payload contract and the log/RCA data surface

**To:** copilot team · **From:** platform · **Date:** 2026-07-29 · **Updated:** 2026-08-10 (v1.1)
**Answers:** the A through G questionnaire (query contract, response contract, volume, retention,
device context, transport, categorization) plus the master payload request.

> **v1.1 (2026-08-10).** Every §9 open point is now RESOLVED (see §9, kept in place with its
> answers so the reasoning survives). Three contract deltas were agreed with the copilot team and
> are normative: **field projection** on every list tool, **reply sizing semantics** (the ~8 KB
> figure is advisory; `limit` and `size_cap` interplay defined), and **`fetch_raw_log_window` is
> bounded and paged — no bulk mode**. Details in §11; the master payload doc carries the same
> deltas in its §3/§6/§8. §12 registers the RCA incident fixture pack the copilot team needs for
> local testing before the parser exists. Device ids in examples use the anonymized serial
> convention (`2205609999`); the real capture identity lives only in `artifacts/real-data/`.

**Read alongside:**
- [`mcp-master-payload.md`](./mcp-master-payload.md): the master envelope, with a full worked example
- [`mcp-envelope.schema.json`](./mcp-envelope.schema.json): the same thing, machine-checkable
- [`../nanolink/femtocell_dashboard_data_contract.md`](../nanolink/femtocell_dashboard_data_contract.md): the evidence base every number below comes from
- [`../docs/cloudlynet-rearchitecture/epics/EPIC-8-copilot-mcp-layers.md`](../docs/cloudlynet-rearchitecture/epics/EPIC-8-copilot-mcp-layers.md): S0 (envelope) and S8 (observability/RCA), the stories that build this

---

## 0. The short version

1. **The master payload exists.** One envelope, every tool, every MCP server, every layer. The outer
   body is identical everywhere; the domain-specific part is `data`, discriminated by
   `result.data_type`. You were right that a universal *payload* is not achievable; the envelope does
   not attempt it. Spec + JSON Schema linked above, both validated.
2. **Every query parameter is optional.** Per instruction. A tool called with no arguments returns a
   bounded default, never a validation error. Parameters we accept but cannot honour are reported in
   `query.ignored` rather than rejected, so you can build against the full signature now and we can
   light up capability behind it.
3. **A through G are answered below with evidence**, not estimates. The source is a full-corpus scan
   of 15,907 `Log_*.gz` + 4 `ErrorLog_*.gz` + 5 continuous-logging rings over 14 days from one
   NybSys NanoLink device (ENB-N03002-B3, LTE Band 3, OUI 8C1F64), plus a 20,261-path TR-069 (CWMP)
   parameter-tree dump.
4. **One thing you must not design around: the log ingest pipeline does not exist yet.** Read §8
   before you plan a sprint. The contract is real and stable; the producer that fills it is not
   built, and today's watcher cannot even read the real file format. We would rather tell you now
   than have you build against empty tables.

**Scope note.** For CloudlyNet Lite the "customer's log system" is not a third-party server: NanoLink
femtocells push logs to us over FTP and CloudlyNet parses them, so the query and response contracts
are ours to define, which is why we can answer A and B completely. If a customer arrives with their
own log server, it becomes an adapter behind the same tool signatures and the same envelope.

---

## 1. (A) Queryable parameters, the query contract

`search_device_logs`. **Every parameter is optional.** Zero-argument call returns the last hour
across the tenant's devices, capped at `limit`.

| Param | Type | Values / notes | Default when omitted |
|---|---|---|---|
| `device_id` | string | Device identity; omit for tenant-wide | all devices in tenant |
| `dn` | string | Canonical DN, `device=<cwmp_id>` | derived from `device_id` |
| `start` / `end` | string | RFC 3339 UTC, or relative (`-2h`, `-15m`) | `start = -1h`, `end = now` |
| `q` | string | Substring match on the message | no message filter |
| `regex` | string | Accepted; downgraded to substring where unsupported, reported in `query.ignored` | none |
| `module` | string[] | `TR69`, `SON`, `SCTP`, `FM`, `SCM`, `L1_L2_Wrapper`, … | all modules |
| `severity` | string[] | `critical`, `major`, `minor`, `warning`, `indeterminate`, `cleared`, `info` | all |
| `alarm_id` | string[] | Vendor hex, e.g. `0x16010400` | all |
| `class` | string[] | `FAULT`, `STATE`, `STATE_CM`, `PM_ISH`, `OTHER` | all |
| `stream` | string[] | `log`, `errorlog`, `contlog`, `devicelog` | `["log","errorlog"]` |
| `context_lines` | int | **The neighbours option.** N lines before and after each hit | `0` |
| `limit` | int | Hard cap 500 | `50` |
| `cursor` | string | Opaque base64 over `(boot_epoch, seq)` | none |
| `sort` | enum | `order_key_asc` \| `order_key_desc` | `order_key_asc` |
| `include_raw` | bool | Attach the verbatim unparsed line | `false` |
| `fields` | string[] | **v1.1 projection.** Return only the named per-item fields; unknown names reported in `query.ignored` (`unknown_field`), never rejected. Lean RCA set: `order_key, message, module, severity, alarm_id, match` (~150 B/record vs ~700 B full) | full record |

Direct answers to your sub-questions:

- **Time range:** yes, `start` / `end`, both optional, absolute or relative.
- **Keyword / substring / regex:** substring yes (`q`). Regex is accepted at the signature but is
  honoured only where the backing store supports it; downgrades are reported, never silent.
- **Structured filters:** yes for device, module/subsystem, severity, alarm id, and FCAPS class.
- **Neighbours:** yes, `context_lines`. See §2 for how hits and context are marked.
- **Limit, pagination, sort:** yes, cursor-based. Cursors encode a stable sort key, not an offset,
  so a concurrent ingest cannot shift your page.

The same optionality rule holds for every other tool in the layer. `device_id` is the only parameter
that is ever required, and only on `get_device_timeline` and `fetch_raw_log_window`, where a
tenant-wide answer would be unbounded and meaningless.

---

## 2. (B) Example return payload, the response contract

Full worked example, single hit and many hits, in
[`mcp-master-payload.md` §7](./mcp-master-payload.md). The empty case is the same envelope with
`result.kind: "empty"`, `count: 0`, `success: true`. Per returned line:

| Field | Example | Notes |
|---|---|---|
| `ts` | `2026-06-13T17:58:12.431Z` | UTC, normalised. Source is device-local; see below |
| `ts_device_local` | `2026-06-13 23:28:12.431` | Verbatim from the line, `YYYY-MM-DD HH:MM:SS.mmm` |
| `tz_source` | `device_local` | The device does not stamp a zone; we record what we know |
| `seq` | `165` | Device's 10-digit sequence, the true order key |
| `boot_epoch` | `2026-06-13T17:56:57Z` | Timestamp of the `seq = 0` power-on line |
| `order_key` | `2026-06-13T17:56:57Z#0000000165` | **Sort on this** |
| `device_id`, `dn` | `8C1F64-2205609999` | |
| `module` | `FM` | The `[MODULE]` tag |
| `stream` | `errorlog` | `log` \| `errorlog` \| `contlog` \| `devicelog` |
| `message` | `Critical alarm 0x16010400 raised, …` | Raw message text |
| `severity` | `critical` | From the device's own alarm catalogue |
| `class` | `FAULT` | FCAPS-ish class, see §7 |
| `alarm_id` | `0x16010400` | `null` when not an alarm line |
| `source_ref` | `main/informer.c:307` | Vendor file:line, carried in the line grammar |
| `template_hash` | `t_9f21c4` | Drain-style template id for aggregation |
| `match` | `hit` \| `context` | **Hit vs neighbour marking** |
| `context_offset` | `0`, `-1`, `+2` | Position relative to its hit |
| `hit_group` | `2` | Groups a hit with its own context lines |
| `archive_file` | `nanolink-logs/…/ErrorLog_1758.gz` | Provenance to the raw object |

**Overall shape:** JSON, and a **flat list**, not nested `hit + its context`. Nesting duplicates
lines whenever two hits fall within one context window, and with `context_lines=2` on a burst of
alarms that is the common case, not the edge case. Flat plus `hit_group` renders either way and
never double-counts.

**The order key deserves a paragraph.** Do not sort by timestamp. The device emits bursts inside a
single millisecond, so `ts` does not totally order the stream. Its own 10-digit sequence does, but it
resets to 0 at reboot, observed mid-file: `ErrorLog_1758` runs to seq 165, reboots, resumes at 79.
`order_key = "{boot_epoch}#{seq:010d}"` sorts lexicographically into true stream order across
reboots. This is also the ingest dedup key, so it is stable by construction.

**On correlation ids:** the vendor format carries no per-line request or session id, so we cannot
promise one. What you can correlate on today is `(boot_epoch, seq)` for ordering and adjacency,
`alarm_id` for grouping a fault's occurrences, and the platform's own `command_id` where a log line
follows a TR-069 (CWMP) write we issued. At the MCP layer, `context.correlation_id` in the envelope
ties a multi-tool RCA session together; our recommendation is that the copilot orchestrator mints it.

---

## 3. (C) Volume and limits

Measured on one device over 14 days, extrapolated to 1,000 devices:

| Quantity | 1 device | 1,000 devices |
|---|---|---|
| Files/day | 1,439 to 1,440 (~510 B gzipped each) | ~1.44M |
| Lines/day | ~12,500 | ~12.5M |
| Raw text/day | ~1.41 MB | ~1.4 GB |
| Gzipped/day | ~0.73 MB | ~0.73 GB (~267 GB/yr) |
| Lines/yr if every line became a row | ~4.56M | ~4.6B |
| **Extracted** events + alarms only | ~27 fault + ~11 alarm rows/day | ~38k rows/day |
| Reduction, extract vs full | **463x** | 463x |

Read those last two rows carefully, because they drive the design: 76.8% of log lines are `[TR69]`
CWMP protocol chatter with near-zero analytic value. We store the extracted rows in Postgres and keep
the raw `.gz` verbatim in object storage, rather than making every line a row.

**Worst case for a broad query:** a 24-hour window on one device is ~12,500 lines, and an
error-state window is roughly 5x denser than a quiet one (42.5 lines per ErrorLog file versus 8.68
per Log file). This is exactly why `limit` defaults to 50 with a hard cap of 500 and why
`result.truncated` plus `total_matched` are mandatory: a broad RCA query will routinely match far
more than it returns, and the agent has to know that.

**Response size target:** ~8 KB per tool response as an **advisory default, not a hard cap**
(v1.1, §11.2): `limit` bounds record count, a server-side size guard may stop a reply early with
`truncation_reason: "size_cap"` + a resumable cursor, and the copilot orchestrator self-sizes
larger-but-bounded replies of lean projected lines. Rate limits and latency SLOs: sizing basis in
§9.4; firm p95 arrives after the copilot team times their fixture.

---

## 4. (D) Retention

Two tiers, and the ceiling on RCA is the archive, not the database.

| Tier | What | Where | Retention |
|---|---|---|---|
| Extracted rows | alarms, lifecycle events, boot-scoped PM samples | Postgres, monthly partitions | policy-set; the optional raw-line table is specced at 90 days |
| Raw archives | the verbatim `.gz` files | MinIO/S3, key `nanolink-logs/{tenant}/{cwmp_id}/{yyyymmdd}/{filename}` | long-horizon, fully re-parseable |

So a query reaching past the Postgres floor is not a dead end: `fetch_raw_log_window` re-reads the
archived window on demand. When a query's `start` precedes the row floor we return
`truncation_reason: "retention_boundary"` and put the real floor in `provenance[].coverage.from`, so
you can tell "nothing happened then" from "we do not have that in rows any more".

---

## 5. (E) Device and context info

Yes, separate calls, all in the Actuation domain (EPIC-8 S5), all read-only:

| Tool | Returns |
|---|---|
| `list_devices`, `list_edges` | Inventory from the 30s heartbeat: `cwmp_id`, serial, product class, software version, last inform, IPs, op/RF state |
| `get_device_config` | The curated snapshot of the **24 managed TR-069 (CWMP) parameters** (23 writable; MaxTxPower is read-only), refreshed every 5 min and after each command read-back |
| `get_device_health` | Current health state |
| `get_device_kpis` | PM counters, tiered 30s / 60s / 5min |
| `get_command_status` | State of a TR-069 (CWMP) write we issued |
| `list_device_recommendations` | Pending optimization recommendations |

**Neighbours and topology:** the device exposes a NeighborList in its parameter tree, but it is
**read-only** and not currently polled into a curated surface. Per-field detail in
`../nanolink/fields_cm.csv`. Treat topology as available-on-request, not available-today.

---

## 6. (F) Access and transport

- **Exposure:** an **MCP server**. FastMCP over SSE, host port **8082** (container port 8080),
  service `copilot-mcp-server`. One server for all layers, with per-domain tool modules; the decision
  and its rationale are frozen in the EPIC-8 header.
- **Auth:** `Authorization: Bearer <JWT>` on the MCP connection. Tenant is derived from the
  `custom:tenant_id` claim, and is **never** an LLM-visible tool parameter.
- **Enforcement:** the MCP server is **not** an auth authority. It decodes the token without
  verifying it, purely to build tenant-scoped URLs, and forwards it. Every call goes through the
  gateway (`http://gateway:8080`), which verifies and enforces. A forged tenant claim dies at the
  gateway. Do not add local verification: a second auth authority will drift from the first.
- **Today's state:** this threading is **broken and being fixed** in EPIC-8 S1. Right now the
  standalone server builds its client with no token, and four tools take `tenant_id` as an
  LLM-visible parameter defaulting to a hardcoded literal. Do not build against the current
  behaviour.

---

## 7. (G) Existing categorization

Substantially yes, and richer than most vendor formats. Three independent classifications:

1. **Module tag.** Every line carries `[MODULE]`: `TR69`, `SON`, `SCTP`, `FM`, `SCM`,
   `L1_L2_Wrapper` and others. Note that `SCTP` and `L1_L2_Wrapper` lines appear **only** in
   ErrorLogs, which is why we parse both file types through one pipeline rather than treating
   ErrorLog as a subset.
2. **Alarm identity and severity.** Alarm lines are structured:
   `[MODULE] Alarm Logged|Report, id: 0xHHHHHHHH file: <src> line: <n> detail: <text>`. Seven distinct
   hex ids observed across 153 alarm lines. Better still, the device publishes its **own 15-entry
   supported-alarm catalogue** with declared severity, `RecoveryMechanism` and `ClearingMechanism`,
   so we can drive alarm lifecycle from the vendor's own policy rather than guessing. Example:
   `0x16010400` declares `RecoveryMechanism = System Reboot`, which is how we know a reboot was
   self-healing rather than an actuation regression.
3. **FCAPS class.** Corrected full-corpus totals: STATE-CM 105,756 · STATE 32,123 · FAULT 378 ·
   PM-ish 28. Note the last number: **PM does not come from the logs.** Fourteen days produced 28
   boot-scoped PM-ish lines and zero RSRP/RSRQ/SINR/CQI/PRB/RRC/throughput counters. PM lives in the
   TR-069 (CWMP) tree, 11,145 of 20,261 paths. If you plan a PM query, point it at `get_device_kpis`,
   never at log search.

**One caveat that matters.** All of this classification exists **in the device's output**. The
platform does not extract it yet, because the parser is not built. See §8.

Alarms, once extracted, are **lifecycle records, not log lines**: `fm_alarms` collapses flap and
backoff series, so the 31-line `0x18020400` ACS backoff storm becomes one active alarm with
`occurrence_count: 31`. A tool that hands you 31 alarms would be wrong.

---

## 8. What does not exist yet, stated plainly

The response contract is stable and you can build against it. The **producer is not built**:

- No story in any epic owns the `Log_*.gz` / `ErrorLog_*.gz` parser. The strategy is fully specified
  (`../nanolink/femtocell_dashboard_data_contract.md` §2) and assigned to nobody. We have proposed
  **E1.S9** to fix that (`../upgrade_plans/AUDIT-2026-07-29.md` §4).
- Today's FTP watcher **cannot read the real files**: it consumes only `*.tgz`, while real devices
  upload single-gzip `Log_*.gz` / `ErrorLog_*.gz`. It also reads the module from the archive member
  name rather than the `[MODULE]` tag, and stamps events with parse time rather than line time.
- FaultMgmt alarms are folded into a single health enum and clobbered within 30 seconds by the
  heartbeat recompute. They are never persisted.

**Therefore EPIC-8 S8 ships in two tranches:**

| Tranche | Tools | Status |
|---|---|---|
| **A** | `get_active_alarms`, `get_alarm_history`, `search_device_events`, `get_device_timeline` | Buildable now, on surfaces E1.S1 and E1.S5 do deliver |
| **B** | `search_device_logs`, `fetch_raw_log_window` | **Not registered** until the pipeline exists, behind a capability probe |

The capability probe is deliberate. An unregistered tool lets the copilot say "not built yet". A
registered tool over an empty table returns zero results, and zero results read to a customer as
"your network is quiet". That failure mode is worse than the missing feature.

---

## 9. What we needed from you — RESOLVED 2026-08-10

Kept in place with the copilot team's answers, because the answers are now contract.

1. **Confirm the envelope.** Confirmed, with the §11 deltas (projection, sizing, bounded raw
   window). No structural pushback; the envelope is frozen as specced.
2. **Who mints `correlation_id`?** **The copilot orchestrator.** It creates one id per RCA session
   and sends it on every tool call in that session. The MCP side echoes it verbatim in
   `context.correlation_id` and must never mint its own when one is supplied.
3. **Is `next_actions` useful?** **Yes — keep it.** The copilot agent loop reads it to choose the
   next tool call. Binding consequence for implementers: `args` must be machine-usable (valid
   arguments for the named tool, ready to pass through), never prose. A `next_actions` entry an
   agent cannot execute verbatim is a defect.
4. **Rate limits and latency SLOs.** No firm p95 yet; the copilot team will send one after timing
   against their fixture (§12). Sizing basis until then, from their side: the RCA loop is bounded
   at **~8 tool calls and 6 reasoning turns per session**, so one session makes a small, bounded
   number of calls — size for a **few concurrent RCA sessions per tenant**. Expect their calls to
   ask for **larger-but-bounded replies than the 8 KB default**: they self-size dynamically up to a
   ceiling derived from the model's input budget, on the order of a **few hundred lean
   (projected) lines per reply**, never a huge blob (see §11.2).
5. **Retention policy sign-off.** **RCA must reach back 90 days in rows**, matching the specced
   raw-line table. Older windows come from the re-parseable archive on demand via
   `fetch_raw_log_window`. The 90-day Postgres floor is now a requirement, not a proposal.

---

## 9b. What the server logs when your agent connects (added 2026-08-27)

Server-side tracing landed on `:8082`. It matters to you because **nothing in-house connects to that
port** — when your agent talks to it, the container log is the only record of what happened, on
either side. Ask us for it by session id and we can answer without guessing.

One line per call, from a real run:

```
mcp_call tool=get_active_alarms outcome=ok ms=290.6 rid=3 sid=1683a6ad tsid=c926940b
         tenant=00000000 role=cloudly_admin xcorr=rca-7781 args=limit
         kind=collection n=5 trunc=limit cursor=yes ign=1 bytes=2923
         up=1 up_att=1 up_ms=274.7 up_status=200
```

Four things in there are yours:

- **`xcorr` is your `X-Correlation-ID`, echoed verbatim.** Mint one per RCA session, send it on the
  connection, and every call you made is one `grep` away in our log. We never mint our own.
- **`up_ms` against `ms` tells you whose latency it is.** `ms=290.6 up_ms=274.7` means the gateway
  took 275ms of the 291ms and our tool did ~16ms of work. Nothing to raise with us.
- **`up_att > up` means we retried upstream.** `up=1 up_att=3` is a flaky gateway, not a slow tool.
  That distinction was previously invisible even to us — see the note below.
- **`trunc=` and `ign=` explain a short reply before you have to ask.** `trunc=limit cursor=yes`
  means there is more and you have a cursor; `ign=1` means a parameter was accepted but not
  honoured, and the envelope's `query.ignored[]` says which and why.

`outcome` is one of `ok` `empty` `error` `preview` `partial` `raised`. **`empty` is a finding, not a
failure**: the tool worked and the platform holds no matching rows. Treat it as evidence of absence,
not as an error to retry.

A refusal looks like this — note there are **no `up=` fields at all**, which is the proof that an
unauthenticated call never reaches the gateway:

```
mcp_call tool=get_active_alarms outcome=error ms=0.6 rid=3 sid=a740b261 tsid=dee4a177
         tenant=- role=- xcorr=- args=limit kind=error n=0 bytes=736
         code=AUTH_CONTEXT_MISSING retryable=False
```

**What we do not log, by design:** response bodies, at any verbosity. If you need to see what a tool
actually returned, capture it your side — the trace reports the shape (`kind`, `n`, `bytes`,
`trunc`) and never the contents.

**Two defects this work turned up that affected you:**

1. **Four of the 34 tools were dead on the wire** in the container — `compare_rapp_policies`,
   `get_inference_report`, `compare_inference_models` and `query_existing_baselines` returned
   `INTERNAL_ERROR` on first call because a cache lookup needed backend settings the MCP container
   does not have. Fixed; they now compute directly, uncached.
2. **The gateway client's retry had never fired.** The policy matched an exception type that the
   client's own error handling had already converted, so three attempts were always one. Fixed, and
   scoped to idempotent methods — a POST that mutates a device is never replayed.

## 10. Where the work lives

| Deliverable | Location |
|---|---|
| Master envelope spec + worked example | `artifacts/copilot/mcp-master-payload.md` |
| JSON Schema (validated; rejects malformed envelopes) | `artifacts/copilot/mcp-envelope.schema.json` |
| Envelope implementation story | EPIC-8 **S0** |
| Auth and tenant threading fix | EPIC-8 **S1** |
| Observability/RCA tools | EPIC-8 **S8** (tranche A now, B gated) |
| Device-plane read tools | EPIC-8 **S5** |
| Log grammar, alarm catalogue, volumes, DDL | `artifacts/nanolink/femtocell_dashboard_data_contract.md` |
| Field-level inventories | `artifacts/nanolink/fields_pm.csv`, `fields_cm.csv`, `fields_fm.csv` |
| Plan audit, including the pipeline gap | `artifacts/upgrade_plans/AUDIT-2026-07-29.md` |

Every EPIC-8 story carries a self-contained coding-agent prompt. Hand the S0 block to an agent and it
can start today without further context.

---

## 11. Contract deltas agreed 2026-08-10 (normative)

Three changes, all driven by the copilot RCA loop's reply-sizing math. The master payload doc
carries the same rules in its §3 (query rules), §6.1/§6.6 (bodies) and §8 (implementation notes);
this section is the decision record.

### 11.1 Field projection (`fields`) — every list tool

A measured `device_log_lines` record is ~700 B, of which ~85% is repeated metadata (seq,
boot_epoch, order_key, ids, flags) and ~15% is the message text. At ~700 B/record an 8 KB reply
carries ~10–12 lines; the copilot RCA loop pages through incidents, so that per-record overhead
multiplies into round-trips and Groq rate-limit pressure.

**Decision:** every list tool accepts an optional `fields: string[]` parameter naming the per-item
fields to return.

- Omitted → the full record (backwards compatible).
- Unknown field names are not errors: honoured where possible, and each unknown name is reported in
  `query.ignored` with reason `unknown_field`. Never reject the call.
- `query.echo.fields` always shows the projection actually applied.
- The recommended lean set for RCA paging, sized at ~150 B/record (~50 lines per 8 KB reply, ~5x
  the full-record density): `["order_key", "message", "module", "severity", "alarm_id", "match"]`
  — `order_key` doubles as the compact line id (it is unique per line and cursor-compatible).
- Projection changes `data.items[*]` shape only. The envelope (`result`, `query`, `provenance`,
  `next_actions`, `errors`) is never projected away.

### 11.2 Reply sizing: ~8 KB is advisory; `limit` and `size_cap` interplay

The ~8 KB figure in §3 is a **target, not a hard cap**. Semantics, agreed:

- `limit` bounds the record count (default 50, hard cap 500). The server MAY additionally stop
  early on reply size; when it does, `result.truncated: true` with
  `truncation_reason: "size_cap"` and a valid `page.next_cursor` so the caller resumes exactly
  where the reply stopped. Whichever bound binds first governs; both are always reported.
- The copilot orchestrator self-sizes: it requests larger-but-bounded replies (a few hundred lean
  lines with §11.1 projection), derived from its model input budget. The platform does not need to
  guess their budget — it needs to honour `limit`, apply its own size guard, and never truncate
  silently.
- Consequence for rate-limit sizing: fewer, larger calls — a handful per RCA session (§9.4), not a
  stream of 8 KB pages.

### 11.3 `fetch_raw_log_window` is bounded and paged — no bulk mode

**Decision (copilot-requested, platform-accepted):** the raw-window escape hatch returns a
**capped window, paged with `next_cursor`, in the same envelope, honouring the same `fields`
projection**. There is no bulk/streaming variant and none is planned; a caller that needs a longer
window pages through it.

- This decision let the copilot team drop an entire compression / reference-tag / trace-back layer
  on their side. Do not reintroduce a bulk mode "helpfully": their design now assumes bounded
  replies, and an unbounded blob would regress their loop.
- Signature stays `device_id` (required), `at` (required), `window_s?` — with `window_s` capped
  server-side (cap reported via `query.ignored` reason `capped` when a larger window is asked
  for), plus `cursor?`, `fields?[]`, `limit?`.
- Body: `result.data_type: "raw_log_lines"` — same per-line shape as `device_log_lines` where
  parseable, with unparseable lines carried as `{order_key?, raw}` so nothing is hidden. Spec in
  the master payload doc §6.6.

---

## 12. RCA incident fixture pack (requested 2026-08-10; item 2 delivered 2026-08-13)

The copilot team can test their LLM RCA loop end-to-end before the log pipeline exists, if we hand
them a fixture. Registered here so it is owned, not forgotten; sized as a platform deliverable
(EPIC-8 **S9** carries the story and acceptance criteria).

**Status, 2026-08-13.** Delivered at [`fixtures/`](./fixtures/) — start at its
[`README.md`](./fixtures/README.md).

| # | Item | Status | Where |
|---|---|---|---|
| 1 | Complete raw logs | **pending platform owner** — real capture, delivered in place or as an approved anonymised copy | pointers in [`fixtures/context/DELIVERY-item1-item3.md`](./fixtures/context/DELIVERY-item1-item3.md) |
| 2 | Hand-built envelope replies | **delivered** — 14 samples across the 5 tools, every one schema-valid | `fixtures/<tool>/*.json` |
| 3 | Incident context | **partly delivered** — the 15-entry alarm catalogue, the vendor policy overlay and the 24-parameter config snapshot are in; the real command history for the window is pending with item 1 | `fixtures/context/supported-alarm-catalogue.json`, `fixtures/get_device_config/01-snapshot-24-params.json` |

Item 2 covers the five variants the story asks for: neighbour context, the v1.1 lean projection with
an `unknown_field` report, `size_cap` truncation with a resumable cursor, an `empty` finding, and a
`NOT_FOUND` error. It also carries the reboot boundary, where `seq` resets and only `order_key`
still orders the stream, and the 31-line ACS backoff series collapsed into one alarm with
`occurrence_count: 31`.

Two things came out of building it that the MCP implementation should settle, both recorded in the
fixtures README: §7 of the payload spec declares `count: 5` while showing 3 items (the fixtures are
self-consistent instead), and `get_device_timeline` needs a decided ordering axis because
platform-side records have no device `seq` and therefore no real `order_key`. Measured projection
gain on this incident is **~3.1x**, not the ~5x the spec estimates, because alarm lines carry the
full `Alarm Logged, id: … file: … line: … detail: …` grammar; size RCA windows off ~200 B per lean
line.

| # | Item | Contents | Confidentiality handling |
|---|---|---|---|
| 1 | Complete raw logs, one device, one real incident window | ALL streams, unfiltered: `Log_*.gz`, `ErrorLog_*.gz`, and the continuous-logging ring — not the edge-forwarded subset. The window: the worked-example reboot incident (SCTP peer failure → S1 setup failure → FM critical `0x16010400` → self-reboot). | Source is the real capture under `artifacts/real-data/` (gitignored, never committed). Delivery is **in place, read-only** there, or as an **anonymized** copy (serial → `2205609999`, MAC host parts → synthetic) if it must leave that directory. The anonymization call on any derived copy is the platform owner's, per repo policy. |
| 2 | Hand-built contract-envelope JSON replies over that incident | 2–3 samples each for `search_device_logs`, `get_device_timeline`, `get_active_alarms`, `get_device_config`, `get_command_status` — real `order_key` / `template_hash` / `class` / `match` / `hit_group` values derived from item 1, so the copilot's envelope adapters validate against the real thing, not a guess. | Committed under `artifacts/copilot/fixtures/` **only in anonymized form**; must validate against `mcp-envelope.schema.json`. |
| 3 | Incident context | The device's 15-entry supported-alarm catalogue, one 24-parameter config snapshot, and the command history for the window. | Catalogue and snapshot shapes are already public in `../nanolink/`; the command history for the real window follows the same anonymization rule as item 1. |

Priority per the copilot team: items 1 + 3 unblock most of their work (they will parse item 1 and
hand-build envelopes); item 2, even at 2–3 samples per tool, de-risks their envelope reading. The
labels they rebuild from item 1 become their golden set, which is one more reason item 1 must be
the complete stream set, not the extract.
