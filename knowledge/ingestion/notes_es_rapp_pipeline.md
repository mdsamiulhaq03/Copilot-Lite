# ES rApp end-to-end data pipeline - synthesis (evidence-labeled)

Confidence tags: [SPEC] = verified against downloaded 3GPP spec text (TS 28.552 V19.8.0, TS 28.541 V19.8.0, TS 28.554 V19.5.0, TS 28.310 V19.1.0, TS 28.552 V17.17.0); [MULTI] = 2+ independent web sources; [SINGLE] = one credible source, re-verify before load-bearing use.

## (a) Data sources and interfaces
- **O1 PM, file-based**: PM jobs controlled per TS 28.550 (performance assurance MnS); measurement collection into ROP files reported via the file data reporting MnS of TS 28.532, with a VES `fileReady` (stndDefined) notification and SFTP/FTPES pull - this is how O-RAN WG10's O1 spec (O-RAN.WG10.O1-Interface.0) profiles it. Legacy XML file format lineage is TS 32.432/32.435. [MULTI]
- **O1 PM streaming**: TS 28.550 clause 5.2.3 streaming MnS, profiled by O-RAN OAM spec; O-RAN SC OAM implements GPB/JSON streaming variants. Streaming shortens the collection latency from ~ROP+minutes to seconds but 15-min files remain the deployed norm. [MULTI]
- **VES**: ONAP/3GPP-aligned VES event streams over O1 carry FM (fault), heartbeat, PM fileReady, and CM change notifications (notifyMOIAttributeValueChanges) - the eventing backbone between O-RAN nodes/SMO collectors. [MULTI]
- **R1 / DME**: inside the SMO, rApps never scrape O1 directly - they subscribe to **Data Management and Exposure (DME)** services over the R1 interface (O-RAN WG2 R1GAP/R1AP + DME type registrations). Ericsson EIAP exposes exactly this (R1 + DME validated with AT&T/Aira 2025-2026); O-RAN SC NONRTRIC implements it as ICS/DME with a data lake behind it. Note: in O-RAN SC terms **SME** = Service Management and Exposure (CAPIF-based service registry), the R1 sibling of DME. [MULTI]
- **PEE data path nuance**: PEE counters are defined per PNF (ManagedElement scope, 'valid for PNF' per TS 28.552 5.1.1.19.1) [SPEC]. For O-RUs, power/energy readings ride the Open FH M-plane to the O-DU/SMO in many implementations; per-RU metering coverage is vendor-dependent - budget for site-meter or rectifier-feed fallback. [MULTI]

## (b) Counter/feature set
See rows. Key [SPEC] verifications: PEE family is TS 28.552 **5.1.1.19** (PEE.AvgPower/MinPower/MaxPower 5.1.1.19.2, PEE.Energy 5.1.1.19.3, Temperature/Voltage/Current/Humidity 5.1.1.19.4-7). PRB usage is 5.1.1.2.x - **naming caution**: Rel-17 name `RRU.PrbTotDl` (V17.17.0 verified) was changed to `RRU.PrbDl` in the Rel-19 text (V19.8.0 verified); deployed O1 stacks overwhelmingly still emit RRU.PrbTotDl - map both. Active-UE counters are 5.1.1.23.x (DRB.MeanActiveUeDl etc.), RRC connections 5.1.1.4.x, UE throughput 5.1.1.3.x, HO executions 5.1.1.6.1.7-9 (per NRCellRelation - gives the per-neighbor-pair matrix), PDCP volumes 5.1.2.1.x (non-split) / 5.1.3.6.x (CU-UP), Tx power CARR.MaxTxPwr/MeanTxPwr 5.1.1.29.x, MIMO layers CARR.AverageLayersDl 5.1.1.30.5. EE KPI = DV/EC in bit/J, TS 28.554 6.7.1. [SPEC]

## (c) Granularity and latency
- 15-min ROP is the industry-standard collection cadence (5-min supported); file availability adds minutes. [MULTI]
- ES decision loop is **non-RT (>=1 s by O-RAN definition; in practice minutes-to-hours)**: nightly/weekly schedule learning + intra-day threshold triggers. Forecast horizon: 24 h with weekly seasonality is the norm (Nokia MantaRay Energy 'multiple daily sleep windows'; Ericsson 4G Energy Optimizer). [MULTI]
- Guardrail evaluation after an action: first 1-2 ROPs (15-30 min) for accessibility/retainability deltas; FM alarms are the fast (seconds) rollback path. [MULTI]

