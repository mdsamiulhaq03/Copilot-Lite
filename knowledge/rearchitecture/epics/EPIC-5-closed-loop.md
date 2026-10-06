# EPIC 5 — Closed loop end-to-end + the rollback demo

**Epic ID:** E5
**Title:** Closed loop end-to-end + the rollback demo (marketing blocker #3)
**Goal:** Wire, verify, observe, and demo the full CloudlyNet closed loop: RAN Intelligence proposal
→ Network Digital Twin evaluation + policy gate → actuation via the NanoLink TR-069 plane → verified
ack → feedback → KPI watch → automatic rollback. Deliver the scripted, deterministic rollback demo
that `artifacts/marketing/README.md` blocker #3 calls "the highest-leverage sales asset in the
company" (line 111: "No scripted, reliable rollback demo exists").
**Dependencies:** E2 (NDT decision hub, evaluate API, loop tables + Kafka consumers on bdt_engine),
E3 (RIC layer — referenced only as the lab-demo variant, not exercised here), E4 (smo_sim actuator
adapter framework `app/actuators/`, NanoLink adapter, loop-action consumer + feedback hook).
**Frozen HLD:** `docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md` — §3 hard constraints,
§4 shared contracts, AND Appendix A (proposal/action/feedback payloads, adapter keys, migration
numbering) are binding. This epic never redefines a §4/Appendix A contract; where it details a
shape those leave open (audit/lineage API, the policy seed), that detail is flagged inline and in
the epic summary. E2's loop status machine and `loop_actions` row shape are authoritative
everywhere in this epic.

**Execution order:** S1 → S6 → S3 → S2 → S4 → S5. (S5 can run any time after S3's contract is fixed.)

**Definition of done (epic):**
- All four §4.1 topics exist in BOTH provisioning paths (local `init-topics.sh` and the ArgoCD kafka
  chart topics-job values) with identical partition counts; the pre-existing rapp-train partition
  drift (local 4 vs chart 2) is resolved.
- `test/e2e/test_closed_loop.py` passes against a docker-compose stack (profiles: default + `apps` +
  `edgeagent`), covering: ES inference → proposal → NDT evaluate + auto policy gate → loop action →
  smo_sim NanoLink command → edge agent → mock CWMP device (testsuite) → verified ack → feedback →
  NDT audit closed; and: injected SINR degradation → KPI-window watch → automatic rollback →
  verified read-back.
- NDT exposes the loop audit-trail query API (list + lineage); every loop hop logs with a correlated
  request_id; Prometheus counters exist for every loop stage on the existing `/metrics` endpoints.
- `scripts/demo/closed_loop_rollback.sh` runs green twice in a row from a clean `compose.sh down`,
  on docker-compose alone, without the `ric-lab` profile, in under ~10 minutes, and prints the full
  audit trail.
- `artifacts/migration/015_ndt_loop_policy.sql` (seed-only, against E2's `loop_policies` table)
  applies cleanly and idempotently; every existing tenant gets a default loop policy
  (`mode='approval'`).
- `artifacts/frontend/loop_actions_api.md` published for the frontend team (contract note only).
- Zero CI/CD change: no new charts/pipelines/images/ports; the only chart touch is the kafka chart
  `values.yaml` topic list (values-only, explicitly allowed); all consumers ride existing containers;
  lab-only pieces (testsuite, demo) are compose-profile-only.

---

## E5.S1 — Provision the four loop/ingest topics in both provisioning paths

**ID:** E5.S1 · **Title:** Kafka topic provisioning + partition-drift alignment · **Size:** S

**Why:** The closed loop rides `maveric.loop.proposal.v1` / `maveric.loop.action.v1` /
`maveric.loop.feedback.v1`, and the Data Platform rides `maveric.ingest.pm.v1` (§4.1). Today only
the two train topics are provisioned, and the two provisioning paths already disagree on
`maveric.rapp.train.v1` partitions (local default 4 in `scripts/kafka/init-topics.sh:6` vs 2 in the
kafka chart `topicManagement`), a drift the recon flagged as "two sources of truth".

**Ownership:** this story is the OWNER-OF-RECORD for topic provisioning in `init-topics.sh` and the
chart values. E1.S2, E2.S6, and E3.S5 are worded as "ensure the topic line exists (add only if
E5.S1 has not landed)"; if any of them already added an `ensure_topic` line, this story
deduplicates and aligns it to the table below rather than appending a second entry.

**Scope**
- In: add the four §4.1 topics to `scripts/kafka/init-topics.sh`; add the same four to
  `submodule/maveric-deployment/argocd/maveric_platform_kafka/values.yaml` `topicManagement.topics`
  (values-only edit — the existing `templates/topics-job.yaml` hook renders them; no template change);
  align `RAPP_PARTITIONS` local default 4 → 2 to match the chart; document message keying.
- Out: any chart template/pipeline/image change; consumer/producer code (E2/E4 own the consumers);
  changing partitions of existing topics in the chart.

**Files**
- `scripts/kafka/init-topics.sh` (modify)
- `submodule/maveric-deployment/argocd/maveric_platform_kafka/values.yaml` (modify — values only)

**Contract** (topic table; §4.1 names are frozen, partition/keying detail is E5's addition)

| Topic | Partitions (both paths) | RF | retention.ms | Message key |
|---|---|---|---|---|
| `maveric.ingest.pm.v1` | 2 | 1 | 604800000 | `tenant_id` |
| `maveric.loop.proposal.v1` | 1 | 1 | 604800000 | `tenant_id` |
| `maveric.loop.action.v1` | 1 | 1 | 604800000 | `{tenant_id}:{target}` (per-device ordering) |
| `maveric.loop.feedback.v1` | 1 | 1 | 604800000 | `tenant_id` |
| `maveric.rapp.train.v1` | 2 (was local-default 4) | 1 | 604800000 | unchanged (round-robin) |
| `maveric.bdt.train.v1` | 2 (unchanged) | 1 | 604800000 | unchanged |

Alignment decision: the chart is authoritative (prod runs 2 partitions, rApp worker replicaCount
baseline 2). Lower the local default; keep the `RAPP_TRAIN_TOPIC_PARTITIONS` env override so
`scripts/kafka/kafka-scale.sh 3` users can still raise it locally. Note in a comment that
`--alter --partitions` can only grow a topic, so existing local clusters at 4 stay at 4 (harmless).

**Key snippets**

`scripts/kafka/init-topics.sh` (after the existing defaults; keep the existing `ensure_topic` helper):

```sh
# Chart topicManagement is the source of truth for partition counts (prod runs 2).
# Override locally via env if you scale rapp-worker beyond 2 (kafka-scale.sh).
RAPP_PARTITIONS="${RAPP_TRAIN_TOPIC_PARTITIONS:-2}"
BDT_PARTITIONS="${BDT_TRAIN_TOPIC_PARTITIONS:-2}"
INGEST_PM_PARTITIONS="${INGEST_PM_TOPIC_PARTITIONS:-2}"
LOOP_PARTITIONS="${LOOP_TOPIC_PARTITIONS:-1}"
```

```sh
ensure_topic "maveric.ingest.pm.v1"     "$INGEST_PM_PARTITIONS"
ensure_topic "maveric.loop.proposal.v1" "$LOOP_PARTITIONS"
ensure_topic "maveric.loop.action.v1"   "$LOOP_PARTITIONS"
ensure_topic "maveric.loop.feedback.v1" "$LOOP_PARTITIONS"
```

`argocd/maveric_platform_kafka/values.yaml` — append under `topicManagement.topics` (mirror the
existing entries' shape exactly):

```yaml
    - name: maveric.ingest.pm.v1
      partitions: 2
      replicationFactor: 1
      config:
        retention.ms: "604800000"
    - name: maveric.loop.proposal.v1
      partitions: 1
      replicationFactor: 1
      config:
        retention.ms: "604800000"
    - name: maveric.loop.action.v1
      partitions: 1
      replicationFactor: 1
      config:
        retention.ms: "604800000"
    - name: maveric.loop.feedback.v1
      partitions: 1
      replicationFactor: 1
      config:
        retention.ms: "604800000"
```

**Acceptance criteria**
- `./scripts/kafka/compose.sh infra` then `docker compose logs kafka-init` shows all six topics
  ensured; `kafka-topics --describe` lists the four new topics with the table's partition counts.
- `helm template submodule/maveric-deployment/argocd/maveric_platform_kafka` renders the topics-job
  with all six topics (no template diff, values diff only).
- `scripts/kafka/init-topics.sh` and the chart agree on every topic's partition count.
- git diff in `maveric-deployment` touches only `argocd/maveric_platform_kafka/values.yaml`.

**Test plan**
- Unit: none (shell + values).
- Integration: fresh `docker network create maveric || true; ./scripts/kafka/compose.sh infra`;
  assert `docker exec kafka kafka-topics --bootstrap-server kafka:9092 --list` contains the four
  new topics; `helm template` (or `yq '.topicManagement.topics[].name'`) check on the chart.

**Coding-agent prompt**

```
You are working in the CloudlyNet dev repo (repo root = cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md §4.1 first — topic names there are frozen.

TASK: provision four new Kafka topics in BOTH provisioning paths and fix a partition-count drift.

1. Edit scripts/kafka/init-topics.sh:
   - Change RAPP_PARTITIONS default from 4 to 2 (comment: chart topicManagement is authoritative;
     env override retained for local kafka-scale.sh use; note --alter only grows partitions).
   - Add env-driven defaults INGEST_PM_PARTITIONS (default 2) and LOOP_PARTITIONS (default 1).
   - After the two existing ensure_topic calls, add ensure_topic calls for:
     maveric.ingest.pm.v1 ($INGEST_PM_PARTITIONS), maveric.loop.proposal.v1,
     maveric.loop.action.v1, maveric.loop.feedback.v1 (all $LOOP_PARTITIONS).
   - Add --describe lines for the new topics mirroring the existing ones.
2. Edit submodule/maveric-deployment/argocd/maveric_platform_kafka/values.yaml ONLY (values-only
   chart change; do NOT touch templates/, Chart.yaml, or any other chart): append the four topics
   to topicManagement.topics with partitions {ingest.pm: 2, loop.*: 1}, replicationFactor 1,
   retention.ms "604800000" — mirror the existing entries' YAML shape exactly.
   Do NOT change the partitions of the two existing train topics in the chart.
3. Verify: bring up infra (docker network create maveric || true;
   ./scripts/kafka/compose.sh infra), then
   docker exec kafka kafka-topics --bootstrap-server kafka:9092 --list
   must include all six maveric.* topics.

CONSTRAINTS: zero CI/CD change beyond the values.yaml topic list; no new files; no template edits;
maveric-deployment is a git submodule — cd into it before any git operation there. Commit style:
"[chore]: kafka: provision loop/ingest topics in init-topics.sh + chart values; align rapp
partitions to 2". Do not stage submodule pointer changes in the parent repo.

DONE WHEN: both paths list all six topics with matching partition counts and the only
maveric-deployment diff is the kafka chart values.yaml.
```

---

## E5.S2 — Closed-loop end-to-end wiring test (compose, mock CWMP device)

**ID:** E5.S2 · **Title:** E2E wiring test: ES inference → proposal → NDT gate → NanoLink action →
verified ack → feedback → watch → rollback · **Size:** L

**Why:** E2/E3/E4 each deliver a segment of the loop; nothing yet proves the segments compose. This
story delivers the repeatable proof: a pytest harness that drives the whole chain on docker-compose
with the edge agent talking to the testsuite's mock CWMP device, and asserts the KPI-window watch
rolls back when the mock device degrades SINR.

**Scope**
- In: extend the edge-agent testsuite mock device (PM SampleSet parameters + a fault-injection
  endpoint); plumb `TESTSUITE_MODE` through docker-compose (lab-only compose edit, allowed); a new
  self-contained pytest harness at `test/e2e/`; EXTEND E3.S5's emitter
  (`app/services/loop_emitter.py`) with a tick-scope emission path behind the same flags (never a
  parallel emitter module - one producer per topic); small fixture CSVs for a tiny 2-cell network.
- Out: any CI wiring (the harness is run manually / by the demo); the NONRTRIC `ric-lab` profile /
  A1 path (explicitly excluded — TR-069 path only); frontend; changes to public gateway-routed API envelopes
  (the emitter must not alter `/rapps/**` response bytes — it is a side effect behind an env flag).

**Files**
- `submodule/cloudlynet_edgeagent/testsuite/main.go` (modify — mock device PM params + injection endpoint)
- `docker-compose.yaml` (modify — `TESTSUITE_MODE` env passthrough on `cloudlynet-edgeagent-testsuite`)
- `submodule/maveric_platform_rapp/app/services/loop_emitter.py` (modify — E3.S5's module; add `emit_tick_proposal(...)` alongside `emit_day_proposal`; do NOT create a parallel emitter file)
- `submodule/maveric_platform_rapp/tests/test_loop_emitter.py` (extend — tick-scope emission cases)
- `test/e2e/pyproject.toml`, `test/e2e/conftest.py`, `test/e2e/test_closed_loop.py`,
  `test/e2e/fixtures/{topology.csv,config.csv,ue_training_data.csv,synthetic_dataset.csv}`,
  `test/e2e/README.md` (create)

**Contract**

1. Topic payloads: ALL loop payload shapes are FROZEN in HLD Appendix A; this story asserts, it
   never redefines. `maveric.loop.action.v1` is §4.1 verbatim with Appendix A.2 field contents
   (`policy_ref` object; cell- or device-scoped `target`; `payload.rollback_of` marks rollbacks) —
   E5 adds only ADDITIVE OPTIONAL fields `proposal_id`, `request_id`, `created_at` (consumers
   ignore unknown fields). The proposal payload is Appendix A.1
   (`{event, version, proposal_id, tenant_id, source{service, rapp_id, rapp_model_id, run_id},
   refs{baseline_id, bdt_id, ue_dataset_id, scope}, per_tick_recommendations[{tick int,
   items[{cell_id, el_degree, on_off}]}], kpi_summary, target_adapter_hint, created_at}`; key =
   tenant_id). The feedback payload is Appendix A.3 (`{schema, feedback_id, action_id, tenant_id,
   adapter, kind: apply|kpi_window|guardrail_breach|rollback, status, command_id, kpis, detail,
   observed_at}`; key = tenant_id). Fixture assertions in this story validate consumed messages
   against these exact shapes: `kind=apply` mirrors smo_sim `AckIn`/`AckResult`
   (`submodule/maveric_platform_smo_sim/app/schemas/nybsys_edge_dto.py:154-164`) inside `detail`;
   `kind=kpi_window` is emitted by smo_sim's telemetry path (E4.S3's kpi_window hook) for devices
   with an in-window applied loop action; `kind=guardrail_breach` when the device-level watcher
   fires. The executor-side command payload the NanoLink adapter produces after translation is
   CommandPayload-shaped: `{"type": "configure", "writes": [{"path", "value"}], "verify": {...},
   "rollback_on_fail": true}` (`nybsys_edge_dto.py:125-135`).

2. Action↔command linkage (smo_sim side, per E4.S2/S3): the loop-action consumer creates the
   command via `command_service.create_command(db, tenant_id=..., device_id=...,
   body=CommandIn(...), created_by="loop", origin="loop", loop_action_id=action_id,
   policy_ref=...)`; the e2e asserts on `commands.origin = 'loop'` AND
   `commands.loop_action_id = <action_id>` (NEVER on `created_by` string prefixes - E4 sets
   `created_by="loop"`, not `loop:{action_id}`), which is how `complete()` acks map back to
   `action_id` for `kind=apply` feedback.

3. ES→NanoLink mapping: OWNED BY THE EXECUTOR ADAPTER per HLD Appendix A.2 (smo_sim E4.S2), not by
   rapp. rapp emits the Appendix A.1 proposal with cell-scoped recommendations; the NanoLink
   adapter resolves the cell to a device via smo_sim setting `NANOLINK_CELL_DEVICE_MAP` and
   translates `on_off=false/true` to ReferenceSignalPower `LOOP_ES_POWER_SAVE_DBM` (default `-20`)
   / `LOOP_ES_POWER_NORMAL_DBM` (default `-10`) writes (smo_sim settings, E4.S2). For the e2e,
   compose sets `NANOLINK_CELL_DEVICE_MAP={"cell_1": "<demo device uuid>"}` on smo_sim. On the
   rapp side this story only extends E3.S5's emitter with a tick-scope emission path behind the
   SAME flags (`LOOP_PROPOSALS_ENABLED` env + `tenants.feature_flags['loop_proposals']`).

4. Testsuite mock device additions (`testsuite/main.go`): seed the PeriodicStatistics SampleSet
   parameters the agent's T3 collector reads
   (`goagent/internal/collector/metrics.go:55-73`), plus AdminState:

```
Device.Services.FAPService.1.FAPControl.LTE.AdminState                  = "1"
Device.PeriodicStatistics.SampleSet.1.Parameter.316.X_8C1F64_CurrentValue = "42.0"   // prb_dl_pct
Device.PeriodicStatistics.SampleSet.1.Parameter.315.X_8C1F64_CurrentValue = "18.0"   // prb_ul_pct
Device.PeriodicStatistics.SampleSet.1.Parameter.412.X_8C1F64_CurrentValue = "12.5"   // sinr_avg_db (healthy)
Device.PeriodicStatistics.SampleSet.1.Parameter.10.X_8C1F64_CurrentValue  = "6"      // rrc_conn_mean
Device.PeriodicStatistics.SampleSet.1.Parameter.118.X_8C1F64_CurrentValue = "35.2"   // thp_dl
Device.PeriodicStatistics.SampleSet.1.Parameter.119.X_8C1F64_CurrentValue = "9.8"    // thp_ul
Device.PeriodicStatistics.SampleSet.1.Parameter.168.X_8C1F64_CurrentValue = "120"    // RRC.AttConnEstab
Device.PeriodicStatistics.SampleSet.1.Parameter.170.X_8C1F64_CurrentValue = "118"    // RRC.SuccConnEstab (98.3%)
Device.DeviceInfo.UpTime = "86400", MemoryStatus.Free = "180000", MemoryStatus.Total = "256000",
Device.DeviceInfo.ProcessStatus.CPUUsage = "17"
```

   New injection endpoint on `:9000` in BOTH `cloudMux` and `acsHealthMux` (pass `dev` into
   `cloudMux`): `POST /device/params` with body `{"<full TR-069 path>": "<string value>"}` →
   `dev.set(...)` → `{"ok": true, "written": N}`. This is how tests/demo degrade SINR
   (`Parameter.412... = "-5.0"`) and restore it.

5. docker-compose: on `cloudlynet-edgeagent-testsuite.environment` add
   `TESTSUITE_MODE: ${EDGEAGENT_TESTSUITE_MODE:-full}` (default preserves today's behavior; the
   e2e/demo run uses `acsftp` so the testsuite serves ONLY the mock device + FTP and the agent
   talks to the real gateway via the existing `CLOUDLYNET_EDGE_BASE_URL` override,
   `docker-compose.yaml:436`).

**Key snippets**

`testsuite/main.go` injection endpoint (add to both muxes):

```go
// POST /device/params — test/demo fault injection: overwrite mock-device TR-069 params.
mux.HandleFunc("/device/params", func(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodPost {
        w.WriteHeader(http.StatusMethodNotAllowed)
        return
    }
    var kv map[string]string
    if err := json.NewDecoder(r.Body).Decode(&kv); err != nil {
        w.WriteHeader(http.StatusBadRequest)
        return
    }
    writes := make([][2]string, 0, len(kv))
    for k, v := range kv {
        writes = append(writes, [2]string{k, v})
    }
    dev.set(writes)
    writeJSON(w, http.StatusOK, map[string]any{"ok": true, "written": len(writes)})
})
```

rapp emitter extension (`app/services/loop_emitter.py`, E3.S5's module) — interface, not implementation:

```python
def emit_tick_proposal(
    db: Session,
    *,
    tenant_id: str,
    rapp_id: str,
    rapp_model_id: str,
    run_id: str,
    baseline_id: str,
    bdt_id: str,
    ue_dataset_id: str,
    tick: int,
    recommendation_items: list[dict],   # [{cell_id, el_degree, on_off}] from the tick result "text" payload
    adapter_hint: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Optional[str]:
    """Tick-scope sibling of E3.S5's emit_day_proposal, same flags
    (settings.LOOP_PROPOSALS_ENABLED AND tenants.feature_flags['loop_proposals']),
    same frozen payload (HLD Appendix A.1) with refs.scope = {"type": "tick", "tick": tick}
    and per_tick_recommendations = [{"tick": tick, "items": recommendation_items}]
    (tick as int). Returns the proposal_id on publish, None when gated. Never raises
    into the inference path (log + swallow; /rapps/** responses stay byte-identical).
    Reuses E3.S5's payload builder - one producer, one shape, no parallel module."""
```

`test/e2e/test_closed_loop.py` — staged assertions (single test, ordered stages; `wait_until`
helper polls with timeout):

```python
@pytest.mark.slow
def test_closed_loop_auto_apply_and_rollback(stack, demo_tenant, edge_device_online):
    # A. seed: upload fixture CSVs to minio, register baseline + ue dataset (smo_sim :8002)
    # B. train tiny BDT (maxiter<=10) then tiny ES model (minimal timesteps); poll status=ready
    # C. PUT ndt loop policy {mode: auto, watch_window_min: 5} (bdt-engine :8000, X-API-Key)
    # D. POST rapp /infer tick-scope with LOOP_PROPOSALS_ENABLED=true env on the rapp container
    #    and tenants.feature_flags['loop_proposals'] set for the demo tenant
    #    -> assert a proposal lands on kafka (consumer fixture) matching HLD Appendix A.1
    #       field-for-field (source block, refs.scope type=tick, integer ticks)
    # E. wait_until: NDT action exists for the proposal, status in {approved, dispatched, applied}
    # F. wait_until: smo_sim commands row with origin='loop' AND loop_action_id=<action_id>
    #    reaches status=applied (never assert on created_by string prefixes)
    #    AND ack readback confirms ReferenceSignalPower=-20 on the mock device (testsuite GPV)
    # G. assert kind=apply feedback consumed by NDT: action status=applied (audit API)
    # H. inject degradation: POST testsuite :9000/device/params {Parameter.412...: "-5.0"}
    # I. wait_until: action status=rolled_back (NDT KPI watch or device-level watcher; either
    #    path must converge on rolled_back with a verified read-back of the previous value)
    # J. GET /v1/tenants/{t}/ndt/loop/actions/{id}?include=lineage -> proposal, evaluation,
    #    action, >=2 feedback entries (ack + breach/window), rollback action present
```

The fast variant `test_loop_from_canned_proposal` skips A/B/D and POSTs the proposal directly to
`POST /v1/tenants/{t}/ndt/loop/proposals` (§4.2) — same assertions from E onward.

**Acceptance criteria**
- `TESTSUITE_MODE=acsftp` testsuite serves the mock CWMP device + `/device/params` + `/health` only;
  default `full` behavior is unchanged (existing testsuite consumers unaffected).
- With the `edgeagent` profile up (`EDGEAGENT_TESTSUITE_MODE=acsftp`,
  `CLOUDLYNET_EDGE_BASE_URL=http://gateway:8080`) and a seeded edge key, the agent registers against
  the real gateway→smo_sim path and T3 telemetry carries `sinr_avg_db` and `rrc_success_pct` from
  the mock device's SampleSet params.
- Full staged test passes: apply is verified by CWMP read-back; injected SINR `-5.0` (below the
  `min_sinr_db=0` floor) triggers rollback; final lineage is complete; audit shows `rolled_back`.
- Emitter flags off ⇒ zero behavioral diff in rapp (`/rapps/**` responses byte-identical; no Kafka
  publish); emitter unit tests cover tick-scope gating + the Appendix A.1 payload shape (integer
  ticks, nested source block) without a broker (producer mocked). The ES on_off → ReferenceSignalPower
  write translation is the NanoLink adapter's (E4.S2), covered by E4's adapter tests and asserted
  end-to-end here via stage F's CWMP read-back.
- No new deployables: proposal emission runs in the existing rapp API container; all consumers ride
  existing containers (per E2/E4).

**Test plan**
- rapp unit: `cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest tests/test_loop_emitter.py`
- testsuite: `cd submodule/cloudlynet_edgeagent/testsuite && go test ./...` (add a small test for
  `/device/params` handler if a test file exists; otherwise build check `go build ./...`)
- agent regression: `cd submodule/cloudlynet_edgeagent && go test ./...`
- E2E: `./scripts/kafka/compose.sh up` then
  `EDGEAGENT_TESTSUITE_MODE=acsftp CLOUDLYNET_EDGE_BASE_URL=http://gateway:8080 docker compose --profile edgeagent up -d --build`
  then `cd test/e2e && uv run pytest -v -m slow` (fast variant: `uv run pytest -v -k canned`).

**Coding-agent prompt**

```
You are in the CloudlyNet dev repo (repo root = cloudlynet_ai). MANDATORY pre-reads:
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (§3 constraints, §4 contracts) and
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-5-closed-loop.md story E5.S2 (payload shapes,
mock-device parameter list, staged test outline). E2/E4 have landed the NDT decision hub
(bdt_engine) and the smo_sim actuator framework + loop-action consumer; discover their exact module
paths in the code before wiring.

TASK: deliver the closed-loop end-to-end wiring test on docker-compose.

1. submodule/cloudlynet_edgeagent/testsuite/main.go:
   - Seed newDevice() with the PM SampleSet parameters listed in the epic story (Parameter indexes
     316/315/412/10/118/119/168/170 under Device.PeriodicStatistics.SampleSet.1., plus AdminState,
     UpTime, MemoryStatus.Free/Total, CPUUsage). Healthy sinr (412) = "12.5".
   - Add POST /device/params (JSON map path->string, applies dev.set, returns {"ok":true,
     "written":N}) to BOTH cloudMux and acsHealthMux; pass *device into cloudMux to do so.
   - Keep TESTSUITE_MODE semantics unchanged (full|acsftp|acs).
2. docker-compose.yaml: add TESTSUITE_MODE: ${EDGEAGENT_TESTSUITE_MODE:-full} to the
   cloudlynet-edgeagent-testsuite service environment. No other compose changes.
3. rapp (submodule/maveric_platform_rapp): EXTEND E3.S5's emitter
   app/services/loop_emitter.py with emit_tick_proposal(...) per the epic snippet (same flags:
   settings.LOOP_PROPOSALS_ENABLED AND tenants.feature_flags['loop_proposals']; same frozen
   payload, HLD Appendix A.1, with refs.scope {"type": "tick", "tick": n} and integer ticks;
   reuse E3.S5's payload-building code - do NOT create app/services/loop_proposal_emitter.py or
   any parallel emitter/module; one producer per topic). Hook it after tick-scope ES inference
   completes (app/api/v1/endpoints/rapps.py) so failures NEVER propagate to the HTTP response —
   the /rapps/** public contract must stay byte-compatible. The ES on_off -> ReferenceSignalPower
   mapping is NOT rapp's job: the smo_sim NanoLink adapter owns it (HLD Appendix A.2; set
   NANOLINK_CELL_DEVICE_MAP='{"cell_1": "<demo device uuid>"}' on the smo_sim compose env for the
   e2e). Platform logger, type hints, Pydantic-first per CLAUDE.md. Extend
   tests/test_loop_emitter.py (mock the producer).
4. Create test/e2e/ in the PARENT repo: pyproject.toml (deps: pytest, httpx, kafka-python-ng,
   psycopg[binary], boto3), conftest.py (fixtures: service URLs/API keys from env with compose
   defaults bdt=localhost:8000, smo=localhost:8002, rapp=localhost:8001, testsuite=localhost:9000,
   postgres=localhost:5432; wait_until helper; kafka consumer helper; demo tenant seeding via psql;
   edge_device seeding = sha256 of the api_key inside
   submodule/cloudlynet_edgeagent/.env.example's enrollment token, inserted into public.edge_devices
   for the test tenant), fixtures/ tiny 2-cell CSVs (topology.csv, config.csv,
   ue_training_data.csv with cell_id, avg_rsrp, lon, lat, cell_el_deg columns, synthetic_dataset.csv
   with ue_id, lon, lat, tick, day columns), test_closed_loop.py implementing the staged test in the
   epic story (stages A-J) plus the fast canned-proposal variant. NOT wired into any CI.
5. test/e2e/README.md: exact run steps (compose up, edgeagent profile env overrides, uv run pytest).

CONSTRAINTS: zero CI/CD change; no new containers/ports (testsuite :9000 is already published); do
not modify gateway code; do not touch the ric-lab profile or its NONRTRIC containers; /rapps/** responses must stay
byte-identical; cd into each submodule before git operations; never stage parent-repo submodule
pointer bumps.

DONE WHEN: (a) go test ./... passes in cloudlynet_edgeagent and its testsuite builds; (b) rapp unit
tests pass via PYTHONPATH=app:app/radplib/dependencies uv run pytest; (c) on a compose stack with
the edgeagent profile in acsftp mode, cd test/e2e && uv run pytest -v passes both the canned and
slow tests, demonstrating verified apply AND automatic rollback after POST /device/params sets
Parameter.412 to "-5.0".
```

---

## E5.S3 — Loop observability: audit-trail API, log correlation, stage counters

**ID:** E5.S3 · **Title:** Audit trail query API on NDT + X-Request-ID correlation + Prometheus loop
counters · **Size:** M

**Why:** A closed loop nobody can inspect is a liability: the demo (S4) must print lineage, the
frontend (S5) needs a queryable action list, and operators need per-stage counters to see where a
loop stalls. §4.2 gives only `GET /ndt/loop/actions/{id}`; this story adds the list + lineage
surface and the cross-service correlation plumbing.

**Scope**
- In: NDT list endpoint + `include=lineage` expansion on the get endpoint; `request_id` propagation
  through all loop topic payloads and into each service's existing request-ID logging pattern
  (gateway mints `X-Request-Id`, `submodule/maveric_platform_gateway/internal/middleware/middleware.go:75`;
  FastAPI services already carry `request.state.request_id` and echo `X-Request-ID`); Prometheus
  counters per loop stage on existing `/metrics` endpoints in rapp, bdt_engine, smo_sim.
- Out: gateway exposure of `/ndt/**` (explicitly a later optional story per §4.2); Grafana/alerting;
  new metrics ports; tracing spans (gateway tracing is a stub today).

**Files**
- `submodule/maveric_platform_bdt_engine/app/api/v1/endpoints/ndt_loop.py` (modify — E2 created it;
  if E2 chose a different path, extend E2's module instead, do not create a parallel router)
- `submodule/maveric_platform_bdt_engine/app/models/loop_models.py` (modify/create — lineage models)
- `submodule/maveric_platform_bdt_engine/app/db/loop_repository.py` (modify — list/lineage queries)
- `submodule/maveric_platform_bdt_engine/app/utils/loop_metrics.py` (create)
- `submodule/maveric_platform_rapp/app/utils/loop_metrics.py` (create)
- `submodule/maveric_platform_smo_sim/app/utils/loop_metrics.py` (create)
- consumer touchpoints for counter increments + request_id binding: E2's NDT consumers/watch loop,
  E4's smo_sim loop-action consumer + feedback hook, S2's rapp emitter
- unit tests per service under each `tests/`

**Contract** (detail beyond §4.2 — flagged)

```
GET /v1/tenants/{tenant_id}/ndt/loop/actions
    ?status=<proposed|suppressed|rejected_by_gate|pending_approval|approved|rejected|dispatched
             |applied|failed|watching|completed|rolled_back|expired>   (E2's status machine, authoritative)
    &target=<device_id or cell_id>&since=<iso8601>&until=<iso8601>&limit=50&offset=0
  -> 200 {"items": [LoopActionOut], "total": <int>}     (X-API-Key, RLS-scoped, newest first)

GET /v1/tenants/{tenant_id}/ndt/loop/actions/{action_id}?include=lineage
  -> 200 LoopActionOut                        (no include — §4.2 shape, unchanged)
  -> 200 LoopLineageOut                       (include=lineage)
```

Responses use bdt_engine's existing envelope/error-handler conventions (same as `/bdt/**`).
`request_id` field rules: HTTP entry points take it from `request.state.request_id`; Kafka consumers
read it from the message and bind it into the service logger's existing request-ID ContextVar before
processing, so one loop pass greps as a single id across rapp, bdt_engine, and smo_sim logs.

Prometheus (one counter per service, stage-labeled; registered on the default registry already
exposed at `/metrics`):

```
cloudlynet_loop_stage_events_total{stage, tenant_id, outcome}
  rapp stages:       proposal_emitted
  bdt_engine stages: proposal_received, evaluated, policy_gated, action_dispatched,
                     feedback_received, watch_breach, rollback_ordered
  smo_sim stages:    action_received, command_created, action_executed, feedback_published
  outcome: ok|error|skipped (policy_gated: auto|approval|off; action_executed: applied|failed|rolled_back)
```

**Key snippets**

```python
# app/models/loop_models.py (bdt_engine) — additions
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel

# E2's loop_actions row shape and status machine are AUTHORITATIVE; this model mirrors
# them 1:1 (no invented names: pending_approval not awaiting_approval, prev_action_id not
# rollback_of, target/policy_ref are JSON objects matching E2's jsonb columns).
LoopActionStatus = Literal[
    "proposed", "suppressed", "rejected_by_gate", "pending_approval", "approved",
    "rejected", "dispatched", "applied", "failed", "watching", "completed",
    "rolled_back", "expired",
]


class LoopActionOut(BaseModel):
    action_id: str
    tenant_id: UUID
    proposal_id: Optional[str] = None
    kind: Literal["change", "rollback"] = "change"
    source: Optional[dict[str, Any]] = None        # proposal source block
    adapter: str
    target: dict[str, Any]                         # {"cell_id", "tick"} or {"device_id"} (jsonb)
    status: LoopActionStatus
    payload: dict[str, Any]
    policy_ref: Optional[dict[str, Any]] = None    # policy snapshot (jsonb), never a str
    evaluation: Optional[dict[str, Any]] = None    # {"run_id", "verdict", "reasons"}
    prev_action_id: Optional[str] = None           # rollback rows: the action being reverted
    expires_at: Optional[datetime] = None
    dispatched_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    watch_deadline: Optional[datetime] = None
    error: Optional[str] = None
    request_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class LoopLineageOut(BaseModel):
    """Full loop lineage: proposal -> evaluation -> action -> feedback[] -> rollback."""
    proposal: Optional[dict[str, Any]] = None      # loop_proposals.payload (E2.S6 persists intake)
    evaluation: Optional[dict[str, Any]] = None    # loop_actions.evaluation + the matching ndt_kpi_snapshots row (source='loop_gate')
    action: LoopActionOut
    feedback: list[dict[str, Any]] = []            # loop_feedback.payload rows (E2.S7 persists), oldest first
    rollback: Optional[LoopActionOut] = None       # action with prev_action_id == action_id
```

```python
# app/utils/loop_metrics.py (same shape in all three services; only STAGES docstring differs)
from __future__ import annotations

from prometheus_client import Counter

LOOP_STAGE_EVENTS = Counter(
    "cloudlynet_loop_stage_events_total",
    "Closed-loop lifecycle events by stage",
    ["stage", "tenant_id", "outcome"],
)


def observe_stage(stage: str, tenant_id: str, outcome: str = "ok") -> None:
    LOOP_STAGE_EVENTS.labels(stage=stage, tenant_id=tenant_id, outcome=outcome).inc()
```

```python
# repository signature (bdt_engine app/db/loop_repository.py)
def list_actions(
    db: Session, *, tenant_id: str, status: str | None, target: str | None,
    since: datetime | None, until: datetime | None, limit: int, offset: int,
) -> tuple[list[dict], int]: ...

def load_lineage(db: Session, *, tenant_id: str, action_id: str) -> dict | None:
    """Join loop_proposals + loop_actions + loop_feedback (E2.S6/S7 tables, which persist
    raw proposal/feedback payloads) + ndt_kpi_snapshots (source='loop_gate') for the
    evaluation slot + the prev_action_id self-join for the rollback slot."""
```

**Acceptance criteria**
- List endpoint filters/paginates correctly under RLS; `?include=lineage` returns the five lineage
  slots; a non-lineage GET is byte-identical to E2's §4.2 shape.
- After one full loop pass (S2 fast test), a single `request_id` value appears in rapp, bdt_engine,
  and smo_sim structured logs for that pass.
- `/metrics` on rapp/bdt_engine/smo_sim exposes `cloudlynet_loop_stage_events_total` and one full
  loop pass increments: proposal_emitted, proposal_received, policy_gated{outcome="auto"},
  action_dispatched, action_received, command_created, action_executed{outcome="applied"},
  feedback_published, feedback_received; a rollback pass adds watch_breach + rollback_ordered +
  action_executed{outcome="rolled_back"}.
- No new endpoints outside `/v1/tenants/{t}/ndt/loop/**`; no gateway changes.

**Test plan**
- bdt_engine: `cd submodule/maveric_platform_bdt_engine && uv run pytest` (new tests: list filters,
  lineage assembly with a seeded chain, counter increments via `prometheus_client` REGISTRY inspection).
- smo_sim: `cd submodule/maveric_platform_smo_sim && uv run pytest` (feedback publish increments
  counters; request_id bound from consumed message).
- rapp: `cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest`.
- Integration: covered by S2 stage J + a curl of all three `/metrics` in the S4 demo.

**Coding-agent prompt**

```
You are in the CloudlyNet dev repo (repo root = cloudlynet_ai). MANDATORY pre-reads:
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (§4.2 NDT API contract is frozen) and
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-5-closed-loop.md story E5.S3. EPIC-2 delivered
the NDT decision hub in submodule/maveric_platform_bdt_engine (loop tables, proposal consumer,
policy gate, watch loop) and EPIC-4 the smo_sim loop-action consumer + feedback hook — locate their
modules first and EXTEND them; create nothing parallel.

TASK: loop observability in three parts.
1. Audit API (bdt_engine): add GET /v1/tenants/{tenant_id}/ndt/loop/actions (filters status, target,
   since, until, limit<=200 default 50, offset; response {"items": [...], "total": n}, newest first)
   and ?include=lineage on GET /v1/tenants/{tenant_id}/ndt/loop/actions/{action_id}. Use the
   LoopActionOut/LoopLineageOut Pydantic models from the epic story. X-API-Key auth at router level
   and RLS set_current_tenant exactly like the existing /bdt endpoints. The plain get without
   include must remain byte-identical to E2's response.
2. Correlation: ensure every loop topic payload carries optional request_id (additive field);
   at HTTP entry points source it from request.state.request_id (existing middleware); in every
   Kafka consumer (NDT proposal/feedback consumers, smo_sim action consumer, watch loop) bind the
   message's request_id into that service's existing request-ID logging ContextVar
   (app/utils/logger.py in each service) before processing, generating uuid4 when absent.
3. Metrics: create app/utils/loop_metrics.py in rapp, bdt_engine, smo_sim with the shared
   cloudlynet_loop_stage_events_total Counter (labels: stage, tenant_id, outcome) + observe_stage()
   helper per the epic snippet, and instrument the stages listed in the epic table at the exact
   points where each stage completes. The existing /metrics endpoints already serve the default
   registry — no new ports, no new endpoints for metrics.

CONVENTIONS: Pydantic-first, full type hints, platform logger, DRY (one loop_metrics module per
service, no copy-paste divergence beyond the stages docstring). Tests: bdt_engine & smo_sim via
`uv run pytest` in each submodule; rapp via `PYTHONPATH=app:app/radplib/dependencies uv run pytest`.

CONSTRAINTS: zero CI/CD change; no gateway edits (gateway /ndt/** exposure is a later story); do not
alter §4.1/§4.2 contract shapes — request_id and lineage are additive; cd into each submodule for
git operations.

DONE WHEN: unit tests pass in all three services; on a compose stack one loop pass shows a single
request_id across all three services' logs and increments the documented counter stages on
/metrics of :8000, :8001, :8002.
```

---

## E5.S4 — THE ROLLBACK DEMO (scripted, deterministic, compose-only)

**ID:** E5.S4 · **Title:** `scripts/demo/closed_loop_rollback.sh` + demo docs · **Size:** L

**Why:** Marketing blocker #3 (`artifacts/marketing/README.md:111`): "No scripted, reliable rollback
demo exists — the highest-leverage sales asset in the company, and it is unbuilt." This story builds
it: one command, docker-compose only, TR-069 path only, deterministic, repeatable, ends by printing
the audit trail.

**Scope**
- In: demo orchestration script + library + README/talk-track; deterministic demo tenant + edge-key
  seeding (SQL via the postgres container); demo policy (auto mode, 5-minute watch window); canned
  "recommendation" proposal (labeled honestly as standing in for a live model recommendation; the
  full model path is exercised by `test/e2e`, which the doc links); degradation injection; audit
  trail print; counter snapshot print; reset logic so back-to-back runs pass.
- Out: `ric-lab` profile / NONRTRIC / A1 anything (the doc carries one pointer paragraph to the
  E3 A1-path lab-demo variant, wording per claims guardrails); kubernetes; frontend; video assets.

**Files**
- `scripts/demo/closed_loop_rollback.sh` (create, executable)
- `scripts/demo/lib.sh` (create — step/log/poll/psql/curl helpers)
- `scripts/demo/README.md` (create — run instructions + talk track + troubleshooting)

**Contract** (script behavior)

- Fixed identities: demo tenant `00000000-0000-0000-3029-0000000000de` ("Closed Loop Demo",
  `feature_flags = {"nybsys": true}`); edge identity reused from the agent's committed
  `.env.example` enrollment token (`submodule/cloudlynet_edgeagent/.env.example`): the script decodes
  the token (base64url JSON `{tenant_id, edge_id, base_url, api_key}`), computes
  `sha256(api_key)`, and upserts `public.edge_devices (edge_id, tenant_id, name, api_key_hash,
  status)` under the DEMO tenant (auth resolves tenant from this row, not from the token —
  `smo_sim/app/services/nybsys/edge_auth.py:46-80`), so no dynamic token plumbing is needed.
- Service access: host-published ports, direct with per-service `X-API-Key` read from each
  submodule's local `.env` (bdt-engine `localhost:8000`, smo_sim `localhost:8002`, rapp
  `localhost:8001`, testsuite `localhost:9000`); the edge agent path goes through the real gateway
  in-network (`CLOUDLYNET_EDGE_BASE_URL=http://gateway:8080`). Gateway `/ndt/**` exposure is not
  required (later optional story per §4.2).
- Steps (each prints a numbered banner, polls with explicit timeout, exits non-zero on timeout):
  1. Preflight: `docker network create maveric || true`; `./scripts/kafka/compose.sh up`; wait for
     `/health` on gateway, bdt-engine, rapp, smo-sim; verify the four loop topics exist (S1).
  2. Seed: apply `artifacts/migration/015_ndt_loop_policy.sql` (idempotent, seed-only; requires
     E2's `014_ndt_loop.sql` applied first) via
     `docker exec -i postgres psql -U <user> -d maveric`; upsert demo tenant + edge_devices row;
     set `NANOLINK_CELL_DEVICE_MAP='{"cell_1": "<demo device uuid>"}'` on the smo_sim compose env;
     cancel any stale `pending` demo commands; POST testsuite `/device/params` to restore healthy
     SINR (`Parameter.412... = "12.5"`) so re-runs start clean.
  2b. Seed twin refs (the E2 gate ALWAYS runs a real twin evaluation; there is no skip path):
     idempotently create a tiny demo baseline (3-cell topology/config/UE-training CSVs uploaded to
     the S3 convention keys + a `baselines` row, `baseline_id=demo-loop-baseline`) and a small UE
     dataset (`ue_dataset_id=demo-loop-dataset`); `POST /v1/tenants/{t}/bdt/train`
     (`bdt_id=demo-loop-bdt`) and poll until `ready` (tiny GP, seconds; skip when already `ready`
     from a prior run). Export the three ids for step 5. This keeps the demo honest: the twin
     really gates the change.
  3. Policy: `PUT /v1/tenants/{t}/ndt/loop/policy` body
     `{"mode": "auto", "guardrails": {"min_sinr_db": 0, "min_rrc_success_pct": 95, "max_outage_rate": 0.05}, "watch_window_min": 5}`.
  4. Device online: `EDGEAGENT_TESTSUITE_MODE=acsftp CLOUDLYNET_EDGE_BASE_URL=http://gateway:8080
     docker compose --profile edgeagent up -d --build`; poll smo_sim
     `GET /v1/tenants/{t}/custom/nybsys/devices` until the device appears with recent KPIs
     (`sinr_avg_db` present).
  5. Apply recommendation (auto mode): `POST /v1/tenants/{t}/ndt/loop/proposals` (§4.2) with a
     canned proposal in the FROZEN HLD Appendix A.1 shape (tick scope, one item
     `{"cell_id": "cell_1", "el_degree": 0.0, "on_off": false}`, `target_adapter_hint`
     `nanolink_tr069`, and `refs` carrying the step-2b ids `demo-loop-baseline` /
     `demo-loop-bdt` / `demo-loop-dataset` so the gate's twin evaluation has real inputs); the NanoLink adapter translates `on_off=false` into the
     ReferenceSignalPower `-10 → -20` write for the bound device (Appendix A.2 seam,
     `NANOLINK_CELL_DEVICE_MAP` from step 2); poll the audit API until the action is `applied`;
     print the CWMP-verified read-back from the apply feedback.
  6. Inject degradation: POST testsuite `/device/params` `{"...Parameter.412...": "-5.0"}`; print
     "device now reporting SINR -5.0 dB (below the 0 dB guardrail floor)".
  7. Watch → rollback: poll the audit API until the action is `rolled_back` (budget: 2 × T3 interval
     + watch tick + command round-trip; cap 5 min); print the rollback action's verified read-back
     showing ReferenceSignalPower restored to `-10`.
  8. Audit trail: `GET .../ndt/loop/actions/{id}?include=lineage`; pretty-print the
     proposal → evaluation → action → feedback → rollback chain (jq), plus a
     `cloudlynet_loop_stage_events_total` snapshot from the three `/metrics` endpoints.
- Determinism levers: agent cadences are already fast in the committed compose config
  (`submodule/cloudlynet_edgeagent/config/agent.yaml`: T3 30s, poll 2s, verify 3s); demo watch
  window 5 min; NDT watch tick configurable (E2.S7 env `LOOP_WATCH_TICK_SECONDS`, default 60s) — demo
  asserts outcomes, never sleeps blind.
- Flags: `--keep` (skip teardown; default keeps stack up), `--reset-only`, `--skip-build`.

**Key snippets**

```bash
#!/usr/bin/env bash
# CloudlyNet closed-loop rollback demo. Docker Compose only. NanoLink TR-069 path.
# Applies a recommendation in auto mode, injects a KPI breach on the mock device,
# and shows the Network Digital Twin ordering an automatic, verified rollback.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$REPO_ROOT/scripts/demo/lib.sh"

DEMO_TENANT_ID="00000000-0000-0000-3029-0000000000de"
NDT_URL="${NDT_URL:-http://localhost:8000}"
SMO_URL="${SMO_URL:-http://localhost:8002}"
TESTSUITE_URL="${TESTSUITE_URL:-http://localhost:9000}"
SINR_PARAM="Device.PeriodicStatistics.SampleSet.1.Parameter.412.X_8C1F64_CurrentValue"
RSP_PARAM="Device.Services.FAPService.1.CellConfig.LTE.RAN.RF.ReferenceSignalPower"
```

```bash
# lib.sh essentials
step()       { printf '\n== %s ==\n' "$*"; }
wait_until() { # wait_until <timeout_s> <desc> <cmd...>; polls every 3s
  local t="$1" desc="$2"; shift 2
  local deadline=$((SECONDS + t))
  until "$@"; do
    (( SECONDS < deadline )) || { echo "TIMEOUT: $desc" >&2; return 1; }
    sleep 3
  done
}
psql_maveric() { docker exec -i postgres psql -v ON_ERROR_STOP=1 -U "$PGUSER" -d maveric "$@"; }
ndt()          { curl -fsS -H "X-API-Key: $BDT_API_KEY" -H "Content-Type: application/json" "$@"; }
```

```bash
step "5/8 apply recommendation (auto mode)"
ACTION_ID=$(ndt -X POST "$NDT_URL/v1/tenants/$DEMO_TENANT_ID/ndt/loop/proposals" -d "$(proposal_json)" \
  | jq -r '.data.proposal_id' | poll_action_for_proposal)
wait_until 120 "action applied" action_has_status "$ACTION_ID" applied
print_readback "$ACTION_ID"   # CWMP GPV read-back: ReferenceSignalPower = -20 (verified)
```

`scripts/demo/README.md` content rules (this text is marketing-bound):
- Follow `artifacts/marketing/claims-guardrails.md` §everything. Say: "closed loop on the NanoLink
  TR-069/CWMP device plane", "Network Digital Twin policy gate and KPI watch", "verified read-back".
  Never say: O-RAN / RIC / SMO compliance, carrier-grade, zero-touch. The A1 paragraph must read:
  the same loop can dispatch A1-policy-aligned intents through the RAN Intelligence RIC layer
  (proposal with `target_adapter_hint=a1_policy` -> NDT gate -> rapp `a1_policy` executor ->
  NONRTRIC A1-PMS -> A1 Simulator) with the lab-only `ric-lab` compose profile (O-RAN SC NONRTRIC
  A1-PMS + A1 Simulators, Apache-2.0 container images, see E3 docs); this demo intentionally uses
  only the TR-069 path.
- No em dashes (U+2014). Product name CloudlyNet. Solution term Network Digital Twin. State plainly
  that the demo proposal is a canned recommendation standing in for a live model output, and that
  `test/e2e/test_closed_loop.py` exercises the full ES-model path.

**Acceptance criteria**
- From `./scripts/kafka/compose.sh down` + volume-clean state:
  `./scripts/demo/closed_loop_rollback.sh` exits 0 in ≤10 min, printing all eight banners, the
  verified apply read-back (`-20`), the breach notice, the verified rollback read-back (`-10`), the
  full lineage JSON, and the counters snapshot.
- Running it a second time immediately (no down) also exits 0 (reset logic works).
- No `ric-lab` profile referenced or required; profiles used: default, `apps`, `edgeagent` only.
- `shellcheck scripts/demo/*.sh` clean (or documented suppressions).
- README passes a claims review: no forbidden claims, no em dashes, correct naming.

**Test plan**
- `bash -n` + `shellcheck` on both scripts.
- Manual double-run per acceptance criteria on a clean checkout (documented in README).
- The demo itself is the integration test; component coverage lives in S2/S3 suites.

**Coding-agent prompt**

```
You are in the CloudlyNet dev repo (repo root = cloudlynet_ai). MANDATORY pre-reads, in order:
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (§4.2 NDT API),
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-5-closed-loop.md story E5.S4 (script contract),
artifacts/marketing/claims-guardrails.md (binding for every sentence in the README).
Prereqs already merged: E5.S1 topics, E5.S2 testsuite /device/params + e2e harness, E5.S3 audit
API + counters, E5.S6 migration 011. Verify each exists before starting; stop and report if not.

TASK: build the scripted closed-loop rollback demo.
1. Create scripts/demo/lib.sh (helpers: step, wait_until with timeout, psql_maveric via docker exec
   into the postgres container, curl wrappers injecting X-API-Key read from
   submodule/maveric_platform_bdt_engine/.env and submodule/maveric_platform_smo_sim/.env, jq
   pretty-printers for the lineage and metrics snapshot).
2. Create scripts/demo/closed_loop_rollback.sh (executable) implementing exactly the 8 steps in the
   epic story: preflight/compose up + topic check; idempotent seed (apply
   artifacts/migration/015_ndt_loop_policy.sql - seed-only, requires E2's 014_ndt_loop.sql
   applied first - upsert demo tenant
   00000000-0000-0000-3029-0000000000de with feature_flags {"nybsys": true}, decode the enrollment
   token in submodule/cloudlynet_edgeagent/.env.example, sha256 its api_key, upsert
   public.edge_devices under the demo tenant, set NANOLINK_CELL_DEVICE_MAP for cell_1 -> the demo
   device on the smo_sim env, cancel stale pending demo commands, restore healthy
   SINR via POST http://localhost:9000/device/params); PUT ndt loop policy mode=auto
   watch_window_min=5; start the edgeagent profile with EDGEAGENT_TESTSUITE_MODE=acsftp and
   CLOUDLYNET_EDGE_BASE_URL=http://gateway:8080 and poll smo_sim devices until KPIs flow; POST the
   canned proposal in the FROZEN HLD Appendix A.1 shape (tick scope, item {cell_id: "cell_1",
   el_degree: 0.0, on_off: false}, target_adapter_hint nanolink_tr069; the NanoLink adapter
   translates it to the ReferenceSignalPower -10 -> -20 write) to
   /v1/tenants/{t}/ndt/loop/proposals and poll
   the audit API to applied, printing the verified read-back; inject
   {"Device.PeriodicStatistics.SampleSet.1.Parameter.412.X_8C1F64_CurrentValue": "-5.0"}; poll to
   rolled_back and print the restored read-back; print full ?include=lineage JSON + a
   cloudlynet_loop_stage_events_total snapshot from :8000 :8001 :8002 /metrics. Flags: --keep,
   --reset-only, --skip-build. Every wait is a bounded poll; no blind sleeps.
3. Create scripts/demo/README.md: one-command quickstart, what the audience sees at each step, talk
   track, troubleshooting (agent not registering -> check edge_devices seed; no rollback -> check
   watch window/policy), a short honest note that the canned proposal stands in for a live model
   recommendation (full model path: test/e2e/test_closed_loop.py), and ONE paragraph noting the
   lab-demo variant: the A1 path (proposal with target_adapter_hint=a1_policy -> NDT gate -> rapp
   a1_policy executor -> NONRTRIC A1-PMS -> A1 Simulator) under the lab-only ric-lab compose
   profile (O-RAN SC NONRTRIC, Apache-2.0 images; never claim A1/O-RAN/RIC compliance). ABSOLUTE RULES for the
   README: no em dash characters (U+2014) anywhere; product name CloudlyNet; solution term Network
   Digital Twin; no O-RAN/RIC/SMO-compliance, carrier-grade, or zero-touch claims.

CONSTRAINTS: docker-compose only (profiles default/apps/edgeagent); MUST NOT require the ric-lab
profile; no new services, ports, images, charts, or CI; parent-repo files only (scripts/demo/*);
bash with set -euo pipefail; shellcheck-clean.

DONE WHEN: from a clean `./scripts/kafka/compose.sh down`, the script exits 0 end-to-end in <=10
minutes AND exits 0 again on an immediate second run; the README passes the claims checklist above.
```

---

## E5.S5 — Frontend hook: loop-action approve/reject contract note

**ID:** E5.S5 · **Title:** API contract note for the frontend approve/reject surface · **Size:** S

**Why:** In `approval` mode, loop actions park as `pending_approval` (E2's status machine, authoritative) and need an operator surface.
The frontend already renders exactly this UX for NanoLink self-optimizer recommendations
(recommendation cards with approve/reject, backed by
`POST /custom/nybsys/recommendations/{reco_id}:approve|:reject`); the frontend team needs the NDT
equivalent documented now so they can plan, with zero frontend implementation in this epic.

**Scope**
- In: one contract note in `artifacts/frontend/` (the designated home for frontend design docs per
  CLAUDE.md) documenting list/get/approve/reject shapes, states, polling guidance, and the reuse
  mapping onto the existing recommendation-cards pattern.
- Out: any frontend code; any gateway route (the note states plainly that `/ndt/**` is not yet
  gateway-exposed and names that as the blocking dependency); any new NDT endpoint implementation
  (approve/reject handlers are E2 decision-hub scope; if E2 shipped without them, file the gap
  against E2 — this story only writes the contract down).

**Files**
- `artifacts/frontend/loop_actions_api.md` (create)

**Contract** (documented in the note; the endpoints and shapes are E2.S8's, quoted verbatim —
E2's status machine and row shape are authoritative; states and list shape come from E5.S3)

```
GET  /v1/tenants/{tenant_id}/ndt/loop/actions?status=pending_approval&limit=50&offset=0
  -> {"items": [LoopActionOut], "total": n}
GET  /v1/tenants/{tenant_id}/ndt/loop/actions/{action_id}?include=lineage
POST /v1/tenants/{tenant_id}/ndt/loop/actions/{action_id}:approve
  -> 200 {"action_id": "...", "status": "dispatched"}   (approve transitions
     pending_approval -> approved -> dispatched in one call, per E2.S8)
POST /v1/tenants/{tenant_id}/ndt/loop/actions/{action_id}:reject
  -> 200 {"action_id": "...", "status": "rejected"}
  404 {"detail": "ACTION_NOT_FOUND"} | 409 {"detail": "ACTION_NOT_PENDING"}
     (409 when the action is no longer pending_approval, e.g. expired/dispatched)
```

State machine for the card UI (E2's machine, authoritative):
`pending_approval → approved → dispatched → applied → watching → (completed | rolled_back)`,
`dispatched → failed`, plus terminal `rejected` / `expired` and the gate outcomes
`suppressed` / `rejected_by_gate` (list-only, no card actions); `expires_at` from the §4.1
action payload drives a countdown chip.

**Key snippets** (note skeleton)

```markdown
# Loop actions: approve/reject surface (contract note)

Status: contract note only. No frontend work is scheduled in EPIC-5.
Blocking dependency: gateway exposure of /ndt/** (optional later story per the frozen HLD §4.2).
Until it lands, these endpoints are reachable only service-to-service with the BDT X-API-Key.

## Reuse: recommendation-cards pattern
Map 1:1 onto the existing NanoLink recommendation cards
(devices dashboard; approve -> POST :approve, reject -> POST :reject, optimistic
update + poll). Differences: source is the Network Digital Twin decision hub, payload
is an adapter-addressed write set (not a device recommendation row), and the card must
render lineage (proposal source, evaluation KPIs, expiry countdown from expires_at).

## Endpoints ...(shapes above)...
## Polling: list every 30 s while the approvals tab is visible; lineage on card expand.
```

Copy rules: product CloudlyNet, Network Digital Twin naming, no em dashes, no O-RAN/RIC/SMO
compliance claims (this doc seeds future UI copy).

**Acceptance criteria**
- Note exists at `artifacts/frontend/loop_actions_api.md`, covers all four endpoints + state
  machine + reuse mapping + the gateway-exposure dependency callout.
- Endpoint shapes are consistent with S3's implemented list/lineage API and §4.1/§4.2 (no invented
  fields beyond the flagged approve/reject pair).
- Claims/naming rules pass review; no em dashes.

**Test plan**
- Doc review only: cross-check every field against `app/models/loop_models.py` (S3) and §4; run a
  claims-guardrails checklist pass.

**Coding-agent prompt**

```
You are in the CloudlyNet dev repo (repo root = cloudlynet_ai). Pre-reads:
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md §4.1-§4.2,
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-5-closed-loop.md stories E5.S3 + E5.S5,
artifacts/marketing/claims-guardrails.md, and the implemented models in
submodule/maveric_platform_bdt_engine/app/models/loop_models.py (source of truth for field names).
Also skim the existing frontend recommendation-cards flow
(submodule/maveric_platform_frontend, devices dashboard + smo_sim endpoints
POST /custom/nybsys/recommendations/{id}:approve|:reject) so the reuse mapping is concrete.

TASK: write artifacts/frontend/loop_actions_api.md, a contract note for the frontend team covering
the loop-action approval surface. Include: (1) status banner saying this is a contract note, no
frontend implementation in EPIC-5, and that gateway exposure of /ndt/** is the blocking dependency;
(2) the four endpoints (list filtered by status=pending_approval, get with ?include=lineage,
POST {action_id}:approve -> 200 {action_id, status: "dispatched"} per E2.S8, POST
{action_id}:reject -> 200 {action_id, status: "rejected"}, with 404 ACTION_NOT_FOUND / 409
ACTION_NOT_PENDING) with request/response JSON examples matching LoopActionOut/LoopLineageOut
exactly (E2's status machine and row shape are authoritative); (3) the action state machine
pending_approval -> approved -> dispatched -> applied -> watching -> (completed | rolled_back),
dispatched -> failed, terminal rejected/expired plus list-only suppressed/rejected_by_gate,
expires_at countdown; (4) a 1:1 reuse mapping table onto the existing
recommendation-cards pattern; (5) polling guidance (list 30 s, lineage on expand).

HARD COPY RULES: no em dash characters (U+2014); product name CloudlyNet; solution term Network
Digital Twin; never claim O-RAN/RIC/SMO compliance. Do NOT implement anything; if the :approve/
:reject handlers are missing from bdt_engine, add a "gap: file against EPIC-2 decision hub" line
rather than writing code.

DONE WHEN: the note exists, every field name matches the implemented Pydantic models, and it passes
the copy rules above.
```

---

## E5.S7 — Gateway exposure of `/ndt/**` (ADDED 2026-08-04)

**ID:** E5.S7 · **Title:** Route the closed-loop API through the gateway · **Size:** S

**Why:** This was the plan's one genuinely unowned item. Frozen HLD §4.2 calls gateway exposure of
`/ndt/**` "a later optional story"; E2.S6, E2.S8, E5.S2, E5.S3 and E6.S1 each defer to it by name,
and E2's own risk register (risk 7) states plainly that "frontend integration needs the gateway
story". No epic ever claimed it. It stayed invisible while the loop was server-to-server only, and
became load-bearing the moment E5.S5's approvals surface was built: `apiClient` talks to the
gateway, bdt_engine's `X-API-Key` is server-side only, and there is no route around it. The screen
could not fetch one row.

It is no longer optional, so it is a story with acceptance criteria rather than a drive-by edit.

**Scope**
- In: one `registerProxy` line for the `/ndt` prefix in `cmd/gateway/main.go`; the route-list test;
  correcting every doc that still calls this a later optional story.
- Out: any new gateway middleware, auth scheme, or upstream (all four already exist); `X-User-Id`
  forwarding (the gateway still mints no operator identity - E2.S8's `updated_by` stays nullable,
  which is a separate gap); rate-limit tuning.

**Contract**

```
/v1/tenants/{tenant_id}/ndt/**  ->  bdt_engine (pr.BDT upstream)
```

Not a proxy of `/bdt`. `/ndt` is its own first-class prefix that happens to share an upstream,
because bdt_engine IS the Network Digital Twin service - there is no separate deployable and never
was. `pr.BDT` is the variable holding its URL, nothing more.

Three properties come free from the existing group, and all three were verified rather than assumed:

- **AuthN/AuthZ.** The prefix registers on the same `/v1/tenants/:tenant_id` group as `/bdt` and
  `/rapps`, which carries `middleware.RequireMembership(database)` and `middleware.TrialWriteGuard()`
  (`cmd/gateway/main.go:209`). Cognito JWT plus tenant membership, identical to every sibling.
- **The service key never reaches the browser.** `proxy.apiKeyForTarget` matches on the BDT target
  and injects `BDT_API_KEY` server-side (`internal/proxy/proxy.go:77-78`).
- **Path fidelity.** `normalizeProxyPath` only trims a trailing slash, so
  `/v1/tenants/{t}/ndt/loop/actions/{id}:approve` arrives at bdt_engine verbatim, colon verb intact.

**Files**
- `submodule/maveric_platform_gateway/cmd/gateway/main.go` (modify - one line)
- `submodule/maveric_platform_gateway/cmd/gateway/main_test.go` (modify - route-list assertion)

**Acceptance criteria**
- `go test ./cmd/...` passes with `/v1/tenants/:tenant_id/ndt` and `.../ndt/*path` asserted present.
- Against a running stack, `GET /v1/tenants/{t}/ndt/loop/actions` through the gateway returns the
  loop list, not a 404.
- No new gateway middleware, no new upstream, no auth change: the diff is one `registerProxy` call.
- Every doc that called this "a later optional story" is corrected, including frozen HLD §4.2's
  parenthetical and E6.S1's OpenAPI tag description (which would otherwise publish a false claim).

**Execution status: DONE 2026-08-04.** `go test ./cmd/...` green. Verified live through the gateway
on the compose stack: the list came back carrying the e2e's own action row. The 200 seen without a
bearer token is `DEV_BYPASS_JWT`, which is local-dev only per CLAUDE.md; `RequireMembership` is what
runs everywhere else. Closes E2 risk 7.

---

## E5.S6 — Loop guardrail defaults + tenant policy seeding migration

**ID:** E5.S6 · **Title:** `015_ndt_loop_policy.sql`: per-tenant default policy seed (seed-only,
against E2's `loop_policies`) · **Size:** S

**Why:** The §4.2 policy API (`GET|PUT /ndt/loop/policy`) needs a row per tenant with safe defaults;
without seeding, the first loop pass for an existing tenant would hit the fail-closed policy-miss
path (`mode='off'`). Defaults must mirror the proven device-level guardrails
(`smo_sim/app/services/nybsys/self_optimizer.py:32`: `min_sinr_db 0, min_rrc_success_pct 95`, 15-min
watch) so the two defense layers agree. E2 owns the `loop_policies` table (created by
`014_ndt_loop.sql` and E2.S6's ORM); this migration is SEED-ONLY.

**Scope**
- In: idempotent seed-only SQL migration in `artifacts/migration/` inserting a default policy row
  into E2's `loop_policies` for every existing tenant; README execution-index entry; note that
  deployed-env application is manual (CLAUDE.md: data migration is manual) — the ArgoCD postgres
  chart SQL packs are NOT touched (that would exceed the values-only chart allowance).
- Out: ANY DDL (no CREATE TABLE, no ALTER, no RLS statements — `loop_policies`, `loop_actions`,
  `loop_proposals`, `loop_feedback` are E2-owned and created by `014_ndt_loop.sql`; a seed
  migration that also creates tables would fork the schema); demo-tenant seeding (S4 script does
  that, including flipping the demo tenant to `auto` — the migration seeds `approval` for everyone
  and never `auto`).

**Files**
- `artifacts/migration/015_ndt_loop_policy.sql` (create)
- `artifacts/migration/README.md` (modify — append 015 to the execution index)

**Contract** (seed rows only; the table name, columns, and defaults are E2's — copied verbatim
from E2's landed `014_ndt_loop.sql` at authoring time; if E2's landed DDL differs from the sketch
below, E2 wins and this file is corrected)

```sql
-- 015_ndt_loop_policy.sql — Network Digital Twin closed-loop policy: per-tenant default seeding.
-- SEED-ONLY: the loop_policies table is created by 014_ndt_loop.sql (EPIC-2, owner); this file
-- performs no DDL. Idempotent; safe to re-run. Never seeds 'auto'.
-- Guardrail defaults mirror smo_sim's device-level GUARD constants so both defense layers agree.
-- min_sinr_db=0 is the placeholder floor pending RF sign-off (smo_sim OD4).
-- Note: a superuser DSN silently bypasses the FORCE RLS that 014 applies (known 009-era footgun).

INSERT INTO public.loop_policies (tenant_id, mode, guardrails, watch_window_min)
SELECT t.tenant_id,
       'approval',
       '{"min_sinr_db": 0, "min_rrc_success_pct": 95, "max_outage_rate": 0.05}'::jsonb,
       15
FROM public.tenants t
ON CONFLICT (tenant_id) DO NOTHING;
```

Runtime rule (E2 coordination, restated here because the seed depends on it): the decision hub
treats a missing row as `{mode: 'off'}` (fail-closed) and `PUT /ndt/loop/policy` upserts; new
tenants created after the migration get their row lazily on first policy read/write. E2's column
defaults (`mode='off'`) are deliberately NOT changed by this story: the safe-onboarding
`approval` value is seeded per-row here, never baked into the DDL.

**Key snippets** — the migration above is complete; README index entry:

```markdown
### 015_ndt_loop_policy.sql
Network Digital Twin closed-loop policy: per-tenant default seeding into E2's `loop_policies`
(`mode='approval'`, guardrails aligned with the smo_sim device-level GUARD constants,
`watch_window_min=15`). SEED-ONLY (table created by 014_ndt_loop.sql). Idempotent; safe to
re-run. Never seeds `auto`. Apply after 014.
```

**Acceptance criteria**
- The file contains zero DDL statements (`grep -iE "CREATE|ALTER|DROP" artifacts/migration/015_ndt_loop_policy.sql` returns nothing beyond comments).
- Applying twice in a row on a compose database (after `014_ndt_loop.sql`) succeeds with no errors and no duplicate rows.
- Every pre-existing tenant has a row with `mode='approval'`, the exact guardrails jsonb above, and `watch_window_min=15`; no tenant is seeded `auto`.
- Column names/`ON CONFLICT` target match E2's landed `loop_policies` exactly (verified against `014_ndt_loop.sql` and E2's ORM at authoring time; E2 wins on any drift).
- `artifacts/migration/README.md` execution order lists 015 after 014 (numbering per HLD Appendix A.6).

**Test plan**
- Integration (compose): `./scripts/kafka/compose.sh infra`, apply migrations 001-015 in order via
  `docker exec -i postgres psql -U <user> -d maveric -f -`, re-apply 015, assert row counts and RLS
  behavior with `SELECT set_config('app.current_tenant', ...)` probes (RLS itself is 014's DDL).
- bdt_engine unit (E2 suite): `cd submodule/maveric_platform_bdt_engine && uv run pytest` still
  green (policy read path tolerates both seeded and missing rows).

**Coding-agent prompt**

```
You are in the CloudlyNet dev repo (repo root = cloudlynet_ai). Pre-reads:
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md §4.2 (loop policy shape is frozen:
{mode: off|approval|auto, guardrails: {min_sinr_db, min_rrc_success_pct, max_outage_rate},
watch_window_min}) and Appendix A.6 (migration numbering: 014 = E2's loop tables, 015 = this
seed), docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-5-closed-loop.md story E5.S6, and
E2's landed artifacts/migration/014_ndt_loop.sql + the loop_policies ORM in
submodule/maveric_platform_bdt_engine (the table name and columns there are authoritative;
copy them verbatim into the INSERT - never write DDL and never touch the ORM).

TASK:
1. Create artifacts/migration/015_ndt_loop_policy.sql: SEED-ONLY, per the SQL block in the epic
   story - one INSERT INTO public.loop_policies (tenant_id, mode, guardrails, watch_window_min)
   SELECT ... FROM public.tenants ON CONFLICT (tenant_id) DO NOTHING, seeding mode='approval',
   guardrails {"min_sinr_db": 0, "min_rrc_success_pct": 95, "max_outage_rate": 0.05},
   watch_window_min 15. Header comment: seed-only (table created by 014_ndt_loop.sql, EPIC-2
   owner), idempotent, defaults mirror smo_sim GUARD constants
   (app/services/nybsys/self_optimizer.py:32), min_sinr_db=0 is the pre-RF-sign-off placeholder,
   superuser DSN silently bypasses FORCE RLS (known footgun), never seeds 'auto'. Contains NO
   CREATE/ALTER/DROP statement.
2. Append the 015 section to artifacts/migration/README.md's execution order (after 014),
   matching the existing entries' format.
3. Verify on compose: ./scripts/kafka/compose.sh infra; apply 014 then 015 twice via
   docker exec -i postgres psql -U <postgres user from docker-compose.yaml> -d maveric; assert
   one row per tenant, mode='approval', and RLS isolation via set_config probes.

CONSTRAINTS: SEED-ONLY - do NOT create or alter loop_policies/loop_proposals/loop_actions/
loop_feedback (EPIC-2 owns them via 014_ndt_loop.sql; if 014 has not landed, STOP and report);
do NOT touch the ArgoCD postgres chart (deployed-env application is manual per CLAUDE.md); parent
repo files only; migration must be idempotent and re-runnable.

DONE WHEN: double-apply is clean, every tenant is seeded 'approval' with the exact guardrails
jsonb, RLS probes pass, and the README index lists 015 after 014.
```

---

## Rollout / migration notes

Order (matches execution order; each step is independently shippable and reversible):

1. **S1 topics** land first (both paths). Local: re-run `compose.sh infra` (kafka-init is
   idempotent). Cluster: ArgoCD sync of the kafka chart re-runs the topics-job hook; creating new
   topics is non-disruptive; existing train topics are untouched in the chart. Backward compat: no
   consumer exists yet, so empty topics are inert.
2. **S6 migration** next (manual, per the repo's manual data-migration posture): apply
   `015_ndt_loop_policy.sql` AFTER E2's `014_ndt_loop.sql` has created `loop_policies` in the
   target DB (numbering per HLD Appendix A.6: 011=E1, 012/013=E4, 014=E2, 015=this seed). Seeded
   `approval` mode changes nothing behaviorally until an operator (or the demo) opts a tenant into
   `auto`; a missing row fails closed (`off`). Rollback = `DELETE FROM public.loop_policies` for
   the seeded rows (the table itself is E2's; never drop it here).
3. **S3 observability** rides the existing bdt/rapp/smo image streams (code-only). Additive API
   (`GET` list, `include=lineage`) and additive optional Kafka fields; consumers ignore unknown
   fields, so mixed-version rollout is safe in both directions.
4. **S2 harness + testsuite** are lab-only: testsuite/compose changes affect only the `edgeagent`
   compose profile (no chart exists for the edge agent); `TESTSUITE_MODE` defaults preserve current
   behavior. The rapp emitter ships dark (`LOOP_PROPOSALS_ENABLED=false` plus the per-tenant
   `loop_proposals` feature flag, E3.S5's gating) — enabling it is a per-env
   env-var + flag decision, not a deploy.
5. **S4 demo** and **S5 note** are pure additions (scripts + docs); no runtime surface.

No shared-table or S3-key-convention changes anywhere in this epic (§3.3 preserved by construction).
No public gateway-routed contract changes: `/rapps/**`, `/custom/**`, `/v1/agent/**` byte-identical;
all new HTTP surface is under `/v1/tenants/{t}/ndt/loop/**` behind X-API-Key, not gateway-exposed.

## Epic-level risks

1. **Parallel-epic contract skew (highest).** E5 consumes module paths, loop-table names, and the
   approve/reject handlers from E2/E4 that §4 does not pin. Mitigation baked into every story:
   "locate and extend E2/E4's modules, never create parallel ones; E2's ORM wins on table naming";
   S6 is seed-only against E2's landed `loop_policies`. Residual risk: if E2 shipped no approval-mode
   handlers, S5's note carries a filed gap and S4 still works (auto mode only).
2. **Double rollback from defense-in-depth.** Both the NDT KPI watch and smo_sim's device-level
   watcher (`self_optimizer._guardrail_rollback`) can order a rollback for the same breach. The
   rollback restores `prev_values`, so double-apply is effect-idempotent, but the audit trail shows
   both paths. S2 asserts convergence on `rolled_back` regardless of which path won; NDT's watch
   must check-and-skip when a `rolled_back` feedback already arrived (E2 coordination point).
3. **Demo timing determinism.** The chain agent-T3 (30 s) → smo ingest → feedback → NDT watch tick →
   rollback command → agent poll (2 s) → CWMP verify has several cadences; a slow laptop could
   overrun poll budgets. Mitigated by bounded `wait_until` polls with generous caps (5 min for the
   rollback leg), fast committed agent cadences, and a configurable NDT watch tick; the double-run
   acceptance criterion catches flakiness before marketing touches it.
4. **Partition-drift alignment surprises local users.** Dropping the local rapp-train default from
   4 to 2 leaves existing local clusters at 4 (alter can't shrink) — harmless — but users of
   `kafka-scale.sh 3` on FRESH clusters will see one idle worker unless they set
   `RAPP_TRAIN_TOPIC_PARTITIONS=4`; called out in the script comment and S1 README note.
5. **Prometheus label cardinality.** `tenant_id` as a counter label is fine at today's tenant count
   but would bloat at thousands of tenants; acceptable now, noted for the metrics review in E6.
6. **Claims exposure in demo collateral.** The demo README is the most marketing-adjacent artifact
   in the epics; S4's prompt hard-codes the guardrails (no O-RAN/RIC/SMO compliance claims, no em
   dashes, CloudlyNet / Network Digital Twin naming, honest "canned recommendation" framing) and E6
   re-verifies.
7. **`.env.example` edge identity reuse.** The demo seeds `edge_devices` with the committed example
   token's key hash — deterministic and compose-only, but if that example token ever rotates, the
   demo seed must follow; the seed derives the hash from the file at runtime (never hard-coded), so
   rotation is absorbed automatically.

---

## Execution status

In progress, 2026-08-04. **S1, S6 and S3 are done and committed; S2, S4 and S5 remain.**
Nothing is pushed anywhere.

    cloudlynet_ai (parent)        5123169
    maveric_platform_bdt_engine   511b2f4
    maveric_platform_smo_sim      f89c04c
    maveric_platform_rapp         76dd135
    maveric-deployment            e5104da

Test results after S3, all measured with the compose infra up. No new failures anywhere; the
counts below are baseline plus the tests this story added.

| Service | Result | vs `test-baselines.md` |
| --- | --- | --- |
| `maveric_platform_bdt_engine` | 466 passed / 11 failed / 18 skipped | +17 passing, same 11 pre-existing failures |
| `maveric_platform_smo_sim` | 688 passed / 3 failed / 1 skipped | +7 passing, same 3 `test_placement` failures |
| `maveric_platform_rapp` | 418 passed / 5 errors | +5 passing, same 5 missing-MRO-fixture errors |

**bdt_engine's suite now refuses to run against the `maveric` database.** A guard added during
E2 demands a throwaway target; `test-baselines.md`'s recorded command
(`DATABASE_URL=...localhost:5432/maveric`) no longer works for this service. Use
`docker exec postgres createdb -U postgres bdt_engine_test` and point `DATABASE_URL` at that.

### S1 DONE — topic provisioning

Both provisioning paths now carry all six topics with matching partition counts, and the local
rapp-train default is 2, matching the chart.

Three corrections to the story text:

1. **Four of the six topics were already in `init-topics.sh`.** E1.S2 and E2.S6 added them under
   an explicit "E5.S1 owns this; dedupe rather than append" comment, exactly as their stories
   instructed. This story deduplicated and hoisted the inline `${...:-N}` defaults into the named
   variables the story specifies; the per-topic loop overrides collapsed into one
   `LOOP_TOPIC_PARTITIONS`, which is the only rename. No code referenced the old names (only
   EPIC-3's story text, at line 1091, which also disagrees with the S1 table on the proposal
   partition count — the S1 table wins, it is the owner of record).
2. **The story's file list omitted `docker-compose.yaml`, which would have made the change a
   no-op locally.** Compose pins `RAPP_TRAIN_TOPIC_PARTITIONS: ${...:-4}` and passes it into
   kafka-init, so lowering the script default alone changes nothing on the path every developer
   actually uses. Compose now defaults to 2 and also passes through the two new knobs.
3. **`ensure_topic` logged an ERROR on every healthy re-run.** `--alter --partitions` errors when
   the count already matches, and the script swallowed it with `|| true` — so a clean boot printed
   three `InvalidPartitionsException` stack traces. It now reads the current count first and only
   alters when it must grow, printing a plain note when a topic is already wider than the target.

Verified live: `compose.sh infra` then `kafka-topics --list` shows all six; partition counts are
rapp 4 (this cluster predates the change — `--alter` cannot shrink, which is the documented and
harmless case from epic risk 4), bdt 2, ingest.pm 2, and 1 for each of the three loop topics.
`helm template` renders the topics-job with all six and the correct counts; the only
maveric-deployment diff is `argocd/maveric_platform_kafka/values.yaml`.

### S6 DONE — the policy seed

`artifacts/migration/015_ndt_loop_policy.sql` applies cleanly and idempotently (second run is
`INSERT 0 0`), contains no DDL, and every tenant now holds a policy row.

**The story's RLS note is wrong in the direction that matters, and this was measured, not
reasoned.** It calls a non-superuser apply a "silent bypass" footgun. What actually happens is
worse: `public.tenants` is itself FORCE RLS, so under a non-bypassing role the seed's source
`SELECT` returns zero rows, the INSERT reports `INSERT 0 0`, and psql exits 0. It is
indistinguishable from a successful idempotent re-run — the migration appears to have worked and
seeded nothing. Confirmed by running it as `ndt_rls_probe`: no rows, no error.

The file therefore opens with a guard block that raises unless `current_user` is a superuser or
carries `BYPASSRLS`. It is procedural, not DDL, so the "zero DDL" acceptance criterion still
holds. Verified both ways: superuser applies clean, `ndt_rls_probe` fails loudly with exit 3.

Two smaller notes:

- **A pre-existing `loop_policies` row survived untouched.** The local trial tenant was already
  `auto` with custom guardrails from E2 testing. `ON CONFLICT DO NOTHING` left it alone, which is
  the correct behaviour — the seed must never overwrite an operator's choice — and it means "every
  tenant is seeded `approval`" is really "every tenant WITHOUT a policy".
- **`artifacts/migration/README.md` claimed 013 was "reserved, not yet written"** while
  `013_commands_loop_columns.sql` had been on disk since E4.S3. Anyone running the index in order
  would have skipped it. The entry is now written up from the file.

### S3 DONE — observability

Delivered in three parts across three services. The API half was smaller than the story assumed
and the metrics half was larger.

1. **`smo_sim had no prometheus dependency and no `/metrics` route at all.`** The story's scope
   says "Prometheus counters ... on existing `/metrics` endpoints in rapp, bdt_engine, smo_sim"
   and its prompt says "the existing /metrics endpoints already serve the default registry — no
   new ports, no new endpoints for metrics". That is true of rapp and bdt_engine and false of
   smo_sim, which meant the executor hop — the one place a loop stalls between `dispatched` and
   `applied` — was the only unmeasurable one. Added `prometheus-client==0.20.0` to both
   `pyproject.toml` and `requirements.txt`, plus a `/metrics` route on the existing :8002 app.
   Still no new port and no new deployable. Verified serving:
   `cloudlynet_loop_stage_events_total{outcome="ok",stage="action_received",tenant_id="tenant-x"} 1.0`.
2. **E2.S8 had already shipped `GET /actions`** with `status`, `proposal_id` and `kind` filters,
   so the "list endpoint" half of the story was mostly done. What was missing: `target`, `since`,
   `until`, and `?include=lineage`. All are additive; a caller written against E2.S8's signature
   gets the same page. `target` matches `cell_id` OR `device_id`, because a caller holding an id
   does not know which scope the loop used and matching only one would silently return nothing.
3. **`request_id` has no `loop_actions` column and does not get one.** E5 was allocated no
   migration number beyond 015 (seed-only), so the id rides the Kafka payloads and the log
   ContextVars, and its durable copy lives in `loop_proposals.payload` / `loop_feedback.payload`,
   both of which store the raw message. `LoopActionOut.request_id` in the story's key snippet is
   therefore not implemented as a row field; the correlation the acceptance criterion actually
   names — one id across three services' logs — is.
4. **The action envelope gained exactly three keys**, `proposal_id`, `request_id`, `created_at`,
   which is what the S2 contract sanctions. Three tests asserted `set(message) == {frozen keys}`
   and were updated to assert the frozen set is present AND that the difference is a subset of the
   sanctioned three — so they still catch unsanctioned drift. `FROZEN_ACTION_KEYS` and
   `E5_ADDITIVE_ACTION_KEYS` now live in `app/models/ndt_loop_models.py` rather than being
   restated in each test, so a fourth key cannot be smuggled in by editing a test.
5. **ContextVars leak across tests, and the first version of these tests proved it.** A
   `request_id` set by a loop test appeared on an unrelated `test_placement` log line. Each of the
   three services' `tests/conftest.py` now carries an autouse fixture that clears the log context
   around every test. The production consumers do the same between messages, for the same reason:
   a long-lived consumer thread would otherwise log a message that carries no id under the
   PREVIOUS message's id, which reads as correct correlation and is not.

**Watch-item 9 vs the S3 contract, resolved in favour of the contract.** `02-execution-guide.md`
says "keep tenant_id out of high-cardinality labels"; the S3 contract makes `tenant_id` a label and
epic risk 5 accepts it explicitly ("acceptable now, noted for the metrics review in E6"). It is
implemented as the contract specifies, with the cardinality note carried in each
`loop_metrics.py` docstring pointing at E6.

**Not yet verified live:** the acceptance criterion "one `request_id` appears in all three
services' logs for one pass" and "one full loop pass increments the documented stages" both need a
running loop, which is S2's harness. Unit coverage pins each hop's behaviour in isolation
(17 new bdt_engine tests, 7 smo_sim, 5 rapp); the cross-service assertion belongs to S2 stage J.

## Execution status (continued): S2 + S5 done, frontend built, S4 open

2026-08-04, same session. Heads: parent `7dbe8ad`, bdt_engine `511b2f4`, smo_sim `f89c04c`,
rapp `0c7ec02`, edgeagent `4d17f67`, frontend `d0883d7`, maveric-deployment `e5104da`.

### S2 DONE (harness), with the live loop verified only as far as the gate

Delivered: testsuite PM-counter seeding + `/device/params` (POST inject, GET read-back) on both
muxes with 8 Go tests; `emit_tick_proposal` sharing E3.S5's payload builder via a new
`_publish_proposal` core (10 new tests); the job-runner hook; and `test/e2e/` (conftest, fixtures,
two variants, README).

**Verified live on the compose stack:** the six topics exist (asserted from a Kafka client, not
from the init script's log); the testsuite serves the seeded params and the injection round trip
(SINR 12.5 -> -5.0 -> 12.5); the harness seeds its tenant, edge device and NanoLink device, sets
`mode=auto`, POSTs an Appendix A.1 proposal, and the NDT **gates it with a real twin verdict**:
`sinr_p5 -3.1225 < min_sinr_db 0.0000` -> `rejected_by_gate`.

**Not verified live: everything after the gate.** That verdict is correct behaviour, not a defect —
the lab fixture (`lab-bdt-1` / `lab-baseline-1` / `lab-dataset-1`, tenant `...3029-...0001`)
describes a network where turning that cell off genuinely breaches the floor, and the gate is
fail-closed by design. Finishing the run needs a fixture whose twin evaluation PASSES for an
`on_off=false` recommendation. That is the single remaining task for S2, and it is a fixture
problem, not a code one. The harness already fails with that exact message rather than a bare
assertion, so the next session does not have to rediscover it.

Four story-text corrections:

1. **`TESTSUITE_MODE` was already wired** in `docker-compose.yaml`. Step 2 of the prompt is a no-op.
2. **The testsuite is on host port 9100, not 9000** (`${EDGEAGENT_TESTSUITE_PORT:-9100}:9000`; 9000
   is minio's). The story's conftest default would have hit minio.
3. **`nanolink_devices.genieacs_id` is `cwmp_id`** since migration 010. 009's DDL still shows the
   old name and seeding against it fails.
4. **bdt_engine's API key is not `changeme`.** Compose sets `API_KEY=bdt-secret-key-a1b2c3d4e5f6`;
   `changeme` is only the Pydantic field default. The conftest reads it from the running container.

Also: **restarting a container is not enough after editing a module another module already
imported.** bdt_engine served the new `decision_hub.py` against the old cached `app.utils.logger`
and 500'd on `ImportError: cannot name current_request_id`. smo_sim additionally needs a REBUILD,
not a restart, because `prometheus-client` is a new image-level dependency.

### S5 DONE — and the frontend was then built on top of it, at the user's direction

`artifacts/frontend/loop_actions_api.md` covers all four endpoints, the thirteen-state machine, the
recommendation-cards reuse mapping, the error table, polling guidance, and the gateway-exposure
blocker.

**The story scoped frontend code OUT; the user asked for it explicitly mid-session, so it was
built** (frontend `d0883d7`, 8 files, 812 lines): `types/loop.ts`, `lib/ndt/loop-ui.ts` (one status
table, not a switch per component), `lib/api/services/ndt-loop.ts`, `components/ndt/LoopActionCard`
(approve/reject, twin reasons, expiry chip, lineage on expand), `components/ndt/LoopActionsPanel`
(four tabs, 30 s polling that pauses when the tab is hidden), the `/closed-loop` route and a nav
entry. `tsc --noEmit` and `eslint` both clean.

**It cannot work end to end yet and the UI says so.** `apiClient` talks to the gateway and the
gateway does not route `/ndt/**`; the panel catches the 404 and renders "not exposed through the
gateway yet" rather than a generic failure. Gateway exposure is the blocking dependency, and it is
an optional later story under frozen HLD §4.2 — it is now on the critical path for this screen.
`PUT /policy` was left out deliberately: `ApiClient` has no `put` verb and the contract note does
not cover a policy editor.

### S4 NOT STARTED

`scripts/demo/closed_loop_rollback.sh` (marketing blocker #3) is the one E5 story with no work done.
It depends on the same passing-gate fixture S2 needs, so both unblock together.

## Execution status (continued): the unknown-cell defect, the delta fixture, local enrollment

2026-08-04. **S4 remains NOT STARTED.** Three findings that unblock it, all measured live.

### DEFECT (FIXED 2026-08-04, verified live): a proposal naming an unknown cell was dispatched as gate-approved

> **Resolution.** `unscored_recommendations` now takes a required `known_cells` set and rejects any
> `cell_id` outside it; `ndt_runner.topology_cell_ids` supplies it from RAW topology (safe because
> `build_cell_config_frame` only LEFT-merges the config CSV, so the config can never add a cell id).
> The check runs BEFORE the twin, like the tick guard, and fails closed on three conditions: an
> unknown cell, a topology with no `cell_id` column, and a topology that cannot be read. Live
> re-run of the table below now gives `rejected_by_gate` with
> `unscorable_proposal: cell 'cell_1' is not in the baseline topology…`, while `cell_1_0` +
> `cell_1_1` `on_off=false` at tick 4 still dispatches at `sinr_p5` -2.881 → -1.429.
> `run_evaluation` itself is unchanged, so `/ndt/evaluate` called directly still no-ops silently on
> an unknown cell — only the loop gate refuses. The original analysis is kept below as the record.

**A proposal whose `cell_id` does not exist in the baseline topology is scored against the
UNTOUCHED network and returned `verdict: pass`.** The twin silently ignores a config item for a
cell it has never heard of, evaluates the baseline, and the gate - having nothing to compare - sees
healthy KPIs and dispatches. A change is then applied to real hardware carrying an audit record
that says a twin approved it, when the twin evaluated something else.

Measured. `lab-baseline-1`'s cells are `cell_1_0`, `cell_1_1`, `cell_1_2`, `cell_2_0`, ... There is
no `cell_1`. Every proposal in this epic's e2e and every manual probe used `cell_1`:

    cell_id     el_degree  on_off   baseline sinr_p5 -> proposed    verdict
    cell_1       4.0       false    -3.1225 -> -3.1225   (identical) dispatched
    cell_1       2.0       true     -2.6718 -> -2.6718   (identical) dispatched
    cell_1      20.0       true     -2.6718 -> -2.6718   (identical) dispatched

Bit-identical to 4 decimal places across a 10x tilt change is the signature: the config never
reached the twin. This is the same class as the `unscored_recommendations` guard E2.S6 already
carries for unknown TICKS - that guard exists for exactly this failure and does not cover cells.

**The fix belongs in `decision_hub`**, alongside `unscored_recommendations`: reject a proposal whose
cell_ids are not in the evaluated topology. The gate already holds the twin result; the cheapest
correct check is to compare the proposal's cell set against the topology the baseline loaded, and
fail closed on any name it does not recognise. Until then the E5.S3 lineage API is the only way to
see it, by noticing `baseline_kpis == guardrail_kpis` exactly.

### The non-zero-delta fixture (what E5.S4's demo should use)

With REAL cell ids the twin responds, and switching cells off is the change with a demo-sized
effect - it removes interference, so p5 SINR IMPROVES, which is the honest energy-saving story:

    tick 4, cell_1_0 + cell_1_1 on_off=false   sinr_p5  -2.881 -> -1.429   (+1.45 dB)  pass

Tilt alone is nearly inert on this model (`el_degree` 1.0 vs 25.0 moved p5 by 0.0001 dB), so a demo
built on tilt would look broken. **Use `on_off=false` on `cell_1_0` and `cell_1_1` at tick 4.**

The rollback leg does not depend on this delta: it is driven by the DEVICE's `sinr_avg_db`
(injected through the testsuite), not by the twin's p5.

### Local edge-agent enrollment (verified, and not what it looked like)

The chain stalled at `queued` because no `edge_devices` row existed for the token the agent
actually uses. Two tokens are in play and the obvious one is wrong:

- `submodule/cloudlynet_edgeagent/.env.example` carries a production-shaped token.
- **`docker-compose.yaml` overrides it** with a dev token already scoped to the lab tenant:
  `edge_id 11111111-1111-1111-1111-111111111111`, `api_key <edge_id>.devsecret`.

`auth_edge` resolves the tenant from the ROW, not the token, so enrolling is one upsert:

    INSERT INTO public.edge_devices (edge_id, tenant_id, name, api_key_hash, status)
    VALUES ('11111111-1111-1111-1111-111111111111', '<tenant>', 'local-dev-edge',
            'd78f71bdd9f83932adda906b73d558548c00652c8d6b94717de417f26f3e026d', 'online')
    ON CONFLICT (edge_id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id,
        api_key_hash = EXCLUDED.api_key_hash, status = 'online';

After that: 401 INVALID_EDGE_KEY stops, and smo_sim creates the `nanolink_devices` row itself from
the agent's report (`last_inform_at` populated, `health = healthy`) - the real path, not a
hand-seeded row. Note `nanolink_devices.edge_id` is ON DELETE CASCADE, so deleting an edge row
takes its devices with it.

**`test/e2e/conftest.py` reads the wrong file** (`.env.example`) and greps for `CLOUDLYNET_API_KEY`,
which is not in it - so it silently hashed a fallback and enrolled nothing usable. Fix it to decode
the compose token.
