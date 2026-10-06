# OCUDU integration surfaces

Part of the [`artifacts/ric/`](./README.md) bundle.

> **Integration layer, NOT a RIC.** OCUDU (Linux Foundation, BSD-3-Clause, srsRAN
> lineage) is an **integration target, never a customer**. Nothing here implements or
> claims conformance with E2, O1, A1 or any O-RAN interface. Each surface below carries
> its own status rung; none is a present-tense product capability unless labeled
> Today.

OCUDU ships an open-source gNB (DU, CU-CP, CU-UP). CloudlyNet can reach it on three
distinct surfaces, each with a different mechanism and a different status.

## Surface 1: E2SM-KPM v3 via a near-RT RIC (ROADMAP, deferred)

OCUDU's DU/CU components ship E2 agents implementing E2SM-KPM v3.00 (27 of the 287
defined metrics; RC support is thinner than its configuration flags suggest). Consuming
that stream requires a near-RT RIC and an xApp, and the production near-RT track is
DEFERRED (see [`nearrt-placeholder.md`](./nearrt-placeholder.md) for the rationale,
recorded past-tense).

What exists in committed scope is reservation only, no bridge code:

- the reserved `nearrt_xapp` adapter key (`app/ric/registry.py` in the rApp submodule,
  inert by default, lab-only activation via `allow_reserved=True` per frozen HLD v1.2 D5);
- the reserved streaming `source_type` `nearrt_kpm_stream` (frozen HLD Appendix A.5),
  never emitted.

## Surface 2: JSON metrics over WebSocket to the data platform (BUILDING, placeholder adapter exists)

OCUDU's `remote_control` port emits plain JSON metrics frames when `metrics.enable_json`
is on: no RIC and no ASN.1 needed. The `ocudu_ws_collector` adapter
(`submodule/maveric_platform_smo_sim/app/actuators/adapters/ocudu_ws_collector.py`,
epic E4) is an outbound WebSocket client, gated off by default, that translates frames
into frozen HLD Appendix A.5 `kind="records"` envelopes on `maveric.ingest.pm.v1` with
`source_type="ocudu_ws"`. It is a data-plane collector only: `capabilities().apply` is
False, so loop actions can never target it. Contract doc:
[`../actuation/ocudu_ws_collector.md`](../actuation/ocudu_ws_collector.md).

## Surface 3: O1-style configuration via the `ocudu_netconf` companion (ROADMAP, placeholder only)

The OCUDU gNB itself has no NETCONF or YANG implementation (code-confirmed: no `lib/o1/`
in its tree). Configuration goes through the companion service `ocudu_netconf`, which
rewrites the gNB config file and RESTARTS the gNB. That restart semantic is why the
`o1_netconf` adapter
(`submodule/maveric_platform_smo_sim/app/actuators/adapters/o1_netconf.py`) stays a
placeholder: a closed-loop action must not restart a radio. When implemented it must
reject live-loop actions with `restart_required` unless the action is explicitly flagged
for a maintenance window. No NETCONF or YANG code exists in CloudlyNet, and no O1
conformance is claimed. Contract doc:
[`../actuation/o1_netconf.md`](../actuation/o1_netconf.md).

## Claims

Governed by [`../marketing/claims-guardrails.md`](../marketing/claims-guardrails.md).
OCUDU is a third-party open-source project we integrate against in the lab; it is not a
customer, not a partner endorsement, and not evidence of O-RAN conformance.