## (d) Decision/action path
1. rApp pulls topology (NRM) + PM history via R1/DME; classifies **coverage layer vs capacity booster** cells per TS 28.310 5.1.3.2/5.1.3.3 (booster partially/fully overlaid by candidate cells - terms from TS 32.551 ESM). [SPEC]
2. Forecast low-load window; check activation thresholds (intraRatEsActivationOriginalCell/CandidateCellsLoadParameters) and esNotAllowedTimePeriod. [SPEC]
3. **Pre-action offload**: A1 policy (traffic-steering preference marking target cells FORBID/AVOID) so the near-RT RIC / TS-xApp drains UEs; Rimedo's PoC reports 100% HO success on drain; monitor RRC.ConnMean -> ~0. [MULTI]
4. **Actuate over O1 provisioning MnS**: set `energySavingControl = TO_BE_ENERGY_SAVING` on the CES scope (TS 28.541 4.3.63), or administrativeState=LOCKED on NRCellDU/NRSectorCarrier for hard carrier shutdown; RF-channel/MIMO reconfiguration (TRX shutdown, e.g. 64->32) goes via O1/M-plane per the O-RAN RF Channel Reconfiguration use case. [SPEC]/[MULTI]
5. Verify `energySavingState = IS_ENERGY_SAVING` via CM change notification; log PEE.Energy delta for savings accounting (TS 28.554 6.7.1 EE KPI). [SPEC]

## (e) Safeguards / verification
- **Coverage compensation**: only sleep boosters whose footprint candidate cells cover (TS 32.551 candidate-cell + compensatingForEnergySaving concepts; TS 28.310 requirements; optional evidence from L1M.SS-RSRPNrNbr histograms or MDT). [SPEC]/[MULTI]
- **KPI guardrails** on compensation cells: RRC/DRB establishment success (accessibility), DRB.RelActNbr (retainability), MM.HoExeInterSucc/Fail (mobility), DRB.UEThp (QoE), PRB headroom - breach => deactivate ES. [MULTI]
- **Wake conditions**: standardized via intraRatEsDeactivationCandidateCellsLoadParameters (candidate overload wakes the sleeper) [SPEC]; plus schedule end, FM alarms, and RACH/attempt surges. Cells in energySaving state remain O1-controllable by definition (TS 32.551). [SPEC]
- **Rollback triggers**: guardrail breach, alarm on candidate cell, energySavingState mismatch, or failed wake (escalate to self-healing). [MULTI]
- **Blackout windows**: esNotAllowedTimePeriod. [SPEC]

## (f) Reference implementations
- **O-RAN SC NONRTRIC**: rApp Manager sample **Energy Saving rApp** (I/J releases, github o-ran-sc/nonrtric-plt-rappmanager) - full loop with ACM participants: A1PMS (policy), DME (data types), Kserve (ML inference), K8s (deploy). [MULTI]
- **Rimedo Labs ES-rApp + TS-xApp**: O1 cell on/off + A1 FORBID policies + E2SM-RC steering; multi-vendor testing documented (arXiv 2409.19807 with Keysight RICtest). [MULTI]
- **Ericsson EIAP**: rApp directory incl. **4G Energy Optimizer rApp** (drives Cell Sleep Mode feature); ecosystem rApps e.g. Future Connections 'Nix RAN Energy Saver' (MasOrange deployment, Dec 2025). [MULTI]
- **Nokia MantaRay Energy** (SON-based, AI sleep-window optimization, claimed ~25% radio energy reduction; 'extreme deep sleep' with Orange). MantaRay is an SMO/SON suite - not an O-RAN-SC-style rApp platform claim. [MULTI]
- **O-RAN WG1 NES Technical Report** (O-RAN.WG1.Network-Energy-Savings-Technical-Report / NESUC R003): four use-case families - Carrier & Cell Switch Off/On, RF Channel Switch Off/On (Massive-MIMO TRX reduction), Advanced Sleep Modes, O-Cloud resource ES; Phase-2 (July 2024) added A1 policy + E2SM-CCC enhancements (O-RAN SuFG white paper, Jan 2025). [MULTI]

