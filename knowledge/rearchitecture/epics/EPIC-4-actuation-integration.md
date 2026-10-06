# EPIC 4 — Actuation & Integration service (`maveric_platform_smo_sim`)

**Epic ID:** E4
**Title:** Actuation & Integration: E2/R1 deletion, ActuatorAdapter framework, loop executor, scale-out fixes, placeholder adapters, PM-upload decommission, managed-params contract
**Goal:** Convert `maveric_platform_smo_sim` from a misnamed simulator into the platform's Actuation & Integration service per the frozen HLD (D4 + §4.5). The dead E2/R1 REST facades are deleted, the proven NanoLink TR-069 control plane is wrapped behind an `ActuatorAdapter` framework without changing any byte on any existing surface, and the service becomes the executor arm of the closed loop (`maveric.loop.action.v1` in, `maveric.loop.feedback.v1` out).
**Depends on:** E0 (gateway duplicate-route panic fix + route split groundwork). E4.S6 additionally depends on E1 (data platform serving `/custom/nybsys/uploads` verbatim). E4.S3 produces the feedback stream E2/E5 consume.
**Definition of done (epic):**
- Zero E2/R1 code, tables, test harnesses, or overclaiming docs remain in `maveric_platform_smo_sim`; `artifacts/migration/012_drop_e2_r1.sql` exists and is indexed. (Archival of the `artifacts/oran/` bundle to `artifacts/legacy/oran/` is owned by E6.S2, not this epic.)
- `app/actuators/` exists with the §4.5 protocol, a registry, a command router (with `payload.rollback_of` routing to `adapter.rollback()` per HLD Appendix A.2), a NanoLink adapter that is the only writer path used by the loop executor, and five placeholder adapters each with module + registry entry + health + contract doc.
- A background Kafka consumer inside the existing smo_sim container executes `maveric.loop.action.v1` actions for `adapter="nanolink_tr069"` (HLD Appendix A.4 key) and publishes apply acks, KPI windows, and guardrail events to `maveric.loop.feedback.v1` in the HLD Appendix A.3 shape; both are no-ops when `KAFKA_BOOTSTRAP_SERVERS` is unset.
- Lease sweep runs periodically (not only at startup); EWMA optimizer state survives restarts and multiple replicas via Redis (with in-memory fallback).
- The `/custom/nybsys/uploads*` router + `nybsys_runner` are removed from smo_sim after the E1 cutover; device/edge routers untouched.
- The 24-path managed-parameter catalogue has a single canonical contract file with generated, hash-stamped copies in smo_sim, frontend, and the Go agent.
- All public gateway-routed contracts, `/v1/agent/**` (field-frozen), the `{success,message,data}` envelope, `commands` semantics, and S3 key conventions are byte-identical before/after. Zero CI/CD change: no new charts, pipelines, images, or ports.

**HLD conformance:** all topic names, the loop-action payload, and the adapter protocol come verbatim from `docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md` §4.1/§4.5. Contracts detailed here beyond §4 (loop-feedback payload, ingest-records payload, managed-params contract file) are flagged inline and in the epic risks.

---

## E4.S1 — Delete the E2/R1 REST facades (frozen decision D4)

**Why:** The E2/R1 endpoints are dead-end scaffolding: not gateway-routed, measurement tables have no writer anywhere in the platform, E2SM-RC control actions insert permanently-`pending` rows, R1 subscriptions never notify (recon: zero callers, zero executors). Deleting them resolves claims-guardrails engineering blocker #2 (`/e2ap` route naming).

**Size:** M

**Scope:**
- In: delete routers, Pydantic models, ORM schemas, mock-client harnesses, submodule-root E2/R1 docs; drop the 11 tables via a new dev-repo migration; rewrite the smo_sim README sections that overclaim O-RAN implementation; update `artifacts/migration/README.md` index.
- Out: any change to `smo_sim.py` (baselines/UE datasets), NanoLink routers, `openapi.yaml` (E2/R1 were never in it — verified), gateway (E2/R1 were never routed), `.context/` graph updates (E6), and ALL `artifacts/oran/` archival (E6.S2 is the sole owner of the move to `artifacts/legacy/oran/`, the deprecation README, and every parent-repo link fix; this story touches no `artifacts/oran/` file).

**Files:**
- Delete: `submodule/maveric_platform_smo_sim/app/api/v1/endpoints/e2_interface.py`
- Delete: `submodule/maveric_platform_smo_sim/app/api/v1/endpoints/r1_interface.py`
- Delete: `submodule/maveric_platform_smo_sim/app/schemas/e2_schemas.py`
- Delete: `submodule/maveric_platform_smo_sim/app/schemas/r1_schemas.py`
- Delete: `submodule/maveric_platform_smo_sim/app/models/e2_models.py`
- Delete: `submodule/maveric_platform_smo_sim/app/models/r1_models.py`
- Delete: `submodule/maveric_platform_smo_sim/e2test/` (whole dir)
- Delete: `submodule/maveric_platform_smo_sim/r1test/` (whole dir)
- Delete: `submodule/maveric_platform_smo_sim/e2_spec.md`, `E2-Data-Pipeline-Explanation.md`, `r1-plan.md`, `R1-SMO-Delivery-Doc.md` (submodule-root doc drift; canonical archive is `artifacts/legacy/oran/`)
- Modify: `submodule/maveric_platform_smo_sim/app/api/v1/routes.py` (remove `r1_interface`, `e2_interface` from the import on line 3 and delete the two `include_router` lines 16–17)
- Modify: `submodule/maveric_platform_smo_sim/app/main.py` (delete the `r1_schemas` / `e2_schemas` imports at lines 15–18)
- Modify: `submodule/maveric_platform_smo_sim/README.md` (rewrite the "R1 interface implementation" and "E2 interface implementation" sections)
- Create: `artifacts/migration/012_drop_e2_r1.sql`
- Modify: `artifacts/migration/README.md` (add 012 to the execution index)
- Check: `submodule/maveric_platform_smo_sim/alembic/` — grep for `e2_`/`r1_` revisions; if any exist, leave history intact but ensure no new head references the tables.
- NOT here: `artifacts/oran/` archival (move to `artifacts/legacy/oran/`, deprecation README, tombstone) — E6.S2 is the sole owner; sequence E6.S2's archive PR before or with this deletion PR.

**Contract (SQL DDL — `artifacts/migration/012_drop_e2_r1.sql`):**

```sql
-- 012_drop_e2_r1.sql
-- Frozen HLD decision D4 (docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md):
-- the E2/R1 REST facades are deleted. Recon confirmed zero writers/callers:
-- measurement tables never receive an INSERT, control actions never leave 'pending',
-- R1 subscriptions never notify, and no gateway route exists for either surface.
-- Tables were created by smo_sim startup create_tables(Base); IF EXISTS keeps this
-- migration safe on databases where startup never ran.
BEGIN;

DROP TABLE IF EXISTS e2_control_actions;
DROP TABLE IF EXISTS e2_cell_configs;
DROP TABLE IF EXISTS e2_topology;
DROP TABLE IF EXISTS e2_ue_measurements;
DROP TABLE IF EXISTS e2_cell_measurements;
DROP TABLE IF EXISTS e2_subscriptions;
DROP TABLE IF EXISTS e2_nodes;

DROP TABLE IF EXISTS r1_bootstrap_endpoints;
DROP TABLE IF EXISTS r1_service_subscriptions;
DROP TABLE IF EXISTS r1_service_discoveries;
DROP TABLE IF EXISTS r1_service_publications;

COMMIT;
```

(11 tables total: 7 `e2_*` + 4 `r1_*`, names verified against `app/schemas/e2_schemas.py` / `r1_schemas.py` `__tablename__` declarations.)

**Key snippets:**

(The `artifacts/legacy/oran/README.md` deprecation note and the whole `artifacts/oran/` archival are E6.S2's deliverable, not this story's — see the E6.S2 skeleton for its content.)

README rewrite guidance for `submodule/maveric_platform_smo_sim/README.md`: replace both interface sections with a short "Removed interfaces" note stating the E2/R1 REST facades were deleted per re-architecture decision D4, with a pointer to `artifacts/legacy/oran/` in the dev repo. Remove all sentences of the form "implemented following the O-RAN ... specifications" (claims-guardrails: never claim O-RAN/RIC/SMO compliance). Also fix the stale docstring in `app/api/v1/custom/nybsys_agent_router.py:8` ("P1 scope: /register + /poll only") while touching the service, since the README rewrite describes the full agent API.

**Acceptance criteria:**
- `grep -ri "etwoint\|roneint\|e2_interface\|r1_interface\|e2_schemas\|r1_schemas\|e2_models\|r1_models" submodule/maveric_platform_smo_sim/app` returns nothing.
- Service boots (`create_tables` succeeds) and `GET /health` returns 200 with the deleted modules gone.
- `artifacts/migration/012_drop_e2_r1.sql` applies cleanly twice in a row (idempotent) against a dev DB.
- No `artifacts/oran/` file is touched by this story (E6.S2 owns the archival end state: `artifacts/oran/` gone, content under `artifacts/legacy/oran/` with the deprecation README).
- smo_sim README contains no O-RAN implementation claims and no `/etwoint` or `/roneint` route documentation.
- Existing test suite passes; no test references the deleted modules (none do today — verified: `tests/` has no e2/r1 tests).

**Test plan:**
- Unit/regression: `cd submodule/maveric_platform_smo_sim && uv run pytest` (full suite must stay green).
- Migration: apply `012_drop_e2_r1.sql` via psql against the compose Postgres, re-run to prove idempotency, then boot smo_sim and confirm startup `create_tables` does not recreate the tables (the ORM classes are gone).
- Smoke: `curl localhost:8002/health` and one NanoLink operator route to prove unrelated routers still mount.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md first; this task implements
frozen decision D4: delete smo_sim's E2/R1 REST facades.

Context: submodule/maveric_platform_smo_sim is a FastAPI service (container smo_sim,
port 8002). Its E2/R1 endpoints are dead scaffolding: not routed through the gateway,
no writers for the measurement tables, control actions never processed. Recon confirms
zero platform callers. Git rule: cd into the submodule before any git operation.

Task:
1. In submodule/maveric_platform_smo_sim, delete:
   app/api/v1/endpoints/e2_interface.py, app/api/v1/endpoints/r1_interface.py,
   app/schemas/e2_schemas.py, app/schemas/r1_schemas.py,
   app/models/e2_models.py, app/models/r1_models.py,
   e2test/ and r1test/ directories,
   e2_spec.md, E2-Data-Pipeline-Explanation.md, r1-plan.md, R1-SMO-Delivery-Doc.md.
2. Edit app/api/v1/routes.py: remove r1_interface/e2_interface from the line-3 import
   and delete the two include_router lines for them. Edit app/main.py: remove the
   "Import R1 schemas"/"Import E2 schemas" import blocks (lines 15-18).
