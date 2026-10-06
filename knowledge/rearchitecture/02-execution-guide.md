# CloudlyNet Re-architecture: Execution Guide

Date: 2026-07-16 (updated 2026-07-29) · The hand-off index for the coding agent. 65 stories across
9 epics; E0–E7 critic-verified for cross-epic consistency (17 seam defects found and fixed; payload
contracts frozen in `01-hld-frozen.md` Appendix A; HLD amended v1.1: RIC track pivoted to the
non-RT O-RAN SC NONRTRIC, near-RT reserved; **v1.2: OCUDU-first demo mandate — D5 + §4.7 + EPIC-7;
near-RT placeholder activated for lab via the dockerized OSC RIC**). E8 (copilot MCP layer
coverage) added 2026-07-23, outside the frozen-HLD merge chain; **E8 extended 2026-07-29 with S0
(master response envelope `cloudlynet.mcp.response.v1`) and S8 (Observability/RCA domain), 7 to 9
stories**.

## Reading order

1. `01-hld-frozen.md` — the constitution: decisions D1–D4, hard constraints §3 (including merge
   order §3.5), shared contracts §4, frozen payloads Appendix A, migration numbering A.6.
2. `00-hld-assessment.md` — evidence base: plan-vs-code corrections, CI/CD constraints, spec and
   license research, drift register.
3. The epic file for whatever you are implementing. Every story carries a self-contained
   **Coding-agent prompt** block: hand that block (plus repo access) to the agent; it references
   the frozen HLD for deeper context.

## Epic and story inventory

| Epic | File | Stories | Theme |
|---|---|---|---|
| E0 | `epics/EPIC-0-platform-hygiene.md` | S1–S5 | Gateway panic fix + /custom route split (dark), internal contracts doc, repo-wide rebrand, secrets hygiene |
| E1 | `epics/EPIC-1-data-platform.md` | S1–S8 | Canonical PM/FM/CM schema, ingest framework + Kafka jobs, NanoLink store-only adapter, legacy uploads contract, query APIs, records-envelope consumer |
| E2 | `epics/EPIC-2-ndt-consolidation.md` | S1–S9 | NDT evaluate API, rapp delegation w/ golden-response parity, feature builder, KPI snapshots, decision hub, approval mode, feature-builder cutover |
| E3 | `epics/EPIC-3-ran-intelligence-ric.md` | S1–S8 | RIC ports/adapters (non-RT-first), ric-lab NONRTRIC profile (A1-PMS + A1 Simulator images), A1-PMS connector, a1_policy loop executor, loop proposal emitter, R1-shaped packaging, near-RT placeholder (nearrt_xapp), regression |
| E4 | `epics/EPIC-4-actuation-integration.md` | S1–S7 | E2/R1 deletion, ActuatorAdapter framework, loop executor + feedback, scale-out fixes, placeholder adapters (O1/OCUDU-WS/M-Plane/SAS DP/NMS), uploads decommission, managed-params SoT |
| E5 | `epics/EPIC-5-closed-loop.md` | S1–S6 | Topic provisioning (owner-of-record), e2e wiring test, loop observability + lineage, THE ROLLBACK DEMO, frontend contract note, policy seed |
| E7 | `epics/EPIC-7-ocudu-demo.md` | S1–S7 | OCUDU demo: ran-lab stack (Open5GS + OCUDU ZMQ + srsUE), dockerized OSC RIC + E2, cloudlynet-xapp (nearrt_xapp lab executor, RC PRB-quota), A1 mediator spike + fallback, ocudu_ws PM ingestion, ocudu_rc_loop demo script, O1 track + OCUDU-changes contingency |
| E8 | `epics/EPIC-8-copilot-mcp-layers.md` | S0–S8 | Copilot MCP layer coverage: ONE :8082 server with per-domain tool modules (frozen decision, not N servers) — master response envelope `cloudlynet.mcp.response.v1` returned by every tool in every layer (S0, `artifacts/copilot/mcp-master-payload.md`), JWT/tenant threading fix (kills the hardcoded tenant default), Network Digital Twin + Ingest/Data + Optimization + Actuation/TR-069 (confirm-gated mutations) + Policy & Guardrails + Observability/RCA modules, placeholder retirement, docs lockstep. Merge order: independent of E0–E7, can run any time after E0; depends only on copilot submodule state, except S8 tranche A which needs E1.S1 + E1.S5 |
| E6 | `epics/EPIC-6-docs-and-verification.md` | S1–S6 | Design docs v0.6.0 lockstep, artifacts/oran archival + artifacts/ric bundle, .context refresh, submodule README fixes, claims re-verification, marketing follow-ups |

## Sequencing (hard constraint, frozen HLD §3.5)

```
E0.S4 (naming commit) ─ merges FIRST
        │
        E0 (S1 gateway fix, S3 contracts) ──► E1 ──► E2 ──► E5 ──► E6 final gate
                                   └──► E3 ─────────────┤
                                   └──► E4 ─────────────┤
                                   └──► E7.S1/S2 (lab bring-up, anytime) ──► E7.S3–S7 (after E2+E3+E4)
```

