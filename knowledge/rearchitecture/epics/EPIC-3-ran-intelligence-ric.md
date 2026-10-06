# EPIC 3: RAN Intelligence + RIC Integration Layer (maveric_platform_rapp)

**Epic ID:** E3
**Title:** RAN Intelligence: hexagonal RIC layer (non-RT-first), NONRTRIC A1-PMS connector + `ric-lab` compose profile, `a1_policy` loop-action executor, loop proposal emitter, R1-shaped packaging facade, near-RT placeholder
**Frozen HLD:** `docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md` **v1.1** (D1 amended: the integrated open RIC is O-RAN SC NONRTRIC at the non-RT tier; §3 hard constraints; §4.1 topics; §4.4 RIC layer, non-RT-first; Appendix A frozen payloads). This epic conforms to it; it never redefines a shared contract.

**Goal (2-3 sentences):** Turn `maveric_platform_rapp` into the RAN Intelligence service of the frozen HLD v1.1: the existing model lifecycle (training via `maveric.rapp.train.v1`, inference, evaluation) stays byte-identical, and a new hexagonal RIC integration layer (`app/ric/`) is added, non-RT-first. The first real RIC-plane executor is the OSC NONRTRIC A1 Policy Management Service connector (adapter key `a1_policy`, consumed as container images + REST, never by copying source), exercised in a compose-only `ric-lab` profile (A1-PMS 2.11.0 + two OSC A1 Simulators standing in for near-RT RIC A1 terminations), driven by an in-container loop-action executor and fed by a feature-flagged proposal emitter. The near-RT tier is a reserved placeholder (`nearrt_xapp`): registry stub + contract doc only, no submodule, no C code, no compose services.

