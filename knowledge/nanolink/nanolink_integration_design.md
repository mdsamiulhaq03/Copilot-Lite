# CloudlyNet ⇄ NybSys NanoLink Integration — Implementation Handover (Merged)

**Version:** 2.0 (2026-06-10) — merges the CloudlyNet implementation handover v1.0 with the Lead Engineer's *CloudlyNet API Plan*.
**Audience:** Backend coding agent + Frontend coding agent (separate sections below) + GO Agent author.
**Target microservice:** `maveric_platform_smo_sim` (all new platform code), plus one minimal Gateway proxy-route addition and the standalone **GO Agent** repo for the Edge Device.

> **What merged in from the API Plan:** the unified **command table** transport primitive and its delivery semantics, the explicit **§4 SLAs** as acceptance criteria, the **T1/T2/T3 telemetry tiering**, the agent-side **SQLite offline buffer**, and the **enhancement ladder** (long-poll → SSE → gRPC) recorded as the agreed future evolution.
> **What we kept from the base handover:** **Edge-Key auth** (not mTLS), the **10 s poll interval**, the enrollment-token ("hash") flow, the managed-parameter catalogue with validators, the self-optimisation policy/model, the FTP-log rule engine, and the full GO Agent + frontend implementations.

---

## 0. Scope & Constraints (read first)

| # | Constraint | Consequence in this design |
|---|-----------|---------------------------|
| C1 | REST-only between GO Agent and CloudlyNet. No gRPC, NATS, websockets, or new public Kafka topics. | GO Agent **polls** CloudlyNet over HTTPS every **10 s** for commands, and **pushes** telemetry/heartbeats via plain REST POSTs. The richer transports are explicitly deferred — see the Enhancement Ladder note in §7. |
| C2 | All platform-side implementation in **SMO-SIM**. | New routers mount under the existing feature-flag-gated `/custom` parent (`/v1/tenants/{tenant_id}/custom/nybsys/**`). Gateway already proxies `/custom/**` → SMO-SIM with `X-API-Key` injection. The agent endpoints need one new gateway group (§A.6). |
| C3 | GO Agent runs on the Edge Device only (NybSys mandate: no software on the NanoLink — firmware upgrades wipe on-device files). | All device interaction is via the agent's own in-agent TR-069/CWMP ACS on `:7547` (replacing GenieACS — the NanoLink dials the agent directly) and the vsftpd FTP drop (`/srv/nybsys-ftp/nybsysftp/uploads/`) on the Edge Device. |
| C4 | One Edge Device ↔ many NanoLinks. One Tenant ↔ many Edge Devices. | `edge_devices` and `nanolink_devices` tables, both tenant-scoped under RLS. |
| C5 | Respect existing platform conventions. | Response envelope `{success, timestamp, message, data, errors}`; RLS via `set_config('app.current_tenant', …)`; canonical error codes; `X-Request-ID` middleware; Mongo `application_logs`/`error_logs`. |
| C6 | **NAT reminder.** The edge is behind NAT; the cloud can never call in. | *Every* cross-boundary arrow is agent-initiated: telemetry POSTs go out, commands are *fetched* by the poll. Nothing is pushed inward. |

---

## 1. SLAs — product requirements & acceptance criteria

These come from the API Plan §4 and are now **binding acceptance criteria** for this build. Each is met by the plain 10 s polling skeleton — no richer transport is required to hit them.

| SLA | Target | Met because |
|-----|--------|-------------|
| KPI freshness | < 90 s | Telemetry is POSTed immediately on capture (T1 every 30 s); lag ≈ one network round-trip, well under 90 s. |
| Config round-trip | < 30 s | A 10 s poll + CWMP apply + read-back lands comfortably under 30 s. |
| Self-Heal MTTR | < 90 s | Alarm POST → cloud decides → `heal` command picked up on next poll (≤10 s) → apply + verify ≤ 30 s. |

Test these explicitly (§C.2). If empty-poll volume or command latency later becomes a problem, the Enhancement Ladder (§7) swaps transport **without touching endpoints or payloads**.

---

## 2. Architecture Overview

```text
┌────────────────────────────── CloudlyNet (cloud) ──────────────────────────────┐
│                                                                                │
│  Next.js Frontend ──► Gateway (Go/Gin)                                         │
│      │                   │  /v1/tenants/{t}/custom/nybsys/**  (Cognito JWT)    │
│      │                   │  /v1/agent/**                      (Edge-Key auth)  │
│      │                   ▼                                                     │
│      │             SMO-SIM (FastAPI)                                           │
│      │               ├── nybsys_edge_router.py    (operator: CRUD/commands)    │
│      │               ├── nybsys_agent_router.py   (agent: poll/telemetry/ack)  │
│      │               ├── services/nybsys/command_service.py  (the command tbl) │
│      │               ├── services/nybsys/ingest_service.py   (telemetry)       │
│      │               ├── services/nybsys/event_parser.py     (FTP log → events)│
│      │               └── services/nybsys/self_optimizer.py   (policy → cmds)   │
│      │                          │                                              │
│      │                  Postgres (RLS) + Mongo (logs) + S3 (raw log archive)   │
└──────┼─────────────────────────────────────────────────────────────────────────┘
       │ HTTPS REST only — agent-initiated (poll every 10 s / push telemetry)
       ▼
┌──────────────────────────── Edge Device (192.168.8.100) ───────────────────────┐
│  GO Agent (single static binary, systemd) + local SQLite offline buffer        │
│    ├── cloud client   (poll commands; push telemetry/heartbeat; ack)           │
│    ├── in-agent CWMP ACS :7547  (Inform/ATC, SPV/GPV/GPN/Reboot, conn-req)     │
│    └── FTP log watcher      → /srv/nybsys-ftp/nybsysftp/uploads/               │
│                                                                                │
│  agent hosts the CWMP ACS on :7547 (GenieACS removed)   vsftpd (FTP :21)       │
└──────────────┬──────────────────────────────────────────────┬──────────────────┘
               │ TR-069/CWMP (device dials in; conn-req :30005)│ FTP .tgz every 60 s
               ▼                                               │
        NybSys NanoLink 2307  (admin LAN 192.168.8.248) ───────┘
        cwmp_id: 8C1F64-ENB%2DN03002%2DB3-2205609999
```

**Two callers, two APIs, one shared object.** The **GO Agent** (a machine) hits the **Agent API** (push telemetry up, poll commands down). **Operators / dashboard / optimiser** (humans + policy) hit the **Operator API** (create commands, read telemetry). They meet at one shared object: the **`commands` table** — a plain Postgres table, *not* a broker.

---

## 3. Design Decisions (locked)

### 3.1 Edge Device enrollment ("the hash") — Edge-Key

We use the **Edge-Key** approach (decision: not mTLS).

1. Tenant admin clicks **Add Edge Device** → `POST /v1/tenants/{t}/custom/nybsys/edge-devices`.
2. SMO-SIM creates the row, generates a random 32-byte secret, stores only `sha256(secret)`, and returns — **once, never again** — an *enrollment token*:

```text
token = base64url( JSON{
  "v": 1,
  "tenant_id": "<uuid>",
  "edge_id":   "<uuid>",
  "base_url":  "https://api.cloudlynet.example.com",   // exact URL
  "api_key":   "<edge_id>.<secret-hex>"                // composite Edge Key
})
```

3. Operator pastes the token into the GO Agent config (`/etc/cloudlynet-agent/agent.yaml`, key `enrollment_token`) and restarts the agent.
4. On boot the agent decodes the token, calls `POST {base_url}/v1/agent/register` with header `X-Edge-Key: <edge_id>.<secret-hex>`; SMO-SIM verifies the hash, flips `edge_devices.status` → `online`, records `agent_version`.
5. Every subsequent agent call carries `X-Edge-Key`. Rotation = dashboard "Regenerate key" → old hash replaced → token re-pasted + agent restarted.

> Auth contrast with the API Plan: the Plan specified mTLS per PRD §14.3. We are deliberately using Edge-Key for this build (simpler termination, no per-agent cert lifecycle, fits the single-gateway proxy). If the PRD mTLS commitment is later enforced, the token simply carries/bootstraps a client cert instead of a bearer secret — the enrollment UX and the rest of this design are unchanged.

### 3.2 The `commands` table & delivery semantics (merged transport primitive)

The "queue" is a Postgres table; the command endpoints are CRUD on it — the same status-tracked pattern as smo-sim's `nybsys_uploads`. A single polymorphic table carries **all** southbound work:

```text
commands(id, tenant_id, device_id, edge_id, type, payload jsonb, origin,
         status, result jsonb, attempts, prev_values jsonb,
         dispatched_at, acked_at, created_by, created_at, updated_at)

type:   configure | heal | optimise | query | reboot
status: pending ─▶ dispatched ─▶ applied | failed   (─▶ pending again on lease timeout)
```

**Delivery model — at-least-once + idempotent apply.** Exactly-once over an unreliable link is impractical; we make redelivery *safe* instead, via three mechanisms (the first two are essential for the PoC; the third may start as a startup sweep):

1. **Claim-on-fetch (poll)** — one atomic statement fetches *and* claims, so two overlapping polls can never hand out the same row:

```sql
UPDATE commands SET status='dispatched', dispatched_at=now(), attempts=attempts+1
WHERE id IN (
  SELECT id FROM commands
  WHERE edge_id = :e AND status = 'pending'
  ORDER BY created_at
  FOR UPDATE SKIP LOCKED LIMIT 20)
RETURNING id, device_id, type, payload;
```

2. **Idempotent apply (agent side)** — the agent keys on `command_id`; if it has already applied that id (tracked in its local **SQLite buffer**, §A.7.3), it **re-acks without re-applying**. This makes redelivery safe even for non-idempotent ops like `reboot`.

3. **Lease reclaim (crash safety)** — a `dispatched` row with no ack after a timeout returns to `pending`; after `max_attempts` it becomes `failed` (dead-letter) so a poison command can't loop forever. Same idea as smo-sim's `reset_stale_*` sweep — reuse it.

