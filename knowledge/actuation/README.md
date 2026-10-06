# Actuation bundle

One document per southbound actuation plane smo_sim declares. The registry keys are frozen
in HLD Appendix A.4 and shared with the loop action `adapter` field and the proposal
`target_adapter_hint`. Bare `nanolink` is not a valid key.

| Key | State | Doc |
| --- | --- | --- |
| `nanolink_tr069` | IMPLEMENTED. The only plane that can apply a change today. | (EPIC-4.S2, no separate doc) |
| `o1_netconf` | Placeholder | [o1_netconf.md](o1_netconf.md) |
| `ocudu_ws_collector` | Implemented, gated off. Data plane only, never applies. | [ocudu_ws_collector.md](ocudu_ws_collector.md) |
| `open_mplane` | Placeholder | [open_mplane.md](open_mplane.md) |
| `sas_domain_proxy` | Models and state machine implemented; no certified SAS attached. | [sas_domain_proxy.md](sas_domain_proxy.md) |
| `nms_northbound` | Placeholder | [nms_northbound.md](nms_northbound.md) |

Two keys in the A.4 namespace are NOT smo_sim's: `a1_policy` and `nearrt_xapp` belong to the
rApp's RIC layer. The loop consumer skips them so the two executors do not double-report.

A placeholder means: a named slot, an honest health surface, and this contract, with no
protocol code. `dispatch()` checks `capabilities().apply` before invoking an adapter, so a
loop action aimed at a placeholder is rejected without the adapter running.

Nothing in this bundle claims conformance or certification with O-RAN, O1, the Open
Fronthaul M-Plane, or CBRS. See `artifacts/marketing/claims-guardrails.md`.