**Dependencies:** E0 (platform hygiene: gateway duplicate-route fix and `artifacts/design/internal-contracts.md` land first; its section 6 records the Appendix A.4 adapter-key registry this epic keys everything on). Cross-epic touch points (not blockers for merging E3 code): E2's NDT decision hub consumes `maveric.loop.proposal.v1` and dispatches `maveric.loop.action.v1`; E5.S1 is the owner-of-record for topic provisioning (E3 only ensures lab topic lines if E5.S1 has not landed); E4 owns the smo_sim actuator adapters that share the A.4 key namespace; E1's data platform stores the canonical PM that the NDT-side watch (E2.S7's canonical-PM watch tick) uses for A1-path KPI feedback (this epic deliberately emits no KPI windows).

**Definition of done (epic):**
- `app/ric/` exists in the rapp submodule with `ports.py` protocols (`RanControlPort`: submit_policy_intent / delete_policy_intent / policy_status / capabilities; `RanDataPort`: subscribe / unsubscribe), a Pydantic `PolicyIntent` whose `policy_object` maps 1:1 onto an A1 policy-instance body, and an adapter registry keyed by the HLD Appendix A.4 keys (`a1_policy` implemented, `nearrt_xapp` RESERVED); all covered by unit tests.
- `docker compose --profile ric-lab up` brings up `nonrtric-plt-a1policymanagementservice:2.11.0` plus two `a1-simulator:2.8.1` containers (one `STD_2.0.0`, one `OSC_2.1.0`) from `nexus3.o-ran-sc.org:10002`; PMS `GET /rics` (v3 base path `{apiRoot}/a1-policy-management/v1`) lists both simulators; the CloudlyNet policy type is registered on both sims via the simulator admin API; a policy instance created through PMS reaches a sim and its status is readable.
- The NONRTRIC connector (`app/ric/adapters/nonrtric/client.py`, httpx) speaks the pinned v3 API (base path `{apiRoot}/a1-policy-management/v1`, create = `POST /policies`) with env-switchable `A1PMS_API_MODE=v2` fallback (`/a1-policy/v2`, create = `PUT`), registers itself with PMS `/services` under `A1PMS_SERVICE_ID` and runs a keepalive loop, with a defined retry/timeout policy and Pydantic response models.
- The `a1_policy` loop-action executor runs as a background Kafka consumer INSIDE the rapp API container (kill-switch env, default off): consumes `maveric.loop.action.v1`, filters `adapter=a1_policy`, translates the frozen A.2 payload into a policy instance (deterministic instance id from `action_id`), applies via the connector, publishes `maveric.loop.feedback.v1` kind=`apply`, and routes `payload.rollback_of` to the rollback path (kind=`rollback`). It emits NO `kpi_window` feedback: A1-path KPI windows come from canonical PM via the data platform (NDT-side watch).
- Loop proposal emitter publishes to `maveric.loop.proposal.v1` only when the per-tenant feature flag is on; with the flag off, every public response is byte-identical to today. `target_adapter_hint` values come from the A.4 registry (default `nanolink_tr069`; `a1_policy` for RAN-policy-path tenants).
- `packaging/r1/` manifests exist for es/lb/cco/mro and validate against a Pydantic model; metadata only, loosely aligned to the OSC rApp Manager ASD prototype, explicitly ROADMAP (rApp Manager is pre-spec, "not intended for production use"); no R1 protocol claim.
- `nearrt_xapp` is a reserved registry key with a placeholder module + contract doc; zero near-RT protocol work exists anywhere (no submodule, no C code, no compose services, no E42 bridge).
- Full existing rApp suite passes unchanged: `PYTHONPATH=app:app/radplib/dependencies uv run pytest` (run inside `submodule/maveric_platform_rapp`).
- Zero CI/CD change: no new charts, Jenkins pipelines, registry images, or host ports. All lab components are compose-profile-only (`ric-lab`), like the `edgeagent` profile. Production posture (image mirroring, upstream charts) is documented in `artifacts/ric/`, never implemented in our pipelines.
- Every piece of copy obeys `artifacts/marketing/claims-guardrails.md`: "we integrate O-RAN SC NONRTRIC, the open-source non-RT RIC" and "A1-policy-aligned intents" are the ceiling; never "O-RAN compliant", "O-RAN certified", or "A1 compliant". Product name CloudlyNet. No em dash characters anywhere in this epic's deliverables.

---

## E3.S1: Hexagonal RIC ports, PolicyIntent model, A.4-keyed adapter registry

**ID:** E3.S1
**Title:** `app/ric/ports.py` RanControlPort/RanDataPort protocols, Pydantic `PolicyIntent` mapping 1:1 onto an A1 policy-instance body, adapter registry keyed by HLD Appendix A.4 keys
**Why:** Every downstream story (NONRTRIC connector, a1_policy executor, loop emitter hints, near-RT placeholder) programs against these ports; per HLD §4.4 the RIC layer is hexagonal so the RIC is swappable (OSC NONRTRIC lab today, a commercial SMO's A1 termination later) without touching intelligence code.
**Size:** M

**Scope:**
- In: `app/ric/` package skeleton; `ports.py` protocols exactly per HLD §4.4; `models.py` Pydantic intent/ack/status/capability models; `registry.py` adapter registry keyed by A.4 keys with `nearrt_xapp` reserved; unit tests.
- Out: any concrete adapter (S3); the executor (S4); any Kafka emission (S4, S5); wiring into API endpoints.

**Files (all under `submodule/maveric_platform_rapp/`):**
- Create `app/ric/__init__.py`
- Create `app/ric/models.py`
- Create `app/ric/ports.py`
- Create `app/ric/registry.py`
- Create `tests/test_ric_ports.py`

**Contract:**
- `RanControlPort` methods are fixed by HLD §4.4: `capabilities()`, `submit_policy_intent(PolicyIntent) -> IntentAck`, `delete_policy_intent(policy_id) -> IntentAck`, `policy_status(policy_id) -> PolicyStatusInfo`.
- `RanDataPort`: `subscribe(DataSubscriptionSpec) -> SubscriptionHandle`, `unsubscribe(handle)`. Normalized records from data adapters are emitted to `maveric.ingest.pm.v1` per HLD Appendix A.5; the port carries only the subscription lifecycle. NOTE: the only RESERVED streaming `source_type` for this layer is `nearrt_kpm_stream` (A.5) and it is never emitted in E3; no data adapter is implemented in this epic.
- `PolicyIntent.policy_object` IS the A1 policy-instance body, verbatim and 1:1 (HLD §4.4). The surrounding fields (`policy_id`, `tenant_id`, `adapter`, `policy_type_id`, `ric_id`, `transient`) are routing metadata the connector maps onto the PMS create call; nothing in `policy_object` is rewritten by the port layer.
- Registry keyed by the Appendix A.4 namespace. Keys owned by this layer: `a1_policy` (implemented, S3) and `nearrt_xapp` (RESERVED: registration attempts raise, lookups raise with a pointer to the placeholder contract doc, S7). Duplicate registration raises `ValueError`; unknown key raises `LookupError`.
- Wording rule everywhere (docstrings included): "A1-policy-aligned intents", never "A1 compliant"; no O-RAN compliance claims.

**Key snippets:**

```python
# app/ric/models.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class PolicyIntent(BaseModel):
    """A1-policy-aligned intent. policy_object maps 1:1 onto an A1 policy-instance body.

    NOT an A1 protocol message; never claim A1 compliance.
    """
    policy_id: str                      # client-supplied instance id (deterministic when derived from a loop action)
    tenant_id: str
    adapter: str                        # HLD Appendix A.4 key, e.g. "a1_policy"
    policy_type_id: str                 # registered/discovered type id, string form; connector maps per RIC
    ric_id: Optional[str] = None        # target near-RT RIC as known to the non-RT RIC; None = connector default
    policy_object: dict[str, Any]       # the A1 policy-instance body, verbatim (1:1)
    transient: bool = False
    created_at: datetime


class IntentAck(BaseModel):
    policy_id: str
    status: Literal["accepted", "applied", "rejected", "failed", "duplicate"]
    detail: Optional[str] = None
    ric_ref: Optional[str] = None       # opaque RIC/PMS-side reference, if any


class PolicyStatusInfo(BaseModel):
    policy_id: str
    enforced: Optional[bool] = None     # None = RIC did not report enforcement
    raw: dict[str, Any] = Field(default_factory=dict)   # PMS status body, verbatim


class RicCapabilities(BaseModel):
    adapter: str                        # A.4 key
    ric_ids: list[str] = Field(default_factory=list)
    policy_type_ids: list[str] = Field(default_factory=list)
    api_mode: Optional[str] = None      # "v3" | "v2" for the NONRTRIC connector
    notes: Optional[str] = None


class AdapterHealth(BaseModel):
    adapter: str
    status: Literal["up", "degraded", "down"]
    detail: Optional[str] = None


class DataSubscriptionSpec(BaseModel):
    metrics: list[str]                  # source metric names
    granularity_s: int = 60
    scope: dict[str, Any] = Field(default_factory=dict)


class SubscriptionHandle(BaseModel):
    subscription_id: str
    adapter: str
```

```python
# app/ric/ports.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.ric.models import (
    AdapterHealth, DataSubscriptionSpec, IntentAck, PolicyIntent,
    PolicyStatusInfo, RicCapabilities, SubscriptionHandle,
)


@runtime_checkable
class RanControlPort(Protocol):
    """Southbound control port. One implementation per adapter key (HLD Appendix A.4)."""
    adapter: str

    def capabilities(self) -> RicCapabilities: ...
    def submit_policy_intent(self, intent: PolicyIntent) -> IntentAck: ...
    def delete_policy_intent(self, policy_id: str) -> IntentAck: ...
    def policy_status(self, policy_id: str) -> PolicyStatusInfo: ...
    def health(self) -> AdapterHealth: ...


@runtime_checkable
class RanDataPort(Protocol):
    """Southbound data port. Adapters emit normalized PM records per HLD Appendix A.5."""
    adapter: str

    def subscribe(self, spec: DataSubscriptionSpec) -> SubscriptionHandle: ...
    def unsubscribe(self, handle: SubscriptionHandle) -> None: ...
```

```python
# app/ric/registry.py
from __future__ import annotations

from typing import Callable, TypeVar

from app.utils.logger import get_logger

logger = get_logger(__name__)

# One namespace, frozen in HLD Appendix A.4 (recorded in artifacts/design/internal-contracts.md
# section 6). E3 owns a1_policy and the RESERVED nearrt_xapp; the rest are smo_sim-side (E4).
ADAPTER_KEYS: frozenset[str] = frozenset({
    "nanolink_tr069", "o1_netconf", "ocudu_ws_collector", "open_mplane",
    "sas_domain_proxy", "nms_northbound", "a1_policy", "nearrt_xapp",
})
RESERVED_ADAPTER_KEYS: frozenset[str] = frozenset({"nearrt_xapp"})

_CONTROL_ADAPTERS: dict[str, type] = {}
_DATA_ADAPTERS: dict[str, type] = {}

T = TypeVar("T")


def register_control_adapter(adapter: str) -> Callable[[type[T]], type[T]]:
    def _wrap(cls: type[T]) -> type[T]:
        if adapter in RESERVED_ADAPTER_KEYS:
            raise ValueError(
                f"adapter key {adapter} is RESERVED (near-RT track deferred; "
                "see app/ric/adapters/nearrt/README.md)")
        if adapter not in ADAPTER_KEYS:
            raise ValueError(f"unknown adapter key {adapter} (not in HLD Appendix A.4)")
        if adapter in _CONTROL_ADAPTERS:
            raise ValueError(f"control adapter already registered for adapter={adapter}")
        _CONTROL_ADAPTERS[adapter] = cls
        logger.info("registered control adapter adapter=%s cls=%s", adapter, cls.__name__)
        return cls
    return _wrap


def get_control_adapter(adapter: str, **kwargs) -> "RanControlPort":
    if adapter in RESERVED_ADAPTER_KEYS:
        raise LookupError(
            f"adapter key {adapter} is RESERVED, no executor exists "
            "(see app/ric/adapters/nearrt/README.md)")
    try:
        return _CONTROL_ADAPTERS[adapter](**kwargs)
    except KeyError as exc:
        raise LookupError(f"no control adapter for adapter={adapter}") from exc

# register_data_adapter / get_data_adapter: same pattern over _DATA_ADAPTERS.
```

**Acceptance criteria:**
- `PolicyIntent`, `IntentAck`, `PolicyStatusInfo`, `RicCapabilities`, `DataSubscriptionSpec` round-trip via `model_dump_json()`/`model_validate_json()`.
- A dummy class implementing the five `RanControlPort` methods passes `isinstance(obj, RanControlPort)` (runtime_checkable protocol).
- Registry: register + resolve by `a1_policy` works; duplicate registration raises `ValueError`; unknown key raises; registering or resolving `nearrt_xapp` raises with a message naming the placeholder doc.
- No import of `app/ric/` from any existing module (zero behavior change).
- No docstring or comment claims A1/O-RAN/RIC compliance.

**Test plan:**
- Unit (`tests/test_ric_ports.py`): model validation happy/sad paths (e.g. bad `status` literal rejected, missing `policy_object` rejected), protocol conformance via `isinstance`, registry behaviors above including the reserved-key paths.
- Run: `cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest tests/test_ric_ports.py` then full suite `PYTHONPATH=app:app/radplib/dependencies uv run pytest`.

**Coding-agent prompt**

```
CONTEXT
You are working in the CloudlyNet backend monorepo (repo root = cloudlynet_ai). The frozen HLD is
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md; read §3, §4.4 and Appendix A.4 first
(the HLD was amended to v1.1: the RIC track is non-RT-first, the near-RT tier is a reserved
placeholder). The rApp service lives in submodule/maveric_platform_rapp (FastAPI app under app/,
vendored RL lib under app/radplib/). Git rule: cd into the submodule before any git operation.

TASK
Create the hexagonal RIC integration layer skeleton in submodule/maveric_platform_rapp:
1. app/ric/__init__.py (empty package marker)
2. app/ric/models.py: Pydantic models PolicyIntent (policy_id, tenant_id, adapter, policy_type_id,
   ric_id optional, policy_object dict that maps 1:1 onto an A1 policy-instance body, transient
   bool default False, created_at datetime), IntentAck (policy_id, status Literal
   accepted|applied|rejected|failed|duplicate, detail, ric_ref), PolicyStatusInfo (policy_id,
   enforced Optional[bool], raw dict), RicCapabilities (adapter, ric_ids, policy_type_ids,
   api_mode, notes), AdapterHealth, DataSubscriptionSpec, SubscriptionHandle.
3. app/ric/ports.py: runtime_checkable Protocols RanControlPort (adapter attr; capabilities(),
   submit_policy_intent(PolicyIntent)->IntentAck, delete_policy_intent(policy_id)->IntentAck,
   policy_status(policy_id)->PolicyStatusInfo, health()) and RanDataPort (adapter attr;
   subscribe(DataSubscriptionSpec)->SubscriptionHandle, unsubscribe(handle)). Method names are
   fixed by HLD §4.4; do not rename.
4. app/ric/registry.py: ADAPTER_KEYS frozenset holding the eight HLD Appendix A.4 keys
   (nanolink_tr069, o1_netconf, ocudu_ws_collector, open_mplane, sas_domain_proxy, nms_northbound,
   a1_policy, nearrt_xapp) and RESERVED_ADAPTER_KEYS = {"nearrt_xapp"}; decorator
   register_control_adapter(adapter) / register_data_adapter(adapter) and getters
   get_control_adapter / get_data_adapter. Duplicate registration raises ValueError; keys outside
   ADAPTER_KEYS raise ValueError; reserved keys raise on both register and get with a message
   pointing to app/ric/adapters/nearrt/README.md; unknown key on get raises LookupError. Use the
   platform logger (app/utils/logger.py get_logger).
5. tests/test_ric_ports.py covering model validation, protocol isinstance checks, and registry
   register/resolve/duplicate/unknown/reserved behaviors.

CONSTRAINTS
- Follow docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-3-ran-intelligence-ric.md story E3.S1
  Key snippets exactly for model field names (other epics consume these shapes).
- Pydantic-first, full type hints, from __future__ import annotations, concise docstrings.
- Do NOT import app.ric from any existing module. Do NOT touch existing files except adding tests.
- Wording: docstrings must say "A1-policy-aligned", never "A1 compliant"; no O-RAN/RIC compliance
  claims anywhere; no em dash characters in any text you write.

DEFINITION OF DONE
- cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest
  passes fully (new test file green, no existing test changed or broken).
```

---

## E3.S2: `ric-lab` compose profile: NONRTRIC A1-PMS + two A1 Simulators (images, not source)

**ID:** E3.S2
**Title:** Compose profile `ric-lab` with our own service definitions for `nonrtric-plt-a1policymanagementservice:2.11.0` + two `a1-simulator:2.8.1` containers (STD_2.0.0, OSC_2.1.0), PMS application config, healthchecks, and `artifacts/ric/` deployment notes
**Why:** HLD D1 (amended v1.1): the integrated open RIC is O-RAN SC NONRTRIC, consumed component-wise as container images + REST, never by copying source. The lab profile gives CloudlyNet a real non-RT RIC A1-PMS plus simulator-backed near-RT A1 terminations for connector and executor development, with zero CI/CD change.
**Size:** M

**Scope:**
- In: compose services `nonrtric-a1pms`, `a1-sim-std`, `a1-sim-osc` behind profile `ric-lab` (our own definitions, modeled on the upstream `nonrtric` repo `docker-compose/` samples but with tags re-pinned, because the upstream committed `.env` pins stale tags such as PMS 2.3.1); PMS application configuration file with `rics` entries pointing at the two sims; healthchecks; `compose.sh` convenience; `artifacts/ric/nonrtric-lab.md` runbook + deployment notes.
- Out: any chart/Jenkins/registry work (forbidden by §3.1); ICS, Control Panel, SDNC, rApp Manager, SME, RANPM containers (roadmap per D1); the connector code (S3); any near-RT RIC or E2-capable component (near-RT track is a reserved placeholder, S7).

**Files:**
- Modify `docker-compose.yaml` (repo root): add `nonrtric-a1pms`, `a1-sim-std`, `a1-sim-osc` services under profile `ric-lab`.
- Create `deploy/ric-lab/pms/application_configuration.json`
- Modify `scripts/kafka/compose.sh`: add `ric-lab` to the profile list handled by `down`, and a `ric-lab` subcommand (infra + ric-lab profile).
- Create `artifacts/ric/nonrtric-lab.md`

**Contract:**

Image pins (OUR pins; do not trust the upstream `.env`, it is stale):

| Service | Image | Interface version |
|---|---|---|
| `nonrtric-a1pms` | `nexus3.o-ran-sc.org:10002/o-ran-sc/nonrtric-plt-a1policymanagementservice:2.11.0` | northbound v3 (`{apiRoot}/a1-policy-management/v1`) + v2 (`/a1-policy/v2`) |
| `a1-sim-std` | `nexus3.o-ran-sc.org:10002/o-ran-sc/a1-simulator:2.8.1` | `STD_2.0.0` |
| `a1-sim-osc` | `nexus3.o-ran-sc.org:10002/o-ran-sc/a1-simulator:2.8.1` | `OSC_2.1.0` |

Compose additions (profile `ric-lab`; no host port mappings, everything stays on the `maveric` network; rapp reaches PMS at `http://nonrtric-a1pms:8081`):

```yaml
  nonrtric-a1pms:
    profiles: ["ric-lab"]
    image: nexus3.o-ran-sc.org:10002/o-ran-sc/nonrtric-plt-a1policymanagementservice:2.11.0
    container_name: nonrtric_a1pms
    volumes:
      - ./deploy/ric-lab/pms/application_configuration.json:/opt/app/policy-agent/data/application_configuration.json:ro
    depends_on: [a1-sim-std, a1-sim-osc]
    networks: [maveric]
    healthcheck:
      # v3 status endpoint; adjust the probe command to the tooling present in the image
      # (verify at bring-up: the image is Java/Spring; wget or curl availability differs per tag).
      test: ["CMD-SHELL", "wget -q -O /dev/null http://localhost:8081/a1-policy-management/v1/status || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 8

  a1-sim-std:
    profiles: ["ric-lab"]
    image: nexus3.o-ran-sc.org:10002/o-ran-sc/a1-simulator:2.8.1
    container_name: a1_sim_std
    environment:
      A1_VERSION: STD_2.0.0
      ALLOW_HTTP: "true"
    networks: [maveric]

  a1-sim-osc:
    profiles: ["ric-lab"]
    image: nexus3.o-ran-sc.org:10002/o-ran-sc/a1-simulator:2.8.1
    container_name: a1_sim_osc
    environment:
      A1_VERSION: OSC_2.1.0
      ALLOW_HTTP: "true"
    networks: [maveric]
```

PMS application configuration (`deploy/ric-lab/pms/application_configuration.json`): the `ric` entries point at the simulators by compose DNS name; the exact JSON schema (config key names, controller block) must be taken from the 2.11.0 image/docs at bring-up, keeping this shape:

```json
{
  "config": {
    "ric": [
      {"name": "ric-std", "baseUrl": "http://a1-sim-std:8085", "managedElementIds": []},
      {"name": "ric-osc", "baseUrl": "http://a1-sim-osc:8085", "managedElementIds": []}
    ]
  }
}
```

`artifacts/ric/nonrtric-lab.md` must cover, in this order:
1. What runs: O-RAN SC NONRTRIC A1 Policy Management Service 2.11.0 (Apache-2.0, developed upstream in ONAP CCSDK-ORAN, re-released by OSC; M-release) + two OSC A1 Simulators 2.8.1 as lab stand-ins for near-RT RIC A1 terminations. State plainly: the simulators terminate A1 statefully but are NOT functional RICs (no E2, no xApps).
2. Bring-up runbook: `./scripts/kafka/compose.sh ric-lab`; verify PMS `GET http://nonrtric-a1pms:8081/a1-policy-management/v1/rics` lists `ric-std` and `ric-osc`; note the v3 base-path trap (docs call the API "V3" but the served base path is `{apiRoot}/a1-policy-management/v1`) and the v2 fallback base `/a1-policy/v2`.
3. Tag policy: our compose re-pins current release tags because the upstream `nonrtric/docker-compose` sample `.env` is stale (it pins PMS 2.3.1); when bumping, take tags from the OSC release notes, never from the upstream `.env`.
4. Production posture: mirror the `nexus3.o-ran-sc.org:10002` images into our own registry before any customer-facing use (LF nexus has no pull SLA); customer K8s installs use the upstream NONRTRIC charts, never a chart in our pipelines; this stays a documented ops procedure, not CI/CD.
5. License and attribution: all consumed components are Apache-2.0. If the `pms-api-v3.yaml` OpenAPI spec file is ever vendored into this repo, keep its embedded O-RAN ALLIANCE copyright notice intact. Never use O-RAN compliance or certification language anywhere; the approved claim ceiling is "we integrate O-RAN SC NONRTRIC, the open-source non-RT RIC" and "A1-policy-aligned intents". Do not integrate RANPM (it deploys AGPLv3 MinIO); rApp Manager and SME are roadmap only.
6. No em dash characters in the file; product name CloudlyNet.

**Acceptance criteria:**
- `docker compose --profile ric-lab up -d` starts all three containers; PMS healthcheck goes healthy; `GET /a1-policy-management/v1/rics` (from a container on the `maveric` network) returns both rics with reachable state.
- `docker compose config` without `--profile ric-lab` shows the running set unchanged (no
  default-profile drift). **AMENDED 2026-08-03 (EPIC-9):** the no-host-ports clause is
  superseded. The policy service now publishes `${A1PMS_PORT:-8081}` because the NONRTRIC
  demo driver runs on the host and could not otherwise reach it. This follows the repo
  convention (the other lab-only profile, `edgeagent`, publishes 7547 and 9100) and leaves
  the constraint the clause actually protected, zero CI/CD change, fully intact. The two
  simulators still publish nothing. Rationale in `artifacts/ric/nonrtric-lab.md`.
- `./scripts/kafka/compose.sh down` also stops ric-lab containers; `./scripts/kafka/compose.sh ric-lab` brings up infra + profile.
- No chart, Jenkins, or image-registry file touched (verify `git -C submodule/maveric-deployment status` is clean).
- `artifacts/ric/nonrtric-lab.md` exists with all six sections; grep gates pass: no "O-RAN compliant", no "O-RAN certified", no "A1 compliant" (case-insensitive), no em dash characters.

**Test plan:**
- No Python unit tests (infra story). Manual/scripted verification per acceptance criteria on a lab host with network access to `nexus3.o-ran-sc.org:10002`.
- Existing suites untouched: `cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest` still green.

**Coding-agent prompt**

```
CONTEXT
CloudlyNet backend monorepo (repo root = cloudlynet_ai). Frozen HLD:
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md, decision D1 (amended v1.1) and §4.4.
The integrated open RIC is O-RAN SC NONRTRIC at the non-RT tier, consumed as container images +
REST from nexus3.o-ran-sc.org:10002, never by copying source. Everything is Apache-2.0 so images
MAY ship commercially after mirroring into our registry (documented posture only; zero CI/CD
change in this story). The repo already uses compose profiles for lab-only things (see the
edgeagent profile in docker-compose.yaml) and lifecycle goes through scripts/kafka/compose.sh.
Upstream reference: the nonrtric repo docker-compose/ samples show service wiring and the PMS
application_configuration.json shape, but its committed .env pins STALE tags (PMS 2.3.1); we
maintain our own compose with current tags.

TASK
1. Add three services to the repo-root docker-compose.yaml under profiles: ["ric-lab"], network
   maveric, NO host ports:
   - nonrtric-a1pms: image nexus3.o-ran-sc.org:10002/o-ran-sc/nonrtric-plt-a1policymanagementservice:2.11.0,
     container_name nonrtric_a1pms, mounts ./deploy/ric-lab/pms/application_configuration.json
     read-only at the path the 2.11.0 image expects (verify against the image/upstream sample;
     /opt/app/policy-agent/data/application_configuration.json is the historical location),
     depends_on both sims, healthcheck probing GET /a1-policy-management/v1/status on :8081
     (adjust probe command to tooling available in the image).
   - a1-sim-std: image nexus3.o-ran-sc.org:10002/o-ran-sc/a1-simulator:2.8.1, env
     A1_VERSION=STD_2.0.0, ALLOW_HTTP=true, container_name a1_sim_std.
   - a1-sim-osc: same image, env A1_VERSION=OSC_2.1.0, ALLOW_HTTP=true, container_name a1_sim_osc.
2. Create deploy/ric-lab/pms/application_configuration.json with ric entries ric-std ->
   http://a1-sim-std:8085 and ric-osc -> http://a1-sim-osc:8085 (verify the exact key names and
   sim port against the 2.11.0 image docs/upstream sample at bring-up; record what you verified).
3. Update scripts/kafka/compose.sh: include the ric-lab profile in the list that down cleans up,
   and add a "ric-lab" subcommand that starts infra + the ric-lab profile.
4. Write artifacts/ric/nonrtric-lab.md with the six sections mandated by story E3.S2 in
   docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-3-ran-intelligence-ric.md (what runs,
   bring-up + v3 base-path trap, tag re-pin policy vs stale upstream .env, production image
   mirroring + upstream charts posture, Apache-2.0 + O-RAN ALLIANCE attribution rule for a
   vendored pms-api-v3.yaml + never-compliance-claims, no em dashes).

CONSTRAINTS
- ZERO CI/CD change: no charts, Jenkins pipelines, registry pushes, or host ports. Lab-only =
  compose-profile-only. Do not modify submodule/maveric-deployment.
- Images only, never source: do not clone or vendor any NONRTRIC repo.
- Text obeys artifacts/marketing/claims-guardrails.md: never claim O-RAN, RIC, A1 or R1
  compliance/certification; approved ceiling: "we integrate O-RAN SC NONRTRIC, the open-source
  non-RT RIC". Product name CloudlyNet. No em dash characters (U+2014).
- If docker or network access is unavailable in your environment, still produce all files and add
  a TODO checklist at the top of artifacts/ric/nonrtric-lab.md naming the unverified items (image
  config mount path, sim port, healthcheck tooling); state clearly in your final report which
  steps were not executed.

DEFINITION OF DONE
- docker compose config validates with and without --profile ric-lab; compose.sh down covers
  ric-lab; artifacts/ric/nonrtric-lab.md complete; existing rApp tests still pass
  (cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest).
```

---

## E3.S3: NONRTRIC A1-PMS connector (`a1_policy` adapter, httpx)

**ID:** E3.S3
**Title:** `app/ric/adapters/nonrtric/client.py`: A1-PMS client (pinned v3 API, v2 fallback), `/services` registration + keepalive, CloudlyNet policy-type registration on the lab sims, per-RIC type discovery; registers adapter key `a1_policy`
**Why:** HLD §4.4 pins the OSC NONRTRIC A1-PMS connector as the first real RIC-plane executor. A1-style JSON policy is the most portable RIC seam (per the RIC landscape recon: the OSC southbound-connector pattern with multi-version support is the proven shape), and PMS gives CloudlyNet one northbound API over any number of near-RT RICs.
**Size:** L

**Scope:**
- In: httpx-based PMS client with both API modes; Pydantic response models; retry/timeout policy; service registration + keepalive loop; the CloudlyNet policy type (JSON schema derived from the Recommendation Table item shape) + a registration helper for the lab simulators' admin API; type discovery/negotiation surface for real RICs; the `a1_policy` control adapter implementing `RanControlPort`; config additions; unit tests.
- Out: the loop-action executor (S4); any consumer of `maveric.loop.action.v1`; wiring into `app/main.py` (S4 does the guarded wiring); RANPM/ICS/rApp Manager integration (roadmap per D1).

**Files (all under `submodule/maveric_platform_rapp/` unless noted):**
- Create `app/ric/adapters/__init__.py`
- Create `app/ric/adapters/nonrtric/__init__.py`
- Create `app/ric/adapters/nonrtric/api_models.py` (Pydantic response models)
- Create `app/ric/adapters/nonrtric/client.py` (PMS HTTP client, both modes, retries, services/keepalive)
- Create `app/ric/adapters/nonrtric/policy_type.py` (CloudlyNet type schema + simulator admin registration helper)
- Create `app/ric/adapters/nonrtric/adapter.py` (`@register_control_adapter("a1_policy")`)
- Modify `app/core/config.py` (additive settings only)
- Create `tests/test_nonrtric_client.py`
- Modify `artifacts/ric/nonrtric-lab.md` (extend runbook: policy-type registration + end-to-end policy create/status/delete verification)

**Contract:**

1. API modes (env-switchable; the mode maps paths AND field-name dialects):

| Operation | `A1PMS_API_MODE=v3` (default; R1-AP v5.0-aligned) | `A1PMS_API_MODE=v2` (fallback) |
|---|---|---|
| Base path | `{A1PMS_BASE_URL}/a1-policy-management/v1` (NAMING TRAP: the docs call this API "V3" but the served base path segment is `v1`) | `{A1PMS_BASE_URL}/a1-policy/v2` |
| Status | `GET /status` | `GET /status` |
| List RICs | `GET /rics` | `GET /rics` |
| Policy types | `GET /policy-types`, `GET /policy-types/{id}` | `GET /policy-types` |
| Create policy | `POST /policies` (body: camelCase PolicyObjectInformation: `nearRtRicId`, `policyId`, `policyTypeId`, `policyObject`, `serviceId`, `transient`) | `PUT /policies` (body: snake_case: `ric_id`, `policy_id`, `policytype_id`, `policy_data`, `service_id`, `transient`) |
| Read policy | `GET /policies/{policyId}` | `GET /policies/{policy_id}` |
| Policy status | `GET /policies/{policyId}/status` | `GET /policies/{policy_id}/status` |
| Delete policy | `DELETE /policies/{policyId}` | `DELETE /policies/{policy_id}` |
| Service registration | `PUT /services` then `PUT /services/{serviceId}/keepalive` | `PUT /services` then `PUT /services/keepalive?name={service}` |

The client owns the dialect mapping; callers only ever see `PolicyIntent`/`IntentAck`/`PolicyStatusInfo` (S1 models). `PolicyIntent.policy_object` goes into `policyObject`/`policy_data` verbatim (the 1:1 rule). Exact per-mode field names must be verified against the running 2.11.0 PMS at bring-up; the dialect split itself (v3 camelCase POST-create vs v2 snake_case PUT-create) is pinned here.

2. Service registration + keepalive: on client start, `PUT /services` registering `A1PMS_SERVICE_ID` with `keepAliveIntervalSeconds = 2 * A1PMS_KEEPALIVE_S` and no callback URL; a background keepalive task fires every `A1PMS_KEEPALIVE_S` seconds. This prevents PMS from garbage-collecting policies owned by a dead service. Every create call carries the service id.

3. Retry/timeout policy: single `httpx.Client` with `timeout=A1PMS_TIMEOUT_S` (default 10.0). GET/DELETE/PUT are retried up to `A1PMS_MAX_RETRIES` (default 3) on connect errors, timeouts, and 5xx, with exponential backoff (0.5s base, factor 2, jitter). POST create is retried only on connect errors (request provably not sent); because `policy_id` is client-supplied, a create that hits an already-exists conflict is mapped to `IntentAck(status="duplicate")`, not an error. 4xx (other than conflict) maps to `rejected`; exhausted retries/5xx map to `failed`. Connector methods never raise into callers; they return acks.

4. Policy types, two regimes (HLD §4.4):
- Lab sims: CloudlyNet registers its OWN policy type via the simulator admin API (`PUT {sim}/policytype?id=<id>` with the JSON schema body; the OSC_2.1.0 interface takes an integer type id, STD_2.0.0 a string id; the helper takes the id as a parameter). Type name `cloudlynet.cell_config.v1`; create-schema derived from the Recommendation Table item shape:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "cloudlynet.cell_config.v1",
  "type": "object",
  "properties": {
    "scope": {
      "type": "object",
      "properties": {"cell_id": {"type": "string"}},
      "required": ["cell_id"]
    },
    "statements": {
      "type": "object",
      "properties": {
        "el_degree": {"type": "number", "minimum": 0, "maximum": 15},
        "on_off": {"type": "boolean"}
      }
    }
  },
  "required": ["scope", "statements"]
}
```

- Real RICs (commercial SMOs / near-RT RICs behind PMS): the connector DISCOVERS the RIC's advertised types (`GET /policy-types` filtered per ric) and negotiates per RIC (the OSC multi-version southbound pattern); `capabilities()` surfaces the discovered `policy_type_ids` per `ric_id` so the caller can pick. No assumption that `cloudlynet.cell_config.v1` exists outside the lab.

5. New settings (additive, `app/core/config.py`, consumed via the existing `get_settings()`): `A1PMS_BASE_URL: str | None = None` (lab: `http://nonrtric-a1pms:8081`), `A1PMS_API_MODE: str = "v3"`, `A1PMS_SERVICE_ID: str = "cloudlynet-rapp"`, `A1PMS_TIMEOUT_S: float = 10.0`, `A1PMS_MAX_RETRIES: int = 3`, `A1PMS_KEEPALIVE_S: int = 60`, `A1PMS_DEFAULT_RIC_ID: str | None = None`, `A1PMS_POLICY_TYPE_ID: str = "cloudlynet.cell_config.v1"`.

6. `httpx` becomes a rapp dependency: recon confirms no service-to-service HTTP client exists in rapp today, so add `httpx` to `pyproject.toml` (and the effective lock for the image); it rides the existing image stream, no CI/CD change.

**Key snippets:**

```python
# app/ric/adapters/nonrtric/client.py (shape)
from __future__ import annotations

import threading
import time
from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.ric.adapters.nonrtric.api_models import PolicyTypeInfo, RicInfo
from app.ric.models import IntentAck, PolicyIntent, PolicyStatusInfo
from app.utils.logger import get_logger

logger = get_logger(__name__)


class A1PmsClient:
    """HTTP client for the OSC NONRTRIC A1 Policy Management Service.

    Pinned v3 API: base path {apiRoot}/a1-policy-management/v1, create = POST /policies.
    Fallback v2 (A1PMS_API_MODE=v2): base path /a1-policy/v2, create = PUT /policies.
    Carries A1-policy-aligned intents; makes no A1 or O-RAN compliance claim.
    """

    def __init__(self, base_url: str | None = None, api_mode: str | None = None,
                 service_id: str | None = None) -> None:
        s = get_settings()
        self._base_url = (base_url or s.A1PMS_BASE_URL or "").rstrip("/")
        self._mode = (api_mode or s.A1PMS_API_MODE).lower()
        self._service_id = service_id or s.A1PMS_SERVICE_ID
        self._http = httpx.Client(timeout=s.A1PMS_TIMEOUT_S)
        self._keepalive_stop = threading.Event()

    @property
    def _api_base(self) -> str:
        # v3 NAMING TRAP: the served base path segment is v1 even though the API is "V3".
        return (f"{self._base_url}/a1-policy-management/v1" if self._mode == "v3"
                else f"{self._base_url}/a1-policy/v2")

    def register_service(self) -> None: ...      # PUT /services + start keepalive thread
    def stop(self) -> None: ...                  # stop keepalive, close client

    def list_rics(self) -> list[RicInfo]: ...
    def list_policy_types(self, ric_id: str | None = None) -> list[PolicyTypeInfo]: ...
    def create_policy(self, intent: PolicyIntent) -> IntentAck: ...
        # v3: POST {api_base}/policies  body camelCase (policyObject = intent.policy_object verbatim)
        # v2: PUT  {api_base}/policies  body snake_case (policy_data = intent.policy_object verbatim)
        # conflict -> IntentAck(status="duplicate"); 4xx -> "rejected"; retries exhausted -> "failed"
    def get_policy_status(self, policy_id: str) -> PolicyStatusInfo: ...
    def delete_policy(self, policy_id: str) -> IntentAck: ...

    def _request_with_retry(self, method: str, url: str, *, retry_post: bool = False,
                            **kwargs) -> httpx.Response: ...
        # GET/PUT/DELETE: retry connect/timeout/5xx up to A1PMS_MAX_RETRIES, backoff 0.5s * 2^n + jitter
        # POST: retry only httpx.ConnectError (request provably unsent)
```

```python
# app/ric/adapters/nonrtric/adapter.py (shape)
from __future__ import annotations

from app.ric.adapters.nonrtric.client import A1PmsClient
from app.ric.models import (AdapterHealth, IntentAck, PolicyIntent,
                            PolicyStatusInfo, RicCapabilities)
from app.ric.registry import register_control_adapter


@register_control_adapter("a1_policy")
class NonRtRicControlAdapter:
    """RanControlPort over the NONRTRIC A1-PMS connector (HLD Appendix A.4 key: a1_policy)."""
    adapter = "a1_policy"

    def __init__(self, client: A1PmsClient | None = None) -> None:
        self._client = client or A1PmsClient()

    def capabilities(self) -> RicCapabilities: ...      # rics + discovered policy types + api_mode
    def submit_policy_intent(self, intent: PolicyIntent) -> IntentAck: ...
    def delete_policy_intent(self, policy_id: str) -> IntentAck: ...
    def policy_status(self, policy_id: str) -> PolicyStatusInfo: ...
    def health(self) -> AdapterHealth: ...              # GET /status -> up/down
```

**Acceptance criteria:**
- Unit tests (httpx mocked with respx or monkeypatch): v3 mode issues `POST {base}/a1-policy-management/v1/policies` with camelCase body carrying `policy_object` verbatim; v2 mode issues `PUT {base}/a1-policy/v2/policies` with snake_case body; conflict on create maps to `duplicate`; 4xx to `rejected`; connect-error exhaustion to `failed` (no exception escapes); GET retries on 5xx with backoff; keepalive thread fires `PUT .../keepalive` on schedule and stops cleanly; `list_policy_types` parses into `PolicyTypeInfo`.
- `policy_type.py` produces the exact schema above and its sim-registration helper hits `PUT {sim}/policytype?id=<id>` (mocked), accepting int and str ids.
- `get_control_adapter("a1_policy")` returns an object satisfying `RanControlPort` (isinstance check).
- Lab end-to-end (manual, documented in `artifacts/ric/nonrtric-lab.md`): with `ric-lab` up, register the type on both sims, create a policy through PMS targeting `ric-std`, read its status, delete it; record the verified v3 request/response field names in the runbook.
- rapp/rapp-worker prod behavior untouched: new modules are never imported by `app/main.py` or the worker in this story; full existing suite green.
- No text claims A1/O-RAN compliance; no em dashes.

**Test plan:**
- Unit: `cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest tests/test_nonrtric_client.py tests/test_ric_ports.py`
- Full regression: `PYTHONPATH=app:app/radplib/dependencies uv run pytest`
- Integration (lab host, documented not CI): compose bring-up + type registration + policy create/status/delete per acceptance criteria.

**Coding-agent prompt**

```
CONTEXT
CloudlyNet backend monorepo (repo root = cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md §4.4 (amended v1.1, non-RT-first) and
story E3.S3 in docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-3-ran-intelligence-ric.md
(follow its Contract section exactly: API mode table, retry policy, policy-type schema).
Prerequisites already merged: app/ric ports/models/registry (E3.S1; RanControlPort methods are
capabilities/submit_policy_intent/delete_policy_intent/policy_status/health) and the ric-lab
compose profile (E3.S2: PMS at http://nonrtric-a1pms:8081, sims a1-sim-std STD_2.0.0 and
a1-sim-osc OSC_2.1.0). KEY API FACTS (verified research): the recommended PMS "V3" API is served
at base path {apiRoot}/a1-policy-management/v1 (naming trap) with POST-create; the older v2 API is
at /a1-policy/v2 with PUT-create; /services registration + keepalive prevents PMS from
garbage-collecting policies owned by dead services; the A1 Simulator admin API accepts policy-type
PUT for the OSC_2.1.0 and STD_2.0.0 interfaces. The rApp config module is app/core/config.py with
a get_settings() accessor; the platform logger is app/utils/logger.py get_logger.

TASK
In submodule/maveric_platform_rapp (cd into it for git ops):
1. app/ric/adapters/nonrtric/api_models.py: Pydantic response models RicInfo (ric_id, state,
   policy_type_ids, managed_element_ids), PolicyTypeInfo (policy_type_id, schema dict),
   ServiceStatus. Tolerate both API dialects (populate_by_name + per-dialect aliases or explicit
   mapping functions).
2. app/ric/adapters/nonrtric/client.py: A1PmsClient per the epic Key snippet: api-mode-switched
   base path and field dialects (v3 camelCase POST-create; v2 snake_case PUT-create);
   PolicyIntent.policy_object passes through VERBATIM as policyObject/policy_data (1:1 rule);
   /services registration + background keepalive thread (interval A1PMS_KEEPALIVE_S, registered
   keepAliveIntervalSeconds = 2x); retry policy: GET/PUT/DELETE retry connect/timeout/5xx up to
   A1PMS_MAX_RETRIES with exponential backoff + jitter, POST retries connect errors only; create
   conflict -> IntentAck(status="duplicate"), other 4xx -> "rejected", exhausted -> "failed";
   methods return acks, never raise into callers.
3. app/ric/adapters/nonrtric/policy_type.py: CLOUDLYNET_CELL_CONFIG_SCHEMA exactly per the epic
   Contract (scope.cell_id required; statements.el_degree number 0..15; statements.on_off bool)
   and register_type_on_simulator(sim_base_url, type_id) helper doing
   PUT {sim}/policytype?id=<type_id> with the schema body (type_id may be int for OSC_2.1.0 or
   str for STD_2.0.0).
4. app/ric/adapters/nonrtric/adapter.py: @register_control_adapter("a1_policy") class
   NonRtRicControlAdapter implementing RanControlPort by delegating to A1PmsClient; capabilities()
   returns rics + per-RIC discovered policy types + api_mode (per-RIC type discovery/negotiation
   for real RICs; never assume the CloudlyNet type exists outside the lab).
5. Extend app/core/config.py Settings (additive only): A1PMS_BASE_URL=None, A1PMS_API_MODE="v3",
   A1PMS_SERVICE_ID="cloudlynet-rapp", A1PMS_TIMEOUT_S=10.0, A1PMS_MAX_RETRIES=3,
   A1PMS_KEEPALIVE_S=60, A1PMS_DEFAULT_RIC_ID=None, A1PMS_POLICY_TYPE_ID="cloudlynet.cell_config.v1".
6. Add httpx to pyproject.toml (and the effective lock for the image) if absent; no other
   dependency changes.
7. tests/test_nonrtric_client.py: both API modes (paths + body dialects + verbatim policy_object),
   duplicate/rejected/failed mapping, retry/backoff behavior (sleep mocked), keepalive lifecycle,
   policy-type schema shape + sim registration call, adapter isinstance RanControlPort. Mock all
   HTTP (respx or monkeypatch).
8. Extend artifacts/ric/nonrtric-lab.md: policy-type registration steps for both sims and a manual
   end-to-end verification (create via PMS -> status -> delete), with a note to record the
   verified v3 field names there at bring-up.

CONSTRAINTS
- Public rapp API and worker behavior byte-identical; new modules must not be imported from
  app/main.py or app/workers/ in this story (the executor story does the guarded wiring).
- Zero CI/CD change. Pydantic-first, type hints, platform logger, DRY (reuse get_settings, logger).
- Wording: "A1-policy-aligned intents", never "A1 compliant"; never O-RAN compliant/certified;
  product name CloudlyNet; no em dash characters.

DEFINITION OF DONE
- cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest is
  fully green (new + existing). Report any step you could not execute (e.g. no lab PMS) explicitly.
```

---

## E3.S4: `a1_policy` loop-action executor (in-container Kafka consumer, apply + rollback + feedback)

**ID:** E3.S4
**Title:** Background Kafka consumer inside the rapp API container: consume `maveric.loop.action.v1`, filter `adapter=a1_policy`, translate the frozen A.2 payload to a policy instance, apply via the S3 connector, publish `maveric.loop.feedback.v1`
**Why:** HLD §4.4 places the `a1_policy` loop-action executor in the rapp RIC layer (no new deployable). This is the RAN-policy leg of the closed loop: the NDT dispatches approved actions, this executor turns them into A1 policy instances on the non-RT RIC, and feedback flows back per the frozen A.3 matrix.
**Size:** L

**Scope:**
- In: executor module (consumer thread + dispatch router + translation); guarded startup wiring in `app/main.py` (kill-switch env, default off); A.2 payload translation (both forms) + deterministic policy-instance id; A.2 rollback routing; A.3 `apply`/`rollback` feedback publication; lab topic lines in `scripts/kafka/init-topics.sh` ONLY if E5.S1 has not landed; unit tests.
- Out: KPI-window feedback (`kind="kpi_window"`) - EXPLICITLY out: for the A1 path the KPI window comes from canonical PM via the data platform and is watched NDT-side (E2.S7's canonical-PM watch tick polls `/data/pm` for watching `a1_policy` actions); this executor never emits it. Also out: guardrail_breach feedback (no device-level watcher exists on this path); MRO actions; any UI.

**Files (all under `submodule/maveric_platform_rapp/` unless noted):**
- Create `app/ric/executor.py` (consumer loop + dispatch router)
- Create `app/ric/translation.py` (A.2 payload -> policy instance body; deterministic ids)
- Modify `app/main.py` (startup/shutdown hooks, guarded by the kill switch; thread start only, no import-time side effects beyond the module import)
- Modify `app/core/config.py` (additive settings)
- Modify `scripts/kafka/init-topics.sh` (repo root): ensure `maveric.loop.action.v1` + `maveric.loop.feedback.v1` lines exist - add ONLY if E5.S1 (owner-of-record for topic provisioning) has not landed; check for existing entries first
- Create `tests/test_a1_executor.py`

**Contract:**

1. Runtime shape: a daemon consumer thread started from the FastAPI startup hook when `A1_EXECUTOR_ENABLED=true` (default `false`; with the flag off, `app/main.py` imports the module but starts nothing and opens no connections). This mirrors the in-container background-consumer pattern the other epics use (E1's ingestion consumer runs inside the data_sim API container the same way). Consumer group `rapp-a1-executor`, manual commit after feedback publication (at-least-once; idempotency comes from the deterministic policy id), reusing the consumer construction/commit patterns from `app/workers/rapp_worker.py` and `app/event_handlers/kafka_handler.py` (do not fork new Kafka plumbing).

2. Input: `maveric.loop.action.v1`, envelope frozen in HLD §4.1 + Appendix A.2: `{action_id, tenant_id, adapter, target, payload, policy_ref, expires_at}`. Filter: process only `adapter == "a1_policy"`; everything else is committed and skipped silently (other executors own their keys).

3. Dispatch router (binding, A.2): inspect `payload.rollback_of` FIRST. If set, route to rollback, never to apply. Then check `expires_at`: an expired action publishes feedback `kind="apply", status="expired"` (audit-only for the NDT) and commits.

4. Translation seam (A.2 rules for this adapter):
- `target` is a JSON object. Cell-scoped `{"cell_id": "c1", "tick": 0}` is the primary form: `cell_id` goes into the policy body `scope`. Device-scoped `{"device_id": "..."}` MUST be accepted without crashing: the a1_policy adapter has no device registry, so it publishes `kind="apply", status="rejected"` with detail "a1_policy is cell-scoped; device targets are not routable" and commits (rejected is audit-only for the NDT).
- Recommendation form `{"cell_el_deg": 6.0, "on_off": true, "rollback_of": null}` translates to the CloudlyNet policy type body: `{"scope": {"cell_id": target.cell_id}, "statements": {"el_degree": payload.cell_el_deg, "on_off": payload.on_off}}` (omit absent keys; an empty statements set is rejected).
- Explicit-writes form `{"writes": [{"path": "...", "value": "..."}], "rollback_on_fail": true}` translates to `{"scope": {"cell_id": target.cell_id}, "statements": {write.path: write.value for each write}}`.
- Policy instance id is DETERMINISTIC from the action: `policy_id = str(uuid5(NAMESPACE_URL, "a1-policy:" + action_id))`. Redelivery of the same action therefore re-creates the same instance id and the connector's `duplicate` mapping absorbs it.
- The built `PolicyIntent` uses `policy_type_id = settings.A1PMS_POLICY_TYPE_ID`, `ric_id = settings.A1PMS_DEFAULT_RIC_ID` (per-tenant RIC routing is a later story), `transient = False`.

5. Apply path: `submit_policy_intent` via `get_control_adapter("a1_policy")`; then one `policy_status` fetch. Feedback `kind="apply"` on `maveric.loop.feedback.v1` (A.3 envelope, Kafka key = `tenant_id` bytes): ack `applied` + status enforced/unreported -> `status="applied"`; ack `duplicate` -> `status="duplicate"`; ack `rejected` -> `status="rejected"`; ack `failed` -> `status="failed"`. `command_id` = the policy instance id; `detail.readback` carries the raw PMS status body; `adapter="a1_policy"`.

6. Rollback path (A.2 binding): `payload.rollback_of = "<reverted action_id>"`. Derive the REVERTED action's policy id (`uuid5(NAMESPACE_URL, "a1-policy:" + rollback_of)`) and `delete_policy_intent` it. If the NDT supplied a previous instance body to restore (optional additive field `payload.reapply` carrying a prior recommendation-form payload), re-apply it as a new instance under THIS action's deterministic id after the delete. Feedback `kind="rollback"`, `status` in `rolled_back|failed` (delete ack `applied`/`duplicate` counts as `rolled_back`; a delete of a nonexistent instance also counts as `rolled_back` with detail, so rollback is idempotent).

7. KPI feedback: NONE from this executor. Document in the module docstring: "KPI-window feedback for the A1 path comes from canonical PM via the data platform (NDT-side canonical-PM watch, E2.S7); this executor emits only apply/rollback feedback."

8. New settings (additive): `A1_EXECUTOR_ENABLED: bool = False` (kill switch), `LOOP_ACTION_TOPIC: str = "maveric.loop.action.v1"`, `LOOP_FEEDBACK_TOPIC: str = "maveric.loop.feedback.v1"`, `A1_EXECUTOR_GROUP_ID: str = "rapp-a1-executor"`, `A1_EXECUTOR_POLL_TIMEOUT_S: float = 1.0`.

**Key snippets:**

```python
# app/ric/translation.py (shape)
from __future__ import annotations

import uuid
from typing import Any

ACTION_POLICY_NAMESPACE = "a1-policy:"


def policy_id_for_action(action_id: str) -> str:
    """Deterministic A1 policy-instance id for a loop action (idempotent redelivery)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ACTION_POLICY_NAMESPACE + action_id))


def action_to_policy_object(target: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Frozen A.2 payload (recommendation form OR explicit writes) -> policy-instance body.

    Raises TranslationError for device-scoped targets or empty statements; the caller maps
    that to feedback status="rejected" (audit-only for the NDT).
    """
```

```python
# app/ric/executor.py (shape)
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone

from app.core.config import get_settings
from app.event_handlers.kafka_handler import kafka_producer  # reuse; no new plumbing
from app.ric.registry import get_control_adapter
from app.ric.translation import action_to_policy_object, policy_id_for_action
from app.utils.logger import get_logger

logger = get_logger(__name__)


class A1PolicyExecutor:
    """maveric.loop.action.v1 consumer for adapter=a1_policy (HLD §4.4, Appendix A.2/A.3).

    Runs as a daemon thread inside the rapp API container; started only when
    A1_EXECUTOR_ENABLED is true. KPI-window feedback for the A1 path comes from canonical PM
    via the data platform (NDT-side canonical-PM watch, E2.S7); this executor emits only
    apply/rollback feedback.
    """

    def start(self) -> None: ...      # build consumer (group rapp-a1-executor), spawn thread
    def stop(self) -> None: ...       # signal, join, close consumer + adapter client

    def _handle(self, action: dict) -> None:
        # 1. adapter filter  2. rollback_of routing (rollback NEVER goes to apply)
        # 3. expires_at check -> kind=apply status=expired
        # 4. translate -> PolicyIntent(policy_id=policy_id_for_action(action_id), ...)
        # 5. apply via get_control_adapter("a1_policy") + one policy_status fetch
        # 6. publish feedback (A.3 envelope, key=tenant_id bytes), commit offset

    def _publish_feedback(self, *, action: dict, kind: str, status: str,
                          command_id: str | None, detail: dict | None) -> None:
        # A.3: {schema:"maveric.loop.feedback.v1", feedback_id: uuid4, action_id, tenant_id,
        #       adapter:"a1_policy", kind, status, command_id, kpis:{}, detail, observed_at}
```

```python
# app/main.py (guarded wiring; startup hook)
    settings = get_settings()
    if settings.A1_EXECUTOR_ENABLED:
        from app.ric.executor import A1PolicyExecutor
        app.state.a1_executor = A1PolicyExecutor()
        app.state.a1_executor.start()
        logger.info("a1_policy loop-action executor started")
    # shutdown hook: if getattr(app.state, "a1_executor", None): app.state.a1_executor.stop()
```

**Acceptance criteria:**
- With `A1_EXECUTOR_ENABLED` unset/false (default): importing `app.main` starts no thread, opens no Kafka consumer, instantiates no HTTP client; public behavior byte-identical.
- Unit tests (Kafka consumer/producer and adapter mocked): non-`a1_policy` actions are committed and skipped; expired action -> `kind="apply", status="expired"` feedback; recommendation form translates to the exact policy body above with deterministic `policy_id`; explicit-writes form translates; device-scoped target -> `rejected` feedback, no adapter call; apply happy path -> `applied` feedback with `command_id` = policy id and PMS status in `detail.readback`; duplicate ack -> `duplicate`; connector `failed` -> `failed`; rollback action deletes the REVERTED action's policy id and publishes `kind="rollback", status="rolled_back"`; rollback of a nonexistent instance still `rolled_back` (idempotent); feedback envelope validates field-for-field against HLD Appendix A.3 (schema, feedback_id, action_id, tenant_id, adapter, kind, status, command_id, detail, observed_at; Kafka key = tenant_id bytes).
- Redelivery of an already-applied action results in `duplicate` feedback, not a second policy instance (deterministic id + connector mapping).
- No `kind="kpi_window"` or `kind="guardrail_breach"` emission exists anywhere in the module (grep gate in tests).
- `scripts/kafka/init-topics.sh`: `maveric.loop.action.v1` and `maveric.loop.feedback.v1` ensure-lines present exactly once (added only if E5.S1 had not already landed them).
- Full existing suite green, unchanged.

**Test plan:**
- Unit (`tests/test_a1_executor.py`): all cases above with fakes/mocks; reuse the test conventions from the existing kafka worker utils tests (the best-covered area per repo docs).
- Run: `cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest tests/test_a1_executor.py` then full suite.
- Lab end-to-end (manual): with `ric-lab` up and `A1_EXECUTOR_ENABLED=true`, produce a hand-built A.2 action onto `maveric.loop.action.v1`; observe the policy instance on the STD sim and the `apply` feedback on `maveric.loop.feedback.v1`; produce the rollback action; observe deletion + `rollback` feedback. Document in `artifacts/ric/nonrtric-lab.md`.

**Coding-agent prompt**

```
CONTEXT
CloudlyNet backend monorepo (repo root = cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md §4.1, §4.4 (amended v1.1) and Appendix
A.2 + A.3 (the action and feedback payloads are FROZEN there), then story E3.S4 in
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-3-ran-intelligence-ric.md (follow its
Contract exactly: dispatch routing, translation rules, deterministic policy id, feedback mapping).
Already merged: app/ric ports/models/registry (E3.S1) and the NONRTRIC connector + a1_policy
adapter (E3.S3: get_control_adapter("a1_policy") returns a RanControlPort whose
submit_policy_intent/delete_policy_intent/policy_status return acks and never raise).
Patterns to reuse, do not fork: Kafka consumer construction, manual commit and poll loop from
app/workers/rapp_worker.py + app/event_handlers/kafka_handler.py (the rapp-worker consumes
maveric.rapp.train.v1 with enable_auto_commit=False and explicit offset commit); producer =
kafka_producer.send_message. Config module: app/core/config.py with get_settings(). Platform
logger: app/utils/logger.py. The executor runs INSIDE the rapp API container as a daemon thread
(same in-container background-consumer pattern E1 uses inside the data_sim API container); there
is NO new deployable.

TASK
In submodule/maveric_platform_rapp:
1. app/ric/translation.py: policy_id_for_action(action_id) = str(uuid5(NAMESPACE_URL,
   "a1-policy:" + action_id)); action_to_policy_object(target, payload) handling BOTH frozen A.2
   forms: recommendation {"cell_el_deg","on_off","rollback_of"} -> {"scope":{"cell_id":
   target.cell_id},"statements":{"el_degree":...,"on_off":...}} (omit absent keys, empty
   statements -> TranslationError) and explicit writes {"writes":[{"path","value"}]} ->
   statements={path: value}; device-scoped target {"device_id":...} -> TranslationError (the
   caller maps it to feedback status="rejected": a1_policy has no device registry).
2. app/ric/executor.py: A1PolicyExecutor daemon-thread consumer, group
   settings.A1_EXECUTOR_GROUP_ID ("rapp-a1-executor"), topic settings.LOOP_ACTION_TOPIC
   (maveric.loop.action.v1), manual commit AFTER feedback publication. Router (binding, A.2):
   payload.rollback_of set -> rollback path, NEVER apply; then expires_at past -> feedback
   kind="apply" status="expired". Apply path: build PolicyIntent (policy_id deterministic,
   policy_type_id=settings.A1PMS_POLICY_TYPE_ID, ric_id=settings.A1PMS_DEFAULT_RIC_ID,
   policy_object from translation, adapter="a1_policy"), submit via
   get_control_adapter("a1_policy"), one policy_status fetch, publish A.3 feedback kind="apply"
   with status mapped applied/duplicate/rejected/failed, command_id=policy id, detail.readback=
   raw PMS status. Rollback path: delete the policy id derived from payload.rollback_of; optional
   additive payload.reapply (a prior recommendation-form payload) is re-applied under THIS
   action's deterministic id after the delete; feedback kind="rollback" status
   rolled_back|failed; deleting a nonexistent instance is still rolled_back (idempotent).
   Feedback envelope EXACTLY per HLD Appendix A.3 (schema, feedback_id uuid4, action_id,
   tenant_id, adapter, kind, status, command_id, kpis {}, detail, observed_at RFC3339 UTC; Kafka
   message key = tenant_id bytes). Non-a1_policy actions: commit and skip silently. This executor
   NEVER emits kind="kpi_window" or "guardrail_breach": A1-path KPI windows come from canonical
   PM via the data platform (NDT-side watch); say so in the module docstring.
3. app/main.py: startup hook starts the executor ONLY when settings.A1_EXECUTOR_ENABLED
   (default False); shutdown hook stops it. No import-time side effects; with the flag off,
   importing app.main must not create threads, consumers, or HTTP clients.
4. app/core/config.py (additive): A1_EXECUTOR_ENABLED=False, LOOP_ACTION_TOPIC=
   "maveric.loop.action.v1", LOOP_FEEDBACK_TOPIC="maveric.loop.feedback.v1",
   A1_EXECUTOR_GROUP_ID="rapp-a1-executor", A1_EXECUTOR_POLL_TIMEOUT_S=1.0.
5. scripts/kafka/init-topics.sh (repo root): E5.S1 is the owner-of-record for topic provisioning.
   Check the script first; ONLY IF the maveric.loop.action.v1 / maveric.loop.feedback.v1 ensure
   lines are not already present (E5.S1 not landed), add them; never duplicate an existing entry.
6. tests/test_a1_executor.py: every acceptance-criteria case (filter/skip, expired, both
   translation forms, device-target rejection, deterministic policy id, apply status mapping,
   duplicate absorption on redelivery, rollback delete + idempotency + reapply, A.3 envelope
   field-for-field, no kpi_window/guardrail_breach strings in the module source). Mock Kafka and
   the adapter; no network.

CONSTRAINTS
- HARD: default state OFF; with A1_EXECUTOR_ENABLED unset, public rapp behavior is byte-identical
  and no background resources are created. Topic names are frozen shared contracts; do not rename.
- At-least-once semantics: commit only after feedback publication; idempotency via the
  deterministic policy id. Reuse existing Kafka plumbing; do not add new client libraries.
- Pydantic-first, type hints, platform logger, DRY. No em dashes; no compliance claims.

DEFINITION OF DONE
- cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest
  fully green (new + existing). Report untested lab steps explicitly.
```

---

## E3.S5: rApp loop proposal emitter (feature-flagged, `maveric.loop.proposal.v1`)

**ID:** E3.S5
**Title:** After day-scope inference, publish recommendation proposals to `maveric.loop.proposal.v1`, gated by a per-tenant feature flag; direct response behavior unchanged
**Why:** The HLD closed loop (§2, §4.1) starts with rapp emitting recommendation proposals for the NDT decision hub (E2 epic) to evaluate and dispatch; this story creates that emission without touching the public `/infer` contract.
**Size:** M

**Scope:**
- In: emitter module; the FROZEN proposal payload (HLD Appendix A.1) on `maveric.loop.proposal.v1`; per-tenant flag read from `tenants.feature_flags['loop_proposals']` (same read-only pattern as smo_sim's feature guard) plus a global env kill-switch (default off); `target_adapter_hint` selection (A.4 keys; per-tenant override); hook in the day-scope sync `/infer` path for ES/LB/CCO; topic line ensured in lab `scripts/kafka/init-topics.sh` (only if E5.S1, the owner-of-record, has not landed); unit tests.
- Out: MRO proposals (different payload: hyst/ttt; lands with E5 loop hardening); tick-scope and compare emission; NDT HTTP path (`POST /ndt/loop/proposals` is E2's API; E3 uses the topic per §4.2 "also via topic"); any consumer.

**Files:**
- Create `submodule/maveric_platform_rapp/app/services/loop_emitter.py`
- Modify `submodule/maveric_platform_rapp/app/core/config.py` (additive: `LOOP_PROPOSALS_ENABLED: bool = False`, `LOOP_PROPOSAL_TOPIC: str = "maveric.loop.proposal.v1"`, `LOOP_DEFAULT_ADAPTER_HINT: str = "nanolink_tr069"`)
- Modify `submodule/maveric_platform_rapp/app/api/v1/endpoints/rapps.py` (day-scope sync completion block, after the `inference_runs` row is persisted, around the `response.status_code = status.HTTP_200_OK` line of the day path; best-effort call, never affects the response)
- Modify `scripts/kafka/init-topics.sh` (repo root): ensure the `maveric.loop.proposal.v1` topic line exists - add ONLY if E5.S1 (owner-of-record for topic provisioning) has not landed; check for an existing entry first
- Create `submodule/maveric_platform_rapp/tests/test_loop_emitter.py`

**Contract:**

Topic name is fixed by HLD §4.1: `maveric.loop.proposal.v1`. The payload is FROZEN in HLD Appendix A.1 (E2's NDT consumer parses exactly this shape; this story is the producer; the emitting module of record is `app/services/loop_emitter.py`):

```json
{
  "event": "loop.proposal",
  "version": 1,
  "proposal_id": "<uuid5(NAMESPACE_URL, 'loop-proposal:' + run_id)>",
  "tenant_id": "<uuid>",
  "source": {"service": "rapp", "rapp_id": "es", "rapp_model_id": "energysavingmodel-01", "run_id": "<inference run id>"},
  "refs": {
    "baseline_id": "baseline-01",
    "bdt_id": "bdt-01",
    "ue_dataset_id": "dataset-01",
    "scope": {"type": "day", "day": 0}
  },
  "per_tick_recommendations": [
    {"tick": 0, "items": [{"cell_id": "cell_1", "el_degree": 4.0, "on_off": true}]}
  ],
  "kpi_summary": {"guardrail_kpis": {}, "objective_kpis": {}},
  "target_adapter_hint": "nanolink_tr069",
  "created_at": "2026-07-16T10:00:00Z"
}
```

- `per_tick_recommendations` items reuse the EXACT public response shape (`app/models/rapp.py`: `cell_id`, `el_degree`, `on_off`); `tick` is serialized as an INTEGER 0-23 (coerce if the source dict carries string ticks). Note for the NDT consumer: the NDT evaluate API (§4.2) uses `cell_el_deg`; mapping `el_degree -> cell_el_deg` is the consumer's concern, pinned in HLD Appendix A.1 so neither side guesses.
- `target_adapter_hint` takes values from the HLD Appendix A.4 registry. Guidance (v1.1): producer default is `nanolink_tr069` (device-plane actuation via smo_sim); tenants on the RAN-policy path get `a1_policy` (routes the action to this epic's S4 executor via the NDT). `nearrt_xapp` is RESERVED and must never be emitted as a hint. Selection: per-tenant override read from `tenants.feature_flags['loop_adapter_hint']` (string, validated against `app.ric.registry.ADAPTER_KEYS` minus reserved keys; invalid or absent falls back to `settings.LOOP_DEFAULT_ADAPTER_HINT`).
- `kpi_summary` carries the already-computed `guardrail_kpis` and `objective_kpis` dicts verbatim from the evaluation result (no recomputation).
- Gating: emit only when `settings.LOOP_PROPOSALS_ENABLED` is true AND `tenants.feature_flags` jsonb for the tenant contains truthy key `loop_proposals` (read-only SELECT on the gateway-owned table, mirroring `smo_sim/app/api/v1/custom/feature_guard.py`). Any check failure = skip emission silently (log info).
- Delivery is best-effort: producer failure logs a warning (+ `log_error_to_mongodb` severity `warning`) and never changes the HTTP response. Uses the existing `kafka_producer.send_message(topic, json.dumps(payload))` from `app/event_handlers/kafka_handler.py`. Kafka message key = `tenant_id` bytes (A.1).

**Key snippets:**

```python
# app/services/loop_emitter.py
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.event_handlers.kafka_handler import kafka_producer
from app.ric.registry import ADAPTER_KEYS, RESERVED_ADAPTER_KEYS
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _tenant_flags(db: Session, tenant_id: str) -> dict:
    """Read-only fetch of the gateway-owned tenants.feature_flags jsonb."""
    row = db.execute(
        text("SELECT feature_flags FROM tenants WHERE tenant_id = :tid"), {"tid": tenant_id}
    ).fetchone()
    flags = row[0] if row else None
    return flags if isinstance(flags, dict) else {}


def _resolve_adapter_hint(flags: dict, override: Optional[str]) -> str:
    """A.4-validated hint: explicit override > tenant flag loop_adapter_hint > default."""
    settings = get_settings()
    candidate = override or flags.get("loop_adapter_hint") or settings.LOOP_DEFAULT_ADAPTER_HINT
    if candidate not in ADAPTER_KEYS or candidate in RESERVED_ADAPTER_KEYS:
        logger.warning("invalid loop_adapter_hint=%s, falling back to default", candidate)
        return settings.LOOP_DEFAULT_ADAPTER_HINT
    return candidate


def emit_day_proposal(
    db: Session,
    *,
    tenant_id: str,
    rapp_id: str,
    rapp_model_id: str,
    run_id: str,
    baseline_id: str,
    bdt_id: str,
    ue_dataset_id: str,
    day: int,
    evaluation_result: dict[str, Any],
    adapter_hint: Optional[str] = None,
) -> bool:
    """Best-effort publish of a loop proposal; NEVER raises into the request path."""
    settings = get_settings()
    if not settings.LOOP_PROPOSALS_ENABLED:
        return False
    try:
        flags = _tenant_flags(db, tenant_id)
        if not flags.get("loop_proposals"):
            return False
        payload = {
            "event": "loop.proposal",
            "version": 1,
            "proposal_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"loop-proposal:{run_id}")),
            "tenant_id": tenant_id,
            "source": {
                "service": "rapp",
                "rapp_id": rapp_id,
                "rapp_model_id": rapp_model_id,
                "run_id": run_id,
            },
            "refs": {
                "baseline_id": baseline_id,
                "bdt_id": bdt_id,
                "ue_dataset_id": ue_dataset_id,
                "scope": {"type": "day", "day": day},
            },
            "per_tick_recommendations": _int_ticks(
                evaluation_result.get("per_tick_recommendations") or []
            ),  # tick coerced to int per HLD Appendix A.1
            "kpi_summary": {
                "guardrail_kpis": evaluation_result.get("guardrail_kpis") or {},
                "objective_kpis": evaluation_result.get("objective_kpis") or {},
            },
            "target_adapter_hint": _resolve_adapter_hint(flags, adapter_hint),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if not kafka_producer or not kafka_producer.send_message(
            settings.LOOP_PROPOSAL_TOPIC, json.dumps(payload)
        ):
            logger.warning("loop proposal publish failed run_id=%s tenant=%s", run_id, tenant_id)
            return False
        logger.info("loop proposal published run_id=%s tenant=%s", run_id, tenant_id)
        return True
    except Exception:  # noqa: BLE001 - must never break the inference response
        logger.warning("loop proposal emission error run_id=%s", run_id, exc_info=True)
        return False
```

Hook (day-scope sync path in `rapps.py`, immediately before `response.status_code = status.HTTP_200_OK` of the day branch; the run row is already persisted there):

```python
        from app.services.loop_emitter import emit_day_proposal  # top-of-file import in practice
        emit_day_proposal(
            db,
            tenant_id=tenant_id, rapp_id=rapp_id.value, rapp_model_id=rapp_model_id,
            run_id=run_id, baseline_id=baseline_id, bdt_id=bdt_id,
            ue_dataset_id=ue_dataset_id, day=evaluated_day_value,
            evaluation_result=evaluation_result,
        )
```

**Acceptance criteria:**
- With `LOOP_PROPOSALS_ENABLED` unset/false (default): zero Kafka messages, zero extra DB queries beyond today, `/infer` responses byte-identical (assert on serialized envelope in tests).
- With env flag on but tenant flag absent/false: no emission.
- With both flags on: exactly one message on `maveric.loop.proposal.v1` per completed day-scope evaluation, matching the payload contract (validated field-by-field in tests, producer mocked); repeated identical requests reuse the same `proposal_id` (uuid5 of run_id).
- Hint selection: default `nanolink_tr069`; tenant flag `loop_adapter_hint: "a1_policy"` switches the emitted hint; `nearrt_xapp` or an unknown string in the flag falls back to the default with a warning; the emitted value is always a non-reserved A.4 key.
- Producer failure or DB error during flag check: response still 200, warning logged, no exception propagates.
- `scripts/kafka/init-topics.sh` creates the topic in the lab stack (only added if E5.S1 had not landed it).
- Full existing suite green, unchanged.

**Test plan:**
- Unit (`tests/test_loop_emitter.py`): flag matrix (env off / tenant off / both on), payload shape + determinism of `proposal_id`, hint-selection matrix (default, tenant override, reserved key rejected, unknown key rejected), producer-failure swallow, DB-error swallow. Mock `kafka_producer` and the `tenants` SELECT (SQLite/monkeypatched session per existing test conventions in `tests/conftest.py`).
- Integration-ish: extend day-mode endpoint test to assert the response envelope is unchanged when the emitter is active (mock producer) and that `emit_day_proposal` was called with the persisted `run_id`.
- Run: `cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest`.

**Coding-agent prompt**

```
CONTEXT
CloudlyNet backend monorepo. Read docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md §2, §4.1,
§4.2, Appendix A.1 (the proposal payload is FROZEN there) and Appendix A.4 (adapter keys), then
story E3.S5 in docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-3-ran-intelligence-ric.md
(the NDT consumer in epic E2 parses exactly the Appendix A.1 shape). The rApp
day-scope /infer path lives in submodule/maveric_platform_rapp/app/api/v1/endpoints/rapps.py: the
sync day branch computes evaluation_result via app/services/rapp_evaluator.evaluate_rapp, derives
run_id = uuid5("rapp-day-eval:{cache_key}"), persists an inference_runs row, then returns 200.
Kafka publishing pattern to reuse: the train endpoint in the same file publishes with
kafka_producer.send_message("maveric.rapp.train.v1", json.dumps(event)). Feature-flag read pattern
to mirror: submodule/maveric_platform_smo_sim/app/api/v1/custom/feature_guard.py reads
tenants.feature_flags jsonb read-only. Prerequisite: app/ric/registry.py (E3.S1) exposes
ADAPTER_KEYS and RESERVED_ADAPTER_KEYS.

TASK
1. Create app/services/loop_emitter.py exactly per the E3.S5 Key snippet: emit_day_proposal(...)
   best-effort, gated by settings.LOOP_PROPOSALS_ENABLED AND tenants.feature_flags['loop_proposals'],
   publishing the FROZEN HLD Appendix A.1 payload (source nested as {service, rapp_id,
   rapp_model_id, run_id}; tick always an int) to settings.LOOP_PROPOSAL_TOPIC via the existing
   kafka_producer; target_adapter_hint resolved as: explicit override > tenant flag
   loop_adapter_hint > settings.LOOP_DEFAULT_ADAPTER_HINT, validated against ADAPTER_KEYS minus
   RESERVED_ADAPTER_KEYS (nearrt_xapp must never be emitted; invalid values fall back to the
   default with a warning); never raises; platform logger; log_error_to_mongodb only at warning
   severity on publish failure (optional).
2. Extend app/core/config.py Settings (additive): LOOP_PROPOSALS_ENABLED: bool = False,
   LOOP_PROPOSAL_TOPIC: str = "maveric.loop.proposal.v1",
   LOOP_DEFAULT_ADAPTER_HINT: str = "nanolink_tr069".
3. Hook the day-scope sync completion in app/api/v1/endpoints/rapps.py: after the inference_runs
   row is persisted and before the 200 return, call emit_day_proposal with the persisted run_id,
   tenant/model/baseline/bdt/dataset ids, evaluated day, and evaluation_result. One call site only;
   do not touch tick-scope, MRO, or compare paths.
4. scripts/kafka/init-topics.sh (repo root): E5.S1 is the owner-of-record for topic
   provisioning. Check the script first; ONLY IF the maveric.loop.proposal.v1 ensure_topic
   line is not already present (E5.S1 not landed), add it with
   LOOP_PROPOSAL_TOPIC_PARTITIONS default 2; never duplicate an existing entry.
5. tests/test_loop_emitter.py: flag matrix (env off, tenant off, both on), payload field-by-field
   check against HLD Appendix A.1 incl. per_tick_recommendations passthrough with items
   {cell_id, el_degree, on_off} and INTEGER ticks, the nested source block, uuid5 proposal_id
   determinism, the hint-selection matrix (default nanolink_tr069, tenant override a1_policy,
   nearrt_xapp and unknown values fall back), producer-failure and DB-error swallowing. Also
   extend the existing day-mode endpoint test to prove the HTTP envelope is byte-identical with
   the feature off and on (producer mocked).

CONSTRAINTS
- HARD: public /rapps/** responses stay byte-compatible in all flag states; the emitter must be
  incapable of breaking the request (catch-all, log, return False). Default state is OFF.
- Topic name maveric.loop.proposal.v1 is a frozen shared contract; do not rename. Do not add an
  HTTP path to the NDT; topic-only in this story.
- Pydantic-first elsewhere, but the payload here is a plain dict serialized with json.dumps to
  match the existing producer contract (value_serializer str-encodes). Type hints, platform logger.
- Zero CI/CD change: only the local scripts/kafka/init-topics.sh; deployment topic provisioning is
  an ops step outside this story. No em dashes; no compliance claims.

DEFINITION OF DONE
- cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest fully
  green, including untouched existing tests proving no behavior drift.
```

---

## E3.S6: R1-shaped rApp packaging facade (metadata only, ROADMAP posture)

**ID:** E3.S6
**Title:** `packaging/r1/` manifests (id, version, data-needs, policy-types produced, artifact refs) + validating Pydantic model, loosely aligned to the OSC rApp Manager ASD prototype; onboarding via CAPIF/Service Manager registration is explicitly ROADMAP
**Why:** Commercial rApp distribution converges on the non-RT/SMO tier (Ericsson EIAP, Nokia MantaRay, Samsung CognitiV NOS); an R1-shaped metadata facade lets CloudlyNet onboard its rApps there later without re-architecture. The open-source packaging reference is the OSC rApp Manager ASD prototype, which is pre-spec and "not intended for production use" (its ONAP ACM + SME + DME dependency chain confirms it): so this story ships metadata only and stamps the whole surface ROADMAP.
**Size:** S

**Scope:**
- In: manifest schema (Pydantic), four manifests (es, lb, cco, mro), loader + validation test, README stating the ROADMAP + no-claims posture.
- Out: any R1 protocol code (SME/CAPIF/Service Manager/DME clients, A1 services), rApp Manager deployment or ASD/CSAR packaging tooling, any packaging pipeline/CI, any SMO onboarding work.

**Files (all under `submodule/maveric_platform_rapp/`):**
- Create `app/ric/r1_manifest.py`
- Create `packaging/r1/README.md`
- Create `packaging/r1/es/manifest.yaml`
- Create `packaging/r1/lb/manifest.yaml`
- Create `packaging/r1/cco/manifest.yaml`
- Create `packaging/r1/mro/manifest.yaml`
- Create `tests/test_r1_manifest.py`

**Contract:**

```python
# app/ric/r1_manifest.py
from __future__ import annotations
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import yaml


class DataNeed(BaseModel):
    metric: str                       # canonical metric name (TS 28.552 where mappable)
    source: str = "pm_measurements"   # canonical data platform table (HLD §4.3)
    granularity_s: int = 3600


class PolicyTypeProduced(BaseModel):
    id: str                           # e.g. "cloudlynet.cell_config.v1"
    aligned_to: str = "A1-policy-aligned intent (no A1 compliance claim)"


class ArtifactRefs(BaseModel):
    model_registry_table: str = "rapp_models"
    s3_key_template: str              # existing convention, e.g. "{tenant}/models/rapps/es/{model}.zip"


class RappInfo(BaseModel):
    id: str                           # "cloudlynet-es" | "cloudlynet-lb" | "cloudlynet-cco" | "cloudlynet-mro"
    name: str
    version: str                      # semver
    vendor: str = "CloudlyIO"
    description: Optional[str] = None


class R1Manifest(BaseModel):
    """R1-shaped rApp packaging metadata, loosely aligned to the OSC rApp Manager ASD prototype.

    Facade only, ROADMAP: no R1 protocol implementation or claim; no ASD/CSAR packaging; no
    CAPIF/Service Manager registration (upstream rApp Manager is pre-spec, not for production).
    """
    schema_id: str = Field(alias="schema", default="cloudlynet.r1.manifest/v1")
    rapp: RappInfo
    data_needs: list[DataNeed] = Field(default_factory=list)
    policy_types_produced: list[PolicyTypeProduced] = Field(default_factory=list)
    artifacts: ArtifactRefs

    model_config = {"populate_by_name": True}


def load_manifest(path: Path) -> R1Manifest:
    return R1Manifest.model_validate(yaml.safe_load(path.read_text()))
```

Example manifest (`packaging/r1/es/manifest.yaml`):

```yaml
schema: cloudlynet.r1.manifest/v1
rapp:
  id: cloudlynet-es
  name: CloudlyNet Energy Saving rApp
  version: 1.0.0
  vendor: CloudlyIO
  description: RL-based cell tilt and on/off recommendations scored by the Network Digital Twin.
data_needs:
  - {metric: DRB.UEThpDl, source: pm_measurements, granularity_s: 3600}
  - {metric: RRU.PrbTotDl, source: pm_measurements, granularity_s: 3600}
  - {metric: RRC.ConnMean, source: pm_measurements, granularity_s: 3600}
policy_types_produced:
  - id: cloudlynet.cell_config.v1
artifacts:
  model_registry_table: rapp_models
  s3_key_template: "{tenant}/models/rapps/es/{model}.zip"
```

(mro's `s3_key_template` reflects its JSON artifact naming; keep templates identical to the existing S3 conventions in `app/services/utils/data_loader.py` / `app/workers/rapp_worker.py`; do NOT invent new keys, per HLD §3.3. `policy_types_produced` for es/lb/cco is `cloudlynet.cell_config.v1`, the S3-registered type; mro stays empty until its control action exists.)

**Acceptance criteria:**
- All four manifests load and validate via `load_manifest`; a test iterates `packaging/r1/*/manifest.yaml`.
- `s3_key_template` values match the templates actually used by `data_loader.py`/`rapp_worker.py` (assert against the existing constants/paths in the test to prevent drift).
- `packaging/r1/README.md` states: metadata facade for future non-RT RIC/SMO onboarding (EIAP, MantaRay); loosely aligned to the OSC rApp Manager ASD prototype; CAPIF/Service Manager registration and any rApp Manager integration are ROADMAP because upstream rApp Manager is pre-spec and "not intended for production use"; "R1-shaped" only, no R1 protocol implementation, conformance, or compliance claim; product name CloudlyNet; no em dashes.
- PyYAML availability: reuse if already a dependency; otherwise add to dev/runtime deps minimally (check `pyproject.toml` first).
- Full suite green.

**Test plan:**
- Unit (`tests/test_r1_manifest.py`): validate all manifests; reject a manifest with a missing `rapp.id`; s3 template drift check.
- Run: `cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest tests/test_r1_manifest.py` then full suite.

**Coding-agent prompt**

```
CONTEXT
CloudlyNet backend monorepo. Read docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md §4.4
(packaging/r1; amended v1.1) and story E3.S6 in
docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-3-ran-intelligence-ric.md. The rApp service
(submodule/maveric_platform_rapp) hosts four rApps: es, lb, cco, mro. Their model artifacts live in
S3 under existing key templates (see app/services/utils/data_loader.py and
app/workers/rapp_worker.py; ES/LB/CCO artifacts are {tenant}/models/rapps/{rapp}/{model}.zip, MRO
persists a JSON artifact). Purpose: an R1-SHAPED metadata facade, loosely aligned to the OSC rApp
Manager ASD packaging prototype, so these rApps can later onboard onto commercial non-RT RIC/SMO
platforms (Ericsson EIAP, Nokia MantaRay). Upstream OSC rApp Manager is pre-spec and "not intended
for production use", so onboarding automation (CAPIF/Service Manager registration, ASD/CSAR) is
explicitly ROADMAP; this story is metadata only, no protocol code, no compliance claims.

TASK
In submodule/maveric_platform_rapp:
1. app/ric/r1_manifest.py per the epic Key snippet: Pydantic models DataNeed, PolicyTypeProduced,
   ArtifactRefs, RappInfo, R1Manifest (schema alias "schema", default "cloudlynet.r1.manifest/v1"),
   and load_manifest(path) using yaml.safe_load.
2. packaging/r1/{es,lb,cco,mro}/manifest.yaml with real values: ids cloudlynet-es/-lb/-cco/-mro,
   version 1.0.0, vendor CloudlyIO, data_needs drawn from canonical PM metrics (DRB.UEThpDl,
   RRU.PrbTotDl, RRC.ConnMean etc.), policy_types_produced [cloudlynet.cell_config.v1] for
   es/lb/cco (mro: leave empty until its control action exists), artifacts.s3_key_template copied
   EXACTLY from the existing loader/worker conventions (verify in code; do not invent keys).
3. packaging/r1/README.md: purpose, "R1-shaped metadata facade" posture, loose alignment to the
   OSC rApp Manager ASD prototype, explicit ROADMAP statement (rApp Manager is pre-spec, "not
   intended for production use"; CAPIF/Service Manager registration deferred), explicit statement
   that no R1 protocol implementation/conformance/compliance is claimed, pointer to
   artifacts/marketing/claims-guardrails.md.
4. tests/test_r1_manifest.py: all four manifests validate; missing rapp.id fails; s3_key_template
   matches the template used in code (import or duplicate the constant and assert equality).
5. Ensure PyYAML is available (check pyproject.toml; add minimally if absent).

CONSTRAINTS
- Metadata only; no new runtime imports from app/main.py or workers. Product name CloudlyNet; no em
  dashes; never write "R1 compliant". S3 key conventions are a frozen contract (HLD §3.3): copy,
  do not redesign.

DEFINITION OF DONE
- cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest fully
  green.
```

---

## E3.S7: Near-RT placeholder: reserved `nearrt_xapp` key + contract doc

**ID:** E3.S7
**Title:** Reserved adapter key `nearrt_xapp`: registry stub module + contract doc capturing the near-RT findings; no submodule, no C code, no compose services
**Why:** HLD v1.1 defers the near-RT tier (D1 amended): the market's commercial energy sits at the non-RT tier and xApp portability is broken by design, so CloudlyNet reserves the seam instead of building it. This story makes the reservation explicit and durable: the key exists in the registry as unregisterable, and one contract doc records everything the research established so the track can be re-opened without re-research.
**Size:** S

**Scope:**
- In: placeholder package `app/ric/adapters/nearrt/` (module docstring + README.md contract doc); a copy of the contract doc's decision summary at `artifacts/ric/nearrt-placeholder.md` (single source: the submodule README is canonical, the artifacts file is a pointer + summary per the repo's design-artifacts rule); reserved-key behavior tests (the enforcement itself landed in S1's registry).
- Out: ANY implementation: no git submodule, no C code, no compose services, no E42 bridge, no xApp SDK bindings, no KPM sidecar (deferred with the near-RT track), no `nearrt_kpm_stream` emission anywhere.

**Files:**
- Create `submodule/maveric_platform_rapp/app/ric/adapters/nearrt/__init__.py` (docstring-only placeholder module)
- Create `submodule/maveric_platform_rapp/app/ric/adapters/nearrt/README.md` (the contract doc, canonical)
- Create `artifacts/ric/nearrt-placeholder.md` (summary + pointer; design artifacts live in the parent repo per CLAUDE.md)
- Create `submodule/maveric_platform_rapp/tests/test_nearrt_placeholder.py`

**Contract:**

The contract doc (`app/ric/adapters/nearrt/README.md`) must capture, as recorded findings with dates, the following. This doc is the ONLY place in the epic's committed scope (besides the epic risks) where FlexRIC may be named:

1. Reservation: adapter key `nearrt_xapp` is RESERVED in the Appendix A.4 registry (was `flexric_xapp` pre-v1.1); `app/ric/registry.py` rejects registration and lookup with a pointer here. The reserved streaming `source_type` for the future KPM data path is `nearrt_kpm_stream` (HLD Appendix A.5); it must never be emitted until this track opens. The KPM sidecar concept is deferred with the track (no sidecar envs, no sidecar code).
2. Why deferred (mid-2026 findings): per-RIC xApp SDKs are non-portable by design; E2 fragments across E2AP v1-v4 and E2SM version matrices with non-overlapping feature sets; every near-RT RIC ships its own SDK; the standalone near-RT RIC merchant market has consolidated sharply while commercial energy sits at the non-RT tier (rApps over A1/R1), which is where the HLD v1.1 track now points.
3. Candidate 1, FlexRIC (EURECOM/Mosaic5G): nearRT-RIC + E2 emulators + xApps as separate processes over E42, a custom SCTP interface similar to E2AP; C SDK covers E2SM-KPM v2.01/v2.03/v3.00 and E2SM-RC v1.03, Python SDK covers custom SMs only (not KPM/RC). LICENSE IS THE BLOCKER: the dev branch is Collaborative Standards Software License v1.0 (CSSL) since 2026-03-31 (master/v2.0.0 = OAI Public License v1.1); both are Apache-derived texts whose patent grant is royalty-free solely for study, testing and research, with FRAND negotiation required for commercial use; the GitLab "Apache-2.0" badge is an automated misdetection. Any future FlexRIC use is lab-only unless legal clears the FRAND question.
4. Candidate 2: a commercial RIC's own SDK (write a per-RIC xApp on that vendor's SDK; never port).
5. E2-node reality check: OCUDU, the Linux Foundation's open-source CU/DU project (BSD-3-Clause, srsRAN lineage), ships DU/CU-CP/CU-UP E2 agents implementing E2SM-KPM v3.00 with 27 of 287 defined metrics; its RC support is thinner than the config flags suggest; OCUDU-FlexRIC interop is inferred from srsRAN lineage, not documented upstream.
6. Re-open criteria: a paying design partner requiring sub-second control loops; or a commercial near-RT RIC engagement providing its own SDK + support; plus legal clearance of the chosen SDK's license. Until then the intelligence stays at the rApp tier and reaches the RAN via `a1_policy` (S3/S4) and the smo_sim actuators (E4).
7. Wording: no O-RAN/RIC/E2 compliance claims; this doc describes third-party projects and reserved seams, not CloudlyNet capabilities.

`artifacts/ric/nearrt-placeholder.md`: one-page summary of the above + link to the canonical README path; keeps the parent-repo artifacts tree authoritative for design decisions without duplicating detail.

**Key snippets:**

```python
# app/ric/adapters/nearrt/__init__.py
"""RESERVED near-RT placeholder (HLD v1.1, Appendix A.4 key: nearrt_xapp).

No executor exists and none may be registered; app/ric/registry.py enforces this.
See README.md in this package for the contract, the deferral rationale, and re-open criteria.
The reserved streaming source_type nearrt_kpm_stream (HLD Appendix A.5) is never emitted.
"""
```

**Acceptance criteria:**
- `register_control_adapter("nearrt_xapp")` and `get_control_adapter("nearrt_xapp")` both raise with messages naming `app/ric/adapters/nearrt/README.md` (tests assert the message content).
- Grep gates: `nearrt_kpm_stream` appears nowhere in `app/` outside the placeholder docstring/README; `flexric` (case-insensitive) appears nowhere in the rapp submodule outside `app/ric/adapters/nearrt/README.md`; no `.c`/`.h` files, no new submodule, no compose service, and no sidecar/`SIDECAR_*`/`RIC_LAB_TENANT_ID` envs were added anywhere in the epic.
- Both docs exist, cover all seven contract points, contain no compliance claims and no em dashes.
- Full suite green.

**Test plan:**
- Unit (`tests/test_nearrt_placeholder.py`): reserved-key raise behavior + message; source-tree grep assertions (walk `app/` for the forbidden strings).
- Run: `cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest tests/test_nearrt_placeholder.py` then full suite.

**Coding-agent prompt**

```
CONTEXT
CloudlyNet backend monorepo (repo root = cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md D1 (amended v1.1), §4.4
adapters/nearrt bullet, Appendix A.4 (nearrt_xapp RESERVED) and A.5 (nearrt_kpm_stream RESERVED),
then story E3.S7 in docs/task_docs/cloudlynet-rearchitecture/epics/EPIC-3-ran-intelligence-ric.md
(its Contract section lists the seven points the contract doc must capture; use them verbatim as
your outline). Prerequisite: app/ric/registry.py (E3.S1) already enforces RESERVED_ADAPTER_KEYS =
{"nearrt_xapp"}. This story is DOCUMENTATION + STUB ONLY: the near-RT track is deferred; you must
not add any submodule, C code, compose service, E42/xApp/SDK code, or sidecar env.

TASK
1. submodule/maveric_platform_rapp/app/ric/adapters/nearrt/__init__.py: docstring-only placeholder
   module per the epic Key snippet.
2. submodule/maveric_platform_rapp/app/ric/adapters/nearrt/README.md: the canonical contract doc
   covering all seven points from the epic Contract: (1) the nearrt_xapp reservation (was
   flexric_xapp pre-v1.1) + reserved streaming source_type nearrt_kpm_stream never emitted + KPM
   sidecar deferred; (2) why deferred: per-RIC xApp SDKs are non-portable, E2AP v1-v4 / E2SM
   version fragmentation with non-overlapping features, near-RT merchant market consolidation
   while commercial energy sits at the non-RT tier; (3) FlexRIC candidate: E42 custom SCTP
   interface + C SDK for E2SM-KPM v3.00 / E2SM-RC v1.03 (Python SDK excludes KPM/RC), licensed
   CSSL v1.0 on dev since 2026-03-31 (master = OAI-PL v1.1) with patent grant royalty-free solely
   for study/testing/research and FRAND negotiation for commercial use; the GitLab Apache-2.0
   badge is a misdetection; lab-only unless legal clears FRAND; (4) commercial RIC SDK candidate:
   write per-RIC xApps, never port; (5) OCUDU, the Linux Foundation's open-source CU/DU project:
   E2 agents with E2SM-KPM v3.00 at 27/287 metrics, thin RC, FlexRIC interop inferred from srsRAN
   lineage not documented; (6) re-open criteria (design partner needing sub-second loops or
   commercial RIC engagement, plus legal clearance); until then control flows via a1_policy and
   the smo_sim actuators; (7) wording rules: no compliance claims.
3. artifacts/ric/nearrt-placeholder.md (parent repo): one-page summary of the same seven points +
   pointer to the canonical README (design artifacts live in the parent repo per CLAUDE.md).
4. submodule/maveric_platform_rapp/tests/test_nearrt_placeholder.py: assert
   register_control_adapter("nearrt_xapp") and get_control_adapter("nearrt_xapp") raise with
   messages naming app/ric/adapters/nearrt/README.md; walk app/ to assert "nearrt_kpm_stream"
   appears only in the placeholder package and "flexric" (case-insensitive) appears only in
   app/ric/adapters/nearrt/README.md.

CONSTRAINTS
- NO submodule, NO C code, NO compose services, NO xApp/E42/SDK code, NO sidecar envs. FlexRIC may
  be named ONLY inside the two contract docs. No em dashes anywhere; never O-RAN
  compliant/certified; product name CloudlyNet.

DEFINITION OF DONE
- cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest
  fully green; both docs complete; grep gates in the new test pass.
```

---

## E3.S8: Regression gate: ES/LB/CCO/MRO training + inference unchanged, golden-response checks, new-module test inventory

**ID:** E3.S8
**Title:** Epic-closing regression: full existing suite green unchanged + golden-response byte-compat checks on `/infer` + inventory of the new E3 module tests
**Why:** Hard constraint §3.2: every gateway-routed rapp endpoint keeps its contract byte-compatible; this story proves E3 changed nothing observable while adding the RIC layer, and pins the inventory of new unit tests so E6's final gate can audit coverage.
**Size:** S

**Scope:**
- In: run the full untouched suite; add/execute golden-response checks for the day-scope `/infer` envelope (top-level key set + `per_tick_recommendations` item shape + success envelope framing) with all E3 flags at defaults; reuse the E2 (NDT epic) golden harness if it has landed, else add a minimal snapshot test in rapp; inertness proofs for the executor and emitter; the new-module test inventory.
- Out: fixing unrelated pre-existing failures (record them, do not paper over); performance benchmarking; lab end-to-end runs (documented per-story, not CI).

**Files:**
- Create `submodule/maveric_platform_rapp/tests/test_golden_infer_contract.py` (only if E2's golden harness is not yet in the repo; otherwise run E2's harness and reference it here)
- No production file changes. If any regression is found, fix forward in the offending E3 story's files.

**Contract:**
- Golden assertion set (day-scope, non-MRO): success envelope framing unchanged; result contains exactly the documented keys of `DayEvaluationResult` (`scope, day, guardrail_kpis, objective_kpis, per_tick_kpis, per_tick_recommendations, worst_tick_stats, warnings, status, metadata, raw_tick_data`); `per_tick_recommendations[*].items[*]` keys are exactly `{cell_id, el_degree, on_off}`; MRO `/infer` still returns 202 with unchanged envelope; 409 on non-ready model unchanged.
- All defaults: `LOOP_PROPOSALS_ENABLED` false, `A1_EXECUTOR_ENABLED` false. Inertness proof: importing `app.main` (PYTHONPATH set) creates no consumer thread, no keepalive thread, no httpx client, and no `app.ric.adapters.nonrtric` network activity; with default settings the loop emitter publishes nothing (kafka producer mock never called). The executor module import from `app/main.py` is allowed (guarded wiring), so the assertion is on RESOURCES (threads/clients/connections), not on `sys.modules`.
- New-module unit test inventory recorded in the PR description (all must be green): `tests/test_ric_ports.py` (S1), `tests/test_nonrtric_client.py` (S3), `tests/test_a1_executor.py` (S4), `tests/test_loop_emitter.py` (S5), `tests/test_r1_manifest.py` (S6), `tests/test_nearrt_placeholder.py` (S7), plus this story's golden/inertness tests.

**Acceptance criteria:**
- `cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest` passes with zero modifications to pre-existing test files (git diff over `tests/` shows only additions).
- Golden contract test passes on the E3 branch AND on the pre-E3 base commit (proving it encodes today's behavior, not new behavior): run it once against base via `git stash` / worktree and record the result in the PR description.
- Inertness test green: default settings start no threads and publish nothing; `threading.enumerate()` after `import app.main` + startup shows no `rapp-a1-executor`/keepalive thread.
- The new-module test inventory is complete and every listed file exists and is green.

**Test plan:**
- `cd submodule/maveric_platform_rapp && PYTHONPATH=app:app/radplib/dependencies uv run pytest` (full).
- If E2's golden harness exists (check `docs/task_docs/cloudlynet-rearchitecture/epics/` E2 deliverables and `tests/golden/` in rapp/bdt), execute it per its README and attach output.

**Coding-agent prompt**

```
CONTEXT
CloudlyNet backend monorepo. Epic E3 (docs/task_docs/cloudlynet-rearchitecture/epics/
EPIC-3-ran-intelligence-ric.md) added an app/ric layer (ports/registry), a NONRTRIC A1-PMS
connector (a1_policy adapter), an in-container a1_policy loop-action executor (kill-switch
A1_EXECUTOR_ENABLED, default off), a feature-flagged loop emitter (LOOP_PROPOSALS_ENABLED, default
off), packaging/r1 manifests, and a nearrt_xapp placeholder to submodule/maveric_platform_rapp.
Hard constraint (frozen HLD docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md §3.2): public
/rapps/** responses must stay byte-compatible; all E3 features default OFF.

TASK
1. Run the full suite: cd submodule/maveric_platform_rapp &&
   PYTHONPATH=app:app/radplib/dependencies uv run pytest. Zero pre-existing test files may be
   modified; if anything fails, fix the E3 production code (not the tests) and re-run.
2. Golden contract test: if a golden-response harness from the NDT epic (E2) exists (look for
   tests/golden/ in maveric_platform_rapp or maveric_platform_bdt_engine and for E2 deliverables in
   docs/task_docs/cloudlynet-rearchitecture/epics/), run it and report. Otherwise create
   tests/test_golden_infer_contract.py in maveric_platform_rapp asserting, against the existing
   day-mode endpoint test fixtures: success-envelope framing; DayEvaluationResult top-level key
   set exactly {scope, day, guardrail_kpis, objective_kpis, per_tick_kpis,
   per_tick_recommendations, worst_tick_stats, warnings, status, metadata, raw_tick_data};
   per_tick_recommendations items shaped {tick, items:[{cell_id, el_degree, on_off}]}; MRO /infer
   202 envelope unchanged; 409 for non-ready models unchanged.
3. Prove defaults are inert: a test that imports app.main (PYTHONPATH set), runs the startup
   hooks, and asserts (a) no rapp-a1-executor or A1PMS keepalive thread in threading.enumerate(),
   (b) no Kafka consumer constructed (mock/patch the consumer factory and assert not called),
   (c) with default settings the loop emitter publishes nothing (kafka producer mock never
   called). Assert on RESOURCES, not sys.modules: the guarded executor import in app/main.py is
   allowed.
4. Report: full pytest output summary, the new-module test inventory status (test_ric_ports,
   test_nonrtric_client, test_a1_executor, test_loop_emitter, test_r1_manifest,
   test_nearrt_placeholder, plus this story's tests), any deviations found and fixed, and
   confirmation that git diff --stat over tests/ shows only added files.

CONSTRAINTS
- Never edit pre-existing tests to make them pass. Never change public response shapes. All fixes
  go into E3-authored files.

DEFINITION OF DONE
- Full suite green; golden test green; inertness test green; inventory complete; written
  confirmation of byte-compat.
```

---

## Rollout / migration notes

**Order:** E3.S1 -> E3.S2 -> E3.S3 -> E3.S4 -> E3.S5 -> E3.S6 -> E3.S7 -> E3.S8 (S1 gates every code story; S2 gates S3's lab verification but not its unit-tested merge; S3 gates S4; S5/S6/S7 only need S1; S8 closes the epic). Each story is independently mergeable with all features inert by default.

**Backward compatibility / shims:**
- No shims needed: the RIC layer is additive. The only touches to existing runtime files are (a) the single best-effort emitter call in the day-scope path, double-gated (env default off + per-tenant flag default absent) and exception-proof, and (b) the guarded executor start in `app/main.py`, dead code while `A1_EXECUTOR_ENABLED` is false.
- Public `/rapps/**` contracts are untouched by construction; E3.S8 proves it.
- rapp/rapp-worker keep their existing image stream; the NONRTRIC components are pulled images under compose profile `ric-lab` only (mirroring the edgeagent lab pattern); nothing is built or pushed.

**Data migration:** none. No owned-table changes, no alembic revision in rapp, no seed SQL (the A1 path has no streaming ingest in this epic, so no `vendor_dictionaries` rows are needed; the canonical-PM feedback path is E1/E2's).

**Topic provisioning:** E5.S1 is the owner-of-record. Lab topics (`maveric.loop.proposal.v1` for S5; `maveric.loop.action.v1` + `maveric.loop.feedback.v1` for S4) ride `scripts/kafka/init-topics.sh` ONLY if E5.S1 has not landed the lines first (each story checks before adding; never duplicate). Staging/prod provisioning goes through the existing kafka chart topics-job values per HLD §4.1: that is an ops/values edit coordinated with E2/E5 rollout, deliberately NOT part of E3 code (zero CI/CD change).

**Enablement sequence for the RAN-policy loop leg (with E2/E5):** 1) `ric-lab` profile up, policy type registered on both sims (S2/S3 runbook); 2) E2 NDT proposal consumer + action dispatcher live; 3) set `LOOP_PROPOSALS_ENABLED=true` on rapp (env edit via existing secretData/values path, ops step); 4) flip `tenants.feature_flags['loop_proposals']` and set `loop_adapter_hint: "a1_policy"` per pilot tenant via manual SQL; 5) set `A1PMS_BASE_URL`, `A1PMS_DEFAULT_RIC_ID` and `A1_EXECUTOR_ENABLED=true` on rapp; 6) actions flow NDT -> executor -> PMS -> sim, apply/rollback feedback flows back, and the NDT's KPI watch runs on canonical PM via the data platform (E1's `/data/pm` + E2.S7's canonical-PM watch tick), not on executor-emitted windows.

**Re-pinning NONRTRIC images:** take new tags from the OSC release notes (never from the upstream docker-compose `.env`, which is stale); bump the compose pins and the table in `artifacts/ric/nonrtric-lab.md` in the same commit; re-run the S2/S3 lab verification. If the PMS v3 base path or field dialect shifts in a future release, the change is confined to `app/ric/adapters/nonrtric/client.py` by design.

## Epic-level risks

1. **PMS v3 base-path and dialect trap:** the recommended "V3" API is served at `{apiRoot}/a1-policy-management/v1` (POST-create, camelCase) while v2 lives at `/a1-policy/v2` (PUT-create, snake_case). Wrong-base-path or wrong-dialect bugs look like 404s/400s at bring-up. Mitigations: the mode table in E3.S3 is pinned, `A1PMS_API_MODE=v2` is an env flip, and the runbook records the field names verified against the live 2.11.0 PMS.
2. **Upstream pin rot:** the upstream `nonrtric/docker-compose` `.env` pins stale tags (PMS 2.3.1), and `nexus3.o-ran-sc.org:10002` has no pull SLA. Mitigations: our own compose defs with re-pinned tags (2.11.0 / 2.8.1), documented mirror-to-own-registry posture for anything customer-facing, re-pin procedure in the rollout notes.
3. **A1-PMS upstream health:** the component is "inactive in OSC, active in ONAP" (development moved to ONAP CCSDK-ORAN; OSC re-releases). The A1 artery is the best-maintained part of NONRTRIC, but release cadence and the exact southbound config keys can shift; keep the connector surface small and the application_configuration.json under our control.
4. **Policy-type semantics vary per RIC:** the lab sims accept our registered type (integer ids on OSC_2.1.0, string ids on STD_2.0.0), but commercial SMOs/RICs advertise their own types; the per-RIC discovery/negotiation surface in S3 is the mitigation, and nothing may assume `cloudlynet.cell_config.v1` exists outside the lab. STD_1.1.3-style endpoints without policy types are visible in PMS and must be tolerated by `capabilities()`.
5. **Executor-in-API-container lifecycle:** the a1_policy consumer thread shares the rapp API process; a crash-looping consumer or a blocking keepalive must never take the API down. Mitigations: kill-switch default off, daemon thread with catch-all loop, at-least-once + deterministic policy ids for redelivery, and S8's inertness proof. Horizontal scaling of the API container multiplies consumers in the same group, which is safe (partition assignment) but should be noted at ops enablement.
6. **Cross-epic contract coupling, FROZEN in HLD Appendix A:** (a) loop-proposal payload = A.1 (E3 produces via `app/services/loop_emitter.py`, E2 consumes; `el_degree` -> `cell_el_deg` mapping pinned there); (b) action/rollback semantics = A.2 (rollback routing on `payload.rollback_of` is binding); (c) feedback matrix = A.3 (this epic emits only `apply`/`rollback` kinds; KPI windows for the A1 path are NDT-side over canonical PM, E2.S7); (d) adapter keys and `target_adapter_hint` values = A.4 (`a1_policy` implemented, `nearrt_xapp` RESERVED), recorded in `artifacts/design/internal-contracts.md` section 6 (E0.S3); (e) `nearrt_kpm_stream` = A.5 RESERVED, never emitted. Any divergence is a freeze deviation; reconcile against Appendix A before merging either side.
7. **Near-RT deferral debt:** the placeholder captures why (per-RIC SDK non-portability; FlexRIC's E42 custom SCTP + C SDK under CSSL v1.0 with a lab-only patent grant and FRAND terms for commercial use; OCUDU E2 agents exposing only 27/287 E2SM-KPM v3.00 metrics). If a customer demands sub-second loops before the re-open criteria are met, the honest answer is the roadmap doc, not a rushed xApp; any future FlexRIC work re-enters through legal review first.
8. **rApp Manager temptation:** the R1 facade (S6) may create pressure to "just deploy rApp Manager". It is pre-spec, "not intended for production use", and drags ONAP ACM + SME + DME; RANPM additionally drags AGPLv3 MinIO. All of it stays ROADMAP per D1; reject scope creep in review.
9. **Wording/claims drift:** every new doc (`artifacts/ric/nonrtric-lab.md`, `nearrt-placeholder.md`, r1 README, docstrings) must survive `artifacts/marketing/claims-guardrails.md` review: "we integrate O-RAN SC NONRTRIC, the open-source non-RT RIC", "A1-policy-aligned intents", "R1-shaped", never compliance/certification claims; keep the O-RAN ALLIANCE attribution notice if `pms-api-v3.yaml` is ever vendored; product name CloudlyNet; no em dashes. E6 re-verifies; keep E3 clean so E6 has nothing to unwind.

---

## Execution status

Completed 2026-07-31. rApp `d718130 -> 586aa8c` (7 commits), parent `638c31a -> 618490a` (3 commits).
Nothing pushed. 164 new tests; rApp suite **413 passed / 0 failed / 5 errors**, against the recorded
baseline of 249 passed / 5 errors in the same environment. The 5 errors are the pre-existing missing
MRO fixture CSV (`test-baselines.md`). Every story's delta was isolated by running the suite with and
without the new test files.

The `ric-lab` profile was brought up for real, so S2, S3 and S4 are verified against running
containers rather than against the documentation. Where the epic's assumptions and the software
disagreed, the software won and the correction is recorded below.

**S1 DONE** (`915a294`, 28 tests). Ports, models and the A.4-keyed registry as specified.

One deliberate deviation. The story requires the registry to raise on `nearrt_xapp` for both
registration and lookup, but the frozen HLD has moved on: **A.4 and section 4.4 were amended by v1.2
(D5)** to make `nearrt_xapp` the LAB executor key for EPIC-7's `NearRtLabExecutor`, and E7.S3 builds
exactly that. As written, S1 would have blocked E7. The registry therefore keeps the hard raise as the
default (S1's and S7's acceptance criteria hold unchanged, and are tested) and adds an explicit
`allow_reserved=True` opt-in that E7 uses. Default behaviour is identical under both readings.
Recorded in the S7 contract doc as the only sanctioned use.

**S2 DONE** (parent `ad46cc2`). Profile up, both simulators `AVAILABLE`, PMS healthy in about five
seconds. The four details the epic flagged as unpinnable were read out of the images, not guessed:

| Item | Verified | Source |
| --- | --- | --- |
| PMS config path | `/opt/app/policy-agent/data/application_configuration.json` | `config/application.yaml` key `app.filepath` |
| PMS HTTP port | 8081 (HTTPS 8433) | same file |
| Simulator port | 8085 | `/usr/src/app/nginx.conf` in the simulator image |
| Healthcheck tooling | `wget` present, `curl` absent | probed in the image |

Both images are `linux/amd64` only and run under emulation on Apple Silicon; they work, and no
`platform:` override is pinned so native amd64 lab hosts are unaffected. `ric-std` pins
`customAdapterClass` to `StdA1ClientVersion2$Factory` so the southbound dialect is explicit.

**S3 DONE** (rapp `c7f5157`, parent `0ffdc1e`, 40 tests). Connector, adapter and policy-type helper.
Verified end to end against the live service: register, keepalive, discover both RICs and both types,
apply -> `applied`, re-apply -> `duplicate`, status -> `NOT_ENFORCED`, delete -> `applied`, re-delete
-> `duplicate`.

Four corrections to the story as written:

1. **`httpx` was already a rApp dependency** (`pyproject.toml`, added by EPIC-2's NDT client). The
   story's step 6 was a no-op; nothing was added.
2. **`callbackUrl` is mandatory on `PUT /services`.** Omitting it returns 400 with a raw
   `NullPointerException`, not a default.
3. **The two simulators need structurally different type-registration bodies**, and the story implied
   one shared schema body. `OSC_2.1.0` needs an integer id plus `{name, description, policy_type_id,
   create_schema}`; `STD_2.0.0` needs `{policySchema, statusSchema}`. `statusSchema` is the trap:
   its registration handler does not validate it, but `src/STD_2.0.0/a1.py:162` reads it unguarded on
   every policy create, so a type registered without it accepts registration and then fails every
   create with an opaque 500.
4. **The v2 dialect spells it `policytype_ids`**, with no underscore between "policy" and "type".

Also measured, and left alone deliberately: **a rejected policy body surfaces as 500, not 4xx**,
because the policy service wraps the RIC's 400. Under the frozen A.3 matrix that maps to `failed`
rather than `rejected`, after spending the full retry budget on a request that can never succeed.
Changing that mapping is a contract amendment, not a connector fix. **EPIC-4 and EPIC-5 should expect
`failed` where they might reason `rejected`.**

**S4 DONE** (`8c7b348`, 36 tests). Executor, translation, guarded wiring. Verified end to end on real
Kafka against the real policy service: an apply action created the deterministic instance and emitted
`apply/applied`; the rollback deleted it (confirmed 404 on the instance) and emitted
`rollback/rolled_back`; both feedback records carried `tenant_id` bytes as the Kafka key.

`kafka_handler.send_message` gained an optional `key` parameter (additive, default `None`, every
existing caller unchanged) because A.3 mandates a keyed record and the helper had no way to set one.
**Caveat worth carrying into E5:** the shared producer is built with a round-robin partitioner that
IGNORES the key, so the key is recorded on the message but gives no partition affinity and no
per-tenant ordering. That is pre-existing behaviour for every rApp-produced topic; changing it would
affect the training topic too and is out of E3's scope.

**S5 DONE** (`ca8a98c`, 22 tests). Emitter plus one call site in the day-scope path.

The tick coercion turns out to be load-bearing rather than defensive: rApp's public
`NonMroTickRecommendation.tick` is a **`str`**, while Appendix A.1 and the twin's `LoopProposal`
model both require an **int** in 0..23. Forwarding `per_tick_recommendations` unmodified, as the
appendix suggests, would have been rejected by the consumer. The emitter also skips emission rather
than publishing a proposal the twin would reject, because `ProposalRefs` forbids extra keys and
requires all three ids non-empty.

`init-topics.sh` was NOT touched: EPIC-2.S6 already landed all three loop topic lines, and the story
says to add only if absent.

**S6 DONE** (`4deebc7`, 15 tests). Four manifests, validating model, README.

The story's example `s3_key_template` (`{tenant}/models/rapps/es/{model}.zip`) does not exist in the
code. The real convention, identical in `rapp_worker.py` and `data_loader.py` and overridable by
`RAPP_WORKER_S3_ARTIFACT_TEMPLATE`, is `{tenant_id}/models/rapps/{rapp_id}/{rapp_model_id}`, with no
`.zip`. The manifests use the real one and a test asserts both source files still contain it.
`pyyaml` was present only transitively and is now declared, since the loader imports it.

**S7 DONE** (rapp `eeb1f6d`, parent `618490a`, 13 tests). Placeholder package, canonical contract doc
covering all seven points plus the v1.2 lab-activation opt-in, parent-repo summary, and grep gates
(reserved stream type, third-party RIC naming, no C sources, no sidecar envs, placeholder holds no
implementation).

**S8 DONE** (`586aa8c`, 10 tests). Golden `/infer` envelope plus inertness.

The five envelope assertions were also run against the **pre-E3 base commit `d718130`** in a
throwaway worktree and pass identically there, which is what makes them a regression gate rather than
a description of new behaviour. `git diff d718130..HEAD -- tests/` is additions only: seven new files,
zero pre-existing test files touched. Inertness is asserted on resources, not modules: with defaults,
running the lifespan startup creates no executor thread, no keepalive thread, no Kafka consumer, and
the emitter publishes nothing.

Writing this test corrected the epic's own key list: `DayEvaluationResult.raw_tick_data` is a
`Dict`, not a list.

### Deliberately not done

- No CI/CD change of any kind. `submodule/maveric-deployment` is untouched; no chart, no pipeline, no
  registry push, no host port.
- No `kind="kpi_window"` or `kind="guardrail_breach"` emission, enforced by a test over the module
  source. A1-path KPI windows come from canonical PM on the twin side (E2.S7).
- No near-RT protocol work: no submodule, no C sources, no compose services, no E42 bridge, no
  `nearrt_kpm_stream` emission.
- Per-tenant RIC routing: `ric_id` still comes from `A1PMS_DEFAULT_RIC_ID` for every tenant.
- The lab `ric-lab` containers were left running after verification. `./scripts/kafka/compose.sh down`
  stops them along with everything else.

### Carried into later epics

1. **E4, E5:** a rejected policy arrives as `failed`, not `rejected` (S3 above).
2. **E5:** the feedback topic's `tenant_id` key does not partition by tenant (S4 above).
3. **E7:** `nearrt_xapp` is reachable only via `allow_reserved=True` (S1 above).
4. **E0 or E6 gap:** frozen HLD A.4 states that `artifacts/design/internal-contracts.md` records the
   adapter-key table as "the adapter-key contract of record (section 6)". It does not. That file's
   section 6 is "What this document does not cover", and no adapter key appears anywhere in it. The
   registry cites the frozen HLD directly instead. Worth closing where E0.S3 is owned.