```sql
UPDATE commands SET status='pending'
WHERE status='dispatched' AND dispatched_at < now() - interval '60 seconds'
  AND attempts < :max;
```

**Ack:** `UPDATE … SET status=:status, result=:r, acked_at=now() WHERE id=:id AND status='dispatched'`.
**Create idempotency (optional):** accept `Idempotency-Key` on command-create so a retried create doesn't enqueue a duplicate.

### 3.3 Config edit pipeline (dashboard → device)

```text
UI edit → POST .../devices/{id}/commands  (type=configure, payload.writes[], status=pending)
  → agent GET /v1/agent/poll claims it    (status=dispatched, dispatched_at)
  → agent: in-agent ACS SetParameterValues (+ optional connection request)
  → CWMP session applies; agent reads back via GetParameterValues until the expected values match or verification times out
  → POST /v1/agent/commands/{id}/ack      (status=applied|failed, readback in result)
  → optional auto-rollback command if verification mismatches (see §6 guardrails)
```

A `configure` command's `payload` is validated server-side against the managed-parameter catalogue (§A.2) before it is written `pending`. `prev_values` is captured at create time for rollback.

### 3.4 Telemetry tiering (adopted from the API Plan §5.1)

Northbound telemetry is **fire-and-forget**, batched, and tiered. The agent reads each tier at its own cadence from its in-agent ACS parameter cache (refreshed by queued GPV reads on each device session) and POSTs to `/v1/agent/telemetry`. This replaces the base handover's single 5-min KPI push and resolves the open question of *which* `PeriodicStatistics` references matter.

> **FINALISED 2026-06-10** against `archive/dmcli.new.conf` (live NanoLink dump, 20,261 params). The example tiers below are now concrete paths. `P = Device.Services.FAPService.1.`

| Tier | Cadence | Source kind | Paths (→ metric key) |
|------|---------|-------------|----------------------|
| **T1 — critical** | 30 s | **live** direct GPV (instantaneous) | `P+FAPControl.LTE.OpState`→`op_state`, `P+FAPControl.LTE.RFTxStatus`→`rf_tx_status`, `P+FAPControl.LTE.AdminState`→`admin_state`, `P+FAPControl.LTE.Gateway.X_8C1F64_S1Status`→`s1_status` (`"Success"`), `P+Transport.SCTP.Assoc.1.Status`→`sctp_status` (`"Active"`), **`P+X_8C1F64_Status.UeNumber`→`connected_ues`** (live), `P+X_8C1F64_Status.VolteUeNumber`→`volte_ues` |
| **T2 — RF/coverage** | 60 s | **live** SON/RF GPV | `P+X_8C1F64_SON.RIP.RIPAverage`→`rip_average` (dBm), `P+X_8C1F64_SON.RIP.RIPPRB`→`rip_prb[]` (100-element), `P+X_8C1F64_SON.RIP.RIPThreshold`→`rip_threshold`, `P+CellConfig.LTE.RAN.RF.X_8C1F64_EARFCNDLInUse`→`earfcn_dl_inuse`, `P+…RF.X_8C1F64_PhyCellIDInUse`→`pci_inuse`, `P+…RF.ReferenceSignalPower`→`rs_power` (lever readback), `P+…RF.DLBandwidth`/`ULBandwidth`→`dl_bw`/`ul_bw` |
| **T3 — PM + hw/alarms** | 5 min | **PM** (`PeriodicStatistics.SampleSet.1`, 900 s) + **live** hw | PM: `RRU.TotalPrbUsageMeanDl`→`prb_dl_pct`, `RRU.TotalPrbUsageMeanUl`→`prb_ul_pct`, `RRC.AttConnEstab`+`RRC.SuccConnEstab`→`rrc_success_pct` (succ/att·100), **`RRU.Sinr.Average`→`sinr_avg_db`**, `RRC.ConnMean`→`rrc_conn_mean`, `MAC.ThroughputDl`/`Ul`→`thp_dl`/`thp_ul`. Live: `Device.DeviceInfo.UpTime`→`uptime`, `…MemoryStatus.Free`/`Total`→`mem_free`/`mem_total`, `…ProcessStatus.CPUUsage`→`cpu_usage`, `Device.FaultMgmt.CurrentAlarm.*`→`alarms[]` |

**Canonical optimiser metric keys (single source of truth — see §A.8.1):**

| Key | Source | Tier | Note |
|-----|--------|------|------|
| `connected_ues` | `X_8C1F64_Status.UeNumber` | T1 (live) | instantaneous; not the PM `RRC.ConnMean` |
| `prb_dl_pct` | `RRU.TotalPrbUsageMeanDl` | T3 (PM) | mean DL PRB utilisation % |
| `rrc_success_pct` | `RRC.SuccConnEstab` / `RRC.AttConnEstab` | T3 (PM) | ratio ·100 |
| `sinr_avg_db` | `RRU.Sinr.Average` | T3 (PM) | **replaces `median_rsrp`** — see caveat |

**Caveats (locked findings from the dump):**
1. **No serving-cell RSRP exists** on this NanoLink. Every RSRP path is a *config threshold* (`Mobility…A1–A5ThresholdRSRP`, SON/ANR `…RSRPThreshold*`) or *handover-event* RSRP (`HO.SrcCellQual.RSRP`, empty in a single-cell lab). The original `median_rsrp` guardrail is therefore **substituted by `sinr_avg_db`** (`RRU.Sinr.Average`); CQI distribution (`PHY.NbrCqi0..15`) is a secondary quality signal. *RF owners to confirm the SINR floor — ties to §C.4 #4.*
2. **PM granularity = 900 s.** `PeriodicStatistics.SampleSet.1` (the only enabled set: `Enable=1`, `SampleInterval=900`, `ReportSamples=24`, 549 params) samples every 15 min. So `prb_dl_pct`/`rrc_success_pct`/`sinr_avg_db`/throughput refresh every 15 min **on-device** — reading faster than T3 only repeats values. Hence these sit in T3, not T2.
3. **T1/T2 freshness is real** because every T1/T2 metric is a directly-readable param (not PM). `connected_ues` via live `UeNumber` is what makes the < 90 s KPI-freshness SLA meaningful (the PM `RRC.ConnMean` would be 15 min stale).
4. Most counter values are `0`/empty in this dump — expected for an idle lab cell; does not affect path selection.

The telemetry payload carries `metrics[]`, `events[]` (from FTP logs, §3.6), and `alarms[]` in one batch, each item tagged with its `tier` and `ts`. KPI freshness < 90 s is met because T1 (the SLA-relevant tier) is pushed every 30 s.

### 3.5 Poll & cadence summary (agent → cloud)

| Call | Interval | Purpose |
|------|----------|---------|
| `GET  /v1/agent/poll` | **10 s** | Claim pending commands for this edge (plain GET, no long-poll). |
| `POST /v1/agent/heartbeat` | 30 s | Edge liveness + NanoLink inventory (serial, IPs, sw version, last-inform age, CWMP health). |
| `POST /v1/agent/telemetry` | T1 30 s / T2 60 s / T3 5 min | Tiered metrics + parsed events + alarms (batched). |
| `POST /v1/agent/devices/{device_id}/config-snapshot` | 5 min + after every applied `configure` | Curated 24-managed-param snapshot (not all 20,261). Periodic reads are full; command read-backs may be deltas, which merge into the latest non-empty cloud snapshot. |
| `POST /v1/agent/commands/{id}/ack` | after each command | `applied` / `failed` / `rolled_back` + verification read-back. |