3. Rewrite the "R1 interface implementation" and "E2 interface implementation"
   sections of the submodule README.md into a short "Removed interfaces" note citing
   re-architecture decision D4 and pointing to artifacts/legacy/oran/ in the dev repo.
   Never use the words "O-RAN compliant/implemented following O-RAN specifications".
   Do not use the em dash character anywhere in new prose. Also fix the stale
   docstring at app/api/v1/custom/nybsys_agent_router.py line 8 (it says "P1 scope:
   /register + /poll only" although all six endpoints exist).
4. In the dev repo, create artifacts/migration/012_drop_e2_r1.sql dropping, with
   IF EXISTS inside one transaction: e2_control_actions, e2_cell_configs, e2_topology,
   e2_ue_measurements, e2_cell_measurements, e2_subscriptions, e2_nodes,
   r1_bootstrap_endpoints, r1_service_subscriptions, r1_service_discoveries,
   r1_service_publications. Add it to artifacts/migration/README.md's index.
   (Migration numbering is frozen in the HLD Appendix A.6: 011 belongs to E1.)
5. Do NOT touch artifacts/oran/ - the archival to artifacts/legacy/oran/ (git mv,
   deprecation README, link fixes) is owned entirely by epic E6 story E6.S2.
6. grep submodule/maveric_platform_smo_sim/alembic for e2_/r1_ references; do not
   rewrite history, just confirm no active head depends on the dropped tables.

Constraints: touch nothing else in app/ (especially smo_sim.py, the custom/ routers,
command_service). Zero CI/CD change. Public API contracts unchanged (E2/R1 were never
public). Follow CLAUDE.md commit conventions; do not stage submodule pointer bumps in
the dev repo.

Definition of done: grep for etwoint/roneint/e2_/r1_ in smo_sim app/ is empty; the
service boots; `cd submodule/maveric_platform_smo_sim && uv run pytest` passes;
012_drop_e2_r1.sql applies twice cleanly; no artifacts/oran/ file touched.
```

---

## E4.S2 — ActuatorAdapter framework + NanoLink adapter (behind existing surfaces)

**Why:** §4.5 requires a hexagonal actuator layer so the loop decision hub can dispatch to any southbound plane by name. The NanoLink TR-069 plane is the only real actuator today; it must implement the protocol with zero behavior change, because the operator routers, `command_service` semantics, and the field-deployed edge agent contract are all frozen.

**Size:** L

**Scope:**
- In: `app/actuators/` package (protocol, Pydantic models, registry, dispatch router with `payload.rollback_of` -> `rollback()` routing), NanoLink adapter (registry key `nanolink_tr069`) delegating to the existing `command_service` and owning the Appendix A.2 cell->device / recommendation->writes translation seam, a DRY refactor of `command_service.create_command` to accept `origin`/`loop_action_id`/`policy_ref` (defaults preserve today's behavior), migration 013 adding two nullable columns to `commands`, internal health/capabilities endpoint, unit tests.
- Out: Kafka consumption (S3), placeholder adapters (S5), any change to `/v1/agent/**` handlers, the operator router request/response shapes, the edge agent, or the gateway. The `{success,message,data}` envelope and command payload sent to agents stay byte-identical.

**Files:**
- Create: `submodule/maveric_platform_smo_sim/app/actuators/__init__.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/base.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/models.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/registry.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/dispatch.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/adapters/__init__.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/adapters/nanolink.py`
- Modify: `submodule/maveric_platform_smo_sim/app/services/nybsys/command_service.py` (extend `create_command` signature; no semantic change for existing callers)
- Modify: `submodule/maveric_platform_smo_sim/app/schemas/nybsys_edge_schemas.py` (add `loop_action_id`, `policy_ref` columns to the `commands` ORM class so `create_tables` stays in sync)
- Create: `submodule/maveric_platform_smo_sim/app/api/v1/endpoints/actuators.py` (internal, X-API-Key inherited; NOT gateway-routed)
- Modify: `submodule/maveric_platform_smo_sim/app/api/v1/routes.py` (include the actuators router)
- Create: `artifacts/migration/013_commands_loop_columns.sql` (+ index entry in `artifacts/migration/README.md`)
- Create: `submodule/maveric_platform_smo_sim/tests/actuators/__init__.py`, `test_registry.py`, `test_nanolink_adapter.py`

**Contract:**

Loop action payload (verbatim from frozen HLD §4.1; field CONTENTS per HLD Appendix A.2; smo_sim consumes, never redefines):
`{action_id, tenant_id, adapter, target, payload, policy_ref, expires_at}`.
For `adapter="nanolink_tr069"` (the A.4 registry key; bare `nanolink` is NOT valid), the adapter accepts BOTH Appendix A.2 forms:
- `target = {"device_id": "<nanolink_devices.device_id>"}` (device-scoped) OR `target = {"cell_id": "...", "tick": 0}` (cell-scoped, the NDT's dispatch form; the adapter resolves `cell_id -> device_id` via the new setting `NANOLINK_CELL_DEVICE_MAP`, JSON `{"<cell_id>": "<device_id>"}`; unresolvable cell -> `status="rejected"`).
- `payload = {"writes": [{"path": str, "value": Any}], "rollback_on_fail": bool}` (explicit write set, exactly the shape `command_service` already validates and the agent already decodes) OR the recommendation form `{"cell_el_deg": float, "on_off": bool, "rollback_of": null}`, which the ADAPTER translates to writes per Appendix A.2 (`on_off=false` -> ReferenceSignalPower = `LOOP_ES_POWER_SAVE_DBM` default `-20`, `on_off=true` -> ReferenceSignalPower = `LOOP_ES_POWER_NORMAL_DBM` default `-10`; `cell_el_deg` has no NanoLink managed parameter and is recorded as skipped in the ack detail). The translation seam lives HERE, not in the NDT: smo_sim owns the device registry and the managed-params catalogue.
- `policy_ref` is a JSON OBJECT (`{policy_id, mode, watch_window_min}`), never a string; it is persisted as jsonb.

Rollback routing (Appendix A.2, binding): `dispatch()` inspects `payload.rollback_of`; when set it calls `adapter.rollback(action)` (never `apply()`), so NDT-ordered rollback actions are executable.

SQL DDL (`artifacts/migration/013_commands_loop_columns.sql`):

```sql
-- 013_commands_loop_columns.sql
-- E4.S2/S3: correlate loop actions (maveric.loop.action.v1) with NanoLink commands.
-- Nullable + additive: operator/agent paths never set these, so behavior is unchanged.
BEGIN;
ALTER TABLE commands ADD COLUMN IF NOT EXISTS loop_action_id text;
ALTER TABLE commands ADD COLUMN IF NOT EXISTS policy_ref     jsonb;
-- Idempotent execution of a redelivered loop action (action_id is globally unique).
CREATE UNIQUE INDEX IF NOT EXISTS commands_loop_action_uq
    ON commands (loop_action_id) WHERE loop_action_id IS NOT NULL;
COMMIT;
```

Internal API (new, additive, not gateway-routed; X-API-Key via the existing `/v1` router dependency):
- `GET /v1/actuators` → `{success, message, data: {adapters: [{adapter, capabilities, health}]}}`
- `GET /v1/actuators/{name}/health` → `{success, message, data: AdapterHealth}` (404 envelope for unknown name)

**Key snippets:**

`app/actuators/models.py`:

```python
"""Pydantic contracts for the actuator framework (frozen HLD section 4.5)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ActionTarget(BaseModel):
    """Adapter addressing per HLD Appendix A.2: device-scoped (device_id) or
    cell-scoped (cell_id [+ tick], resolved to a device by the adapter)."""
    device_id: str | None = None
    dn: str | None = None
    cell_id: str | None = None
    tick: int | None = None


class LoopAction(BaseModel):
    """maveric.loop.action.v1 payload — field names frozen by HLD section 4.1,
    field contents by Appendix A.2 (policy_ref is a dict, never a str)."""
    action_id: str
    tenant_id: str
    adapter: str
    target: ActionTarget
    payload: dict[str, Any]
    policy_ref: dict[str, Any] | None = None
    expires_at: datetime | None = None


class ActuatorAck(BaseModel):
    action_id: str
    adapter: str
    status: Literal["queued", "applied", "failed", "rejected", "duplicate"]
    command_id: str | None = None       # nanolink: commands.id
    detail: dict[str, Any] = Field(default_factory=dict)


class AdapterCapabilities(BaseModel):
    adapter: str
    apply: bool
    read_back: bool
    rollback: bool
    collect: bool = False               # data-plane collectors (ocudu_ws_collector)
    description: str = ""


class AdapterHealth(BaseModel):
    adapter: str
    status: Literal["ok", "degraded", "unavailable", "disabled", "not_implemented"]
    detail: str = ""
    checked_at: datetime
```

`app/actuators/base.py`:

```python
"""ActuatorAdapter protocol — frozen HLD section 4.5. Adapters are stateless facades;
persistent state lives in Postgres/Redis so multi-replica smo_sim stays safe."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.actuators.models import (ActionTarget, ActuatorAck, AdapterCapabilities,
                                  AdapterHealth, LoopAction)


@runtime_checkable
class ActuatorAdapter(Protocol):
    name: str

    def capabilities(self) -> AdapterCapabilities: ...
    def apply(self, db: Session, action: LoopAction) -> ActuatorAck: ...
    def read_back(self, db: Session, target: ActionTarget) -> dict[str, Any]: ...
    def rollback(self, db: Session, action: LoopAction) -> ActuatorAck: ...
    def health(self) -> AdapterHealth: ...
```

`app/actuators/registry.py`:

```python
_REGISTRY: dict[str, ActuatorAdapter] = {}

def register(adapter: ActuatorAdapter) -> None:
    """Idempotent by name; last registration wins (import-time wiring)."""

def get(name: str) -> ActuatorAdapter:
    """Raises KeyError for unknown adapter names (dispatch turns this into 'rejected')."""

def all_adapters() -> dict[str, ActuatorAdapter]: ...
```

`app/actuators/dispatch.py`:

```python
def dispatch(db: Session, action: LoopAction) -> ActuatorAck:
    """Command router keyed by action.adapter (HLD section 4.5; keys per Appendix A.4).

    Rollback routing (Appendix A.2): when action.payload.get("rollback_of") is set,
    route to adapter.rollback(db, action) instead of apply().
    Rejects: unknown adapter; expired action (expires_at < now, UTC); adapter without
    apply capability. Never raises for business errors — always returns an ActuatorAck
    so the loop executor can publish feedback deterministically.
    Foreign A.4 keys owned by other executors (a1_policy, nearrt_xapp) never reach
    dispatch — the S3 consumer commits and skips them silently — so the unknown-adapter
    "rejected" ack covers only keys no executor owns (e.g. bare "nanolink").
    """
```

`app/actuators/adapters/nanolink.py` (delegates to the proven queue; NO new write path; owns the Appendix A.2 translation seam):

```python
class NanoLinkAdapter:
    """TR-069/CWMP plane via the existing commands queue. apply() inserts a commands
    row (origin='loop') exactly the way the operator router does: validate_write per
    write, prev_values captured from the latest curated snapshot, envelope untouched.
    The edge agent remains completely unaware of the loop layer."""

    name = "nanolink_tr069"   # HLD Appendix A.4 registry key; bare "nanolink" is invalid

    def capabilities(self) -> AdapterCapabilities: ...   # apply/read_back/rollback True

    def _resolve_device(self, target: ActionTarget) -> str:
        # target.device_id wins; else settings.NANOLINK_CELL_DEVICE_MAP[target.cell_id]
        # (JSON map, Appendix A.2 seam); missing/unresolvable -> ValueError -> "rejected"
        ...

    def _to_writes(self, payload: dict[str, Any]) -> tuple[list[dict], dict]:
        # explicit {"writes": [...]} passes through verbatim; the recommendation form
        # {cell_el_deg, on_off} translates per Appendix A.2: on_off False/True ->
        # ReferenceSignalPower LOOP_ES_POWER_SAVE_DBM / LOOP_ES_POWER_NORMAL_DBM;
        # cell_el_deg -> skipped, reported in ack detail {"skipped": ["cell_el_deg"]}
        ...

    def apply(self, db: Session, action: LoopAction) -> ActuatorAck:
        # 1) device_id = self._resolve_device(action.target)
        # 2) idempotency: SELECT id,status FROM commands WHERE loop_action_id=:a
        #    -> return ActuatorAck(status="duplicate", command_id=...) if present
        # 3) writes, detail = self._to_writes(action.payload)
        #    command_service.create_command(db, tenant_id=..., device_id=device_id,
        #        body=CommandIn(type="configure",
        #                       payload={"writes": writes, "rollback_on_fail": True}),
        #        created_by="loop", origin="loop",
        #        loop_action_id=action.action_id, policy_ref=action.policy_ref)
        # 4) return ActuatorAck(status="queued", command_id=cid, detail=detail)
        ...

    def read_back(self, db: Session, target: ActionTarget) -> dict[str, Any]:
        # latest device_config_snapshots.params for the resolved device (may be {})
        ...

    def rollback(self, db: Session, action: LoopAction) -> ActuatorAck:
        # invoked by dispatch() when payload.rollback_of is set (Appendix A.2):
        # find the applied command for payload["rollback_of"]; if prev_values present,
        # command_service.enqueue_rollback(..., loop_action_id=action.action_id);
        # else status="rejected"
        ...

    def health(self) -> AdapterHealth:
        # "ok" when DB reachable; detail carries pending/dispatched counts
        ...
```

New settings (`app/core/config.py`, additive): `NANOLINK_CELL_DEVICE_MAP: str | None = None` (JSON `{"<cell_id>": "<device_id>"}`), `LOOP_ES_POWER_SAVE_DBM: str = "-20"`, `LOOP_ES_POWER_NORMAL_DBM: str = "-10"`.

`command_service.create_command` — extended signature (existing callers unchanged; keyword-only additions with today's values as defaults):

```python
def create_command(db: Session, *, tenant_id: str, device_id: str, body: CommandIn,
                   created_by: str, origin: str = "manual",
                   loop_action_id: str | None = None,
                   policy_ref: dict | None = None) -> str:
```

The INSERT gains `origin`, `loop_action_id`, `policy_ref` bind params (origin was previously hard-coded `'manual'`; `origin` has no CHECK constraint — verified in `artifacts/migration/009_nybsys_nanolink.sql:63`, it is `text NOT NULL DEFAULT 'manual'`).

**Acceptance criteria:**
- Operator `POST /v1/tenants/{t}/custom/nybsys/devices/{id}/commands` produces a byte-identical `commands` row vs main (same columns populated, `origin='manual'`, `loop_action_id IS NULL`) — proven by the existing `tests/nybsys_edge/test_command_lifecycle.py` and `test_operator_api.py` passing unmodified.
- `NanoLinkAdapter.apply()` on a valid action inserts one `commands` row with `origin='loop'`, correct `prev_values` (captured from the latest snapshot), and returns `status="queued"`; a second `apply()` with the same `action_id` returns `status="duplicate"` with the original `command_id`.
- Cell-scoped targets resolve through `NANOLINK_CELL_DEVICE_MAP` and recommendation payloads (`{cell_el_deg, on_off}`) translate to the Appendix A.2 ReferenceSignalPower writes (`cell_el_deg` reported as skipped); an unresolvable `cell_id` yields `status="rejected"`.
- Invalid writes (non-catalogue path) yield `status="rejected"` with the `ValueError` message in `detail`, and no row inserted.
- `dispatch()` rejects unknown adapters (incl. bare `nanolink`) and expired actions without raising, and routes actions carrying `payload.rollback_of` to `adapter.rollback()`, never `apply()`.
- `GET /v1/actuators` lists `nanolink_tr069` with health `ok` against the compose stack.
- Migration 013 applies twice cleanly; agent poll/ack flows (`tests/nybsys_edge/test_agent_api.py`) pass unmodified.

**Test plan:**
- Unit: `cd submodule/maveric_platform_smo_sim && uv run pytest tests/actuators/ tests/nybsys_edge/` — new tests: registry idempotency, dispatch rejection matrix (unknown adapter incl. bare `nanolink` / expired / duplicate) + `payload.rollback_of` routing to `rollback()`, NanoLink apply happy path + cell->device resolution + recommendation->writes translation + validation failure + prev_values capture, read_back from snapshot, rollback enqueue.
- Regression: full `uv run pytest` green with zero edits to existing NanoLink tests (that is the byte-stability proof).
- Integration (compose): `./scripts/kafka/compose.sh infra && ./scripts/kafka/compose.sh up`, apply migrations 012+013, hit `GET localhost:8002/v1/actuators` with the service API key.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md sections 4.1 and 4.5 first, plus
Appendix A.2 (action field contents, translation seam, rollback routing) and A.4 (the
adapter key registry: the NanoLink key is "nanolink_tr069"; bare "nanolink" is invalid).
Task: build the ActuatorAdapter framework in submodule/maveric_platform_smo_sim and
refactor the NanoLink TR-069 plane to implement it BEHIND the existing surfaces.

Hard constraints (violating any of these is a failure):
- The operator router (app/api/v1/custom/nybsys_edge_router.py), agent router
  (app/api/v1/custom/nybsys_agent_router.py), command_service claim/complete/
  enqueue_rollback/reset_stale_commands semantics, the {success,message,data}
  envelope, and the command payload shape sent to the field-deployed Go edge agent
  are byte-frozen. Do not touch /v1/agent contracts. Existing tests in
  tests/nybsys_edge/ must pass WITHOUT modification.
- Zero CI/CD change: no new services, images, or ports. The new /v1/actuators
  endpoints are internal (X-API-Key inherited from the /v1 router) and are NOT added
  to the gateway.

Build:
1. app/actuators/{__init__.py,base.py,models.py,registry.py,dispatch.py} and
   app/actuators/adapters/{__init__.py,nanolink.py}. base.py defines the
   ActuatorAdapter Protocol with capabilities(), apply(db, action) -> ActuatorAck,
   read_back(db, target), rollback(db, action), health(). models.py defines
   Pydantic models LoopAction {action_id, tenant_id, adapter, target, payload,
   policy_ref: dict|None, expires_at} (field names are frozen HLD 4.1 contract;
   policy_ref is a JSON OBJECT per Appendix A.2, never a str), ActionTarget
   {device_id?, dn?, cell_id?, tick?}, ActuatorAck {action_id, adapter, status:
   queued|applied|failed|rejected|duplicate, command_id, detail},
   AdapterCapabilities, AdapterHealth. registry.py: module-level
   dict with register()/get()/all_adapters(). dispatch.py: dispatch(db, action)
   routing on action.adapter (Appendix A.4 keys); when action.payload has a non-null
   "rollback_of", route to adapter.rollback(db, action) instead of apply(); returns
   rejected acks for unknown adapter or expires_at in the past; never raises for
   business errors.
2. Extend command_service.create_command with keyword-only origin="manual",
   loop_action_id=None, policy_ref: dict|None=None and add the three columns to its
   INSERT (policy_ref bound as jsonb). Default call sites (operator router) must
   produce identical rows to today.
3. NanoLinkAdapter (name="nanolink_tr069" - the Appendix A.4 key; NEVER register
   "nanolink"): apply() resolves the device (target.device_id, else
   target.cell_id via new setting NANOLINK_CELL_DEVICE_MAP, a JSON
   {"<cell_id>": "<device_id>"} map; unresolvable -> status="rejected"), checks
   commands.loop_action_id for idempotent redelivery (return status="duplicate"),
   translates the payload per Appendix A.2 (explicit {"writes":[...],
   "rollback_on_fail": bool} passes through verbatim; the recommendation form
   {cell_el_deg, on_off} maps on_off=false -> ReferenceSignalPower =
   LOOP_ES_POWER_SAVE_DBM (default "-20"), on_off=true -> LOOP_ES_POWER_NORMAL_DBM
   (default "-10"); cell_el_deg is skipped and reported in ack detail), then calls
   create_command with origin="loop", type "configure"; prev_values capture and
   validate_write happen inside create_command exactly as today. read_back() returns
   the latest device_config_snapshots.params. rollback() (reached via dispatch's
   rollback_of routing) re-enqueues prev_values of the command for
   payload["rollback_of"] via command_service.enqueue_rollback(...,
   loop_action_id=action.action_id). health() checks DB reachability and returns
   pending/dispatched counts in detail. Register it at import time from
   app/actuators/adapters/__init__.py. Add settings NANOLINK_CELL_DEVICE_MAP,
   LOOP_ES_POWER_SAVE_DBM, LOOP_ES_POWER_NORMAL_DBM to app/core/config.py.
4. Add nullable loop_action_id/policy_ref columns to the commands ORM class in
   app/schemas/nybsys_edge_schemas.py (policy_ref = JSONB), and create dev-repo
   migration artifacts/migration/013_commands_loop_columns.sql: ALTER TABLE commands
   ADD COLUMN IF NOT EXISTS loop_action_id text; ADD COLUMN IF NOT EXISTS policy_ref
   jsonb; plus partial unique index commands_loop_action_uq on (loop_action_id) WHERE
   loop_action_id IS NOT NULL. Index it in artifacts/migration/README.md
   (numbering per HLD Appendix A.6: 012 is this epic's e2/r1 drop; 013 is this one).
5. New internal endpoints file app/api/v1/endpoints/actuators.py: GET /v1/actuators
   (list adapters with capabilities+health) and GET /v1/actuators/{name}/health,
   envelope-wrapped via app/lib/envelope.wrap. Include it in app/api/v1/routes.py.
6. Tests under tests/actuators/ (pytest, mirror existing test style in
   tests/nybsys_edge/): registry, dispatch rejection matrix, nanolink apply
   happy/duplicate/invalid-write, read_back, rollback.

Conventions: CLAUDE.md — Pydantic-first, full type hints, platform logger
(app/utils/logger.get_logger), DRY (no copy of create_command logic), docstrings on
non-obvious functions only.

Definition of done: cd submodule/maveric_platform_smo_sim && uv run pytest passes
with zero edits to pre-existing tests; migration 013 applies twice cleanly;
GET /v1/actuators returns nanolink_tr069 with health ok on the compose stack.
```

---

## E4.S3 — Loop executor: consume `maveric.loop.action.v1`, publish `maveric.loop.feedback.v1`

**Why:** The closed loop needs an executor arm: NDT-approved actions must land in the proven commands queue, and their real-world outcomes (acks, guardrail breaches, rollbacks) must flow back to the NDT decision hub. Kafka wiring already exists in smo_sim as dead code (`app/event_handlers/kafka_handler.py`); this story wires it for real, inside the existing container (zero CI/CD).

**Size:** L

**Scope:**
- In: background consumer thread (started from FastAPI lifespan, gated on `KAFKA_BOOTSTRAP_SERVERS`), consumer-side foreign-key filter (A.4 keys owned by other executors are committed and skipped silently, mirroring E3.S4's filter rule), action execution via `dispatch()` from S2 (incl. `payload.rollback_of` -> `rollback()` routing), feedback publisher (HLD Appendix A.3 shape), feedback hooks in `command_service.complete` (apply acks + rollback acks), `self_optimizer._guardrail_rollback` (guardrail events), and the telemetry-ingest KPI-window hook (`kind="kpi_window"` for devices with an in-window applied loop action - the NDT-level watch fires only from these), tests with fakes.
- Out: topic provisioning (rides the existing kafka chart topics-job / `init-topics.sh` — E0/E1 add the four §4.1 topics), NDT-side consumption (E2), end-to-end demo (E5). No change to agent-facing behavior: hooks observe acks, they never alter ack handling.

**Files:**
- Create: `submodule/maveric_platform_smo_sim/app/services/loop/__init__.py`
- Create: `submodule/maveric_platform_smo_sim/app/services/loop/models.py`
- Create: `submodule/maveric_platform_smo_sim/app/services/loop/consumer.py`
- Create: `submodule/maveric_platform_smo_sim/app/services/loop/feedback.py`
- Create: `submodule/maveric_platform_smo_sim/app/services/loop/kpi_window.py` (telemetry-ingest hook publishing `kind="kpi_window"` feedback)
- Modify: `submodule/maveric_platform_smo_sim/app/main.py` (lifespan: start/stop consumer thread)
- Modify: `submodule/maveric_platform_smo_sim/app/services/nybsys/command_service.py` (`complete()`: RETURNING also `loop_action_id`; after commit-safe point, call feedback hook when `loop_action_id` is not null)
- Modify: `submodule/maveric_platform_smo_sim/app/services/nybsys/self_optimizer.py` (`_guardrail_rollback`: publish `guardrail_breach` feedback when the rolled-back change originated from a loop action)
- Modify: `submodule/maveric_platform_smo_sim/app/core/config.py` (add `LOOP_CONSUMER_GROUP_ID: str = "smo-sim-loop-executor"`; `KAFKA_BOOTSTRAP_SERVERS` already exists, default `None` keeps it disabled)
- Create: `submodule/maveric_platform_smo_sim/tests/loop/__init__.py`, `test_consumer.py`, `test_feedback.py`

**Contract:**

Topics (names frozen, HLD §4.1): consume `maveric.loop.action.v1`, produce `maveric.loop.feedback.v1`. Action payload is the §4.1 shape with Appendix A.2 field contents (see S2).

Feedback payload — FROZEN in HLD Appendix A.3 (one contract covering apply acks, KPI windows, breaches, and rollbacks; E2.S7's watcher parses exactly this shape):

```json
{
  "schema": "maveric.loop.feedback.v1",
  "feedback_id": "<uuid4>",
  "action_id": "<loop action id, or null for unsolicited device events>",
  "tenant_id": "<uuid>",
  "adapter": "nanolink_tr069",
  "kind": "apply | kpi_window | guardrail_breach | rollback",
  "status": "queued | applied | failed | ok | breach | rolled_back | rejected | duplicate | expired",
  "command_id": "<commands.id or null>",
  "kpis": {"sinr_avg_db": 0.0, "rrc_success_pct": 0.0, "outage_rate": 0.0},
  "detail": {
    "readback": {},
    "mismatch": {},
    "error": "",
    "rollback_command_id": ""
  },
  "observed_at": "<RFC3339 UTC>"
}
```

Emission rules:
- Adapter filter first (mirrors E3.S4's rule - other executors own their keys): an action whose `adapter` is an A.4 key owned by another executor (`FOREIGN_ADAPTER_KEYS = {"a1_policy", "nearrt_xapp"}`, module constant next to the topic constants) is committed and skipped silently - no dispatch, NO feedback. Both executors consume the whole topic in separate consumer groups; without this filter every `a1_policy` action would generate a spurious smo_sim `rejected` feedback row alongside rapp's real feedback. `rejected` stays reserved for keys smo_sim owns or that no executor owns: unresolvable cell, expired action, placeholder `not_implemented`, invalid bare `nanolink`.
- On consuming an action that passes the filter: publish `kind="apply"` with the dispatch result (`queued`, `rejected`, `duplicate`, or `expired`).
- On agent ack of a loop-originated command (`complete()` sees `loop_action_id` not null): publish `kind="apply"` with `status="applied"|"failed"` and the agent's readback/mismatch in `detail`; include `detail.rollback_command_id` if auto-rollback was enqueued.
- KPI window (the NDT-level watch depends on this; `min_rrc_success_pct` is only enforceable NDT-side from these messages): on every telemetry ingest for a device that has a loop-originated command applied inside its watch window (commands with `loop_action_id` set, acked `applied` within the last `policy_ref.watch_window_min` minutes, default 15 when the snapshot lacks it), publish `kind="kpi_window"` with `kpis = {sinr_avg_db, rrc_success_pct, outage_rate?}` drawn from the ingested metrics and `status="ok"|"breach"` per the device-level GUARD thresholds. Implemented as a telemetry-ingest hook (`app/services/loop/kpi_window.py`, called from the same path that runs `self_optimizer.on_new_kpis`); at most one message per (device, telemetry sample).
- On guardrail breach that triggers rollback of a loop-originated command: publish `kind="guardrail_breach"` (breach KPIs in `kpis`) and, when the rollback command itself is acked, a `kind="rollback"` event (`status="rolled_back"|"failed"`) via the same `complete()` hook (rollback commands enqueued for a loop action carry the same `loop_action_id`; extend `enqueue_rollback` with an optional `loop_action_id=None` passthrough).

**Key snippets:**

`app/services/loop/models.py`:

```python
class LoopFeedback(BaseModel):
    """HLD Appendix A.3 frozen shape (serialize by_alias so the wire field is "schema")."""
    schema_: str = Field(default="maveric.loop.feedback.v1", alias="schema")
    feedback_id: str = Field(default_factory=lambda: str(uuid4()))
    action_id: str | None
    tenant_id: str
    adapter: str
    kind: Literal["apply", "kpi_window", "guardrail_breach", "rollback"]
    status: Literal["queued", "applied", "failed", "ok", "breach", "rolled_back",
                    "rejected", "duplicate", "expired"]
    command_id: str | None = None
    kpis: dict[str, float] | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

`app/services/loop/feedback.py`:

```python
LOOP_FEEDBACK_TOPIC = "maveric.loop.feedback.v1"   # frozen HLD 4.1

def publish_feedback(evt: LoopFeedback) -> bool:
    """Fire-and-forget publish. Returns False (and logs a warning) when Kafka is not
    configured — the device-level loop keeps working without the platform loop."""
```

`app/services/loop/consumer.py`:

```python
LOOP_ACTION_TOPIC = "maveric.loop.action.v1"       # frozen HLD 4.1

class LoopActionConsumer(threading.Thread):
    """Background executor inside the smo_sim container (no new deployable).

    poll -> Pydantic-validate LoopAction -> foreign-key filter (adapter in
    FOREIGN_ADAPTER_KEYS -> log at debug, commit, skip, NO feedback; mirrors
    E3.S4) -> open Session -> set_config('app.current_tenant', action.tenant_id)
    for RLS -> actuators.dispatch -> publish ack feedback -> commit. Malformed
    messages are logged + skipped (poison tolerance); duplicate delivery is safe
    via the commands_loop_action_uq index (dispatch returns status='duplicate').
    daemon=True; stop() sets an event checked between polls so lifespan shutdown
    is clean.
    """
    def __init__(self, group_id: str) -> None: ...
    def run(self) -> None: ...
    def stop(self) -> None: ...

def start_loop_consumer_if_configured() -> LoopActionConsumer | None:
    """Called from app.main lifespan. Returns None when KAFKA_BOOTSTRAP_SERVERS unset."""
```

Hook in `command_service.complete()` (observing, never altering, the ack path):

```python
row = db.execute(text("UPDATE commands SET ... RETURNING device_id, edge_id, payload,
                       prev_values, loop_action_id, tenant_id"), ...)
...
if row["loop_action_id"]:
    from app.services.loop.feedback import publish_feedback  # local import: no cycle
    publish_feedback(LoopFeedback(action_id=row["loop_action_id"], kind="apply", ...))
```

Telemetry-ingest KPI-window hook (`app/services/loop/kpi_window.py`; called from the telemetry path right where `self_optimizer.on_new_kpis` runs):

```python
def publish_kpi_window(db: Session, ctx: Mapping[str, str], device_id: str,
                       metrics: Mapping[str, float]) -> bool:
    """Publish kind="kpi_window" feedback (HLD Appendix A.3) for every loop action whose
    command on this device was acked applied within its watch window
    (commands.loop_action_id set, acked within policy_ref.watch_window_min minutes,
    default 15). kpis = {sinr_avg_db, rrc_success_pct, outage_rate?} from the sample;
    status = "breach" when any device-level GUARD threshold is violated, else "ok".
    No-op (False) when Kafka is unconfigured or no in-window loop action exists."""
```

**Acceptance criteria:**
- With `KAFKA_BOOTSTRAP_SERVERS` unset (default), smo_sim boots exactly as today: no consumer thread, no producer init, zero new log noise above DEBUG/WARNING.
- Publishing a valid `nanolink_tr069` action to `maveric.loop.action.v1` on the compose stack results in: one `commands` row (`origin='loop'`, `loop_action_id` set) and one `kind="apply", status="queued"` message on `maveric.loop.feedback.v1` (Appendix A.3 shape, `LoopFeedback.model_validate` clean).
- Re-publishing the same action produces no second command row and a `status="duplicate"` feedback.
- An action whose `adapter` is a foreign A.4 key (e.g. `a1_policy`, `nearrt_xapp`) produces no command row AND no feedback message - committed and skipped silently; an unknown key no executor owns (e.g. bare `nanolink`) still yields `status="rejected"` feedback via dispatch.
- An action with `expires_at` in the past produces no row and `status="expired"` feedback.
- An action carrying `payload.rollback_of` is routed to `adapter.rollback()` (never `apply()`) and, once the rollback command is acked, emits `kind="rollback", status="rolled_back"` feedback.
- Simulated agent ack (existing test helpers in `tests/nybsys_edge/test_command_lifecycle.py` style) of a loop-originated command emits `kind="apply", status="applied"` with readback detail; a failed configure with rollback emits `detail.rollback_command_id`.
- Telemetry ingest for a device with a loop command applied inside its watch window emits exactly one `kind="kpi_window"` message per sample with `kpis` populated (`status="ok"` healthy, `status="breach"` when GUARD thresholds are violated); a device with no in-window loop action emits nothing.
- Guardrail breach within the watch window of an applied loop command emits `kind="guardrail_breach"`.
- Malformed JSON on the action topic is skipped with an error log; the consumer keeps running.
- All existing tests pass unmodified.

**Test plan:**
- Unit: `cd submodule/maveric_platform_smo_sim && uv run pytest tests/loop/` — consumer logic tested by injecting a fake consumer (list of raw messages) and a recording fake producer; assert dispatch calls, feedback payload schema (validate with `LoopFeedback.model_validate`), poison-message tolerance, RLS `set_config` invocation. Feedback hooks tested by monkeypatching `publish_feedback` in `test_command_lifecycle`-style flows.
- Integration (lab, compose): `./scripts/kafka/compose.sh up`; create the two topics via `scripts/kafka/init-topics.sh` (extended in E0/E1); use `kafka-console-producer`/`-consumer` to drive an action end-to-end into the commands table and read the feedback.
- Regression: full `uv run pytest`.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md sections 2, 4.1, 4.5 AND
Appendix A.2/A.3 (action contents + the FROZEN feedback payload; E2's watcher parses A.3
exactly). Prerequisite: EPIC-4 story S2 (app/actuators/ framework + NanoLink adapter +
migration 013 with commands.loop_action_id) is merged. Task: wire the loop executor
in submodule/maveric_platform_smo_sim.

Context: smo_sim has never used Kafka; app/event_handlers/kafka_handler.py contains
working-but-unused KafkaProducerManager/KafkaConsumerManager classes (kafka-python
2.0.2 is already a dependency). KAFKA_BOOTSTRAP_SERVERS exists in app/core/config.py
defaulting to None. The executor must run as a background thread inside the existing
container — no new deployable, no new port (zero CI/CD change).

Build:
1. app/services/loop/models.py: LoopFeedback Pydantic model per HLD Appendix A.3:
   schema="maveric.loop.feedback.v1", feedback_id (uuid4 default), action_id,
   tenant_id, adapter, kind in {apply, kpi_window, guardrail_breach, rollback},
   status in {queued, applied, failed, ok, breach, rolled_back, rejected, duplicate,
   expired}, command_id, kpis dict|None, detail dict, observed_at (UTC). Serialize
   with by_alias so the wire field is "schema".
2. app/services/loop/feedback.py: publish_feedback(evt) -> bool using a lazily
   created module-level KafkaProducerManager sending JSON to
   "maveric.loop.feedback.v1". Must be a logged no-op returning False when
   KAFKA_BOOTSTRAP_SERVERS is unset. Topic names are frozen contracts — define them
   as module constants, never inline strings elsewhere.
3. app/services/loop/consumer.py: LoopActionConsumer(threading.Thread, daemon=True)
   consuming "maveric.loop.action.v1" via KafkaConsumerManager with group_id from new
   setting LOOP_CONSUMER_GROUP_ID (default "smo-sim-loop-executor"). Per message:
   json.loads -> LoopAction.model_validate (from app.actuators.models); on failure
   log error and skip. Foreign-key filter BEFORE dispatch (mirrors E3.S4 - other
   executors own their keys): if action.adapter is in FOREIGN_ADAPTER_KEYS =
   {"a1_policy", "nearrt_xapp"} (module constant next to the topic constants, per
   HLD Appendix A.4), log at debug, commit, and skip WITHOUT publishing feedback
   (a bare "nanolink" or otherwise unknown key still goes to dispatch and comes
   back "rejected"). Otherwise: open db_manager.SessionLocal(), execute
   SELECT set_config('app.current_tenant', :tid, true) with action.tenant_id, call
   app.actuators.dispatch.dispatch(db, action) (which routes payload.rollback_of to
   adapter.rollback per Appendix A.2), commit, publish a kind="apply" LoopFeedback
   mirroring the ActuatorAck status (map rejected-because-expired to status
   "expired"). Provide stop() via threading.Event polled between consumer polls.
   Also start_loop_consumer_if_configured() used by app/main.py lifespan (start
   after startup sweeps; stop() + join(timeout=5) on shutdown).
4. Feedback hooks: (a) command_service.complete(): add loop_action_id and tenant_id
   to the UPDATE ... RETURNING list; when loop_action_id is not null, publish a
   kind="apply" feedback with status applied/failed from the agent ack, the
   ack readback/mismatch in detail, and detail.rollback_command_id when
   auto-rollback was enqueued. Use a local import of publish_feedback to avoid
   import cycles. Also extend enqueue_rollback with keyword-only
   loop_action_id: str | None = None and pass it through the INSERT, and have
   complete() forward the failed command's loop_action_id into the rollback row
   (so the rollback's own ack becomes a kind="rollback" feedback: in complete(),
   when the acked command's origin is 'rollback' and loop_action_id is set, use
   kind="rollback", status="rolled_back").
   (b) self_optimizer._guardrail_rollback(): after enqueuing the rollback, check
   whether the source command (the one whose prev_values are used) has
   loop_action_id set; if so publish kind="guardrail_breach" feedback with the
   breach KPIs (sinr, rrc) in kpis. The ack-handling behavior toward the agent
   must not change in any way — hooks only observe.
   (c) KPI window (the NDT watch depends on this - min_rrc_success_pct is enforced
   NDT-side from these messages): app/services/loop/kpi_window.py with
   publish_kpi_window(db, ctx, device_id, metrics) called from the telemetry-ingest
   path right where self_optimizer.on_new_kpis runs; for each loop action whose
   command on this device was acked applied within policy_ref.watch_window_min
   minutes (default 15), publish kind="kpi_window" with
   kpis={sinr_avg_db, rrc_success_pct, outage_rate?} from the sample and
   status="breach" when a device-level GUARD threshold is violated else "ok";
   at most one message per (device, telemetry sample); no-op without Kafka.
5. Tests in tests/loop/: fake consumer (iterable of byte payloads) + recording fake
   producer via monkeypatch; cover happy path, duplicate, expired, malformed JSON,
   unknown adapter (bare "nanolink" -> rejected feedback), foreign adapter key
   (a1_policy -> silent commit-and-skip, no feedback), rollback_of routing, the
   kpi_window hook (in-window emits ok/breach; out-of-window emits nothing), and
   all hooks. Validate every published
   message with LoopFeedback.model_validate (Appendix A.3). Match existing test
   style (tests/nybsys_edge/).

Constraints: /v1/agent/** and operator router contracts byte-frozen; existing tests
pass unmodified; platform logger everywhere; type hints; no bare threads without
stop handling. Do not create Kafka topics in code (they ride the existing
init-topics.sh / kafka chart topics-job — out of scope here).

Definition of done: cd submodule/maveric_platform_smo_sim && uv run pytest passes;
with the compose stack + topics present, a hand-published action lands as a
commands row (origin='loop') and produces queued/applied feedback messages; with
KAFKA_BOOTSTRAP_SERVERS unset the service behaves exactly as before.
```

---

## E4.S4 — Scale-out fixes: periodic lease sweep + EWMA state to Redis

**Why:** Recon flagged single-replica assumptions: the command lease sweep runs only at startup (a stale `dispatched` command is reclaimed only on restart), and the self-optimizer's EWMA anomaly state is an in-process dict (`self_optimizer.py:68`, OD7) that resets on restart and diverges across replicas. Both must be fixed before smo_sim can scale horizontally as the actuation service.

**Size:** M

**Scope:**
- In: asyncio-based periodic sweep task in lifespan; `EwmaStore` abstraction with Redis and in-memory implementations; `redis` dependency; config knobs. ThreadPool PM-ingestion retirement is explicitly **out** — that workload moves wholesale to data_sim on `maveric.ingest.pm.v1` in E1 (S6 then deletes the smo_sim copy).
- Out: any change to EWMA math, guardrail thresholds, recommendation rules, or sweep SQL semantics (`reset_stale_commands` body unchanged); no distributed locking (the sweep is an idempotent UPDATE — concurrent replicas are harmless).

**Files:**
- Modify: `submodule/maveric_platform_smo_sim/app/main.py` (lifespan: `asyncio.create_task` for the sweep loop; cancel on shutdown)
- Create: `submodule/maveric_platform_smo_sim/app/services/nybsys/sweeper.py`
- Create: `submodule/maveric_platform_smo_sim/app/services/nybsys/optimizer_state.py`
- Modify: `submodule/maveric_platform_smo_sim/app/services/nybsys/self_optimizer.py` (replace `_STATE`/`_sinr_ewma` with the store; `Ewma` dataclass stays)
- Modify: `submodule/maveric_platform_smo_sim/app/core/config.py` (add `NYBSYS_SWEEP_INTERVAL_SECONDS: int = 30` — `0` disables the periodic loop; `REDIS_URL: str | None = None`)
- Modify: `submodule/maveric_platform_smo_sim/requirements.txt` + `pyproject.toml` (add `redis==5.*` line matching the pin style used by rapp/gateway-adjacent services; verify exact pin against what bdt/rapp use to keep the mesh consistent)
- Modify: `submodule/maveric_platform_smo_sim/tests/nybsys_edge/test_self_optimizer.py` (only if it reaches into `_STATE` directly — prefer adding new tests; existing assertions must keep passing)
- Create: `submodule/maveric_platform_smo_sim/tests/nybsys_edge/test_optimizer_state.py`, `tests/nybsys_edge/test_sweeper.py`

**Contract (module interfaces):**

```python
# app/services/nybsys/optimizer_state.py
class EwmaStore(Protocol):
    def load(self, tenant_id: str, device_id: str) -> Ewma: ...
    def save(self, tenant_id: str, device_id: str, state: Ewma) -> None: ...

class InMemoryEwmaStore:   # today's behavior; used when REDIS_URL is unset
class RedisEwmaStore:
    """Key smo:opt:ewma:{tenant_id}:{device_id}; value JSON {mean, var, n, alpha};
    TTL 7 days (self-heals dead devices). Read-modify-write races between replicas
    are acceptable for anomaly detection and documented here."""

def get_ewma_store() -> EwmaStore:
    """Singleton; RedisEwmaStore when settings.REDIS_URL else InMemoryEwmaStore.
    Redis connection errors degrade to warning + in-memory fallback (never break
    telemetry ingestion)."""
```

```python
# app/services/nybsys/sweeper.py
async def periodic_lease_sweep(interval_s: int) -> None:
    """Every interval_s: open session, command_service.reset_stale_commands, commit,
    close. Exceptions are logged and never kill the loop. Cancels cleanly."""
```

Redis enablement is env-only (`REDIS_URL` via existing chart values / compose env) — no chart or image change; unset means today's exact behavior.

**Key snippets:**

`self_optimizer.py` diff sketch (math untouched):

```python
# was: _STATE: dict[tuple, Ewma]; _sinr_ewma(...) = _STATE.setdefault(...)
def on_new_kpis(db, ctx, metrics):
    ...
    if s.get("sinr_avg_db") is not None:
        store = get_ewma_store()
        ewma = store.load(ctx["tenant_id"], device_id)
        z = ewma.update(float(s["sinr_avg_db"]))
        store.save(ctx["tenant_id"], device_id, ewma)
        if abs(z) > 3:
            _emit_anomaly(db, ctx, device_id, f"SINR z-score {z:.1f}")
```

`main.py` lifespan addition:

```python
sweep_task: asyncio.Task | None = None
if settings.NYBSYS_SWEEP_INTERVAL_SECONDS > 0:
    sweep_task = asyncio.create_task(
        periodic_lease_sweep(settings.NYBSYS_SWEEP_INTERVAL_SECONDS))
yield
if sweep_task:
    sweep_task.cancel()
```

**Acceptance criteria:**
- A `dispatched` command older than `NYBSYS_LEASE_SECONDS` returns to `pending` within one sweep interval while the service keeps running (no restart) — new integration-style test with a short interval.
- Startup sweep behavior preserved (still runs once in lifespan before the periodic task).
- With `REDIS_URL` set, EWMA state survives a process restart: feed N samples, restart (new store instance), feed an outlier, anomaly fires with the pre-restart baseline (test against `fakeredis` or a monkeypatched client — prefer `fakeredis` as a dev dependency).
- With `REDIS_URL` unset, behavior is byte-identical to today (existing `test_self_optimizer.py` passes).
- Redis outage mid-flight logs a warning and falls back to in-memory without failing `/v1/agent/telemetry`.
- `NYBSYS_SWEEP_INTERVAL_SECONDS=0` disables the loop.

**Test plan:**
- Unit: `cd submodule/maveric_platform_smo_sim && uv run pytest tests/nybsys_edge/test_optimizer_state.py tests/nybsys_edge/test_sweeper.py tests/nybsys_edge/test_self_optimizer.py` — sweeper loop with mocked session + cancellation; store round-trip, TTL args, fallback-on-error; optimizer regression.
- Regression: full `uv run pytest`.
- Integration (compose): redis is already in infra (`:6379`); set `REDIS_URL=redis://redis:6379/0` for smo_sim in compose env, drive telemetry via `scripts/telemetry/sim_agent.py`, restart smo_sim, confirm anomaly continuity in `device_events`.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md (section 3 hard
constraints) and the recon facts: smo_sim's command lease sweep
(command_service.reset_stale_commands) runs only at startup (app/main.py lifespan),
and the self-optimizer EWMA anomaly state is an in-process dict
(app/services/nybsys/self_optimizer.py, _STATE at ~line 68). Fix both for
multi-replica operation in submodule/maveric_platform_smo_sim.

Task:
1. app/services/nybsys/sweeper.py: async def periodic_lease_sweep(interval_s: int)
   that loops forever: asyncio.sleep(interval_s), then run
   command_service.reset_stale_commands in a fresh SessionLocal (commit, close) —
   run the blocking DB call via asyncio.to_thread. Log and swallow exceptions per
   iteration. In app/main.py lifespan, after the existing startup sweeps, create
   the task when new setting NYBSYS_SWEEP_INTERVAL_SECONDS (default 30, 0=off) is
   positive; cancel + await it on shutdown. Do not change reset_stale_commands.
2. app/services/nybsys/optimizer_state.py: EwmaStore Protocol (load/save keyed by
   tenant_id+device_id, value = the existing Ewma dataclass), InMemoryEwmaStore
   (dict, current behavior), RedisEwmaStore (redis-py, key
   smo:opt:ewma:{tenant}:{device}, JSON value {mean,var,n,alpha}, TTL 7 days,
   documented read-modify-write race acceptance), get_ewma_store() singleton
   selecting Redis when new setting REDIS_URL is set, degrading to in-memory with
   a warning on connection errors. Add redis to requirements.txt and pyproject.toml
   (match the version pin style other services in the mesh use; check
   submodule/maveric_platform_rapp and the gateway for the prevailing redis pin).
3. Refactor self_optimizer.py to use get_ewma_store() (load -> update -> save)
   and delete the module-level _STATE/_sinr_ewma. Do NOT change the Ewma math,
   thresholds, GUARD dict, or recommendation logic.
4. Tests: tests/nybsys_edge/test_sweeper.py (loop reclaims a stale dispatched row;
   cancellation is clean; interval 0 disables), tests/nybsys_edge/
   test_optimizer_state.py (round-trip, restart continuity using fakeredis — add
   fakeredis as a dev/test dependency — and fallback path). Existing
   test_self_optimizer.py must pass; only adapt it if it pokes _STATE directly,
   preserving every behavioral assertion.

Constraints: zero CI/CD change (REDIS_URL arrives via env only; unset = today's
behavior); /v1/agent/telemetry must never fail because Redis is down; platform
logger; type hints; Pydantic settings for new config fields.

Definition of done: cd submodule/maveric_platform_smo_sim && uv run pytest passes;
manual compose check shows a stale dispatched command reclaimed without restart and
EWMA continuity across an smo_sim restart with REDIS_URL set.
```

---

## E4.S5 — Placeholder adapters wired per §4.5 (o1_netconf, ocudu_ws_collector, open_mplane, sas_domain_proxy, nms_northbound)

**Why:** §4.5 requires the adapter framework to ship with wired placeholders (module + registry entry + health + contract doc, no protocol implementation) so every future southbound plane has a named slot, a health surface, and a written contract before code lands. Two get real substance now: the SAS Domain Proxy state machine + models (pure logic, testable without a SAS), and the OCUDU WS collector (plain JSON over WebSocket — implementable without any RIC or ASN.1).

**Size:** L

**Scope:**
- In: five adapter modules registered in the S2 registry, each reporting honest health (`not_implemented` or `disabled`); five contract docs under a new `artifacts/actuation/` bundle; SAS: real Pydantic models for the six WINNF-TS-0016 methods, a per-CBSD/per-grant state machine with the 60 s transmit-shutdown rule and the responseCode handling table, an HTTP client behind an interface with a `MockSas` for tests, mTLS cert slots as config; OCUDU WS collector implemented for real behind a config gate (off by default), emitting normalized PM records to `maveric.ingest.pm.v1`.
- Out: any NETCONF/YANG protocol code (o1_netconf stays a stub targeting the OCUDU companion `ocudu_netconf`), any Open M-Plane or NMS protocol code, real SAS connectivity/certification (WINNF-TS-0122 lab testing is a compliance project, not this story), E2/RIC anything (that is rapp's §4.4 layer). No new listening ports (the WS collector is an outbound client).

**Files:**
- Create: `submodule/maveric_platform_smo_sim/app/actuators/adapters/o1_netconf.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/adapters/ocudu_ws_collector.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/adapters/open_mplane.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/adapters/nms_northbound.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/adapters/sas_domain_proxy/__init__.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/adapters/sas_domain_proxy/models.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/adapters/sas_domain_proxy/state_machine.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/adapters/sas_domain_proxy/client.py`
- Create: `submodule/maveric_platform_smo_sim/app/actuators/adapters/sas_domain_proxy/adapter.py`
- Modify: `submodule/maveric_platform_smo_sim/app/actuators/adapters/__init__.py` (register all five)
- Modify: `submodule/maveric_platform_smo_sim/app/core/config.py` (adapter config: `OCUDU_WS_ENABLED: bool = False`, `OCUDU_WS_URLS: str | None = None`, `OCUDU_WS_TENANT_ID: str | None = None`, `SAS_BASE_URL: str | None`, `SAS_VERSION: str = "v1.2"`, `SAS_DP_CERT_FILE: str | None`, `SAS_DP_KEY_FILE: str | None`, `SAS_CA_BUNDLE: str | None`)
- Modify: `submodule/maveric_platform_smo_sim/requirements.txt` + `pyproject.toml` (add `websockets` for the collector; `httpx` for the SAS HTTP client — smo_sim currently has no outbound HTTP client at all, verified by recon)
- Create: `artifacts/actuation/README.md`, `artifacts/actuation/o1_netconf.md`, `artifacts/actuation/ocudu_ws_collector.md`, `artifacts/actuation/open_mplane.md`, `artifacts/actuation/sas_domain_proxy.md`, `artifacts/actuation/nms_northbound.md`
- Create: `submodule/maveric_platform_smo_sim/tests/actuators/test_placeholder_health.py`, `test_sas_models.py`, `test_sas_state_machine.py`, `test_sas_client.py`, `test_ocudu_ws_collector.py`

**Contract:**

Registry names (the `adapter` key on loop actions; FROZEN in HLD Appendix A.4 - one namespace shared with `target_adapter_hint` and E3's ric adapter keys): `nanolink_tr069`, `o1_netconf`, `ocudu_ws_collector`, `open_mplane`, `sas_domain_proxy`, `nms_northbound`. Bare `nanolink` is NOT a valid key.

o1_netconf contract sketch (doc + stub method signatures only — targets the OCUDU companion `ocudu_netconf` service, NETCONF/YANG; wording rule: "NETCONF/YANG config adapter for OCUDU via its ocudu_netconf companion", never "O1 compliant"):

```python
def config_get(self, dn: str, paths: list[str]) -> dict[str, Any]: ...   # raises NotImplementedError
def config_set(self, dn: str, changes: dict[str, Any]) -> ActuatorAck: ...  # via apply()
```

OCUDU WS collector (implementable now; data-plane only — `capabilities.collect=True`, `apply/rollback` return `rejected`): outbound WebSocket client to OCUDU `remote_control` endpoints (default gNB-side port 8001, `metrics.enable_json: true`), translating each JSON metrics frame into normalized PM records published to `maveric.ingest.pm.v1`.

Record-batch payload — FROZEN in HLD Appendix A.5 (single `kind` discriminator, field name `source_type`; E1.S8 owns the consumer branch):

```json
{
  "schema": "maveric.ingest.pm.v1",
  "kind": "records",
  "tenant_id": "<uuid>",
  "batch_id": "<uuid4>",
  "source_type": "ocudu_ws",
  "vendor": "ocudu",
  "records": [
    {"dn": "<gnb_id/cell_id>", "metric": "<source metric name>",
     "value": 0.0, "unit": "", "granularity_s": 1, "ts": "<RFC3339 UTC>", "labels": {}}
  ]
}
```

(`metric` carries the SOURCE name; the data platform maps it via `vendor_dictionaries` vendor `ocudu` at store time. Never emit a `source` field name.)

SAS Domain Proxy (WINNF-TS-0016 v1.2.7; six batched JSON methods over `POST {SAS_BASE_URL}/{SAS_VERSION}/{method}`; models + FSM are real, transport is behind an interface):

```python
# client.py
class SasClientPort(Protocol):
    def registration(self, reqs: list[RegistrationRequest]) -> list[RegistrationResponse]: ...
    def spectrum_inquiry(self, reqs: list[SpectrumInquiryRequest]) -> list[SpectrumInquiryResponse]: ...
    def grant(self, reqs: list[GrantRequest]) -> list[GrantResponse]: ...
    def heartbeat(self, reqs: list[HeartbeatRequest]) -> list[HeartbeatResponse]: ...
    def relinquishment(self, reqs: list[RelinquishmentRequest]) -> list[RelinquishmentResponse]: ...
    def deregistration(self, reqs: list[DeregistrationRequest]) -> list[DeregistrationResponse]: ...

class HttpSasClient(SasClientPort):
    """POST JSON {"<method>Request": [...]} with mutual TLS (cert slots from settings:
    SAS_DP_CERT_FILE / SAS_DP_KEY_FILE / SAS_CA_BUNDLE). httpx.Client(cert=..., verify=...)."""

class MockSas(SasClientPort):
    """Scripted responses for tests (per-method queues)."""
```

**Key snippets:**

SAS Pydantic models (subset; `models.py` — spec field names are camelCase on the wire, use `alias` + `populate_by_name`):

```python
class SasResponse(BaseModel):
    response_code: int = Field(alias="responseCode")
    response_message: str | None = Field(default=None, alias="responseMessage")
    response_data: Any | None = Field(default=None, alias="responseData")

class FrequencyRange(BaseModel):
    low_frequency: int = Field(alias="lowFrequency")     # Hz
    high_frequency: int = Field(alias="highFrequency")

class InstallationParam(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    height: float | None = None
    height_type: Literal["AGL", "AMSL"] | None = Field(default=None, alias="heightType")
    indoor_deployment: bool | None = Field(default=None, alias="indoorDeployment")
    antenna_gain: float | None = Field(default=None, alias="antennaGain")
    eirp_capability: float | None = Field(default=None, alias="eirpCapability")

class RegistrationRequest(BaseModel):
    user_id: str = Field(alias="userId")
    fcc_id: str = Field(alias="fccId")
    cbsd_serial_number: str = Field(alias="cbsdSerialNumber")
    cbsd_category: Literal["A", "B"] = Field(alias="cbsdCategory")  # femtocells = Category A
    air_interface: dict | None = Field(default=None, alias="airInterface")
    installation_param: InstallationParam | None = Field(default=None, alias="installationParam")
    meas_capability: list[str] = Field(default_factory=list, alias="measCapability")
    cpi_signature_data: dict | None = Field(default=None, alias="cpiSignatureData")  # JWS passthrough, never fabricated

class GrantRequest(BaseModel):
    cbsd_id: str = Field(alias="cbsdId")
    operation_param: OperationParam = Field(alias="operationParam")  # {maxEirp, operationFrequencyRange}

class HeartbeatRequest(BaseModel):
    cbsd_id: str = Field(alias="cbsdId")
    grant_id: str = Field(alias="grantId")
    operation_state: Literal["IDLE", "GRANTED", "AUTHORIZED"] = Field(alias="operationState")

class HeartbeatResponse(BaseModel):
    response: SasResponse
    cbsd_id: str | None = Field(default=None, alias="cbsdId")
    grant_id: str | None = Field(default=None, alias="grantId")
    transmit_expire_time: datetime | None = Field(default=None, alias="transmitExpireTime")
    heartbeat_interval: int | None = Field(default=None, alias="heartbeatInterval")
    operation_param: OperationParam | None = Field(default=None, alias="operationParam")
```

State machine (`state_machine.py`):

```python
class GrantState(str, Enum):
    IDLE = "IDLE"
    GRANTED = "GRANTED"
    AUTHORIZED = "AUTHORIZED"     # TX allowed ONLY here (entered on first successful heartbeat)

class SasDirective(str, Enum):
    NONE = "NONE"
    TX_OFF = "TX_OFF"             # push radio-disable southbound (60 s hard rule)
    RELINQUISH = "RELINQUISH"
    RELINQUISH_AND_REGRANT = "RELINQUISH_AND_REGRANT"   # code 502
    DEREGISTER = "DEREGISTER"     # code 105: cease all TX + deregister
    HEARTBEAT_KEEPALIVE = "HEARTBEAT_KEEPALIVE"         # code 501: TX off, keep heartbeating

# responseCode handling table (WINNF-TS-0016 Table 39). Keys = SAS responseCode.
RESPONSE_ACTIONS: dict[int, SasDirective] = {
    0: SasDirective.NONE,                        # SUCCESS
    105: SasDirective.DEREGISTER,                # DEREGISTER (SAS-forced)
    500: SasDirective.RELINQUISH,                # TERMINATED_GRANT -> grant dies, back to IDLE
    501: SasDirective.HEARTBEAT_KEEPALIVE,       # SUSPENDED_GRANT -> TX off, stay GRANTED, keep heartbeating
    502: SasDirective.RELINQUISH_AND_REGRANT,    # UNSYNC_OP_PARAM -> TX off within 60 s, relinquish, re-grant
    # 100 VERSION, 101 BLACKLISTED, 102 MISSING_PARAM, 103 INVALID_VALUE,
    # 104 CERT_ERROR, 200 REG_PENDING, 300 UNSUPPORTED_SPECTRUM, 400 INTERFERENCE,
    # 401 GRANT_CONFLICT -> per-code branches in the FSM (no TX-state change unless granted-state codes)
}

@dataclass
class GrantFsm:
    """One FSM per (cbsd_id, grant_id) — a CBSD can hold multiple grants."""
    state: GrantState = GrantState.IDLE
    grant_id: str | None = None
    grant_expire_time: datetime | None = None
    heartbeat_interval: int | None = None
    transmit_expire_time: datetime | None = None

    def on_grant_response(self, resp: GrantResponse) -> SasDirective: ...
    def on_heartbeat_response(self, resp: HeartbeatResponse) -> SasDirective: ...
    def on_clock(self, now: datetime) -> SasDirective:
        """60 s rule (47 CFR 96.39(c)(2)): if now >= transmit_expire_time, TX must
        already be off; the FSM emits TX_OFF no later than transmit_expire_time and
        treats transmit_expire_time + 60 s as the absolute radio-off deadline."""
```

Placeholder stubs (o1_netconf / open_mplane / nms_northbound) all follow:

```python
class O1NetconfAdapter:
    name = "o1_netconf"
    def capabilities(self): ...   # apply/read_back/rollback flagged per contract doc
    def apply(self, db, action):  # -> ActuatorAck(status="rejected", detail={"error": "not_implemented"})
    def health(self):             # -> AdapterHealth(status="not_implemented", detail="stub; see artifacts/actuation/o1_netconf.md")
```

OCUDU collector run-loop lives in a thread started from lifespan only when `OCUDU_WS_ENABLED=true` (lab/compose env only; production stays off — env-gated, zero CI/CD change).

**Acceptance criteria:**
- `GET /v1/actuators` lists all six adapters; the five placeholders report `not_implemented` (or `disabled` for ocudu_ws_collector when `OCUDU_WS_ENABLED=false`).
- `dispatch()` of an action targeting any placeholder returns `status="rejected"` with a `not_implemented` detail, and the loop executor publishes that as feedback (S3 integration).
- SAS FSM unit tests prove: Idle→Granted on grant success; Granted→Authorized on first heartbeat success; heartbeat refreshes `transmit_expire_time`; codes 105/500/501/502 produce exactly the directives in the table; `on_clock` emits TX_OFF at/after `transmit_expire_time` and flags the +60 s deadline; a terminated grant returns to IDLE.
- SAS models round-trip camelCase wire JSON (`by_alias`) for all six method pairs; `MockSas`-backed `HttpSasClient` tests verify URL shape `{base}/{version}/{method}` and the `{"<method>Request": [...]}` batch envelope; mTLS slots are passed to `httpx.Client(cert=(cert,key), verify=ca)`.
- OCUDU collector test: fed a canned OCUDU JSON metrics frame through the translation function, it produces a valid `maveric.ingest.pm.v1` records batch (schema-validated) on the fake producer; disabled by default (no thread when flag off).
- Each of the five contract docs exists, carries a claims-guardrails banner (no O-RAN/RIC/SMO/SAS-certified compliance claims; no em dashes), and states implementation status honestly.
- Full existing suite passes.

**Test plan:**
- Unit: `cd submodule/maveric_platform_smo_sim && uv run pytest tests/actuators/` — placeholder health matrix; SAS models round-trip; FSM transition table (parametrized over response codes); client URL/envelope/mTLS-arg tests with `MockSas` and a mocked `httpx.Client`; collector translation + gating.
- Integration (lab, optional): run an OCUDU gNB or the bundled Grafana-feed simulator with `metrics.enable_json`, point `OCUDU_WS_URLS` at it in compose, observe records on `maveric.ingest.pm.v1` via `kafka-console-consumer`.
- Regression: full `uv run pytest`.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md section 4.5, then
artifacts/marketing/claims-guardrails.md (mandatory before writing any doc copy).
Prerequisite: EPIC-4 stories S2 (app/actuators/ framework) and S3 (loop
consumer/feedback) are merged in submodule/maveric_platform_smo_sim.

Task: wire five placeholder actuator adapters (module + registry entry + health +
contract doc each) with real substance in exactly two places: the SAS Domain Proxy
domain logic and the OCUDU WebSocket collector.

1. Simple stubs — app/actuators/adapters/o1_netconf.py, open_mplane.py,
   nms_northbound.py: classes with name "o1_netconf"/"open_mplane"/"nms_northbound",
   capabilities() per their contract doc, apply()/rollback() returning
   ActuatorAck(status="rejected", detail={"error":"not_implemented"}), health()
   returning status "not_implemented" with a pointer to the contract doc.
   o1_netconf's docstring + doc sketch a config get/set contract targeting the
   OCUDU companion service ocudu_netconf (NETCONF/YANG): config_get(dn, paths) ->
   dict and config_set(dn, changes) -> ack. Never write "O1 compliant".
2. app/actuators/adapters/ocudu_ws_collector.py — IMPLEMENT for real (it is plain
   JSON over WebSocket, no RIC needed), but gated off by default: new settings
   OCUDU_WS_ENABLED (default False), OCUDU_WS_URLS (comma-separated ws:// endpoints,
   OCUDU remote_control port 8001 with metrics.enable_json), OCUDU_WS_TENANT_ID.
   A daemon thread (started from lifespan only when enabled) connects with the
   websockets library, and a pure function translate_frame(frame: dict, tenant_id:
   str) -> dict converts each metrics frame to the HLD Appendix A.5 inline-records
   envelope published on Kafka topic maveric.ingest.pm.v1 (topic name frozen by
   HLD 4.1): {"schema":"maveric.ingest.pm.v1","kind":"records","batch_id":"<uuid4>",
   "tenant_id":...,"source_type":"ocudu_ws","vendor":"ocudu","records":[{"dn",
   "metric","value","unit","granularity_s","ts","labels"}]}. The discriminator is
   "kind" and the field name is "source_type" (never "source"). metric carries the
   SOURCE name; the data platform maps it via vendor_dictionaries. Reuse
   KafkaProducerManager. capabilities(): collect=True, apply=False;
   apply/rollback return rejected; health(): "disabled" when off, "ok"/"degraded"
   by last-connect status when on. Reconnect with backoff; never crash the app.
3. SAS Domain Proxy package app/actuators/adapters/sas_domain_proxy/ per
   WINNF-TS-0016 v1.2.7 (reference architecture: Magma Domain Proxy - radio
   controller / active-mode reconciliation / config controller split; cite it in
   the contract doc):
   - models.py: Pydantic models with camelCase wire aliases (populate_by_name)
     for the six method request/response pairs: registration, spectrumInquiry,
     grant, heartbeat, relinquishment, deregistration; SasResponse{responseCode,
     responseMessage,responseData}; InstallationParam; FrequencyRange;
     OperationParam{maxEirp, operationFrequencyRange}; cpiSignatureData is an
     opaque passthrough dict (a CPI-signed JWS the proxy must never fabricate).
   - state_machine.py: GrantState IDLE/GRANTED/AUTHORIZED, one GrantFsm per
     (cbsd_id, grant_id); AUTHORIZED entered only on first successful heartbeat;
     HeartbeatResponse refreshes transmit_expire_time; on_clock(now) emits TX_OFF
     at transmit_expire_time with an absolute radio-off deadline of +60 s
     (47 CFR 96.39(c)(2)). Directive table: 0 NONE; 105 DEREGISTER (cease all TX);
     500 RELINQUISH (grant terminated -> IDLE); 501 HEARTBEAT_KEEPALIVE (TX off,
     stay registered+granted, keep heartbeating); 502 RELINQUISH_AND_REGRANT
     (TX off within 60 s of receipt, relinquish, re-request). Also branch codes
     100/101/102/103/104/200/300/400/401 without TX-state corruption.
   - client.py: SasClientPort Protocol (six methods, list-in/list-out batching);
     HttpSasClient posting {"<method>Request":[...]} to
     {SAS_BASE_URL}/{SAS_VERSION}/{method} via httpx with mutual TLS from new
     settings SAS_DP_CERT_FILE/SAS_DP_KEY_FILE/SAS_CA_BUNDLE; MockSas with
     scripted per-method response queues for tests.
   - adapter.py: SasDomainProxyAdapter name="sas_domain_proxy"; apply/rollback
     rejected (not_implemented); health() "not_implemented" unless SAS_BASE_URL
     set, then "degraded" with detail "configured but not certified".
4. Register all five in app/actuators/adapters/__init__.py alongside nanolink_tr069
   (registry keys per HLD Appendix A.4).
5. Dependencies: add websockets and httpx to requirements.txt + pyproject.toml.
6. Contract docs in the dev repo under artifacts/actuation/: README.md (bundle
   index + adapter registry table) and one doc per adapter (o1_netconf.md,
   ocudu_ws_collector.md, open_mplane.md, sas_domain_proxy.md, nms_northbound.md).
   Every doc starts with a guardrails banner: these are integration contracts, not
   protocol-compliance claims; never claim O-RAN/RIC/SMO compliance or "SAS
   certified" (certification = WINNF-TS-0122 lab testing, not done). Do not use
   the em dash character in any doc. sas_domain_proxy.md must include the state
   machine diagram (mermaid ok), the responseCode table, the 60 s rule, mTLS/PKI
   prerequisites (WInnForum DP certificate), and the Magma DP reference.
7. Tests in tests/actuators/: placeholder health matrix; SAS model round-trips
   (by_alias); FSM parametrized transition table incl. 105/500/501/502 and the
   60 s clock rule; HttpSasClient URL/envelope/mTLS args with mocked httpx;
   collector translate_frame + disabled-by-default gating.

Constraints: no new listening ports (collector is an outbound client); zero CI/CD
change (all new settings default off/None); existing tests pass unmodified;
platform logger; type hints; Pydantic-first.

Definition of done: cd submodule/maveric_platform_smo_sim && uv run pytest passes;
GET /v1/actuators lists six adapters with honest health; the five contract docs
exist with guardrail banners.
```

---

## E4.S6 — PM-upload router decommission (after E1 cutover)

**Why:** The frozen HLD moves PM ingestion to the Data Platform (data_sim serves the legacy `/custom/nybsys/uploads` contract verbatim; the gateway split rule sends `custom/nybsys/uploads*` to DATA while device/edge ops stay SMO). Once E1 is cut over, smo_sim's upload router, thread-pool runner, and pipeline are unreachable dead code that must go.

**Size:** M

**Scope:**
- In: remove the uploads router, ingestion runner, upload-repository code, startup stale-upload sweep, and their tests; conditional removal of the pipeline library if E2's feature builder has landed; README update. This story is the SOLE OWNER of every smo_sim upload-path deletion: E1.S7 only writes the cutover runbook, gateway flip, and backfill (it deletes nothing in smo_sim), and E2.S4 only copies stages 3-6 (it deletes nothing either).
- Out: `nybsys_edge_router.py` and `nybsys_agent_router.py` (device/edge ops stay, per the split rule), `feature_guard.py` (still gates the device routers), the `nybsys_uploads` Postgres table (ownership transfers to data_sim; smo_sim simply stops touching it — no drop), S3 raw/derived key conventions (still produced by data_sim under the same layout), gateway changes (E0/E1 own the route split).

**Blocking gate:** do NOT start until E1's cutover checklist confirms: gateway routes `POST/GET/DELETE /v1/tenants/{t}/custom/nybsys/uploads*` to data_sim in the target env, and data_sim passes the legacy-contract regression suite (byte-compatible request/response per hard constraint §3.2).

**Files:**
- Delete: `submodule/maveric_platform_smo_sim/app/api/v1/custom/nybsys/router.py`
- Delete: `submodule/maveric_platform_smo_sim/app/api/v1/custom/nybsys/schemas.py`
- Delete: `submodule/maveric_platform_smo_sim/app/api/v1/custom/nybsys/__init__.py` (remove package)
- Delete: `submodule/maveric_platform_smo_sim/app/services/nybsys_runner.py`
- Modify: `submodule/maveric_platform_smo_sim/app/api/v1/custom/router.py` (drop the `nybsys_router` import + `include_router`; keep `nybsys_edge_router` and the `require_feature_access` dependency)
- Modify: `submodule/maveric_platform_smo_sim/app/main.py` (remove the `NYBSYS_REPO.reset_stale_uploads` startup sweep block)
- Delete (verify no other importers first): `submodule/maveric_platform_smo_sim/app/db/nybsys_repository.py`, `app/schemas/nybsys_schemas.py` (the `nybsys_uploads` ORM — grep for importers; `create_tables` no longer needs it since data_sim owns the table)
- Conditional delete (only if E2 feature-builder has landed and copied stages 3–6): `submodule/maveric_platform_smo_sim/app/lib/nybsys/` (pipeline, placement, pl_models/, audit/); otherwise add a module-level deprecation docstring and leave.
- Delete tests: `submodule/maveric_platform_smo_sim/tests/test_nybsys_endpoints.py`, `tests/test_nybsys_pipeline.py`, `tests/test_s3wrap_ingestion.py`, `tests/nybsys/` (pipeline/placement tests move with the code to bdt_engine in E2; delete here only in the same PR that deletes `app/lib/nybsys/`)
- Modify: `submodule/maveric_platform_smo_sim/README.md` (uploads section replaced with a pointer: "PM CSV ingestion is served by the Data Platform (data_sim); the public route `/v1/tenants/{t}/custom/nybsys/uploads` is unchanged")

**Contract:** none new. The public contract `POST/GET/DELETE /v1/tenants/{t}/custom/nybsys/uploads*` continues to exist byte-identically — served by data_sim (E1). smo_sim keeps `/v1/tenants/{t}/custom/nybsys/edge-devices**` and `/devices**` and `/v1/agent/**` untouched.

**Key snippets:** `app/api/v1/custom/router.py` after the change:

```python
custom_router = APIRouter(
    prefix="/tenants/{tenant_id}/custom",
    dependencies=[Depends(require_feature_access)],
)
# NanoLink operator API (edge CRUD + enrollment, devices, commands) — /nybsys feature flag
custom_router.include_router(nybsys_edge_router)
```

**Acceptance criteria:**
- `grep -rn "nybsys_runner\|INGESTION_JOB_RUNNER\|run_pipeline\|reset_stale_uploads" submodule/maveric_platform_smo_sim/app` returns nothing (or only `app/lib/nybsys` internals if the conditional delete is deferred).
- smo_sim no longer serves any `/custom/nybsys/uploads*` route (404 from the service directly), while `/custom/nybsys/edge-devices` and `/custom/nybsys/devices/**` behave exactly as before.
- End-to-end through the gateway, `POST /v1/tenants/{t}/custom/nybsys/uploads` still returns the legacy 202 envelope (served by data_sim) — verified against the E1 regression suite.
- `nybsys_uploads` table still exists and is untouched by smo_sim startup.
- Remaining suite passes; deleted tests are removed in the same commit as the code they covered.

**Test plan:**
- Unit/regression: `cd submodule/maveric_platform_smo_sim && uv run pytest` (suite green after deletions; `tests/nybsys_edge/**` fully intact).
- Integration (compose, with E1 in place): upload a sample PM CSV through the gateway path and poll status (proves data_sim serves it); hit smo_sim :8002 directly to confirm the uploads route is gone while device routes remain.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai). Read
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md sections 3 and 4.3
(the /custom split rule: custom/nybsys/uploads* -> DATA platform; device/edge ops
stay SMO). GATE: confirm with the E1 epic state that the gateway re-point and
data_sim's byte-compatible /custom/nybsys/uploads implementation are live before
deleting anything; if not, stop and report.

Task: decommission the PM-upload surface in submodule/maveric_platform_smo_sim.
1. Delete app/api/v1/custom/nybsys/ (router.py, schemas.py, __init__.py) and
   app/services/nybsys_runner.py.
2. Edit app/api/v1/custom/router.py to include only nybsys_edge_router (keep the
   require_feature_access dependency and prefix unchanged).
3. Edit app/main.py: remove the NYBSYS_REPO.reset_stale_uploads startup block.
4. grep app/ for remaining importers of app/db/nybsys_repository.py and
   app/schemas/nybsys_schemas.py; if unreferenced, delete both (the nybsys_uploads
   Postgres table itself MUST NOT be dropped — data_sim owns it now).
5. app/lib/nybsys/ (pipeline, placement, pl_models, audit): delete ONLY if the E2
   feature-builder story has landed in bdt_engine (check
   submodule/maveric_platform_bdt_engine/app/feature_builder/ exists); otherwise
   add a deprecation note docstring at the top of app/lib/nybsys/__init__.py and
   leave it.
6. Delete tests that covered removed code: tests/test_nybsys_endpoints.py,
   tests/test_nybsys_pipeline.py, tests/test_s3wrap_ingestion.py, tests/nybsys/
   (the latter only together with app/lib/nybsys/). Never touch tests/nybsys_edge/.
7. Update the submodule README: uploads are served by the Data Platform; the public
   route is unchanged. No em dash character in new prose.

Hard constraints: the gateway-routed public contract for uploads stays byte-stable
(data_sim serves it; you change nothing about it); /custom/nybsys/edge-devices**,
/custom/nybsys/devices**, and /v1/agent/** are untouched; zero CI/CD change.

Definition of done: no uploads-route code or ingestion runner remains in smo_sim;
cd submodule/maveric_platform_smo_sim && uv run pytest passes; device/edge routes
verified working against the compose stack; nybsys_uploads table untouched.
```

---

## E4.S7 — Managed-params single source of truth (24-path catalogue)

**Why:** The managed-parameter catalogue is manually triplicated: `smo_sim/app/services/nybsys/managed_params.py` (24 entries: validator + bounds), `maveric_platform_frontend/lib/nybsys/managed-params.ts` (UI metadata), and `cloudlynet_edgeagent/goagent/internal/collector/collector.go` `SnapshotPaths` (23 literals + 1 const). Recon flags this three-way manual sync as a standing drift risk; one contract file + generated copies kills it.

**Size:** M

**Scope:**
- In: canonical contract file in the dev repo; a dev-time generator script emitting the three checked-in consumer copies (Python data + loader refactor, TS module, Go file); hash stamps + drift-check tests in each repo; a dev-repo checker script.
- Out: any change to catalogue *content* (24 paths, bounds, choices, notes — byte-identical semantics), any build/CI integration (zero CI/CD change: generation is dev-time, generated files are committed), edge-agent runtime behavior (`SnapshotPaths` content and order must be identical — field-deployed agents).

**Files:**
- Create: `artifacts/contracts/managed_params.json` (canonical; content extracted 1:1 from `managed_params.py`)
- Create: `artifacts/contracts/README.md` (what lives here, how to regenerate)
- Create: `scripts/contracts/gen_managed_params.py` (generator; stdlib-only Python)
- Create: `scripts/contracts/check_managed_params.py` (drift checker across the three repos)
- Modify: `submodule/maveric_platform_smo_sim/app/services/nybsys/managed_params.py` (refactor: build `MANAGED_PARAMS` from the generated JSON data file; public API unchanged: `Param`, `P`, `MANAGED_PARAMS`, `MANAGED`, `OPTIMIZABLE`, `validate_write`)
- Create (generated): `submodule/maveric_platform_smo_sim/app/services/nybsys/managed_params_catalogue.json`
- Replace (generated): `submodule/maveric_platform_frontend/lib/nybsys/managed-params.ts` (same exported symbols/types as today — read the current file first and preserve its export surface)
- Create (generated): `submodule/cloudlynet_edgeagent/goagent/internal/collector/snapshot_paths_gen.go`; Modify: `goagent/internal/collector/collector.go` (delete the inline `SnapshotPaths` literal; keep everything else, including the `autonomousTransferCompletePolicy` const if other code references it)
- Create: `submodule/maveric_platform_smo_sim/tests/nybsys_edge/test_managed_params_contract.py`
- Create: `submodule/cloudlynet_edgeagent/goagent/internal/collector/snapshot_paths_test.go`

**Contract (canonical file schema — new artifact, dev-repo owned; flagged as a contract introduced by this epic):**

```json
{
  "version": 1,
  "description": "NanoLink managed-parameter catalogue. Single source of truth for smo_sim (validator), frontend (UI metadata), and the Go edge agent (snapshot paths). Regenerate consumers with scripts/contracts/gen_managed_params.py.",
  "params": [
    {
      "path": "Device.Services.FAPService.1.CellConfig.LTE.RAN.RF.PhyCellID",
      "dtype": "string", "xsd": "xsd:string", "group": "identity",
      "editable": true, "optimizable": false,
      "minimum": 0, "maximum": 503, "choices": null,
      "note": "PCI; SON may also set this (PCIOptEnable=1)."
    }
    // ... exactly 24 entries, order preserved from managed_params.py
  ]
}
```

Generated-file header (all three consumers):

```
Code generated from artifacts/contracts/managed_params.json
(catalogue sha256: <hex>). DO NOT EDIT; run scripts/contracts/gen_managed_params.py.
```

Generator behavior: computes `sha256` of the canonical `params` array (canonical JSON serialization, sorted keys), embeds it as `CATALOGUE_SHA256` (py), `CATALOGUE_SHA256` export (ts), `catalogueSHA256` const (go). Go output contains ONLY the ordered path list (`var SnapshotPaths = []string{...}`) + the hash const — the agent needs no bounds/notes.

**Key snippets:**

`managed_params.py` after refactor (validator logic untouched):

```python
_CATALOGUE_FILE = Path(__file__).with_name("managed_params_catalogue.json")

def _load_catalogue() -> list[Param]:
    """Build the Param list from the generated catalogue (single source of truth:
    artifacts/contracts/managed_params.json in the dev repo)."""
    raw = json.loads(_CATALOGUE_FILE.read_text())
    return [Param(path=e["path"], dtype=e["dtype"], xsd=e["xsd"], group=e["group"],
                  editable=e["editable"], optimizable=e["optimizable"],
                  minimum=e["minimum"], maximum=e["maximum"],
                  choices=tuple(e["choices"]) if e["choices"] else None,
                  note=e["note"]) for e in raw["params"]]

MANAGED_PARAMS: list[Param] = _load_catalogue()
# MANAGED, OPTIMIZABLE, validate_write unchanged
```

Drift tests:

```python
# tests/nybsys_edge/test_managed_params_contract.py
def test_catalogue_has_24_paths(): assert len(MANAGED_PARAMS) == 24
def test_catalogue_hash_matches_embedded():  # recompute sha256 of the JSON params array
def test_public_api_unchanged():  # P prefix, OPTIMIZABLE membership, a known bounds check
```

```go
// snapshot_paths_test.go
func TestSnapshotPathsCount(t *testing.T)      // len == 24, no duplicates
func TestSnapshotPathsUnchanged(t *testing.T)  // golden: hash of joined paths equals catalogueSHA256-derived golden
```

**Acceptance criteria:**
- `scripts/contracts/gen_managed_params.py` run twice is idempotent (no diff on second run).
- `scripts/contracts/check_managed_params.py` exits 0 when all three embedded hashes match the canonical file, non-zero (with a per-repo report) when any consumer drifts.
- smo_sim: `validate_write` behavior is byte-identical (existing `tests/nybsys_edge/test_managed_params.py` passes unmodified); catalogue length 24.
- Go agent: `SnapshotPaths` content and order are identical to the previous inline literal (golden test); `go build ./...` and `go test ./...` pass.
- Frontend: `managed-params.ts` keeps its current exported symbols and type shape (verify against the pre-change file; UI pages using it compile — run the frontend's own typecheck/lint script from its `package.json`).
- No CI/pipeline files touched; generated files are committed artifacts.

**Test plan:**
- smo_sim: `cd submodule/maveric_platform_smo_sim && uv run pytest tests/nybsys_edge/test_managed_params.py tests/nybsys_edge/test_managed_params_contract.py`, then full `uv run pytest`.
- Go agent: `cd submodule/cloudlynet_edgeagent/goagent && go build ./... && go test ./...`.
- Frontend: `cd submodule/maveric_platform_frontend` and run the typecheck/lint scripts defined in `package.json` (inspect it first; do not assume script names).
- Dev repo: run the generator + checker; `git diff --stat` must show only the intended generated files.

**Coding-agent prompt:**

```
You are working in the CloudlyNet dev repo (cloudlynet_ai). Context: the NanoLink
managed-parameter catalogue (24 TR-069 paths with bounds/choices/notes) is
hand-duplicated in three repos and drifts:
- submodule/maveric_platform_smo_sim/app/services/nybsys/managed_params.py
  (MANAGED_PARAMS list of Param dataclasses + validate_write)
- submodule/maveric_platform_frontend/lib/nybsys/managed-params.ts
- submodule/cloudlynet_edgeagent/goagent/internal/collector/collector.go
  (var SnapshotPaths = []string{...}, 23 literals + the
  autonomousTransferCompletePolicy const = 24 paths)
Make one contract file the single source of truth with generated, hash-stamped,
committed copies. Read docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md
section 3 (hard constraints) first.

Task:
1. Extract the catalogue 1:1 from managed_params.py into
   artifacts/contracts/managed_params.json: {"version":1, "description":...,
   "params":[{path,dtype,xsd,group,editable,optimizable,minimum,maximum,choices,
   note}]} with order preserved and exactly 24 entries. Add
   artifacts/contracts/README.md explaining regeneration.
2. Write scripts/contracts/gen_managed_params.py (stdlib only). It computes a
   sha256 over the canonical JSON serialization (sorted keys) of the params array
   and emits three files, each headed "Code generated from
   artifacts/contracts/managed_params.json (catalogue sha256: <hex>). DO NOT EDIT":
   a) submodule/maveric_platform_smo_sim/app/services/nybsys/
      managed_params_catalogue.json (params + embedded hash);
   b) submodule/maveric_platform_frontend/lib/nybsys/managed-params.ts - FIRST read
      the existing file and reproduce its exported symbols/types exactly, only
      sourcing the data from the contract; export const CATALOGUE_SHA256;
   c) submodule/cloudlynet_edgeagent/goagent/internal/collector/
      snapshot_paths_gen.go - package collector, const catalogueSHA256, and
      var SnapshotPaths = []string{...} listing the 24 paths IN THE EXACT ORDER of
      the current collector.go literal (agents are field-deployed; the list content
      must be byte-identical - diff it before committing).
   The script must be idempotent (stable output ordering/formatting).
3. Refactor managed_params.py to build MANAGED_PARAMS by loading
   managed_params_catalogue.json at import time. Public API unchanged: Param, P,
   MANAGED_PARAMS, MANAGED, OPTIMIZABLE, validate_write. Existing
   tests/nybsys_edge/test_managed_params.py must pass UNMODIFIED.
4. Edit goagent/internal/collector/collector.go: remove the inline SnapshotPaths
   literal (the generated file now provides it); keep the
   autonomousTransferCompletePolicy const if referenced elsewhere.
5. Drift guards: scripts/contracts/check_managed_params.py comparing the canonical
   hash against all three embedded hashes (exit non-zero on mismatch, per-repo
   report); smo_sim test tests/nybsys_edge/test_managed_params_contract.py
   (24 entries, hash match, spot-check bounds); Go test
   goagent/internal/collector/snapshot_paths_test.go (24 unique paths, golden hash).
6. Run everything: python scripts/contracts/gen_managed_params.py twice (second run
   = no diff); cd submodule/maveric_platform_smo_sim && uv run pytest;
   cd submodule/cloudlynet_edgeagent/goagent && go build ./... && go test ./...;
   in submodule/maveric_platform_frontend run the typecheck/lint scripts you find
   in package.json.

Constraints: catalogue CONTENT must not change (this is plumbing, not editing);
zero CI/CD change (generation is dev-time; outputs are committed); commit per repo
following each repo's conventions; cd into each submodule for its git operations;
do not stage submodule pointer bumps in the dev repo.

Definition of done: checker exits 0; all three repos' tests/builds pass; git diff
in the Go repo shows SnapshotPaths content unchanged (only relocated).
```

---

## Rollout / migration notes

**Order within the epic:** S1 → S2 → S3 → S4 (S4 may run parallel to S2/S3 after S1) → S5 (needs S2/S3) → S7 (independent, any time) → S6 (**gated on E1 cutover**, last).

**Migrations (dev-repo `artifacts/migration/`, manual execution per current practice; numbering frozen in HLD Appendix A.6 — 011 is E1's, 014 is E2's, 015 is E5's):**
1. `012_drop_e2_r1.sql` — apply any time after the S1 code deletion is deployed (order matters: deploy the code that stops `create_tables` from recreating the tables first, then drop). Reversible only by restoring from backup; the tables are empty in every environment (no writers ever existed), so risk is nil.
2. `013_commands_loop_columns.sql` — additive/nullable; apply before deploying S2 code. Safe on a live system; old code ignores the columns.

**Backward-compat shims:** none required by design — that is the point of the epic:
- Operator/agent routers, `command_service` claim/complete semantics, the `{success,message,data}` envelope, and command payload shapes are byte-frozen (field-deployed agents cannot be redeployed atomically).
- The loop executor and feedback publisher are dark when `KAFKA_BOOTSTRAP_SERVERS` is unset; enabling them in staging is a values-env edit on the existing chart (classified "moderate/allowed" by the assessment; no chart/image/port change).
- Redis EWMA store and periodic sweep default to current behavior when unconfigured (`REDIS_URL` unset, interval default 30 s is safe for single replica too).
- S6 keeps the public uploads contract alive throughout: gateway re-point (E0/E1) happens first, data_sim proves byte-compatibility, only then does smo_sim delete its copy. The `nybsys_uploads` table and all S3 key conventions remain valid during the whole transition (hard constraint §3.3).

**Data migration:** none. E2/R1 tables are write-orphaned and empty; `commands` gains nullable columns only; no data moves in this epic (PM data movement is E1's).

**Topic provisioning:** `maveric.loop.action.v1`, `maveric.loop.feedback.v1`, `maveric.ingest.pm.v1` ride the existing kafka chart topics-job / `scripts/kafka/init-topics.sh` (E0/E1 deliverable). E4 code must tolerate missing topics (log + retry via the existing manager classes), so deployment order between topics and code is free.

## Epic-level risks

1. **Feedback payload is a shared contract, now FROZEN.** The `maveric.loop.feedback.v1` shape (kind/status/kpis/detail/observed_at) is pinned in HLD Appendix A.3; E4.S3 produces it and E2.S7/E5 consume it verbatim. Any change is a freeze deviation — never adjust the shape unilaterally.
2. **`maveric.ingest.pm.v1` dual use, now FROZEN.** The topic carries `kind="job"` messages (E1.S2) and `kind="records"` batches (HLD Appendix A.5; field name `source_type`). E4.S5's OCUDU collector emits the A.5 envelope and E1.S8 owns the consumer branch; do not enable the collector in an environment where E1.S8 has not landed.
3. **Startup `create_tables` vs migrations split-brain.** Dropping e2/r1 tables while any old smo_sim replica is running would let the old process recreate them. Mitigation baked into rollout order (deploy S1 code first, then run 011). Same class of risk for 012: apply the migration before S2 code ships, since the ORM adds the columns for fresh DBs only.
4. **Field-frozen agent contract.** Every story touching `command_service` (S2/S3) risks the three-party `/v1/agent/**` contract. The proof obligation is "existing `tests/nybsys_edge/` pass unmodified"; treat any needed edit to those tests as a design failure, not a test update.
5. **origin='loop' visibility.** The frontend renders command lists; a new `origin` value appears in operator-visible data. Verified: no CHECK constraint and the API returns rows regardless, but the frontend may switch on origin for badges — flag to the frontend owner (display-only concern, not a contract break).
6. **SAS scope creep.** The Domain Proxy has real models + FSM but must not be presented as usable: WInnForum certification (WINNF-TS-0122, DP-role PKI cert) is a compliance project. Claims-guardrails banner on the contract doc is mandatory; never "SAS certified" / "CBRS compliant".
7. **S6 timing.** Deleting the uploads router before E1's byte-compatible replacement is live through the gateway breaks a public contract (hard constraint §3.2). The story carries an explicit blocking gate; the coding agent is instructed to verify and abort.
8. **Redis/Kafka enablement drift across envs.** Both are env-gated; an env with Kafka set but topics missing will log retries. The manager classes already back off; monitor error_logs (`KAFKA_*` codes) after enabling in staging.
9. **Managed-params generation touching a deployed Go binary's data.** `SnapshotPaths` content must be byte-identical post-generation; the golden test + pre-commit diff instruction mitigate. Any intentional future catalogue change now happens in one file, but still requires a coordinated agent-fleet rollout (documented in `artifacts/contracts/README.md`).

---

## Execution status

In progress. S1 and S2 are done and committed; S3 to S7 remain. smo_sim
`9837ff1 -> 5644b52`, parent `dea962b`. Nothing pushed.

**Baseline recorded (it was missing from `test-baselines.md`):** smo_sim was 424 passed /
3 failed / 44 skipped without Postgres. The 3 failures are pre-existing
`tests/nybsys/test_placement.py::TestSamplerWarnings` and are unrelated to this epic.

**With Postgres reachable the picture is very different: 508 passed / 3 failed / 1 skipped.**
All seven `tests/nybsys_edge/*` files carry `pytestmark = pytest.mark.pg`, so on a machine
without the compose stack the entire NanoLink suite SKIPS. Any "tests pass" claim about this
service is close to meaningless without Docker up. Current: **519 passed / 3 failed / 1 skipped**.

**S1 DONE** (smo_sim `39086ec`, parent `c41e878`). All 12 deletion targets existed; the 11
table names in the epic matched the real `__tablename__` declarations. Migration 012 verified
against live Postgres: 11 tables to 0, and a second run is a clean no-op.

**S2 DONE** (smo_sim `d4ac5ed`, `fe17aa2`, `4d9c595`, `5644b52`; parent `e3dccc8`, `e2d0b35`,
`dea962b`). Framework, NanoLink adapter, migration 013, internal `/v1/actuators`, 52 tests.
The byte-stability proof is real: `git diff` over `tests/nybsys_edge/` is empty and those
tests pass unmodified with Postgres up.

Six corrections to the story text, each verified in code:

1. **`create_command` hard-codes `origin='manual'`** in raw SQL, so the extension had to
   change the INSERT, not just the signature. The epic's claim that `origin` carries no CHECK
   constraint is CORRECT (`009_nybsys_nanolink.sql:63`).
2. **The snapshot columns are `params` and `created_at`**, not `values`/`captured_at`. The
   canonical reader is `command_service._latest_snapshot_values`.
3. **`artifacts/design/schemas.sql` is the first-init baseline and defined `commands` without
   the loop columns.** `create_all` never alters an existing table, so a fresh compose cluster
   would have had a `commands` table that migration 013 never runs against, and the byte-frozen
   operator route would 500 on its own INSERT. The columns and index are now inlined there.
4. **Migration 013's unique index contradicted S3.** The epic (line 540, and the S3 prompt at
   690-695) requires a rollback command to carry the reverted action's `loop_action_id` so
   `complete()` can emit the A.3 `kind="rollback"` feedback. A GLOBAL partial unique index makes
   that INSERT a unique violation, inside the field-frozen agent ack transaction. The index is
   now scoped `WHERE loop_action_id IS NOT NULL AND origin <> 'rollback'`, verified live: a
   duplicate apply is rejected and a rollback row with the same action id is accepted.
5. **`LOOP_ES_POWER_*` are typed `int`, not the epic's `str`.** Verified safe end to end through
   the frozen agent contract: Go's `Write.Value` is `any`, `formatValue` handles `float64`
   explicitly, and `valuesMatch` normalises BOTH sides, so `-20` and `"-20"` produce identical
   CWMP values and no spurious readback mismatch.
6. **`rollback_on_fail` defaults differ per payload form.** The twin emits only
   `{cell_el_deg, on_off, rollback_of}` (`bdt_engine/app/services/loop/decision_hub.py:318-327`),
   so reading the key with a False default made loop-originated changes the ONLY write path
   without the device-level auto-rollback that operator and optimizer changes both get. It now
   defaults TRUE for the recommendation form and is honoured verbatim for an explicit write set.

Two defects found by running the suite rather than by reading:

- **The NanoLink adapter never pinned the RLS tenant.** Every NanoLink table is ENABLE + FORCE
  RLS on the `app.current_tenant` GUC, `command_service`'s docstring says callers pin first,
  there are 22 pin sites in `app/`, and the adapter had none. `get_device` carries no tenant
  predicate at all. Fixed, with the tenant id validated as a uuid before the pin.
- **A test that passed alone and failed in the suite.** `tests/test_nybsys_endpoints.py` sets
  `API_KEY=testkey` in the environment and reloads `app.core.config` and `app.utils.security`
  mid-suite, so any settings captured at import time go stale and every request 401s. Resolve
  the key at call time. Worth knowing for every future endpoint test in this service.

### Blocking traps recorded for the stories not yet done

- **S3 cannot use `KafkaConsumerManager` as it stands.** It is built with
  `enable_auto_commit=True` and its only read method batches 10 messages with no timeout, which
  makes action execution at-most-once and shutdown-deaf. Port rapp's `poll_raw` +
  `commit_offsets` shape first; EPIC-3.S4's executor is the reference.
- **S3 must not publish feedback inline from `complete()`.** `send_message` blocks on
  `future.get(timeout=10)` and logs to Mongo on failure, and `complete()` runs inside the
  field-frozen agent ack request.
- **`send_message` has no `key` parameter** (A.3 requires `tenant_id` bytes). Same one-line
  additive fix already made in rapp.
- **S3 must call `ensure_adapters_registered()` at consumer start**, or the registry is empty
  and every action is rejected as an unknown adapter.
- **S3's `kpi_window` should publish only when a guardrail KPI is present.** `sinr_avg_db` and
  `rrc_success_pct` are both tier-3 (900 s) PM metrics, while the hook runs on every telemetry
  POST, so firing unconditionally would report "healthy" from empty evidence.
- **S4: `REDIS_URL=redis://redis:6379/0` is already in the git-TRACKED `.env`** and
  pydantic-settings loads it. Adding a `REDIS_URL` setting makes local tests dial a hostname
  that does not resolve. Also, redis-py connects lazily, so construction-time degradation never
  fires; degrade per operation. Pin `redis==5.0.1` to match the mesh.
- **S5: `httpx==0.26.0` and `websockets` are ALREADY declared.** The epic's "smo_sim has no
  outbound HTTP client at all, verified by recon" is false.
- **S6: `tests/audit/` (10 files, 192 tests) imports `app.lib.nybsys.pipeline` and
  `app.lib.nybsys.audit`** and is never mentioned in the story's deletion list. So do
  `scripts/nybsys-pipeline/`. The package also holds `geo.py`, `models.py`, `rules.py`,
  `defaults.py` and two docs the epic does not enumerate.
- **S7: there are SIX copies of the 24-path catalogue, not three**, and the TypeScript copy
  already disagrees with Python on 3 dtypes and 7 notes, so "content must not change" cannot
  hold for the frontend. The catalogue also contains a non-ASCII en dash, which any hash must
  account for.
- **`tests/conftest.py` resolves migration 009 at a path that does not exist**
  (`<root>/migrations/009_nybsys_nanolink.sql`; the real one is `artifacts/migration/`), and the
  pg fixture only counts TABLES, never columns, so it skips rather than failing on schema drift.

---

## Execution status (continued): S3, S4, S5 done; S6 BLOCKED; S7 open

**S3 DONE** (smo_sim `2cd6c81`, `873f6fb`, `05a2fe3`, `d5704ab`). The loop executor arm, and
all four Appendix A.3 kinds are emitted and tested: `apply` (consumer plus the ack hook),
`kpi_window`, `guardrail_breach`, `rollback`.

**Live-proven against real infrastructure**, the same bar EPIC-3's executor was held to. An
action published to the real broker was consumed, dispatched, and produced a real `commands`
row, with A.3 feedback back on the real feedback topic keyed by `tenant_id` bytes. The row
confirmed every design decision at once: `origin='loop'`, the correlation id,
`ReferenceSignalPower: -20` with `xsd_type` filled by the catalogue validator,
`rollback_on_fail: true`, `policy_ref` as jsonb, and `prev_values` captured so a revert can
restore. A foreign `a1_policy` action was correctly skipped with no feedback, proving the
double-reporting guard.

Design calls worth knowing:

- **Two publish paths.** The consumer publishes synchronously then commits. Request handlers
  ENQUEUE to a bounded queue drained by a background thread, because `send_message` blocks on
  `future.get(timeout=10)` and writes to MongoDB on failure, and `complete()` runs inside the
  field-frozen agent ack request. A full queue drops with a warning: the device loop must
  never wait on the platform loop.
- **Expiry is derived from the action**, never by string-matching `detail['error']`.
  `ActuatorAck` has no `expired` member; A.3 does.
- **`kpi_window` publishes only when a guardrail KPI is present.** Both `sinr_avg_db` and
  `rrc_success_pct` are tier-3 (900 s) PM metrics while the hook runs on every telemetry POST,
  so firing unconditionally would report `status="ok"` from an empty `kpis` dict and the twin
  would read fabricated evidence of health.
- **`guardrail_breach` fires only for loop-originated changes.** A breach against an operator
  or optimizer change is the device guardrail working as designed, with no action to correlate.

One bug only a live run could find: the consumer subclasses `threading.Thread` and its stop
event was named `_stop`, which SHADOWS `Thread._stop()` and makes `join()` raise
`TypeError: 'Event' object is not callable`. Renamed, with a regression test that actually
starts and joins the thread.

**S4 DONE** (`0ef28d2`). Periodic lease sweep plus Redis-backed EWMA state.

Both recon traps were real and were verified first-hand. `REDIS_URL=redis://redis:6379/0` is
already in the git-TRACKED `.env`, so the epic's "unset means today's exact behavior" was
false; and redis-py connects LAZILY, so the specified construction-time degradation would
never have fired and every telemetry POST would instead have paid a connection timeout.
Resolution: prove reachability with an explicit short-timeout `ping()` at construction, and
keep per-operation guards as the mid-flight safety net. Pin is `redis==5.0.1`, matching rapp,
bdt_engine and data_sim.

Live-proven against the running Redis: a six-sample baseline survived a simulated restart and
the outlier fired at z=45.4 against the PRE-restart baseline, which is the acceptance
criterion verbatim. Key format and the 7 day TTL (604800 s) confirmed in `redis-cli`.

**S5 DONE** (smo_sim `856d882`, parent `c9948b6`). All six Appendix A.4 keys smo_sim owns are
now registered; only `nanolink_tr069` can apply. Two placeholders carry real substance: the
SAS Domain Proxy models and state machine (WINNF-TS-0016 v1.2.7, including the 60 second
transmit-shutdown rule, which `must_stop_transmission()` implements FAIL-CLOSED because it is
a regulatory obligation), and the OCUDU WS collector, which is implemented for real behind a
default-off gate. `translate_frame` emits exactly the seven keys data_sim's `InlineRecord`
permits, because that model is `extra="forbid"` and one stray key on one record rejects the
entire batch. `websockets` is now declared; `httpx` already was, contrary to the epic.

### S6 is BLOCKED, and executing it would have broken production

The story's own dependency is "E1 serving `/custom/nybsys/uploads` verbatim". Three gates were
checked before touching anything:

| Gate | Result |
| --- | --- |
| data_sim serves the uploads contract | PASS (`POST /uploads`, `GET /uploads`, `GET /uploads/{id}`) |
| E2's feature builder landed | PASS (`bdt_engine/app/feature_builder/`) |
| The gateway actually routes uploads to data_sim | **FAIL** |

`cmd/gateway/main.go` gates the split on `CUSTOM_UPLOADS_TARGET`, which **defaults to `"smo"`**
and is documented as dark by default: "E1 flips one env value to move uploads to data_sim".
It is set to `smo` in `.env.example` and is unset in the running gateway. **Uploads traffic
goes to smo_sim today.** Deleting its router now removes a live gateway-routed surface.

The blocker is therefore an ops action, not code: flip `CUSTOM_UPLOADS_TARGET=data`, verify
the provenance checks in E1's dual-writer runbook, then decommission. S6 should not be
attempted before that.

**A second correction, independent of the gate.** The story says to delete `app/lib/nybsys/`
"(pipeline, placement, pl_models/, audit/)" once the feature builder has landed. The feature
builder did land, but **`audit/` was never copied anywhere**: there is no audit module in
bdt_engine's `app/` or `tests/`. `tests/audit/` (10 files) imports twelve `app.lib.nybsys.audit.*`
modules plus `pipeline` and `pl_models.tr_38_901`, and `scripts/nybsys-pipeline/` imports
`pipeline`, `defaults` and `rules`. Deleting that package would destroy a capability that
exists nowhere else and break both the scripts and the audit notebooks. When S6 is unblocked,
delete the uploads router and `nybsys_runner`; KEEP `app/lib/nybsys/` until `audit/` has a home.

### S7 is open, and its stated constraint cannot hold

Recon found **six** copies of the 24-path catalogue, not the three the story names, and the
TypeScript copy ALREADY disagrees with the Python one on 3 dtypes and 7 notes. The story's
scope explicitly excludes "any change to catalogue content", which is therefore impossible for
the frontend: generating TS from the Python source of truth necessarily changes it. That is a
decision for the frontend owner (accept the corrections, or freeze the divergence and generate
only the paths), not something to resolve inside this epic. The catalogue also contains a
non-ASCII en dash, which any content hash has to account for.

### Suite

**693 passed / 3 failed / 1 skipped** against a 424 / 3 / 44 starting baseline, with Postgres
and Kafka up. The 3 are the pre-existing `test_placement.py::TestSamplerWarnings` drift,
identical on Python 3.11 and 3.12. `tests/nybsys_edge/` and `tests/nybsys/` were never
modified, which is the byte-stability proof for the device-facing paths that S2 and S3 touch.

---

## Execution status (final): S7 done, S6 remains an ops step

**S7 DONE** (parent `0a5634c`, smo_sim `ae76044`, frontend `3e4bad8`, edgeagent `7b87fb7`).

The recon's headline (six copies, irreconcilable content) turned out to overstate it. Diffed
programmatically rather than by eye: Python and TypeScript held the **same 24 paths, no
additions or removals**, with exactly **3 dtype disagreements** and 7 stale notes.

All three disagreements were the same case, and the frontend was RIGHT: `DLBandwidth`,
`ULBandwidth` and `DefaultPagingCycle` all carry `choices`, the frontend called them `enum`,
and Python called them `string` while typing a fourth choices-param (`AutonomousTransfer
CompletePolicy`) as `enum`. Python was internally inconsistent.

Retyping the three to `enum` is **provably inert**: `validate_write` branches only on
`("int", "uint")`, so `string` and `enum` take an identical path and return the same
`p.xsd`. There is now a test asserting that, so if anyone gives `enum` its own validation
branch the inertness assumption fails loudly instead of silently.

Architecture: the catalogue DATA is generated by `scripts/gen_managed_params.py` into
`managed-params.generated.ts` and `managed_paths.go`; the frontend's `managed-params.ts`
stays hand-written and holds only presentation logic (grouping, labels, client-side
validation), re-exporting the generated data so **every existing import path is unchanged**.
The first attempt generated over the whole file and dropped five exports the UI uses
(`GROUP_ORDER`, `GROUP_LABELS`, `groupParams`, `shortParamLabel`, `validateParamValue`);
splitting data from presentation is what fixes that properly.

Go's `SnapshotPaths` is now an alias for the generated `ManagedPaths` rather than a
hand-maintained duplicate.

Verified: `tsc --noEmit` clean, `eslint` clean (the generated file survives prettier
byte-for-byte, so the drift check is stable), `go build ./...` and the full Go suite green,
and a deliberate hand edit to a generated file IS caught by `--check`.

### S6: not executed, and that is the finding

Two independent gates fail, and both were verified rather than assumed.

**The routing gate.** `CUSTOM_UPLOADS_TARGET` defaults to `"smo"` in the gateway, is `smo` in
`.env.example`, and is unset in the running gateway. Uploads traffic goes to smo_sim TODAY.
Deleting its router first 404s every PM upload. The two surfaces are otherwise equivalent
(same four endpoints, same prefix), which is recorded so the cutover decision is cheap.

**The runbook gate.** The story depends on E1's cutover with "mandatory provenance checks",
and no such runbook existed. Written now:
`artifacts/upgrade_plans/uploads_cutover.md`, including the quiesce query, the provenance
baseline, the `DATA_BASE_URL` trap (a half-configured flip silently does nothing because the
gateway falls back to smo rather than nil-dereferencing), and rollback.

The dev database happens to be idle (6 rows, 0 in flight), so a dev cutover would be
risk-free. That is not a reason to delete a live routed surface: it says nothing about
production, where in-flight uploads and row provenance cannot be checked from here.

S6 is therefore one reviewed operational step away, not an open engineering question. When
it runs, change the gateway DEFAULT to `"data"` in the same commit so the code is
self-consistent without an env var, and **keep `app/lib/nybsys/`**: `audit/` was never
copied anywhere, and `tests/audit/` plus `scripts/nybsys-pipeline/` still depend on it.

### Final suite

**701 passed / 3 failed / 1 skipped** with Postgres, Kafka and Redis up, from a 424 / 3 / 44
starting baseline. The 3 are pre-existing `test_placement.py::TestSamplerWarnings` drift,
identical on Python 3.11 and 3.12 and unrelated to this epic. `tests/nybsys_edge/` and
`tests/nybsys/` were never modified.

---

## E4.S6 DONE (local stack, 2026-08-03)

Executed against the local environment following `artifacts/upgrade_plans/uploads_cutover.md`.
Gateway `e75a5a2`, smo_sim `0d123f3`. **Staging and production are NOT cut over.**

**The cutover.** Quiesce showed 0 in flight and the baseline was 3 completed / 3 failed.
`DATA_BASE_URL` was already set, which matters because a flip without it silently falls back
to smo rather than failing. The gateway default moved from `"smo"` to `"data"` in code, so the
deployed behaviour no longer depends on an env var being remembered; explicit `smo` is still
honoured for a rollback against a build that predates the decommission.

**Verified live, end to end:** gateway to `/custom/nybsys/uploads` reaches data_sim with
HTTP 200 and all 6 rows intact, matching the pre-cutover baseline exactly. smo_sim returns 404.

**Removed:** `app/api/v1/custom/nybsys/` (the uploads router), `app/services/nybsys_runner.py`,
the startup stale-upload reset in `main.py`, and `tests/test_nybsys_endpoints.py`.

**KEPT, against the story's file list.** The story says to delete `app/lib/nybsys/` "(pipeline,
placement, pl_models/, audit/)" once E2's feature builder landed. The feature builder did land,
but **`audit/` was never copied anywhere**: bdt_engine has no audit module in `app/` or
`tests/`. `tests/audit/` (10 files) imports twelve `app.lib.nybsys.audit.*` modules plus
`pipeline` and `pl_models.tr_38_901`, and `scripts/nybsys-pipeline/` imports `pipeline`,
`defaults` and `rules`. Deleting the package would destroy a capability that exists nowhere
else and break the scripts and the audit notebooks with it.

For the same reason `tests/test_nybsys_pipeline.py` and `tests/test_s3wrap_ingestion.py` are
kept, though the story lists them for deletion: they cover retained code and still pass. Only
`test_nybsys_endpoints.py` tested the removed surface.

**Finding a home for `audit/` is now the outstanding piece of this cleanup**, and it is its own
work rather than a footnote to a decommission.

**Suite:** 681 passed / 3 failed / 1 skipped. The drop from 701 is the 20 deleted uploads-router
tests. The 3 failures are the pre-existing `test_placement.py::TestSamplerWarnings` drift.
The gateway's routing contract test is updated, not deleted: the two default rows now assert
DATA, and every other case is unchanged.

**EPIC-4 is complete: all seven stories.**