## Scope boundary (precision)
**Carrier/cell/RF-channel switch-off = rApp territory** (non-RT, O1/A1, 15-min PM). **Symbol-level micro-sleep (PA muting between symbols) and fast Advanced Sleep Mode state transitions are NOT rApp actions**: they are L1/scheduler- and O-RU-internal (WG4 M-plane/C-plane managed, near-RT or real-time; E2SM-CCC/A1 only tune their envelopes). An ES rApp may configure ASM policy envelopes but never the per-ms sleep decisions. Also: the E2 interface plays a supporting role (E2SM-KPM near-RT metrics, E2SM-RC steering, E2SM-CCC cell config) - an ES rApp itself remains on R1/O1/A1; anything claiming 'rApp controls E2 directly' blurs the architecture. [MULTI]

## Gaps to watch
- PEE per-O-RU metering is the weakest real-world link; many fleets only meter per-site. Plan estimation fallback (TS 28.554 6.7.3.1.2+ estimated EC methods). [MULTI]
- A1 has no dedicated standardized 'ES policy type'; ES-via-A1 rides traffic-steering policy types or vendor extensions (WG2 A1TD evolution post-Phase-2 worth re-checking). [MULTI]
- Multi-vendor: 28.541 ES attributes are 'CM/conditional' - vendor support varies; administrativeState lock is the universal fallback. [SPEC]/[MULTI]

## CloudlyNet today vs this pipeline (stage-by-stage)

CloudlyNet is a non-RT, TR-069 (CWMP) single-vendor platform; it implements none of the
O-RAN/3GPP SA5 interfaces named above. This mapping states what plays each stage's ROLE today.

| Pipeline stage | Industry standard | CloudlyNet today | Gap / owner |
| --- | --- | --- | --- |
| Collection | O1 PM ROP files (15-min) / streaming, VES | Manual NybSys PM CSV upload (5-min vendor counters, aggregated hourly in `pipeline.py`); edge-agent HTTPS tiered telemetry (`device_kpis`) | No O1/VES/streaming; EPIC-1 ingest framework + `ves_listener`/`3gpp_xml_pm` adapter stubs (422 today) |
| Exposure to apps | R1/DME data services, data lake | Direct Postgres/S3 reads inside services | EPIC-1 canonical `pm_measurements` + `GET /data/pm` is the internal analogue |
| ES feature set | PRB usage, active UEs, RRC conns, PDCP volumes, PEE energy, Tx power, MIMO layers | `RRC.ConnMean` (the ONLY counter consumed in production); 10 optional RRC/CONTEXT/HO counters land audit-only; no PRB, no volume, no PEE, no Tx-power counters | Core ES inputs missing — ES coverage 36.6% of mandatory (see `gap_analysis.csv`); highest-value NybSys vendor ask |
| Coverage/booster classification | TS 28.310 coverage-vs-capacity relations from NRM | No real cell-relation or overlay model (topology synthesized for upload tenants) | Needs real site geometry + relations (EPIC-1 `cm_records`) |
| Pre-action drain | A1 traffic-steering policy (FORBID/AVOID) | None (single-cell femtocell context makes drain moot today) | EPIC-3 `a1_policy` executor is the lab-rung seam |
| Actuation | O1 `energySavingControl` / `administrativeState` lock | TR-069 (CWMP) writes via in-agent ACS — but the 24-param managed catalogue has no AdminState/cell on/off write path today | RL ES model recommends on/off it cannot actuate; EPIC-4 owns the write surface |
| Safeguards | KPI guardrails on compensation cells, wake conditions, rollback | GENUINE analogue exists: NanoLink loop's dual auto-rollback (failed apply + KPI-guardrail breach) with verified GPV read-back | Guardrail breadth limited to device KPIs; no compensation-cell concept |
| Savings accounting | PEE.Energy delta, EE KPI (bit/J) | None (no energy metering ingested) | kWh-saved is also the top marketing evidence gap (roadmap) |

Bottom line: the pipeline SHAPE we run (collect -> model -> recommend -> guarded actuate -> rollback)
matches the standard loop, but the ES-specific inputs (PRB/volume/PEE) and the ES actuation surface
(AdminState/cell on/off) are missing — today's ES model demonstrates the loop on the Simulation rung
with `RRC.ConnMean` as the sole live load signal.
