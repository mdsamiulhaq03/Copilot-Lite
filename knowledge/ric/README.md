# RIC Integration Layer: Design Bundle

Design of record for CloudlyNet's RAN-intelligence integration layer (frozen HLD §4.4,
built by epic E3).

> **Integration layer, NOT a RIC.** CloudlyNet integrates a RIC; it is not a RIC and does
> not implement E2 termination itself. The components here carry A1-policy-aligned intents
> to an O-RAN SC NONRTRIC A1 Policy Management Service over REST/JSON. Nothing in this
> bundle implements or claims conformance or certification with the A1, E2, R1, O1 or
> O-RAN interfaces. Wording for anything customer-facing is governed by
> [`../marketing/claims-guardrails.md`](../marketing/claims-guardrails.md).

The predecessor E2/R1 REST facade bundle was archived to
[`../legacy/oran/`](../legacy/oran/README.md) when the facades were deleted per frozen
decision D4 (epic E4).

| Doc | Covers |
|---|---|
| [`ports_and_adapters.md`](./ports_and_adapters.md) | The southbound seam in the rApp: `RanControlPort` / `RanDataPort`, the Appendix A.4 adapter registry (`a1_policy` implemented, `nearrt_xapp` reserved), the NONRTRIC A1-PMS connector. |
| [`nonrtric-lab.md`](./nonrtric-lab.md) | The `ric-lab` compose profile: NONRTRIC A1-PMS 2.11.0 plus two A1 simulators, bring-up runbook, image-mirroring production posture, license and attribution rules. |
| [`nearrt-placeholder.md`](./nearrt-placeholder.md) | One-page summary of the deferred near-RT track and the reserved `nearrt_xapp` / `nearrt_kpm_stream` seam. |
| [`ocudu_integration.md`](./ocudu_integration.md) | The three OCUDU integration surfaces and their per-surface status rungs. |
| [`r1_packaging.md`](./r1_packaging.md) | The R1-shaped rApp manifest facade in `rapp packaging/r1/` for future EIAP/MantaRay onboarding. |

## Code

| Concern | Location |
|---|---|
| Ports, models, registry, executor, translation | `submodule/maveric_platform_rapp/app/ric/` |
| NONRTRIC connector (`a1_policy`) | `submodule/maveric_platform_rapp/app/ric/adapters/nonrtric/` |
| Near-RT reservation (contract of record) | `submodule/maveric_platform_rapp/app/ric/adapters/nearrt/README.md` |
| R1-shaped manifests | `submodule/maveric_platform_rapp/packaging/r1/` |
| Lab containers | `docker-compose.yaml` profile `ric-lab` (images only, no source) |

## Status rungs

- **Today (Lab):** the `ric-lab` compose profile and the `a1_policy` connector, verified
  end to end against NONRTRIC A1-PMS 2.11.0 and the two A1 simulators (see
  `nonrtric-lab.md`). Lab only: compose profile only, no chart, no CI/CD.
- **Building:** loop-action execution over the A1 path as the surrounding epics land.
- **Roadmap:** near-RT xApp track (deferred, see `nearrt-placeholder.md`), R1 onboarding
  automation (see `r1_packaging.md`), OCUDU O1/NETCONF and E2SM-KPM surfaces (see
  `ocudu_integration.md`).