E8 sits outside this chain: it touches only `submodule/cloudlynet_ai_copilot` plus parent docs
bundles, shares no migration numbers and no Kafka topics with E0–E7, and can run any time after
E0 (E0.S4 naming commit). Its only dependency is copilot submodule state (JWT forwarding §22 and
the guardrail middleware merged — both on `main`).

Migration numbers (Appendix A.6): 011 = E1 canonical · 012 = E4 drop e2/r1 · 013 = E4 commands
columns · 014 = E2 ndt/loop · 015 = E5 policy seed (seed-only, requires 014). E8 adds no
migration numbers.

## Watch-items during implementation (carried from the adversarial review)

1. **Threshold-constant duplication window (E2.S2–S3):** rapp and NDT both hold
   DEFAULT_THRESHOLDS until the delegation flips; the parity fixtures must pin the constants,
   not just the shapes. Never edit one copy alone.
2. **Day-scope fan-out volume:** one day-scope proposal can fan out to 24 ticks × N cells of loop
   actions. The decision hub gates per action; validate realistic volumes in the lab before
   enabling `auto` on day-scope proposals (tick-scope is the proven path; the demo uses it).
3. **MRO pickle coupling persists by design:** MRO evaluation and rapp-worker training still
   unpickle BDTs via rapp's vendored twin copies. Never rename
   `app/radp/digital_twin/rf/bayesian/engine.py` (either repo) without a pickle-compat migration.
4. **MRO mobility artifact (resolved):** the smo_sim PM pipeline never produced
   `synthetic_dataset_mobility.csv` (recon: nybsys_runner writes `synthetic_dataset.csv`,
   source_type `utils_traffic_load` only); mobility datasets come from data_sim's synthetic
   factory, which stays. The feature builder correctly excludes it.
5. **Gateway deploy risk (E0.S1):** the first post-fix gateway deploy ships every merged-but-
   never-deployed commit since the panic landed; verify on staging (`/v1/health`, `/custom`
   round-trip, edge-agent poll) before production.
6. **Dual-writer window (E1 rollout):** between dark launch and cutover, nybsys_uploads/baselines/
   ue_datasets have two possible writers; the runbook's provenance checks are mandatory.
7. **Secrets rotation needs a named owner** (E0.S5) before E1 churns those values.yaml files.
8. **NONRTRIC cautions:** mirror the `nexus3.o-ran-sc.org:10002` images into our own registry for
   production pulls (no SLA on the LF nexus); RANPM stays out of scope partly because it drags in
   AGPLv3 MinIO; rApp Manager is pre-spec ("not intended for production use") and stays roadmap;
   the near-RT track is deferred behind the `nearrt_xapp` placeholder (no submodule, no xApp code,
   no E42 bridge).
9. **Prometheus loop metrics:** keep tenant_id out of high-cardinality labels (E5.S3 note).
10. **Trial tenant display name** stays "NetAI Trial" until the E6 ops data change; expected.
11. **IntentAck literal set (E3.S1/S3/S4):** the status literals include `accepted` but the
    connector's create-mapping and the executor's feedback mapping pin
    `applied|duplicate|rejected|failed`; implementers must map create-success to `applied` (never
    return a bare `accepted` the executor has no branch for).
12. **A1-path rung evidence (E6.S5):** the E5 rollback demo is TR-069-only; promoting the
    NONRTRIC A1 path to Today (Lab) requires the A1-path lab verification recorded in
    `artifacts/ric/nonrtric-lab.md`'s runbook (or an A1-path demo run), not the E5 demo artifact.
13. **NONRTRIC bring-up verify list (E3.S2/S3):** unpinnable-from-docs details are flagged
    in-story for verification at bring-up: PMS `application_configuration.json` exact keys/mount,
    a1-simulator container port (8085 assumed), v3/v2 body field spellings, and whether v3
    POST-create honors a client-supplied policyId (fallback: GET-then-create inside the client).
14. **OCUDU lab pinning (E7):** E2AP/E2SM version friction between OCUDU 26.04 and the i-release
    OSC RIC is community-documented; pin what works in `scripts/ran-lab/.env` and treat upgrades
    as spikes. The `oran-sc-ric` wrapper repo's license is unverified (E7.S2 acceptance forces the
    check). srsRAN_4G/srsUE are archived; pin commits.
15. **O1-on-OCUDU rule:** O1 config = sidecar rewrite + gNB RESTART (code-confirmed; `lib/o1/`
    absent from the gNB). The `o1_netconf` adapter must reject live-loop actions
    (`restart_required`) unless flagged `maintenance_window=true`; no demo or copy may imply
    runtime O1 control of OCUDU.

## Verification gates

- Every epic's stories carry acceptance criteria + repo-real test commands (rApp:
  `PYTHONPATH=app:app/radplib/dependencies uv run pytest`; other Python: `uv run pytest`;
  Go: `go test ./...`).
- E2's golden-response parity fixtures gate the rapp twin-eval deletion.
- E5.S2 is the end-to-end proof; E5.S4 (`scripts/demo/closed_loop_rollback.sh`) is the
  customer-facing rollback demo (marketing blocker #3) and doubles as the release gate.
- E6.S5 re-verifies claims-guardrails against the new code state and re-stamps the bundle.
