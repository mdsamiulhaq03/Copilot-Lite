# R1-shaped rApp packaging facade

Part of the [`artifacts/ric/`](./README.md) bundle. Code of record:
`submodule/maveric_platform_rapp/packaging/r1/` and
`submodule/maveric_platform_rapp/app/ric/r1_manifest.py`.

> **R1-shaped manifest (facade), never "R1 compliant".** CloudlyNet implements no part of
> the R1 interface and claims no R1 conformance, certification, or compatibility. This is
> metadata only: nothing in `packaging/r1/` is executed, deployed, or packaged by any
> pipeline.

## What exists (Today)

One `manifest.yaml` per rApp (`es`, `lb`, `cco`, `mro`) under `packaging/r1/`, validated
by `app/ric/r1_manifest.py` (Pydantic) and covered by `tests/test_r1_manifest.py`. The
shape is loosely aligned to the O-RAN SC rApp Manager ASD prototype so that onboarding
onto a commercial non-RT RIC / SMO platform later (Ericsson EIAP, Nokia MantaRay, Samsung
CognitiV NOS) is a packaging exercise rather than a re-architecture.

Load-bearing field notes (from `packaging/r1/README.md`):

- `artifacts.s3_key_template` is a **frozen contract** (frozen HLD §3.3), mirroring the
  `RAPP_WORKER_S3_ARTIFACT_TEMPLATE` default; a test asserts the copies stay in step.
  Copy it, never redesign it.
- `data_needs` describes what each rApp REQUIRES, not what the platform currently
  delivers; the live coverage gap is tracked in [`../ingestion/`](../ingestion/).
- `policy_types_produced` is `cloudlynet.cell_config.v1` for es, lb and cco (the type the
  NONRTRIC connector registers on the lab simulators); empty for mro, which has no
  control action of its own yet.

## What is deliberately NOT built (ROADMAP)

Onboarding automation is deferred:

- The upstream O-RAN SC rApp Manager is pre-spec; upstream states it is "not intended for
  production use", and it drags in an ONAP ACM plus SME plus DME dependency chain.
- CAPIF and Service Manager registration, and ASD or CSAR packaging, are therefore
  deferred with it.

## Claims

Governed by [`../marketing/claims-guardrails.md`](../marketing/claims-guardrails.md).
The sanctioned wording is "R1-shaped manifest (facade)" and "future onboarding target";
never a present-tense R1 capability claim.
