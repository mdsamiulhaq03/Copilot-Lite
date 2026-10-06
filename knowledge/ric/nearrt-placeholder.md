# Near-RT RIC: the `nearrt_xapp` reservation (summary)

Part of the [`artifacts/ric/`](./README.md) bundle (authored by EPIC-3.S7; owned by the
bundle since E6.S2). Canonical document:
`submodule/maveric_platform_rapp/app/ric/adapters/nearrt/README.md`. That file is the
contract of record and carries the full findings. This page is the parent-repo summary, kept
here because design artifacts live in `artifacts/`.

Status: production near-RT integration is DEFERRED. Findings recorded mid-2026.

## The decision in one page

1. **Reserved seam.** `nearrt_xapp` is a RESERVED key in the Appendix A.4 adapter namespace
   (previously `flexric_xapp`). The rApp registry refuses to register or resolve it by
   default. The streaming `source_type` `nearrt_kpm_stream` (Appendix A.5) is likewise
   reserved and never emitted. The KPM sidecar concept is deferred with the track.

2. **Lab activation, HLD v1.2 (D5).** The reservation stands for production, but the key is
   activated for LAB use by EPIC-7 (a CloudlyNet xApp on the dockerized O-RAN SC RIC driving
   OCUDU). The registry allows this only through an explicit `allow_reserved=True` opt-in,
   so every production path stays inert by default. New callers of that flag are a reviewed
   decision, not a routine change.

3. **Why deferred.** Per-RIC xApp SDKs are non-portable by design; E2 fragments across
   E2AP v1 to v4 with non-overlapping E2SM feature sets; every near-RT RIC ships its own SDK;
   and the standalone near-RT merchant market has consolidated while the commercial energy
   sits at the non-RT tier (rApps over A1 and R1), which is where the HLD track points.

4. **FlexRIC is licence-blocked.** E42 custom SCTP transport plus a C SDK (E2SM-KPM v3.00,
   E2SM-RC v1.03; the Python SDK excludes KPM and RC). The dev branch moved to the
   Collaborative Standards Software License v1.0 on 2026-03-31 (master and v2.0.0 are OAI
   Public License v1.1). Both grant patent rights royalty-free **solely for study, testing
   and research**, and require FRAND negotiation for commercial use. The repository's
   "Apache-2.0" badge is an automated misdetection. Lab-only unless legal clears FRAND.

5. **Alternative.** Write a per-RIC xApp on a commercial RIC vendor's own SDK, with their
   support. Never port an xApp between RICs.

6. **E2-node reality.** OCUDU (Linux Foundation, BSD-3-Clause, srsRAN lineage) ships DU,
   CU-CP and CU-UP E2 agents implementing E2SM-KPM v3.00 with 27 of 287 defined metrics; RC
   support is thinner than its configuration flags suggest; FlexRIC interoperability is
   inferred from shared lineage, not documented upstream.

7. **Re-open criteria.** A paying design partner needing sub-second control loops, or a
   commercial near-RT RIC engagement supplying its own SDK and support, AND legal clearance
   of that SDK's patent and FRAND terms. Until then, control reaches the RAN through the
   `a1_policy` connector (EPIC-3) and the smo_sim actuators (EPIC-4).

## Claims

This page describes third-party projects and a reserved internal seam, not a CloudlyNet
capability. No conformance or certification is claimed for O-RAN, E2, A1 or R1. See
`artifacts/marketing/claims-guardrails.md`.
