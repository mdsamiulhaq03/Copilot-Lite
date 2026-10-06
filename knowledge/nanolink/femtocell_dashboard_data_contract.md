# Femtocell Dashboard Data Contract (NybSys NanoLink)

Status: proposed contract, 2026-07-23. Evidence base: analyzer dumps `logs-overlap.json`, `dmcli-tree.json` (20,261 GPV paths), `archive-map.json`, `platform-map.json` over `artifacts/nanolink/nybsys_archive_18june` (one device: NybSys ENB-N03002-B3, LTE Band 3 femtocell, OUI 8C1F64 / serial 2205609999, TR-069 (CWMP) client tr69c) plus repo code cited by file:line.

Scope guardrail (per `artifacts/marketing/claims-guardrails.md`): the device plane is a single-vendor TR-069 (CWMP) EMS. Everything here is REST/CWMP/FTP over Postgres. No O-RAN, no RIC, no E2/A1/O1 protocol claims. The solution term is Network Digital Twin. FCAPS naming: PM (performance), CM (configuration), FM (fault).

---

## 1. Executive answer: the three dashboard sections and what feeds each

The device dashboard should present exactly three data sections plus the existing Optimization tab:

| Section | What feeds it | Canonical store (EPIC-1) | Today's store |
|---|---|---|---|
| PM (Performance) | TR-069 (CWMP) GPV telemetry tiers T1 (30s), T2 (60s), T3 (5min read / 900s device granularity via `Device.PeriodicStatistics.SampleSet.1`, 549 counters on device) | `pm_measurements` (numeric `value double precision`) | `device_kpis` (JSONB, values stored as strings) |
| CM (Configuration) | Agent config snapshot of 24 managed params (5min + post-command read-back) + full-tree GPV audits; commands table for writes | `cm_records` | `device_config_snapshots`, `commands` |
| FM (Faults) | Two independent streams: (a) vendor FTP log stream `Log_*.gz` / `ErrorLog_*.gz` (alarm lines with hex ids), (b) TR-069 `Device.FaultMgmt.*` GPV (CurrentAlarm, HistoryEvent) | `fm_alarms` + `device_events` | `device_events` only; FaultMgmt alarms fold into `nanolink_devices.health` and are never persisted (OD9, issue #321) |

Key empirical facts driving the contract:

- PM never comes from the FTP logs. Full-corpus scan (15,907 Log + 4 ErrorLog + 5 continuouslogging rings): zero RSRP/RSRQ/SINR/CQI/PRB/RRC/throughput/UE-count counters; only 28 boot-scoped "PM-ish" lines (temperature, memory KB, partition %) in 14 days (`archive-map.json` pm_verdict; `logs-overlap.json` corrected_class_totals: PM-ish 24 Log + 4 ErrorLog lines). PM lives in the CWMP tree: 11,145 of 20,261 dmcli paths are PM-STATS, dominated by `SampleSet.1.Parameter.{1..549}` (7,686 paths) and the `X_8C1F64_SupportedMeas` catalogue of 549 measurement types.
- The FTP log stream is CM/FM, not PM: 76.8% of Log lines are `[TR69]` CWMP session/RPC/parameter traffic; corrected class totals STATE-CM 105,756 (all Log), STATE 32,123 (32,085 Log + 38 ErrorLog), FAULT 378 (251 Log + 127 ErrorLog), PM-ish 28 (`logs-overlap.json` q2, q5).
- FM is currently the weakest section: true alarms are folded into a single health enum and clobbered within 30s by the heartbeat recompute; the UI labels log-parse events as "Alarms" (`platform-map.json` OD9, health card widget row).

### 1.1 Per-widget source table (current UI: Config | Monitoring | Optimize tabs)

13 widgets audited (`platform-map.json` widget_source_table). 5 work end to end, 3 are partial, 5 are broken. Every widget has a real designed source; no widget is fed by fabricated data, but 8 need fixes before their data path is truthful and complete.

| # | Widget (tab) | Real source chain | Works today | Fix required |
|---|---|---|---|---|
| 1 | Managed parameters editor (Config) | agent 5min GPV of 24 SnapshotPaths -> config-snapshot -> `device_config_snapshots` | yes | de-triplicate catalogue via EPIC-4 `managed_params.json` contract |
| 2 | Push-to-device commands + history (Config) | `commands` table queue -> agent poll -> CWMP SPV + read-back | yes | none blocking |
| 3 | Events list w/ severity chips (Monitoring) | FTP watcher -> rules -> `device_events` | partial | BROKEN for real devices: scanFTP consumes only `*.tgz` but real uploads are single-gzip `Log_*.gz`/`ErrorLog_*.gz` (collector.go:210); module read from tar member NAME not the `[MODULE]` tag in lines (collector.go:268-280); timestamps are parse-time not line-time. Fix: the section 2 parser |
| 4 | Health card + "Alarms (24h)" (Monitoring) | `nanolink_devices.health` + `device_events` counts | partial | FCAPS mislabel: counts are log EVENTS, not FaultMgmt alarms; fold is clobbered in 30s. Fix: `fm_alarms` table + recompute_health (OD9 Option B, section 3) |
| 5 | Connected UEs chart (Monitoring) | T1 GPV `X_8C1F64_Status.UeNumber` -> `device_kpis` | no | value arrives as JSON string; KpiCharts plots only numbers. Fix: numeric coercion at ingest (or `pm_measurements.value`) |
| 6 | SINR avg chart (Monitoring) | T3 `SampleSet.1.Parameter.412` = RRU.Sinr.Average | no | string-drop + SampleSet provisioning + pinned-index risk (metrics.go:14-18) |
| 7 | PRB util DL/UL chart (Monitoring) | T3 Parameter.316/315 = RRU.TotalPrbUsageMeanDl/Ul | no | string-drop + pinned-index risk |
| 8 | RRC success chart (Monitoring) | agent-derived float from Parameter.170/168 | yes | only guaranteed-numeric chart; needs SampleSet present and attempts>0 |
| 9 | Throughput DL/UL chart (Monitoring) | T3 Parameter.118/119 = MAC.ThroughputDl/Ul | no | string-drop + pinned-index risk |
| 10 | CPU and memory chart (Monitoring) | T3 `DeviceInfo.ProcessStatus.CPUUsage`, `MemoryStatus.Free/Total` | no | string-drop only; values do arrive |
| 11 | Policy mode selector (Optimize) | `nanolink_devices.optimize_mode` | yes | OD4 SINR floor sign-off gates auto mode; OD16 no audit trail |
| 12 | Recommendations grid (Optimize) | `optimization_recommendations` + `commands` on approve | yes | OD14 batch-only optimiser; OD23 approver attribution |
| 13 | Device header (all) | `nanolink_devices` + latest snapshot | partial | frontend reads `genieacs_id`, backend returns `cwmp_id`; id renders blank |

Missing widget with no source today: temperature. The dmcli tree exposes `Device.DeviceInfo.TemperatureStatus.TemperatureSensor.{1..12}.Value` (12 sensors, 54-56 C in the dump) but no tier polls it; logs carry only per-boot PowerOn temperature lines. Fix: add the sensor paths to T3 (see `fields_pm.csv`).

### 1.2 Where the Optimization (C-SON) tab reads from

- Reads: `optimization_recommendations` (GET /devices/{id}/recommendations), `commands` (approve -> optimise command -> agent poll), `nanolink_devices.optimize_mode`.
- Producer today: rule-based `self_optimizer.on_new_kpis` in smo-sim, invoked on each telemetry batch; it coerces the stringified KPIs itself (self_optimizer.py:75-92).
- Producer target: Network Digital Twin outputs (BDT engine predictions and RL rApp policies) writing into the same `optimization_recommendations` + `commands` tables, so the approve/apply/rollback loop is unchanged.
- RIC connection: roadmap only. Nothing in this contract implements or claims E2, A1, O1, an xApp/rApp framework in the O-RAN sense, or RIC conformance. Actuation is TR-069 (CWMP) SetParameterValues via the edge agent, full stop.

---

## 2. Log parsing strategy (Log_*.gz and ErrorLog_*.gz)

### 2.1 Empirical verdict: one stream, two filename triggers

`logs-overlap.json` q1 verdict: SAME-STREAM-DIFFERENT-TRIGGER, neither subset nor superset.

- Identical line grammar in both: 10-digit sequence number, `YYYY-MM-DD HH:MM:SS.mmm` device-local time, `[MODULE]`, message. 0 unparsed non-blank lines in ErrorLogs, 2 in 15,903 Logs.
- Sequence numbers chain ACROSS file-type boundaries exactly as within a type: ErrorLog internal boundaries 79->80, 131->132, 143->144 (3 of 3 chained); archive-wide 15,898 of 15,906 adjacent file pairs chain +1 (remaining 8 = 4 corrupt gz + reboots/holes).
- Both types open each window with the identical `[FM] Periodic VendorLog upload started, PeriodicUploadInterval=60s` line.
- Zero line-level overlap exists between the types, by time-disjoint construction: every file covers the preceding ~60s and no Log exists within +/-10 min of any ErrorLog (nearest gaps 14.0/15.0/16.0/17.0 min). Template-level overlap is partial (53.3% of ErrorLog templates recur in the nearest Logs, 50.0% vs baseline), and two modules (`[SCTP]`, `[L1_L2_Wrapper]`) appear only in ErrorLogs.
- The filename flips to `ErrorLog_*` while the device is in an error/alarm state (here: SCTP S1 transport failure storm ending in an FM-commanded reboot).

### 2.2 Resulting rule: parse BOTH file types through ONE pipeline, with line-level dedup

Because ErrorLog is not a subset of Log (it carries the only copies of SCTP/SON/L1 fault lines) and Log is not a subset of ErrorLog (routine CWMP/upload/lifecycle lines), a one-primary-plus-gap-fill design would lose data whichever file type is primary. The measured facts make parse-both cheap and safe:

- Dedup key: `(device, boot_epoch, seq)` with `ts_ms` as a sanity check. `boot_epoch` = timestamp of the last seen seq `0000000000` power-on line (`[SCM] ---------- eHNB power on ...`); seq is unique and monotonic within a boot and resets to 0 at reboot (observed mid-file: ErrorLog_1758 runs seq 165 -> reboot -> 79).
- Expected duplicate rate between file types is exactly 0 (measured), so dedup normally no-ops. It exists to make ingest idempotent against whole-file re-delivery: the device retries FTP with `curl -C -` resume and re-uploads the same file after failures (observed: repeated `File upload failure, curl code=(7/8/28)` for the same `/tmp/ErrorLog_*.gz` followed by a later success; Log_/ErrorLog_ exemplars).
- Out-of-order and late arrival: the filename stamp is the upload minute, not the content window; content covers the preceding ~60s. Ingest must therefore key on line timestamps, never file arrival time (today's watcher stamps events with parse time, a known defect). Late backlog is real: ErrorLog_1802..1814 were produced but never reached the archive because FTP failed for 14 minutes; if such files arrive hours later they simply insert under their line keys.
- Corrupt files happen (4 of 15,911 gz were not gzip); ingest must quarantine and continue, recording the gap.
- File-level idempotency: record `(device, filename, sha256)` per ingested archive; skip exact re-deliveries before line parsing.

### 2.3 Alarm-record extraction: first-class FM records

Alarm lines are structured and must be lifted out of the event stream into `fm_alarms`, not left as generic events:

- Grammar: `[MODULE] Alarm Logged|Report, id: 0xHHHHHHHH file: <src> line: <n> detail: <text>` plus the FM escalation line `[FM] Critical alarm 0xHHHHHHHH raised, system reboot will be taken to recover it after 90s.`
- Observed catalogue (153 alarm lines, 7 distinct hex ids, `logs-overlap.json` q3): 0x18020500 (TR69 ACS disconnect/connect-status, 62), 0x18020400 (TR69 ACS connect failed, exponential backoff series, 31), 0x12020413 (FM device-log upload failed, 25), 0x02120400 (SCTP Connect Peer Failed, 22, ErrorLog-only), 0x16020509 (SON S1SetupCnf failure, 11, ErrorLog-only), 0x16010400 (SON S1 retry exhaustion, ErrorLog-only), 0x01110400 (L1_L2_Wrapper cpuh send failure, ErrorLog-only). Each carries `source_ref` file:line (e.g. main/informer.c:307, src/sctp_app.c:1588).
- The device's own FaultMgmt tree confirms these ids and their policy: `Device.FaultMgmt.X_8C1F64_InternalSupportedAlarm.129.AlarmId = 0x16010400` with `RecoveryMechanism = System Reboot`, `ClearingMechanism = CellSetup`; 0x18020500 clears on `HeMSConnected`; 0x12020413/0x18020400 clear `Immediately` (dmcli-tree.json). `Device.FaultMgmt.HistoryEvent.{1..64}` holds full 3GPP-style alarm records (AlarmIdentifier 0x18020500, PerceivedSeverity Major, NotificationType NewAlarm, EventTime, AdditionalInformation = the exact log line), which makes it the reconciliation source for raise/clear lifecycle.
- The self-healing chain is captured in-band and should be modeled as one incident: SON alarm 0x16010400 -> FM critical raise (+90s) -> `[SCM] Reboot command received from FM` -> ordered module stops -> `*** force to do power-off` -> power-on with seq reset.

---

## 3. DB design

### 3.1 Recommendation: Postgres, extending the existing platform schema

Reasons, in order: (1) tenancy is enforced platform-wide with Postgres RLS and the edge/operator routers already pin RLS tenants; (2) the dashboard requires joins (alarms x commands x recommendations x snapshots for RCA and rollback gating, OD10/OD11); (3) EPIC-1 already defines canonical `pm_measurements` / `fm_alarms` / `cm_records` in Postgres with per-partition FORCE RLS; (4) `device_events`, `device_kpis`, `device_config_snapshots`, `nanolink_devices`, `commands` already exist (schemas.sql:362-443).

### 3.2 fm_alarms (EPIC-1 aligned, extended for NanoLink)

```sql
CREATE TABLE fm_alarms (
    tenant_id        uuid        NOT NULL,
    source           text        NOT NULL,             -- 'nanolink'
    vendor           text        NOT NULL DEFAULT 'nybsys',
    dn               text        NOT NULL,             -- 'device=<cwmp_id>' (single-cell femto)
    alarm_id         text        NOT NULL,             -- vendor hex id, e.g. '0x16010400'
    module           text,                             -- TR69|SON|SCTP|FM|L1_L2_Wrapper|SCM|...
    kind             text        NOT NULL,             -- 'log_report'|'log_logged'|'log_critical_raised'|'faultmgmt_gpv'|'history_event'
    severity         text        NOT NULL CHECK (severity IN
                     ('critical','major','minor','warning','indeterminate','cleared')),
    probable_cause   text,                             -- FaultMgmt ProbableCause when known
    specific_problem text,                             -- e.g. 'SCTP Connect Peer Failed!'
    source_ref       text,                             -- 'main/informer.c:307'
    raised_at        timestamptz NOT NULL,
    cleared_at       timestamptz,
    state            text        NOT NULL DEFAULT 'active' CHECK (state IN ('active','cleared')),
    last_seen_at     timestamptz NOT NULL,
    occurrence_count integer     NOT NULL DEFAULT 1,   -- flap/backoff collapse counter
    raw              jsonb,                            -- full line / GPV record
    PRIMARY KEY (tenant_id, source, dn, alarm_id, raised_at)
);
ALTER TABLE fm_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE fm_alarms FORCE ROW LEVEL SECURITY;      -- policy: fm_alarms_rls on app.current_tenant, as EPIC-1 / schemas.sql DO-block
CREATE INDEX ON fm_alarms (tenant_id, dn, state, severity);
```

Lifecycle and dedup rules:

- Dedup: a new alarm line with the same `(tenant_id, dn, alarm_id)` while a row is `state='active'` bumps `occurrence_count` and `last_seen_at` instead of inserting (the 31-line ACS backoff series 0x18020400 collapses to one active alarm, occurrence_count 31).
- Clear: (a) explicit `NotificationType='ClearedAlarm'` seen in FaultMgmt HistoryEvent/ExpeditedEvent GPV; (b) mechanism-informed auto-clear from the device's own `InternalSupportedAlarm.ClearingMechanism`: `Immediately` clears on next success line (e.g. upload success clears 0x12020413), `CellSetup` clears on `[SON] S1 setup succeed` or power-on, `HeMSConnected` clears on next CWMP session established.
- `recompute_health(device)` (OD9 Option B) derives `nanolink_devices.health` from active `fm_alarms` + heartbeat, replacing the clobber-prone fold.

### 3.3 device_log_lines: OPTIONAL raw-line table, and why the default is NOT to deploy it

```sql
-- OPTIONAL. Deploy only if operator-facing log search becomes a dashboard requirement.
CREATE TABLE device_log_lines (
    tenant_id    uuid        NOT NULL,
    device_id    uuid        NOT NULL,
    boot_epoch   timestamptz NOT NULL,   -- ts of the seq-0 power-on line
    seq          bigint      NOT NULL,
    ts           timestamptz NOT NULL,
    module       text        NOT NULL,
    stream       text        NOT NULL CHECK (stream IN ('log','errorlog','contlog','devicelog')),
    template_hash text,                  -- drain-style template id for aggregation
    message      text        NOT NULL,
    details      jsonb,                  -- extracted params (curl code, alarm id, ...)
    archive_file text,                   -- provenance: source .gz object key
    PRIMARY KEY (tenant_id, device_id, boot_epoch, seq)
) PARTITION BY RANGE (ts);               -- monthly partitions, 90-day retention default
```

Volume math (from `logs-overlap.json` q5, one device, strict 60s cadence, 15,900/15,910 stamps exactly 1 min apart):

| Quantity | 1 device | 1,000 devices |
|---|---|---|
| Files/day | 1,439-1,440 (~510 B gz each) | ~1.44M |
| Lines/day (avg 8.68/Log file; ErrorLog windows 42.5, ~5x denser) | ~12,500 | ~12.5M rows/day |
| Raw text/day | ~1.41 MB | ~1.4 GB |
| Gzip/day | ~0.73 MB | ~0.73 GB (~267 GB/yr) |
| Rows/yr if every line is a row | ~4.56M | ~4.6B |
| Extracted events+alarms only | ~27 fault + ~11 alarm rows/day avg (89 alarm rows on the incident day, 0 on quiet days) | ~38k rows/day |
| Reduction factor, extract vs full | 463x | 463x |

Decision: keep the `.gz` files verbatim in MinIO/S3 (object key `nanolink-logs/{tenant}/{cwmp_id}/{yyyymmdd}/{filename}`) and store in Postgres only the extracted rows: alarms -> `fm_alarms`, lifecycle/state transitions (power-on, module stop/start, IP config, upload success/failure, reboot chain) -> `device_events`, boot-scoped PM-ish samples (temperature, memory, partition) -> `pm_measurements` with `granularity_s = 0` (aperiodic boot sample; the EPIC-1 column is `NOT NULL`) and `labels.boot=true`. Rationale: 76.8% of lines are CWMP protocol chatter with near-zero analytic value; the 463x reduction keeps Postgres small while the archive stays fully re-parseable for RCA (the copilot can fetch and re-parse any 60s window on demand). Storing every line would cost ~4.6B rows/yr at 1,000 devices for content that is 97% noise.

### 3.4 The MongoDB question, answered directly

- When Mongo would win: schemaless bulk JSON log dumps, no cross-entity joins, no per-tenant row policy, document-shaped queries only. If CloudlyNet had no relational platform and simply needed to dump parsed lines, Mongo would be a fine log sink.
- Why Postgres still wins here: (1) tenancy: RLS with FORCE per partition is already the platform's isolation model and Mongo has no equivalent enforced at the storage layer; (2) joins: FM/PM/CM rows must join `commands`, `optimization_recommendations`, `nanolink_devices` for health gating, rollback and RCA; (3) EPIC-1 alignment: `pm_measurements`/`fm_alarms`/`cm_records` are already specified as partitioned Postgres tables; (4) the working tables (`device_events`, `device_kpis`) are already Postgres; (5) per issue #314 glossary, Mongo is already reserved for cloud `application_logs` only, and widening its role fragments the data platform.
- The compromise (adopted): raw archives in object storage (MinIO/S3), structured rows in Postgres, Mongo untouched by the device-data path.

---

## 4. MCP / RCA readiness (EPIC-8 domains)

The three canonical tables map 1:1 onto future copilot MCP tools, so the dashboard contract doubles as the copilot data contract:

| EPIC-8 domain | MCP tool sketch | Backing store |
|---|---|---|
| PM | `get_pm_series(dn, metric, window)`, `detect_kpi_anomaly` | `pm_measurements` (numeric values make thresholding trivial) |
| CM | `get_config(dn)`, `diff_config(dn, t1, t2)`, `list_pending_commands` | `cm_records`, `commands` |
| FM | `get_active_alarms(dn)`, `alarm_history(dn, alarm_id)` | `fm_alarms` (state machine + occurrence_count) |
| RCA | `get_device_timeline(dn, window)` interleaving alarms, events, commands, recommendations; `fetch_raw_log_window(dn, ts)` re-parsing the archived .gz from MinIO | `fm_alarms` + `device_events` + `commands` + object storage |

Worked example the schema must answer (and does): "why did device X reboot on 2024-06-13?" -> `fm_alarms`: 0x02120400 SCTP connect failures from 17:57:33, 0x16020509 S1 setup failures, 0x16010400 raised critical at 17:58 (device policy: RecoveryMechanism System Reboot after 90s) -> `device_events`: FM-commanded module stops, force power-off, power-on 17:56:57 boot epoch -> `cm_records`: no config change preceded it -> verdict: transport outage, autonomous recovery, not an actuation regression.

---

## 5. Data-source truth table

Every artifact the device produces or exposes, mapped to the contract. "Ingest today" reflects shipped agent/smo-sim code (`platform-map.json`); "ingest target" is this contract.

| Artifact | Carries | FCAPS | Cadence | Ingest today? | Ingest target |
|---|---|---|---|---|---|
| `Log_*.gz` (FTP push) | Module-tagged OAM stream: 76.8% TR-069 CWMP chatter, FM alarm lines, lifecycle, boot PM-ish | CM/FM (NOT PM) | 60s, strict | NO: watcher consumes only `*.tgz`, real uploads are single gzip (collector.go:210) | Parse (section 2): `fm_alarms` + `device_events` + boot PM-ish; raw .gz to MinIO |
| `ErrorLog_*.gz` (FTP push) | Same stream while in error state; only copies of SCTP/SON/L1 fault lines | FM | 60s tick, on-error naming | NO (same defect) | Same single pipeline, dedup on (device, boot_epoch, seq) |
| `*_Devicelog` (FTP, per PowerOn) | Boot/status snapshot: firmware, flash/memory/partition/temperature, IP config, process startup | FM + inventory | Per power-on | NO | `device_events` boot record + inventory refresh; raw to MinIO |
| `*_continuouslogging.tgz` (FTP, per PowerOn) | 10 x 2MB ring of the same OAM stream spanning days, incl. TR-196 FAPService datamodel dumps | FM/CM | Per power-on | Broken-partial: it IS .tgz, but member names yield module=UNKNOWN so only the alarmy fallback fires | Gap-fill source for archive holes (e.g. the 63h Jun 11-13 hole); same parser; raw to MinIO |
| `*_varlog.tgz` | Linux /var/log | Diagnostics | Per power-on; ALL uploads failed in archive (curl 7/25/28) | NO (absent) | Object storage only; RCA fetch |
| `*_reboottraces_{qcom,cpul,cpuh}.tgz` | Crash/reboot traces | FM diagnostics | Per power-on (failed) | NO | Object storage; RCA fetch |
| `*_fsm.log.gz` | FSM9055 modem/DSP log | Diagnostics | Per power-on (failed) | NO | Object storage |
| `*_tmpfiles.txt`, `core-dsp*.tar` | tmp listing, DSP core dumps | Diagnostics | On crash (failed) | NO | Object storage |
| dmcli / TR-069 GPV full tree | 20,261 params: PM-STATS 11,145, CM-CONFIG 3,414, FM 3,212, INVENTORY 1,560, STATUS 803, SECURITY 127 | PM+CM+FM | On demand | Partial (curated subsets below) | Weekly full-tree audit -> `cm_records` origin='ingest'; curated cadences below |
| Telemetry T1 (7 status metrics) | op_state, rf_tx_status, admin_state, s1_status, sctp_status, connected_ues, volte_ues | PM (status) | 30s | YES, as strings | `pm_measurements` numeric |
| Telemetry T2 (RIP + RF in-use) | rip_average/prb/threshold, earfcn_dl_inuse, pci_inuse, rs_power, dl_bw, ul_bw | PM + CM observability | 60s | YES, as strings | `pm_measurements`; in-use RF also mirrored to `cm_records` labels |
| Telemetry T3 (SampleSet + DeviceInfo) | prb_dl/ul, sinr_avg, rrc_conn_mean, rrc_success, thp_dl/ul, uptime, mem, cpu | PM | 5min read / 900s device granularity | YES (strings except derived rrc_success_pct) | `pm_measurements` numeric; add TemperatureSensor paths |
| FaultMgmt CurrentAlarm GPV (T3) | Active alarm set (max 32; 0 at dump time) | FM | 5min | Folded to health only, NOT persisted (OD9) | `fm_alarms` kind='faultmgmt_gpv' |
| FaultMgmt HistoryEvent.{1..64} GPV | Full alarm history records w/ hex AlarmIdentifier, severity, NotificationType | FM | Never polled | NO | `fm_alarms` reconciliation/backfill, kind='history_event' |
| Heartbeat | cwmp_id, serial, product_class, sw_version, last_inform, IPs, op/rf booleans | Inventory | 30s | YES | `nanolink_devices` (unchanged) |
| Config snapshot (24 SnapshotPaths) | Managed CM params, all 24 verified present in dmcli tree (23 writable; MaxTxPower read-only) | CM | 5min + post-command read-back | YES | `cm_records` origin='ingest'/'read_back' |

---

## 6. Field inventories

Detailed per-field contracts live next to this doc:

- `fields_pm.csv`: every PM field with real source or MISSING verdict (the 8 requested dashboard plot fields all resolved; temperature is the one with no polled source today).
- `fields_cm.csv`: the 24 managed params (all present in the dmcli tree) plus the wider writable RAN surface grouped by subtree (e.g. RAN.Mobility 630 params/619 writable, EPC.QoS 423/423, RAN.MAC 288/288, RAN.RF 20/14, NeighborList read-only), with a dashboard grouping proposal.
- `fields_fm.csv`: the 7 observed hex alarm ids, the device's 15-entry SupportedAlarm catalogue with declared severities, FaultMgmt GPV tables, and the agent rules.yaml event types, each with persistence target and today-vs-target handling.
