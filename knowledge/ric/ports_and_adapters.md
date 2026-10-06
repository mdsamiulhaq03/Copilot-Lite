# Ports and adapters: the southbound RIC seam

Part of the [`artifacts/ric/`](./README.md) bundle. Code of record:
`submodule/maveric_platform_rapp/app/ric/`.

> **Integration layer, NOT a RIC.** These ports carry A1-policy-aligned intents to an
> external non-RT RIC over REST/JSON. Nothing here implements A1, E2, R1 or O1, and no
> conformance with any O-RAN interface is claimed. Never write "A1 compliant"; the
> sanctioned phrase is "A1-policy-aligned intents" (frozen HLD §4.4).

## The two ports (`app/ric/ports.py`)

Both are `runtime_checkable` `Protocol`s. Method names are fixed by the frozen HLD; one
implementation per adapter key; the registry in `app/ric/registry.py` resolves them.

### `RanControlPort`

Southbound control port carrying A1-policy-aligned intents. Implementations return an
`IntentAck` rather than raising, so a caller can always map the outcome onto loop
feedback.

| Method | Purpose |
|---|---|
| `capabilities() -> RicCapabilities` | Capability discovery (what the connected RIC path can do). |
| `submit_policy_intent(intent: PolicyIntent) -> IntentAck` | Create/apply a policy intent. |
| `delete_policy_intent(policy_id: str) -> IntentAck` | Remove a policy intent (idempotent rollback). |
| `policy_status(policy_id: str) -> PolicyStatusInfo` | Enforcement status read-back. |
| `health() -> AdapterHealth` | Adapter liveness. |

### `RanDataPort`

Southbound data port carrying subscription lifecycle only (`subscribe(spec) ->
SubscriptionHandle`, `unsubscribe(handle)`). Adapters emit normalized PM records to
`maveric.ingest.pm.v1` (frozen HLD Appendix A.5); the port itself never carries records.

Data shapes (`PolicyIntent`, `IntentAck`, `PolicyStatusInfo`, `RicCapabilities`,
`DataSubscriptionSpec`, `SubscriptionHandle`, `AdapterHealth`) live in
`app/ric/models.py`. Callers only ever see these shapes; upstream API dialects are the
connector's private concern.

## Adapter registry (`app/ric/registry.py`)

One namespace, the frozen HLD Appendix A.4 table, shared by the loop-action `adapter`
field, the proposal `target_adapter_hint`, and every executor-side registry. Bare
`nanolink` is not a valid key.

| Key | Owner | Status |
|---|---|---|
| `a1_policy` | rApp (this bundle, epic E3) | **Today (Lab):** implemented by the NONRTRIC connector below. |
| `nearrt_xapp` | rApp (reserved) | RESERVED: no production executor; inert by default. Lab activation only via the explicit `allow_reserved=True` opt-in (frozen HLD v1.2 D5). See [`nearrt-placeholder.md`](./nearrt-placeholder.md). |
| `nanolink_tr069`, `o1_netconf`, `ocudu_ws_collector`, `open_mplane`, `sas_domain_proxy`, `nms_northbound` | smo_sim actuator side (epic E4) | Documented in [`../actuation/`](../actuation/) and, for the OCUDU pair, in [`ocudu_integration.md`](./ocudu_integration.md). |

The registry refuses to register or resolve unknown keys, refuses duplicates, and keeps
reserved keys inert unless the sanctioned lab caller opts in.

## The NONRTRIC A1-PMS connector (`app/ric/adapters/nonrtric/`)

`NonRtRicControlAdapter` (registered as `a1_policy`) implements `RanControlPort` over
`A1PmsClient`, an HTTP client for the NONRTRIC A1 Policy Management Service northbound
API (v3 base path `/a1-policy-management/v1` by default, v2 `/a1-policy/v2` fallback via
`A1PMS_API_MODE`). The client owns the v2/v3 dialect mapping and the HTTP-to-ack status
mapping (201 -> `applied`, 409/404 on repeat -> `duplicate`, so submit and rollback are
idempotent). `policy_type.py` registers the CloudlyNet policy type
(`cloudlynet.cell_config.v1`) on the lab simulators, picking the right registration
envelope per simulator interface.

Also in `app/ric/`:

- `executor.py`: the `maveric.loop.action.v1` consumer for adapter `a1_policy`, a daemon
  thread inside the rApp API container, off unless `A1_EXECUTOR_ENABLED` is true. It
  emits only `apply` and `rollback` feedback; KPI-window feedback comes from canonical PM
  on the Network Digital Twin side.
- `translation.py`: the binding seam that maps frozen Appendix A.2 loop-action payloads
  onto cell-scoped policy bodies (the policy plane addresses cells, not devices).
- `r1_manifest.py`: validator for the R1-shaped packaging metadata, see
  [`r1_packaging.md`](./r1_packaging.md).

Runbook and verified lab behavior: [`nonrtric-lab.md`](./nonrtric-lab.md).