> Poll-interval decision: **10 s** (vs. the API Plan's 5 s default). Both satisfy config round-trip < 30 s; 10 s halves empty-poll volume. Per-tenant override remains a future option.

### 3.6 Monitoring (per-device Events) — FTP log pipeline

The NanoLink uploads a `.tgz` to the Edge Device FTP root every 60 s. The GO Agent:

1. Watches `/srv/nybsys-ftp/nybsysftp/uploads/` (fsnotify + periodic rescan).
2. Extracts each archive; reads known module logs: **FM** (alarms), **TR69** (CWMP), **FILE_TRANS** (upload status).
3. Runs a **pluggable regex rule table** (`rules.yaml`, hot-reloadable) → structured events. Unknown-but-alarming lines become `severity=warning, event_type=unclassified`; the rest is dropped (raw archives optionally mirrored to S3).
4. Folds events into the next `/v1/agent/telemetry` batch (`events[]`), idempotent via `dedup_key`.

When more logs are uploaded, **only `rules.yaml` changes** — no code.

### 3.7 Self-Optimisation & Self-Heal — policy producing commands

Both Self-Heal and Self-Optimise are **policy layers that emit commands** into the same table:

- **Self-Heal** (post-Q2): an alarm/event triggers a `heal` command (e.g. targeted re-config or `reboot`). Because it rides the unified command pipeline it gets claim/ack/lease/rollback for free, and the MTTR < 90 s SLA is met by the 10 s poll + 30 s apply budget.
- **Self-Optimise**: `self_optimizer.py` writes `optimization_recommendations`; approved (or auto-approved) recommendations are materialised as `optimise`-type commands → same pipeline → auditability + rollback for free. Full model in §A.8.

---

## 4. Data Model — new Postgres tables (add to `schemas.sql`)

All tables are tenant-scoped and **must** be added to the RLS `FOREACH t IN ARRAY [...]` loop in `schemas.sql` (the loop that currently ends `...,'nybsys_uploads'`). RLS policy mirrors the existing ones: `USING (tenant_id = current_setting('app.current_tenant')::uuid)`.

```sql
-- ── Edge Devices (GO Agent hosts) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.edge_devices (
  edge_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL,
  name           text NOT NULL,
  api_key_hash   text NOT NULL,                  -- sha256(secret); secret never stored
  status         text NOT NULL DEFAULT 'pending',-- pending|online|offline|disabled
  agent_version  text,
  last_seen_at   timestamptz,
  meta           jsonb,                           -- {os, edge_ip, cwmp_listen, ftp_dir}
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_edge_devices_tenant ON public.edge_devices(tenant_id);
CREATE TRIGGER trg_edge_devices_updated BEFORE UPDATE ON public.edge_devices
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── NanoLink devices (managed cells behind an Edge Device) ──────────────────
CREATE TABLE IF NOT EXISTS public.nanolink_devices (
  device_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL,
  edge_id          uuid NOT NULL REFERENCES public.edge_devices(edge_id) ON DELETE CASCADE,
  cwmp_id          text NOT NULL,                 -- canonical TR-069/CWMP device id, e.g. 8C1F64-ENB%2DN03002%2DB3-2205609999
  serial_number    text,
  product_class    text,                          -- ENB-N03002-B3
  admin_lan_ip     inet,
  wan_ip           inet,
  sw_version       text,
  rf_tx_status     boolean,                       -- FAPControl.LTE.RFTxStatus
  op_state         boolean,                       -- FAPControl.LTE.OpState
  last_inform_at   timestamptz,
  health           text NOT NULL DEFAULT 'unknown', -- healthy|degraded|down|unknown
  optimize_mode    text NOT NULL DEFAULT 'off',   -- off|approval|auto
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, cwmp_id)
);
CREATE INDEX IF NOT EXISTS idx_nanolink_tenant ON public.nanolink_devices(tenant_id);
CREATE INDEX IF NOT EXISTS idx_nanolink_edge   ON public.nanolink_devices(edge_id);
CREATE TRIGGER trg_nanolink_updated BEFORE UPDATE ON public.nanolink_devices
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── Commands (UNIFIED transport primitive: configure|heal|optimise|query|reboot)
CREATE TABLE IF NOT EXISTS public.commands (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL,
  device_id     uuid NOT NULL REFERENCES public.nanolink_devices(device_id) ON DELETE CASCADE,
  edge_id       uuid NOT NULL,
  type          text NOT NULL,                    -- configure|heal|optimise|query|reboot
  payload       jsonb NOT NULL,                   -- {writes:[{path,value,xsd_type}], verify:{...}, rollback_on_fail:bool}
  prev_values   jsonb,                            -- captured for rollback
  origin        text NOT NULL DEFAULT 'manual',   -- manual|optimizer|healer|rollback
  status        text NOT NULL DEFAULT 'pending',  -- pending|dispatched|applied|failed|cancelled
  attempts      integer NOT NULL DEFAULT 0,
  dispatched_at timestamptz,
  acked_at      timestamptz,
  result        jsonb,                            -- {readback:{...}, mismatch:[...], detail, rolled_back}
  error         text,
  created_by    text,                             -- cognito sub | 'optimizer' | 'healer'
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_commands_device ON public.commands(device_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commands_poll   ON public.commands(edge_id, status);  -- claim-on-fetch path
CREATE TRIGGER trg_commands_updated BEFORE UPDATE ON public.commands
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── Curated parameter snapshots (managed params only) ───────────────────────
CREATE TABLE IF NOT EXISTS public.device_config_snapshots (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  device_id   uuid NOT NULL REFERENCES public.nanolink_devices(device_id) ON DELETE CASCADE,
  params      jsonb NOT NULL,                     -- materialized latest-known map; non-empty deltas merge before insert
  source      text NOT NULL DEFAULT 'agent',      -- agent|command_readback
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_snap_device ON public.device_config_snapshots(device_id, created_at DESC);

-- ── Telemetry: events (from FTP logs) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.device_events (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  device_id   uuid NOT NULL REFERENCES public.nanolink_devices(device_id) ON DELETE CASCADE,
  ts          timestamptz NOT NULL,
  module      text NOT NULL,                      -- FM|TR69|FILE_TRANS|...
  event_type  text NOT NULL,                      -- vendor_acs_unreachable|atc_fault_loop|ftp_upload_ok|...
  severity    text NOT NULL,                      -- critical|major|minor|warning|info|clear
  message     text,
  attrs       jsonb,
  dedup_key   text NOT NULL,                      -- sha256(device|ts|type|hash(msg))
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, dedup_key)
);
CREATE INDEX IF NOT EXISTS idx_events_device_ts ON public.device_events(device_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_sev        ON public.device_events(device_id, severity);

-- ── Telemetry: KPI samples (tiered metrics) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS public.device_kpis (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  device_id   uuid NOT NULL REFERENCES public.nanolink_devices(device_id) ON DELETE CASCADE,
  ts          timestamptz NOT NULL,
  tier        smallint,                           -- 1|2|3
  metrics     jsonb NOT NULL,                     -- {op_state, rf_tx_status, connected_ues, rip_prb[], ...}
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, device_id, ts, tier)
);
CREATE INDEX IF NOT EXISTS idx_kpis_device_ts ON public.device_kpis(device_id, ts DESC);

-- ── Optimisation recommendations (policy layer → emits optimise commands) ────
CREATE TABLE IF NOT EXISTS public.optimization_recommendations (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL,
  device_id    uuid NOT NULL REFERENCES public.nanolink_devices(device_id) ON DELETE CASCADE,
  kind         text NOT NULL,                     -- energy_saving|coverage|mobility|anomaly
  rationale    text NOT NULL,
  changes      jsonb NOT NULL,                    -- proposed {param: value}
  expected     jsonb,                             -- {metric: delta}
  confidence   numeric,                           -- 0..1
  status       text NOT NULL DEFAULT 'proposed',  -- proposed|approved|applied|rejected|expired
  command_id   uuid REFERENCES public.commands(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reco_device ON public.optimization_recommendations(device_id, created_at DESC);
CREATE TRIGGER trg_reco_updated BEFORE UPDATE ON public.optimization_recommendations
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

Extend the RLS enable+policy loop in `schemas.sql`:

```sql
-- add to the existing FOREACH t IN ARRAY [...] list:
'edge_devices','nanolink_devices','commands','device_config_snapshots',
'device_events','device_kpis','optimization_recommendations'
```


---

# PART A — BACKEND AGENT

Work in **`maveric_platform_smo_sim`** unless stated otherwise. You will also make one small Gateway addition (§A.6) and produce the **GO Agent** Go module (§A.7).

## A.1 New modules (SMO-SIM file layout)

```
app/
  api/v1/custom/
    nybsys_edge_router.py        # operator API (Cognito-auth, under /custom/nybsys)
    nybsys_agent_router.py       # agent API (Edge-Key auth, under /agent)
  schemas/
    nybsys_edge_schemas.py       # Pydantic DTOs + ORM
  services/nybsys/
    edge_auth.py                 # Edge-Key verify, enrollment token mint/decode
    command_service.py           # create/claim/ack/lease the commands table
    ingest_service.py            # telemetry (metrics/events/alarms), snapshot, inventory
    event_parser.py              # rule table application (mirror of agent rules)
    self_optimizer.py            # rules + stats model (Phase 1 + Phase 2 hooks)
    managed_params.py            # curated parameter catalogue + validators
```

Reuse the existing `set_current_tenant(db, tenant_id)` helper, response-envelope helpers, and `log_error_to_mongodb()` exactly as other SMO-SIM routers do.

## A.2 Managed parameter catalogue (`managed_params.py`)

Only these parameters are surfaced/editable in the dashboard and writable by `configure`/`optimise` commands. Bounds clamp both the operator and the optimiser. The values below are **firmware-reference evidence** from `dmcli_new.conf`; they are not dashboard Current values. Current values come only from an edge-agent configuration snapshot, and an operator enters a separate proposed value to create a command.

```python
# app/services/nybsys/managed_params.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Param:
    path: str
    dtype: str            # "int" | "uint" | "bool" | "string" | "enum"
    xsd: str              # TR-069 xsd type for the SPV write
    group: str            # "rf" | "power" | "mobility" | "drx" | "identity" | "acs"
    editable: bool
    optimizable: bool
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple | None = None
    note: str = ""

P = "Device.Services.FAPService.1."

MANAGED_PARAMS: list[Param] = [
    # ── Identity / cell (editable, NOT optimisable) ───────────────────────────
    Param(P+"CellConfig.LTE.RAN.RF.PhyCellID", "string", "xsd:string", "identity", True, False,
          0, 503, note="PCI; SON may also set this (PCIOptEnable=1)."),
    Param(P+"CellConfig.LTE.RAN.RF.EARFCNDL", "string", "xsd:string", "rf", True, False,
          note="Downlink EARFCN, observed 1850 (Band 3)."),
    Param(P+"CellConfig.LTE.RAN.RF.EARFCNUL", "string", "xsd:string", "rf", True, False,
          note="Uplink EARFCN, observed 19850."),
    Param(P+"CellConfig.LTE.RAN.RF.FreqBandIndicator", "int", "xsd:int", "rf", True, False,
          note="Band 3."),
    Param(P+"CellConfig.LTE.RAN.RF.DLBandwidth", "string", "xsd:string", "rf", True, False,
          choices=("25","50","75","100"), note="RB count; 100=20MHz observed."),
    Param(P+"CellConfig.LTE.RAN.RF.ULBandwidth", "string", "xsd:string", "rf", True, False,
          choices=("25","50","75","100")),

    # ── POWER / energy-saving (editable AND optimisable) ──────────────────────
    Param(P+"CellConfig.LTE.RAN.RF.ReferenceSignalPower", "int", "xsd:int", "power", True, True,
          -60, 50, note="RS power (dBm), observed -10. Primary power-save knob."),
    Param("Device.Services.FAPService.1.Capabilities.MaxTxPower", "uint", "xsd:unsignedInt", "power", False, False,
          note="HW ceiling = 21 dBm. Read-only; clamps optimiser."),
    Param(P+"CellConfig.LTE.RAN.PHY.PDSCH.Pa", "string", "xsd:string", "power", True, True,
          note="PA offset; affects DL power per RE."),
    Param(P+"CellConfig.LTE.RAN.PHY.PDSCH.Pb", "string", "xsd:string", "power", True, True),

    # ── DRX (editable AND optimisable — UE & cell power saving) ────────────────
    Param(P+"CellConfig.LTE.RAN.MAC.DRX.DRXEnabled", "bool", "xsd:boolean", "drx", True, True,
          note="observed 1."),
    Param(P+"CellConfig.LTE.RAN.MAC.DRX.OnDurationTimer", "string", "xsd:string", "drx", True, True,
          note="observed 40."),
    Param(P+"CellConfig.LTE.RAN.MAC.DRX.DRXInactivityTimer", "string", "xsd:string", "drx", True, True,
          note="observed 1920 — large value keeps UEs awake; key power lever."),
    Param(P+"CellConfig.LTE.RAN.MAC.DRX.LongDRXCycle", "string", "xsd:string", "drx", True, True,
          note="observed 128."),
    Param(P+"CellConfig.LTE.RAN.MAC.DRX.ShortDRXCycle", "uint", "xsd:unsignedInt", "drx", True, True,
          note="observed 128."),
    Param(P+"CellConfig.LTE.RAN.MAC.X_8C1F64_PCH.DefaultPagingCycle", "string", "xsd:string", "drx", True, True,
          choices=("rf32","rf64","rf128","rf256"),
          note="observed rf128; longer cycle = idle power saving, higher latency."),

    # ── MOBILITY / coverage (editable AND optimisable) ────────────────────────
    Param(P+"CellConfig.LTE.RAN.Mobility.IdleMode.IntraFreq.QRxLevMinSIB1", "int", "xsd:int", "mobility", True, True,
          -70, -22, note="observed -62; cell selection floor."),
    Param(P+"CellConfig.LTE.RAN.Mobility.IdleMode.IntraFreq.SIntraSearch", "string", "xsd:string", "mobility", True, True,
          note="observed 21."),
    Param(P+"CellConfig.LTE.RAN.Mobility.ConnMode.EUTRA.A2ThresholdRSRP", "uint", "xsd:unsignedInt", "mobility", True, True,
          0, 97, note="observed 50; A2 (poor coverage) trigger."),
    Param(P+"CellConfig.LTE.RAN.Mobility.ConnMode.EUTRA.A1ThresholdRSRP", "uint", "xsd:unsignedInt", "mobility", True, True,
          0, 97, note="observed 60."),
    Param(P+"CellConfig.LTE.RAN.Mobility.ConnMode.EUTRA.Hysteresis", "string", "xsd:string", "mobility", True, True,
          note="observed 2."),
    Param(P+"CellConfig.LTE.RAN.Mobility.ConnMode.EUTRA.TimeToTrigger", "uint", "xsd:unsignedInt", "mobility", True, True,
          note="observed 40 (ms)."),

    # ── ACS / housekeeping (editable, not optimisable) ────────────────────────
    Param("Device.ManagementServer.PeriodicInformInterval", "uint", "xsd:unsignedInt", "acs", True, False,
          30, 86400, note="observed/recommended 1800."),
    Param("Device.X_8C1F64_DebugMgmt.Upload.AutonomousTransferCompletePolicy",
          "enum", "xsd:string", "acs", True, False, choices=("None","OnSuccess","Always"),
          note="Historical GenieACS fault-loop stopgap; the in-agent ACS now answers ATC directly, so forcing 'None' is no longer required — the agent surfaces the value but no longer writes it."),
]

MANAGED = {p.path: p for p in MANAGED_PARAMS}

def validate_write(path: str, value) -> str:
    """Validates a single write and returns the xsd type for the SPV. Raises ValueError."""
    p = MANAGED.get(path)
    if p is None or not p.editable:
        raise ValueError(f"Parameter not editable: {path}")
    if p.choices and str(value) not in p.choices:
        raise ValueError(f"{path} must be one of {p.choices}")
    if p.dtype in ("int", "uint"):
        v = int(value)
        if p.dtype == "uint" and v < 0:
            raise ValueError(f"{path} must be >= 0")
        if p.minimum is not None and v < p.minimum: raise ValueError(f"{path} < min")
        if p.maximum is not None and v > p.maximum: raise ValueError(f"{path} > max")
    return p.xsd
```

## A.3 Edge-Key auth + enrollment (`edge_auth.py`)

```python
# app/services/nybsys/edge_auth.py
import base64, hashlib, json, secrets
from fastapi import Header, HTTPException
from sqlalchemy import text

def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def mint_enrollment(tenant_id: str, edge_id: str, base_url: str) -> tuple[str, str]:
    """Returns (enrollment_token, api_key_hash). Secret is shown once via token only."""
    secret = secrets.token_hex(32)
    api_key = f"{edge_id}.{secret}"
    token = _b64u(json.dumps({
        "v": 1, "tenant_id": tenant_id, "edge_id": edge_id,
        "base_url": base_url, "api_key": api_key,
    }).encode())
    return token, hashlib.sha256(api_key.encode()).hexdigest()

async def auth_edge(db, x_edge_key: str = Header(...)) -> dict:
    """Dependency for /agent/** routes. Returns {tenant_id, edge_id} and pins RLS."""
    try:
        edge_id, _ = x_edge_key.split(".", 1)
    except ValueError:
        raise HTTPException(401, "MALFORMED_EDGE_KEY")
    key_hash = hashlib.sha256(x_edge_key.encode()).hexdigest()
    # Lookup runs BEFORE set_config tenant — query by edge_id+hash directly via service role.
    row = db.execute(text("""
        SELECT tenant_id, edge_id FROM public.edge_devices
        WHERE edge_id = :eid AND api_key_hash = :h AND status <> 'disabled'
    """), {"eid": edge_id, "h": key_hash}).mappings().first()
    if not row:
        raise HTTPException(401, "INVALID_EDGE_KEY")
    db.execute(text("SELECT set_config('app.current_tenant', :t, true)"),
               {"t": str(row["tenant_id"])})
    return dict(row)
```

> RLS note: the `edge_devices` lookup must run before `set_config`. Use the same service-role pattern the gateway already uses for cross-tenant lookups (or a permissive SELECT policy scoped to the `edge_id`+`api_key_hash` predicate). Once resolved, set the tenant and all later statements honour RLS normally. Document the chosen approach in the PR.


## A.4 Operator API (`nybsys_edge_router.py`) — Cognito-authed

Mount under the existing `/custom` feature-flag parent (gated by `tenants.feature_flags["nybsys"]`). All return the standard envelope.

```
# Edge devices
POST   /v1/tenants/{t}/custom/nybsys/edge-devices            -> create + enrollment_token (ONCE)
GET    /v1/tenants/{t}/custom/nybsys/edge-devices            -> list (online/offline, #devices)
GET    /v1/tenants/{t}/custom/nybsys/edge-devices/{edge_id}  -> detail
POST   /v1/tenants/{t}/custom/nybsys/edge-devices/{edge_id}:regenerate-key -> new token (ONCE)
DELETE /v1/tenants/{t}/custom/nybsys/edge-devices/{edge_id}  -> cascade

# NanoLink devices (the clickable table)
GET    /v1/tenants/{t}/custom/nybsys/devices                 -> list across all edges
GET    /v1/tenants/{t}/custom/nybsys/devices/{device_id}     -> detail + latest snapshot + health
GET    /v1/tenants/{t}/custom/nybsys/devices/{device_id}/config        -> latest curated params
PATCH  /v1/tenants/{t}/custom/nybsys/devices/{device_id}/optimize-mode -> off|approval|auto

# Commands (unified: create/read; type configure here, optimise/heal via policy)
POST   /v1/tenants/{t}/custom/nybsys/devices/{device_id}/commands  -> create (201 {command_id, status:"pending"})
GET    /v1/tenants/{t}/custom/nybsys/devices/{device_id}/commands  -> history
GET    /v1/tenants/{t}/custom/nybsys/commands/{command_id}         -> status + result

# Telemetry read (dashboards)
GET    /v1/tenants/{t}/custom/nybsys/devices/{device_id}/events?severity=&since=&limit=
GET    /v1/tenants/{t}/custom/nybsys/devices/{device_id}/kpis?metric=&tier=&since=
GET    /v1/tenants/{t}/custom/nybsys/devices/{device_id}/health    -> rollup card

# Self-optimisation
GET    /v1/tenants/{t}/custom/nybsys/devices/{device_id}/recommendations
POST   /v1/tenants/{t}/custom/nybsys/recommendations/{id}:approve  -> creates optimise command
POST   /v1/tenants/{t}/custom/nybsys/recommendations/{id}:reject
```

Create-edge handler:

```python
@router.post("/edge-devices")
def create_edge(t: str, body: CreateEdge, db=Depends(get_db), claims=Depends(require_tenant_admin)):
    set_current_tenant(db, t)
    edge_id = str(uuid4())
    token, key_hash = mint_enrollment(t, edge_id, settings.PUBLIC_BASE_URL)
    db.execute(text("""INSERT INTO edge_devices(edge_id,tenant_id,name,api_key_hash,meta)
                       VALUES (:e,:t,:n,:h,:m)"""),
               {"e": edge_id, "t": t, "n": body.name, "h": key_hash,
                "m": json.dumps(body.meta or {})})
    db.commit()
    return ok({"edge_id": edge_id, "name": body.name, "enrollment_token": token})  # once only
```

Create-command handler (validates against catalogue, captures prev values for rollback):

```python
@router.post("/devices/{device_id}/commands")
def create_command(t, device_id, body: CommandIn, db=Depends(get_db), claims=Depends(require_member)):
    set_current_tenant(db, t)
    dev = _get_device(db, device_id)                  # 404 if missing
    if body.type == "configure":
        for w in body.payload["writes"]:
            w["xsd_type"] = validate_write(w["path"], w["value"])  # raises -> 422
        prev = _latest_snapshot_values(db, device_id, [w["path"] for w in body.payload["writes"]])
    else:
        prev = None
    cid = str(uuid4())
    db.execute(text("""INSERT INTO commands
        (id,tenant_id,device_id,edge_id,type,payload,prev_values,origin,created_by)
        VALUES (:c,:t,:d,:e,:ty,:p,:pv,'manual',:u)"""),
        {"c": cid, "t": t, "d": device_id, "e": dev["edge_id"], "ty": body.type,
         "p": json.dumps(body.payload), "pv": json.dumps(prev), "u": claims["sub"]})
    db.commit()
    return created({"command_id": cid, "status": "pending"})
```

## A.5 Agent API (`nybsys_agent_router.py`) — Edge-Key authed

Mounted under `/v1/agent` (gateway §A.6). Every handler depends on `auth_edge`.

```python
@router.post("/register")
def register(body: RegisterIn, ctx=Depends(auth_edge), db=Depends(get_db)):
    db.execute(text("""UPDATE edge_devices
        SET status='online', agent_version=:v, last_seen_at=now(),
            meta = coalesce(meta,'{}') || :m WHERE edge_id=:e"""),
        {"v": body.agent_version, "e": ctx["edge_id"], "m": json.dumps(body.meta)})
    db.commit(); return ok({"edge_id": ctx["edge_id"]})

@router.get("/poll")  # claim-on-fetch, every 10 s
def poll(ctx=Depends(auth_edge), db=Depends(get_db)):
    db.execute(text("UPDATE edge_devices SET last_seen_at=now() WHERE edge_id=:e"),
               {"e": ctx["edge_id"]})
    cmds = db.execute(text("""
        UPDATE commands SET status='dispatched', dispatched_at=now(), attempts=attempts+1
        WHERE id IN (
          SELECT id FROM commands
          WHERE edge_id=:e AND status='pending'
          ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 20)
        RETURNING id, device_id, type, payload"""), {"e": ctx["edge_id"]}).mappings().all()
    db.commit()
    return ok({"server_time": _now_iso(), "commands": [dict(c) for c in cmds]})

@router.post("/heartbeat")   # 30 s — liveness + inventory (auto-onboard new cells)
def heartbeat(body: HeartbeatIn, ctx=Depends(auth_edge), db=Depends(get_db)):
    ingest_service.upsert_inventory(db, ctx, body.devices)
    db.commit(); return ok({})

@router.post("/telemetry")   # tiered metrics + events + alarms, batched
def telemetry(body: TelemetryIn, ctx=Depends(auth_edge), db=Depends(get_db)):
    n_k = ingest_service.upsert_kpis(db, ctx, body.metrics)      # by (device,ts,tier)
    n_e = ingest_service.upsert_events(db, ctx, body.events)     # ON CONFLICT(dedup_key) DO NOTHING
    ingest_service.apply_alarms(db, ctx, body.alarms)            # updates nanolink_devices.health
    self_optimizer.on_new_kpis(db, ctx, body.metrics)           # Phase-1 anomaly + reco hook
    healer.on_new_events(db, ctx, body.events, body.alarms)     # Self-Heal hook (post-Q2)
    db.commit(); return ok({"metrics": n_k, "events": n_e})

@router.post("/devices/{device_id}/config-snapshot")  # 5 min + post-apply
def snapshot(device_id, body: SnapshotIn, ctx=Depends(auth_edge), db=Depends(get_db)):
    ingest_service.save_snapshot(db, ctx, device_id, body.params, body.source)
    db.commit(); return ok({})

@router.post("/commands/{command_id}/ack")
def ack(command_id, body: AckIn, ctx=Depends(auth_edge), db=Depends(get_db)):
    command_service.complete(db, ctx, command_id, body)  # applied|failed + rollback guard
    db.commit(); return ok({})
```

`ingest_service.upsert_inventory` updates `nanolink_devices.health`: **down** if `last_inform_at` stale > 5 min or a critical FM alarm is active; **degraded** on active majors; **healthy** otherwise.

`command_service.complete` writes status/result and, if `payload.rollback_on_fail` and the readback mismatches `payload.verify`, enqueues a `rollback`-origin `configure` command restoring `prev_values`.

A periodic SMO-SIM sweep reclaims leases (the §3.2 lease-reclaim SQL), reusing the existing `reset_stale_*` pattern; start it as a startup sweep, grow to periodic.

## A.6 Gateway addition (Go) — the one routing change

Add an **unauthenticated-by-Cognito** group that injects the SMO `X-API-Key` and forwards to SMO-SIM. Edge-Key validation happens in SMO-SIM, not the gateway.

```go
// router.go — new group, parallel to the existing /v1 group
agent := r.Group("/v1/agent")
agent.Use(middleware.AttachRequestID())            // keep X-Request-ID
agent.Use(middleware.RateLimitByIP(120))           // 120/min — a misconfigured agent can't flood
// NO RequireBearer / RequireMembership here.
agent.Any("/*path", func(c *gin.Context) {
    c.Request.Header.Set("X-API-Key", cfg.SMOAPIKey)  // same SMO_API_KEY as /custom proxy
    proxy.Forward(c, cfg.SMOBaseURL)                  // → http://smo-sim:8002/v1/agent/...
})
```

Rebuild the gateway container after this change (compose runs a compiled binary without a source mount — the LLD calls this out).


## A.7 GO Agent (Edge Device) — new Go module

Repo `cloudlynet_edgeagent`. Single static binary, systemd, **no inbound port toward the cloud** (all cloud traffic is agent-initiated). It does host an in-agent TR-069/CWMP ACS on the LAN-side `:7547` that the NanoLink dials, and watches the local FTP drop. A local **SQLite offline buffer** (≤100 MB per NFR) makes the edge robust to a flaky link.

### A.7.1 Config (`/etc/cloudlynet-agent/agent.yaml`)

```yaml
enrollment_token: "<paste from dashboard>"   # decodes to tenant/edge/base_url/api_key
poll_interval: 10s
heartbeat_interval: 30s
telemetry_t1_interval: 30s
telemetry_t2_interval: 60s
telemetry_t3_interval: 5m
snapshot_interval: 5m
cwmp:
  listen: "0.0.0.0:7547"              # in-agent ACS bind — the exact host:port the NanoLink dials
  full_snapshot_on_first_contact: true
  # optional connection-request trigger: cr_user / cr_pass / cr_url_override
ftp_watch_dir: "/srv/nybsys-ftp/nybsysftp/uploads"
rules_file: "/etc/cloudlynet-agent/rules.yaml"
buffer_db: "/var/lib/cloudlynet-agent/buffer.sqlite"
buffer_max_bytes: 104857600        # 100 MB cap (NFR)
```

### A.7.2 Project layout

```
cmd/agent/main.go
internal/
  config/config.go         # parse yaml + decode enrollment token
  cloud/client.go          # REST client (poll/telemetry/heartbeat/ack) + retry
  buffer/sqlite.go         # offline buffer: telemetry outbox, applied-command dedup, CWMP device/param/event store
  cwmp/                    # in-agent TR-069/CWMP ACS (:7547): SOAP codec, session, ATC handler, connection-request trigger
  ftp/watcher.go           # fsnotify + .tgz extract
  rules/engine.go          # regex rule table → events
  collector/kpi.go         # tiered PeriodicStatistics → metrics
  worker/loop.go           # orchestrates tickers
```

### A.7.3 SQLite offline buffer (`buffer/sqlite.go`)

Two jobs: (a) durably queue outbound telemetry so nothing is lost when the cloud is unreachable; (b) record applied `command_id`s so redelivery is a safe re-ack, not a re-apply (idempotency mechanism #2 from §3.2).

```go
// internal/buffer/sqlite.go
package buffer

// schema:
//   outbox(id INTEGER PK, kind TEXT, body BLOB, created_at INTEGER)   -- telemetry batches
//   applied(command_id TEXT PRIMARY KEY, status TEXT, result BLOB, applied_at INTEGER)

func (b *Buffer) Enqueue(kind string, body []byte) error {
    b.trimToCap()                                   // FIFO-drop oldest if over buffer_max_bytes
    _, err := b.db.Exec(`INSERT INTO outbox(kind,body,created_at) VALUES(?,?,?)`,
        kind, body, time.Now().Unix())
    return err
}

func (b *Buffer) Drain(send func(kind string, body []byte) error) {
    rows, _ := b.db.Query(`SELECT id,kind,body FROM outbox ORDER BY id LIMIT 100`)
    for rows.Next() {
        var id int64; var kind string; var body []byte
        rows.Scan(&id, &kind, &body)
        if err := send(kind, body); err != nil { return }   // stop on first failure; retry next tick
        b.db.Exec(`DELETE FROM outbox WHERE id=?`, id)
    }
}

func (b *Buffer) AlreadyApplied(cmdID string) (bool, []byte, string) {
    var status string; var result []byte
    err := b.db.QueryRow(`SELECT status,result FROM applied WHERE command_id=?`, cmdID).
        Scan(&status, &result)
    return err == nil, result, status
}
func (b *Buffer) MarkApplied(cmdID, status string, result []byte) {
    b.db.Exec(`INSERT OR REPLACE INTO applied(command_id,status,result,applied_at)
               VALUES(?,?,?,?)`, cmdID, status, result, time.Now().Unix())
}
```

### A.7.4 Cloud client (REST, with backoff; telemetry goes through the buffer)

```go
// internal/cloud/client.go
func (c *Client) do(method, path string, in any, out any) error {
    var body io.Reader
    if in != nil { b, _ := json.Marshal(in); body = bytes.NewReader(b) }
    req, _ := http.NewRequest(method, c.base+path, body)
    req.Header.Set("X-Edge-Key", c.apiKey)
    req.Header.Set("Content-Type", "application/json")
    var lastErr error
    for attempt := 0; attempt < 3; attempt++ {          // 1s,2s,4s
        resp, err := c.http.Do(req)
        if err == nil && resp.StatusCode < 500 {
            defer resp.Body.Close()
            if resp.StatusCode >= 400 { return fmt.Errorf("%s %s -> %d", method, path, resp.StatusCode) }
            if out != nil {
                var env struct{ Data json.RawMessage `json:"data"` }
                json.NewDecoder(resp.Body).Decode(&env)
                return json.Unmarshal(env.Data, out)
            }
            return nil
        }
        lastErr = err; time.Sleep(time.Duration(1<<attempt) * time.Second)
    }
    return fmt.Errorf("cloud unreachable: %v", lastErr)
}

type Command struct {
    ID       string            `json:"id"`
    DeviceID string            `json:"device_id"`
    Type     string            `json:"type"`     // configure|heal|optimise|query|reboot
    Payload  CommandPayload    `json:"payload"`
}
func (c *Client) Poll() ([]Command, error) {
    var r struct{ Commands []Command `json:"commands"` }
    err := c.do("GET", "/v1/agent/poll", nil, &r); return r.Commands, err
}
// SendTelemetry is fire-and-forget: enqueue to buffer, then drain.
func (c *Client) SendTelemetry(b *buffer.Buffer, batch TelemetryBatch) {
    body, _ := json.Marshal(batch)
    b.Enqueue("telemetry", body)
    b.Drain(func(kind string, body []byte) error {
        return c.do("POST", "/v1/agent/telemetry", json.RawMessage(body), nil)
    })
}
func (c *Client) Ack(id string, res AckBody) error {
    return c.do("POST", "/v1/agent/commands/"+id+"/ack", res, nil)
}
```

### A.7.5 Device connector — in-agent CWMP ACS

> **SUPERSEDED (implemented differently).** The plan below assumed a GenieACS NBI client
> (`internal/genieacs/nbi.go`) posting tasks to an external GenieACS on `:7557`. **As shipped, the
> agent hosts its own TR-069/CWMP ACS in-process** (`internal/cwmp/`, bound to `:7547` — the exact
> port the NanoLink already dials) and speaks CWMP to the device directly. It answers `Inform`, the
> `AutonomousTransferComplete` (ATC) RPC with the empty `AutonomousTransferCompleteResponse` (never a
> Fault — the ATC Fault is exactly what killed the GenieACS session before it could read/write),
> `GetParameterValues`, `SetParameterValues`, a first-contact `GetParameterNames` writability walk,
> and `Reboot`. `SetParams`/`GetParams` become tasks queued onto the device's session and drained on
> its next dial-in (or immediately via the optional connection-request trigger). Verify-by-read-back
> and the closed-loop apply semantics below are unchanged; only the transport moved from an external
> NBI to the in-agent ACS. The historical NBI code is retained below for provenance.

```go
// internal/genieacs/nbi.go — SetParams queues an SPV with connection_request; GetParams verifies.
func (n *NBI) SetParams(deviceID string, writes []Write) (string, error) {
    var values [][]any
    for _, w := range writes { values = append(values, []any{w.Path, w.Value, w.XSDType}) }
    payload, _ := json.Marshal(map[string]any{"name": "setParameterValues", "parameterValues": values})
    url := fmt.Sprintf("%s/devices/%s/tasks?connection_request", n.base, urlEscape(deviceID))
    resp, err := n.http.Post(url, "application/json", bytes.NewReader(payload))
    if err != nil { return "", err }
    defer resp.Body.Close()
    if resp.StatusCode >= 300 { return "", fmt.Errorf("genieacs task: %d", resp.StatusCode) }
    var t struct{ ID string `json:"_id"` }; json.NewDecoder(resp.Body).Decode(&t)
    return t.ID, nil
}
func (n *NBI) GetParams(deviceID string, paths []string) (map[string]string, error) {
    refresh, _ := json.Marshal(map[string]any{"name": "getParameterValues", "parameterNames": paths})
    n.http.Post(fmt.Sprintf("%s/devices/%s/tasks?connection_request", n.base, urlEscape(deviceID)),
        "application/json", bytes.NewReader(refresh))
    q := url.QueryEscape(fmt.Sprintf(`{"_id":%q}`, deviceID))
    resp, err := n.http.Get(fmt.Sprintf("%s/devices/?query=%s", n.base, q))
    if err != nil { return nil, err }
    defer resp.Body.Close()
    var docs []map[string]any; json.NewDecoder(resp.Body).Decode(&docs)
    out := map[string]string{}
    if len(docs) > 0 { for _, p := range paths { if v := digValue(docs[0], p); v != "" { out[p] = v } } }
    return out, nil
}
```

> **CWMP stability (as shipped):** the ATC fault loop is fixed at the source — the in-agent ACS
> answers `AutonomousTransferComplete` with the empty response, so the session survives. The former
> "ensure baseline" SPV forcing `AutonomousTransferCompletePolicy=None` is therefore no longer
> written; the path stays a read-only entry in the snapshot catalogue. On first contact the agent
> instead runs a `GetParameterNames` writability walk (and, if configured, a first-contact GPV of the
> managed catalogue so the first config snapshot is populated immediately).

### A.7.6 Worker loop (tiered telemetry + buffered, idempotent command apply)

```go
func (w *Worker) Run(ctx context.Context) {
    pollT := time.NewTicker(w.cfg.PollInterval)        // 10s
    hbT   := time.NewTicker(w.cfg.HeartbeatInterval)   // 30s
    t1    := time.NewTicker(w.cfg.TelemetryT1Interval) // 30s
    t2    := time.NewTicker(w.cfg.TelemetryT2Interval) // 60s
    t3    := time.NewTicker(w.cfg.TelemetryT3Interval) // 5m
    snapT := time.NewTicker(w.cfg.SnapshotInterval)    // 5m
    go w.ftp.Watch(ctx, w.onArchive)                   // events folded into next telemetry batch
    w.cloud.Register(w.agentVersion(), w.inventory())
    for {
        select {
        case <-ctx.Done(): return
        case <-pollT.C:  w.handleCommands()
        case <-hbT.C:    w.cloud.Heartbeat(w.inventory())
        case <-t1.C:     w.pushTier(1)
        case <-t2.C:     w.pushTier(2)
        case <-t3.C:     w.pushTier(3)
        case <-snapT.C:  w.pushSnapshots()
        }
    }
}

func (w *Worker) handleCommands() {
    cmds, err := w.cloud.Poll()
    if err != nil { log.Warn("poll failed", err); return }   // buffered telemetry still drains next tick
    for _, cmd := range cmds {
        // idempotency #2: if already applied, re-ack without re-applying
        if done, result, status := w.buf.AlreadyApplied(cmd.ID); done {
            w.cloud.Ack(cmd.ID, AckBody{Status: status, Result: result}); continue
        }
        ack := w.apply(cmd)                                   // SPV/GPV/verify, or reboot, etc.
        body, _ := json.Marshal(ack.Result)
        w.buf.MarkApplied(cmd.ID, ack.Status, body)
        w.cloud.Ack(cmd.ID, ack)
    }
}

func (w *Worker) apply(cmd Command) AckBody {
    switch cmd.Type {
    case "configure", "optimise", "heal", "rollback":
        taskID, err := w.nbi.SetParams(w.genie(cmd.DeviceID), cmd.Payload.Writes)
        if err != nil { return AckBody{Status: "failed", Detail: err.Error()} }
        time.Sleep(8 * time.Second)                          // let CWMP session land
        paths := pathsOf(cmd.Payload.Writes)
        readback, _ := w.nbi.GetParams(w.genie(cmd.DeviceID), paths)
        mismatch := verify(cmd.Payload, readback)
        st := "applied"; if len(mismatch) > 0 { st = "failed" }
        return AckBody{Status: st, Result: Result{Readback: readback, Mismatch: mismatch, TaskID: taskID}}
    case "reboot":
        return w.nbi.Reboot(w.genie(cmd.DeviceID))           // non-idempotent → buffer dedup protects it
    case "query":
        rb, _ := w.nbi.GetParams(w.genie(cmd.DeviceID), cmd.Payload.ReadPaths)
        return AckBody{Status: "applied", Result: Result{Readback: rb}}
    }
    return AckBody{Status: "failed", Detail: "unknown command type"}
}
```

### A.7.7 FTP watcher + rule engine

```go
func (fw *Watcher) onArchive(path string) {
    files, _ := extractTgz(path, fw.tmpDir())          // [](module, lines)
    var events []rules.Event
    for _, f := range files {
        events = append(events, fw.engine.Apply(f.Module, f.Lines, f.DeviceHint)...)
    }
    if len(events) > 0 { fw.collector.QueueEvents(events) } // ride next telemetry batch
    fw.mirrorToCloudOptional(path)
}
```

```yaml
# /etc/cloudlynet-agent/rules.yaml  (hot-reloadable — extend as more logs arrive)
rules:
  - module: FM
    match: "ACS .*124\\.93\\.160\\.157.*unreachable|connect.*124\\.93\\.160\\.157"
    event_type: vendor_acs_unreachable
    severity: major
    message: "Hardcoded vendor ACS unreachable (expected in lab)"
  - module: TR69
    match: "RPC Unknown received from ACS"
    event_type: atc_fault_loop
    severity: major
    message: "ACS returned Fault to ATC"   # legacy-detector; the in-agent ACS now answers ATC, so this should no longer fire
  - module: FILE_TRANS
    match: "File upload success, curl code=\\(0\\)"
    event_type: ftp_upload_ok
    severity: info
  - module: FILE_TRANS
    match: "curl code=\\(25\\)"
    event_type: ftp_upload_path_reject
    severity: minor
  - module: FILE_TRANS
    match: "curl code=\\(67\\)"
    event_type: ftp_auth_fail
    severity: major
  - module: FM
    match: "(?i)reboot|restart"
    event_type: device_reboot
    severity: critical
  # fallback: engine auto-emits unclassified/warning for any unmatched "alarmy" line
```

```go
// internal/rules/engine.go
func (e *Engine) Apply(module string, lines []string, deviceHint string) []Event {
    var out []Event
    for _, ln := range lines {
        ts := parseTS(ln); matched := false
        for _, r := range e.rules {
            if r.Module == module && r.re.MatchString(ln) {
                out = append(out, e.mk(deviceHint, ts, module, r.EventType, r.Severity, r.Message, ln))
                matched = true; break
            }
        }
        if !matched && alarmy(ln) {   // contains alarm|fault|fail|error
            out = append(out, e.mk(deviceHint, ts, module, "unclassified", "warning", "", ln))
        }
    }
    return out
}
// dedup_key = sha256(device|ts|event_type|sha1(rawline)) — set here or server-side.
```

### A.7.8 systemd unit

```ini
# /etc/systemd/system/cloudlynet-agent.service
[Unit]
Description=CloudlyNet GO Agent
After=network-online.target vsftpd.service
[Service]
ExecStart=/usr/local/bin/cloudlynet-agent --config /etc/cloudlynet-agent/agent.yaml
Restart=always
RestartSec=5
User=cloudlynet
StateDirectory=cloudlynet-agent          # provides /var/lib/cloudlynet-agent for the SQLite buffer
[Install]
WantedBy=multi-user.target
```


## A.8 Self-Optimisation model (`self_optimizer.py`)

Single-cell (one radio per NanoLink — the existing multi-radio rApps don't transfer). Optimises **power/energy** and **connectivity/coverage** under hard guardrails. Inputs are `device_kpis` (tiered telemetry) + `device_events`. Outputs are `optimization_recommendations`; approved/auto-approved ones become `optimise` commands.

Levers (from `dmcli_new.conf`, all `optimizable=True` in §A.2): `ReferenceSignalPower` (obs −10, clamp ≤ MaxTxPower 21), `DefaultPagingCycle` (rf128), `DRXInactivityTimer` (1920), `LongDRXCycle` (128), `A2ThresholdRSRP` (50), `PDSCH.Pa/Pb`.

### A.8.1 Phase 1 — guard-railed rules + anomaly detection (ship for Q2)

```python
# app/services/nybsys/self_optimizer.py
from dataclasses import dataclass

# NOTE (2026-06-10): median_rsrp is NOT exposed by the NanoLink (§3.4 caveat 1) →
# coverage-quality guardrail uses sinr_avg_db (RRU.Sinr.Average). SINR floor pending RF sign-off (§C.4 #4).
GUARD = {"min_sinr_db": 0, "max_prb_dl_pct": 70, "min_rrc_success_pct": 95}
RS_POWER     = "Device.Services.FAPService.1.CellConfig.LTE.RAN.RF.ReferenceSignalPower"
PAGING_CYCLE = "Device.Services.FAPService.1.CellConfig.LTE.RAN.MAC.X_8C1F64_PCH.DefaultPagingCycle"
DRX_INACT    = "Device.Services.FAPService.1.CellConfig.LTE.RAN.MAC.DRX.DRXInactivityTimer"

@dataclass
class Ewma:
    mean: float = 0.0; var: float = 1.0; n: int = 0; alpha: float = 0.2
    def update(self, x):
        if self.n == 0: self.mean, self.var = x, 1.0
        else:
            d = x - self.mean
            self.mean += self.alpha * d
            self.var = (1 - self.alpha) * (self.var + self.alpha * d * d)
        self.n += 1
        return (x - self.mean) / (self.var ** 0.5 + 1e-9)   # z-score

def on_new_kpis(db, ctx, metrics):
    for s in _by_device(metrics):
        z = _state(ctx, s["device_id"]).sinr.update(s.get("sinr_avg_db", 0))
        if abs(z) > 3:
            _emit_event(db, ctx, s, "kpi_anomaly", "warning", f"SINR z-score {z:.1f}")
        _maybe_recommend(db, ctx, s)

def _maybe_recommend(db, ctx, s):
    dev = _device(db, s["device_id"])
    if dev["optimize_mode"] == "off": return
    cur = _latest_params(db, s["device_id"]); rs = int(cur.get(RS_POWER, -10))
    low_load   = s.get("prb_dl_pct", 100) < 15 and s.get("connected_ues", 99) <= 2
    good_cover = s.get("sinr_avg_db", -999) > GUARD["min_sinr_db"] + 6   # SINR headroom (RSRP not exposed)
    healthy    = s.get("rrc_success_pct", 0) >= GUARD["min_rrc_success_pct"]

    if low_load and good_cover and healthy and rs > -8:
        _propose(db, ctx, s["device_id"], kind="energy_saving",
                 rationale=f"Low load (PRB {s['prb_dl_pct']}%, {s['connected_ues']} UEs), "
                           f"SINR headroom present; trim RS power 2 dB + relax DRX.",
                 changes={RS_POWER: str(rs - 2), PAGING_CYCLE: "rf256", DRX_INACT: "640"},
                 expected={"radiated_power_dbm": -2, "est_kwh_saved_pct": 6}, confidence=0.7)

    if s.get("prb_dl_pct", 0) > GUARD["max_prb_dl_pct"] and rs < -10:
        _propose(db, ctx, s["device_id"], kind="coverage",
                 rationale="High utilisation — restore RS power toward baseline.",
                 changes={RS_POWER: str(min(rs + 2, -10))},
                 expected={"radiated_power_dbm": +2}, confidence=0.9)
```

`_propose` writes an `optimization_recommendations` row. If `optimize_mode='auto'` **and** `kind` is on the auto-allowlist (coverage-restore; energy steps within ±2 dB of baseline), it immediately creates an `optimise` command (`origin='optimizer'`, `prev_values` captured) → normal command pipeline. Otherwise it stays `proposed` for dashboard approval.

**Auto-rollback guardrail.** When an `optimise`/`configure`/`manual` command completes, `command_service.complete` watches the next KPI window (telemetry keeps arriving). If within 15 min any guardrail breaks (`sinr_avg_db` < floor, RRC success < 95%), it auto-creates a `rollback` command restoring `prev_values`. Safe to leave in `auto`. *Note: the 15-min window aligns with the device PM `SampleInterval=900 s` (§3.4 caveat 2) — one fresh PM sample per window.*

### A.8.2 Phase 2 — seasonal model + safe Bayesian search (post-Q2)

Same interface, no new infra (SMO-SIM background task on the existing thread-pool; persists to Postgres/Mongo).

1. **Hourly occupancy profile (Holt-Winters / seasonal-naïve).** With ≥7 days of `device_kpis`, build a per-device 24×7 robust-median load profile and pre-schedule DRX/paging/power states by hour rather than reacting. `statsmodels.tsa.holtwinters.ExponentialSmoothing` (additive seasonality) is sufficient and explainable.
2. **Safe Bayesian optimisation** of params without a clear monotone rule (Pa/Pb, A2, hysteresis/TTT) via bounded TPE (`optuna`): search space = §A.2 bounds/choices; objective = `w1·coverage_ok − w2·radiated_power − w3·access_failures` over the KPI window; **every trial is a guarded `optimise` command**; guardrail breach scores −∞ and rolls back; ≤1 change/30 min/device, inside an operator maintenance window only.

> Scope note for the team: with a single lab cell and low/synthetic traffic, Phase-2 signal is weak until real UE load exists. Ship Phase 1 for Q2; treat Phase-2 profile-building as data-collection-gated (needs ≥1–2 weeks of real KPIs).

---

# PART B — FRONTEND AGENT

Work in **`maveric_platform_frontend`** (Next.js 14, Tailwind, D3). All calls go through the gateway at `NEXT_PUBLIC_API_BASE=/v1` with the Cognito Bearer token. The `/v1/agent/**` endpoints belong to the GO Agent — the frontend never calls them.

## B.1 New screens / routes

```
src/app/tenants/[tenantId]/nybsys/
  page.tsx                      # Edge Devices + NanoLink table (landing)
  edge/[edgeId]/page.tsx        # Edge detail + enrollment token reveal
  devices/[deviceId]/
    page.tsx                    # Device tab shell (Config | Monitoring | Optimise)
    config/ConfigPanel.tsx
    monitoring/MonitoringPanel.tsx
    optimise/OptimisePanel.tsx
  _lib/api.ts                   # typed fetch wrappers
```

Feature-gate the whole `nybsys` section on `tenants.feature_flags.nybsys` (backend already 403s if absent; hide the nav entry when off).

## B.2 API wrappers (`_lib/api.ts`)

```ts
const base = (t: string) => `/v1/tenants/${t}/custom/nybsys`;

export const listEdges      = (t:string) => api.get(`${base(t)}/edge-devices`);
export const createEdge      = (t:string, name:string) => api.post(`${base(t)}/edge-devices`, { name });
export const regenerateKey   = (t:string, e:string) => api.post(`${base(t)}/edge-devices/${e}:regenerate-key`, {});
export const listDevices     = (t:string) => api.get(`${base(t)}/devices`);
export const getDevice       = (t:string, id:string) => api.get(`${base(t)}/devices/${id}`);
export const getConfig       = (t:string, id:string) => api.get(`${base(t)}/devices/${id}/config`);
// create a configure command (unified commands table)
export const createCommand   = (t:string, id:string, writes:{path:string;value:string}[]) =>
  api.post(`${base(t)}/devices/${id}/commands`, { type:"configure", payload:{ writes, rollback_on_fail:true }});
export const listCommands    = (t:string, id:string) => api.get(`${base(t)}/devices/${id}/commands`);
export const getCommand      = (t:string, cid:string) => api.get(`${base(t)}/commands/${cid}`);
export const getEvents       = (t:string, id:string, q:any) => api.get(`${base(t)}/devices/${id}/events`, q);
export const getKpis         = (t:string, id:string, metric:string, since:string, tier?:number) =>
  api.get(`${base(t)}/devices/${id}/kpis`, { metric, since, tier });
export const getRecommendations = (t:string, id:string) => api.get(`${base(t)}/devices/${id}/recommendations`);
export const approveReco     = (t:string, rid:string) => api.post(`${base(t)}/recommendations/${rid}:approve`, {});
export const rejectReco      = (t:string, rid:string) => api.post(`${base(t)}/recommendations/${rid}:reject`, {});
export const setOptimizeMode = (t:string, id:string, mode:"off"|"approval"|"auto") =>
  api.patch(`${base(t)}/devices/${id}/optimize-mode`, { mode });
```

## B.3 Landing — Edge devices + clickable device table

A device table whose rows route into the device tab, with live health (15 s SWR poll). **Add Edge** opens a modal → `createEdge` → reveal the enrollment token **once** (copy-to-clipboard, "won't be shown again" warning, paste-into-agent instruction inline). Columns: Cell ID (`cwmp_id`), Edge, Health badge, RF Tx, SW version, Last Inform (relative), Optimise-mode chip.

## B.4 Device tab — Config panel (view & edit → command)

Render managed params grouped by `group` (rf, power, drx, mobility, identity, acs). Control type by `dtype`: number input with min/max, `<select>` for `choices`, toggle for bool; `editable=false` params (MaxTxPower, EARFCNDL, band) render read-only. "Push to device" calls `createCommand` with the diff → toast "Command queued — applies on next agent poll (~10 s)". A **CommandHistory** component polls `listCommands` every 5 s while any command is `queued|dispatched`, showing the timeline `pending → dispatched → applied/failed` and, on `failed`, the `result.mismatch`.

## B.5 Device tab — Monitoring panel (events + tiered KPIs)

Severity-filterable event timeline (10 s SWR poll), colour-coded, with friendly labels (`vendor_acs_unreachable` → "Vendor ACS unreachable (expected)", `atc_fault_loop` → "CWMP ATC fault loop", `ftp_auth_fail` → "FTP auth failure", …). KPI charts use the existing D3 contract (`plot.groups[{title,data:[{x,y}]}]`); transform `kpis.samples[{ts,tier,metrics}]`. Ship at least **median RSRP (T2)** and **connected-UE count (T1)** charts, plus a health-rollup card from `/health`. Surface the SLA framing where useful (e.g. KPI age badge against the < 90 s target).

## B.6 Device tab — Optimise panel

Mode selector (off | approval | auto, each explained inline) → `setOptimizeMode`. Recommendations list (20 s poll); each `RecoCard` shows `kind`, `rationale`, a before→after diff of `changes`, `expected` deltas and `confidence`. Approve → `approveReco` (creates the `optimise` command) → card transitions to `applied` once the command lands.

## B.7 Frontend acceptance checklist

- [ ] Nav entry hidden unless `feature_flags.nybsys` true.
- [ ] Add Edge → token shown once, copyable, with "won't be shown again" warning.
- [ ] Device table rows clickable → device tab; health/RF/last-inform live (15 s poll).
- [ ] Config edit validates bounds client-side, creates command, polls to `applied/failed`.
- [ ] Read-only params (MaxTxPower, EARFCNDL, band) not editable.
- [ ] Monitoring shows severity-filtered events + RSRP (T2) + UE-count (T1) charts.
- [ ] Optimise mode switch persists; recommendations approve/reject works.


---

# PART C — BUILD ORDER, TESTING, ENHANCEMENT LADDER, OPEN ITEMS

## C.1 Recommended implementation order

1. **Schema** — add the 7 tables (incl. unified `commands`) + RLS loop entries to `schemas.sql`; apply via the deployment pipeline (gateway does not auto-migrate).
2. **SMO-SIM `managed_params.py`** — pure data; unit-test `validate_write` + xsd mapping.
3. **`edge_auth.py` + agent `/register` + `/poll`** — get an empty agent talking to the cloud.
4. **Gateway `/v1/agent/**` group** — rebuild container; verify Edge-Key round-trip end-to-end.
5. **Operator router** — edge CRUD + enrollment token; device list/detail; command create/read.
6. **GO Agent skeleton** — config decode, register, poll, heartbeat, **SQLite buffer**; confirm rows update offline-safely.
7. **In-agent CWMP ACS + command apply pipeline** — manual `configure` in UI → param change → read-back → `applied`; confirm idempotent re-ack from buffer.
8. **FTP watcher + rule engine + telemetry events** — drop a real `.tgz`, confirm events surface in Monitoring.
9. **Tiered KPI collector (T1/T2/T3) + ingest + charts.**
10. **Self-optimiser Phase 1** (rules + anomaly + auto-rollback); **Self-Heal** `heal` command hook.
11. **Phase 2** (profile + Optuna) — data-gated, post-Q2.

## C.2 Testing (SLAs are acceptance criteria)

- **Contract:** extend `openapi.yaml` with `/custom/nybsys/**` and `/agent/**`; run `schemathesis`.
- **RLS:** cross-tenant attempts on every new table must fail; one Edge-Key must not read another tenant's devices/commands.
- **SLA — KPI freshness < 90 s:** assert T1 telemetry age in `device_kpis` stays under 90 s in a steady-state lab run.
- **SLA — config round-trip < 30 s:** time UI command-create → `applied` ack with the real NanoLink dialing the agent's in-agent CWMP ACS.
- **SLA — Self-Heal MTTR < 90 s:** inject an alarm → assert a `heal` command is created, claimed, applied + verified within 90 s.
- **Delivery semantics:** two overlapping polls never claim the same row (`SKIP LOCKED`); a `dispatched` row with no ack returns to `pending` after the lease; redelivered command re-acks from the SQLite buffer **without** re-applying (test with `reboot`).
- **Idempotency:** replay the same telemetry batch twice → events `ingested` count drops to 0 on the second (dedup_key).
- **Optimiser safety:** simulate a post-apply guardrail breach → assert a `rollback` command is auto-created.
- **Offline buffer:** kill cloud connectivity, run for N minutes, restore → buffered telemetry drains in order, nothing lost, buffer respects the 100 MB cap (FIFO-drop oldest).

## C.3 Enhancement ladder (agreed future evolution — NOT in this build)

Recorded per the API Plan §6. These change **only the transport of the southbound poll**; endpoints, payloads, and the operator loop are invariant, so the skeleton ships now and transport evolves without breaking either side.

| Stage | What changes | Adopt when |
|-------|--------------|-----------|
| **Baseline — polling** (this build) | `GET /poll` returns immediately; agent re-polls every **10 s** | now |
| **E1 — long-poll** | `/poll?wait=25` holds the request open until a command lands or ~25 s elapses (then 204); near-instant delivery, far fewer empty polls. Same endpoint. | command latency matters or empty-poll volume grows |
| **E2 — SSE** | one-way `GET /commands/stream` streams commands down an agent-opened HTTP connection; northbound stays POST. Push without gRPC. | want push but keep the HTTP/REST stack |
| **E3 — gRPC bidi** | telemetry + poll + ack collapse into one bidirectional stream; same JSON→proto payloads. | many devices / high-frequency bidirectional traffic |

**Invariant:** the §5-style data contract and the operator loop never change across stages.

## C.4 Open items / decisions to confirm

1. **PUBLIC_BASE_URL** baked into enrollment tokens — confirm the externally reachable gateway URL for agents (lab vs prod differ).
2. **RLS pre-auth read** for `edge_devices` (§A.3) — adopt the gateway's service-role pattern; document in the PR.
3. ~~**Exact T1/T2/T3 metric keys**~~ — **RESOLVED 2026-06-10** against `archive/dmcli.new.conf`; finalised mapping locked in §3.4. Key outcomes: `connected_ues` ← live `X_8C1F64_Status.UeNumber` (T1); `prb_dl_pct` ← `RRU.TotalPrbUsageMeanDl` (T3/PM); `rrc_success_pct` ← `RRC.SuccConnEstab/AttConnEstab` (T3/PM); **`median_rsrp` dropped (no serving RSRP on device) → replaced by `sinr_avg_db` ← `RRU.Sinr.Average`** (feeds into #4 — RF to confirm the SINR floor). PM granularity is 900 s.
4. **Auto-mode allowlist bounds** — confirm the ±2 dB RS-power auto-step, **the `sinr_avg_db` coverage floor (`GUARD["min_sinr_db"]`, default 0 dB placeholder — was RSRP before #3)**, and maintenance-window policy with RF owners before enabling `auto`. The optimiser must never toggle `AdminState`/`RFTxStatus` (RF enablement is still gated on the vendor question set).
5. **Lease timeout & max_attempts** for the command table (start 60 s / e.g. 5); index `(edge_id, status)` already provided.
6. **Raw archive retention** — mirror `.tgz` to S3 (forensics) vs events-only. Schema supports either.
7. **Auth posture** — Edge-Key is the decision for this build; if PRD §14.3 mTLS is later enforced, the token bootstraps a client cert instead (enrollment UX unchanged).

---

## Appendix — divergences from the Lead Engineer's API Plan (for review)

| Topic | API Plan | This merged build | Why |
|-------|----------|-------------------|-----|
| Agent auth | mTLS (PRD §14.3) | **Edge-Key** (hashed secret) | Decision for this build: simpler termination, no per-agent cert lifecycle; mTLS deferrable behind the same enrollment UX. |
| Poll interval | 5 s default | **10 s** | Both meet round-trip < 30 s; 10 s halves empty-poll volume. |
| Command table | unified `commands(type,payload)` | **adopted as-is** | Gives Self-Heal + reboot for free; optimiser/healer are producers. |
| Telemetry | T1/T2/T3 tiers | **adopted as-is** | Resolves the "which counters" open question; meets KPI freshness SLA. |
| Offline buffer | SQLite ≤100 MB | **adopted as-is** | Robust to flaky edge link; also backs idempotent re-ack. |
| SLAs | §4 targets | **adopted as acceptance criteria** | Made testable in §C.2. |
| Enhancement ladder | §6 stages | **recorded as future** (§C.3) | REST-only now; transport can evolve without contract change. |
| Enrollment ("hash") | not covered | **added** (§3.1) | Plan assumes agents exist; this provisions them. |
| Param catalogue + validators | writable targets listed | **added** with bounds/xsd (§A.2) | Server-side validation + optimiser clamps. |
| Optimiser policy & FTP rule engine | out of scope ("ML policy") | **added** (§A.8, §3.6) | The actual Self-Optimise/monitoring implementation. |
| Frontend | API-only | **added** (Part B) | The dashboard. |

*This handover is implementation-ready: backend from Part A, GO Agent from §A.7, frontend from Part B, all meeting against the §4 data model and the §A.4/§A.5 REST contracts.*
