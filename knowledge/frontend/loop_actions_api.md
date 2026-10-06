# Loop actions: approve/reject surface (contract note)

**Status: contract note only.** No frontend work is scheduled in EPIC-5. This exists so the
frontend team can plan against shapes that already exist in the backend rather than against a
sketch. Every endpoint and every field below is implemented and covered by tests today.

**Blocking dependency: the gateway does not expose `/ndt/**` yet.** That is an optional later story
in the frozen HLD section 4.2. Until it lands these endpoints are reachable only service to service,
on bdt_engine's own port with its internal `X-API-Key`, so the browser cannot call them. Nothing in
this note can be built end to end before that route exists. Plan the components; do not plan the
integration date.

## What this surface is for

CloudlyNet's closed loop has three policy modes per tenant. In **`approval`** mode, which is the
safe default a new customer starts on, an action that passed the Network Digital Twin's evaluation
does not go to the network. It parks as `pending_approval` and waits for a human. This surface is
that human's screen.

In `auto` mode nothing parks, and in `off` mode actions are recorded as `suppressed` and never
dispatched. Both still produce rows this surface lists; only `approval` produces cards to act on.

## Reuse: the recommendation-cards pattern

Map this one to one onto the NanoLink self-optimizer recommendation cards the devices dashboard
already renders (`POST /custom/nybsys/recommendations/{reco_id}:approve|:reject`, optimistic update
then poll). The interaction is identical: a list of proposed changes, approve or reject per card,
the card disappears from the pending tab once decided.

Three differences worth designing around:

1. **The source is the Network Digital Twin decision hub**, not a device-local optimizer. The card
   should say where the recommendation came from, because an operator's trust question is "what
   decided this" before it is "what will it do".
2. **The payload is an adapter-addressed write set**, not a device recommendation row. It names a
   cell and a change; which device that becomes is the executor's business.
3. **The card must render lineage** (see `include=lineage` below): the proposal that caused it, the
   evaluation KPIs it was judged against, and an expiry countdown from `expires_at`.

## Endpoints

All paths are on bdt_engine, authenticated with `X-API-Key`, and RLS-scoped to the path tenant.
All responses use bdt_engine's standard envelope, so the payloads below are what you find under
`data`.

### List

```
GET /v1/tenants/{tenant_id}/ndt/loop/actions
      ?status=pending_approval
      &proposal_id=<id>       # all actions from one proposal
      &kind=change|rollback
      &target=<cell_id or device_id>
      &since=<iso8601>&until=<iso8601>
      &limit=100&offset=0
```

```json
{ "items": [ /* LoopAction */ ], "total": 42, "limit": 100, "offset": 0 }
```

Newest first. `limit` maxes at 200. **`total` is the count matching the filters, not the page
size** — an operator paging through 40 pending approvals needs to know there are 40.

`target` matches a `cell_id` **or** a `device_id`, because the loop scopes some actions to a cell
and some to a device and a caller holding an id does not necessarily know which.

### Get one, optionally with lineage

```
GET /v1/tenants/{tenant_id}/ndt/loop/actions/{action_id}
GET /v1/tenants/{tenant_id}/ndt/loop/actions/{action_id}?include=lineage
```

Without the parameter: one `LoopAction`. With `include=lineage`, five slots instead:

```json
{
  "proposal":   { /* the raw proposal message that caused this action, or null */ },
  "evaluation": { "run_id": "...", "verdict": "pass", "reasons": [],
                  "kpi_snapshot": { "guardrail_kpis": {}, "objective_kpis": {} } },
  "action":     { /* LoopAction */ },
  "feedback":   [ { "kind": "apply", "status": "applied", "observed_at": "...", "payload": {} } ],
  "rollback":   { /* the LoopAction that reverted this one, or null */ }
}
```

`feedback` is oldest first — a lineage reads as a story. Any slot except `action` can be null or
empty: a `suppressed` action was never scored, never executed and never reverted, and that is a
complete lineage, not an error.

Any other `include` value is a `422 UNSUPPORTED_INCLUDE`. It is refused rather than ignored,
because silently returning the plain action for a typo would render as "this action has no
lineage".

### Approve

```
POST /v1/tenants/{tenant_id}/ndt/loop/actions/{action_id}:approve
Header: X-User-Id: <uuid>          # optional, recorded as updated_by
```

```json
{ "action_id": "...", "status": "dispatched" }
```

**Approve is one call, not two.** It moves `pending_approval -> approved -> dispatched` and
publishes the action in the same request, so a 200 means the change is genuinely on its way.

The action is dispatched against the evaluation and policy snapshot it was **already** judged
against; the gate is not re-run. That is deliberate: re-running it would let an operator approve one
thing and dispatch a verdict on another, since the twin's inputs may have moved since.

### Reject

```
POST /v1/tenants/{tenant_id}/ndt/loop/actions/{action_id}:reject
Header: X-User-Id: <uuid>          # optional
```

```json
{ "action_id": "...", "status": "rejected" }
```

Terminal, and nothing is published.

### Errors on both verbs

| Status | `errors[0].code` | Meaning for the UI |
| --- | --- | --- |
| 404 | `ACTION_NOT_FOUND` | No such action for this tenant. Drop the card. |
| 409 | `ACTION_NOT_PENDING` | Someone else decided it, or it expired. **Refresh the list; do not retry.** The response `details.status` carries the current status. |
| 422 | `INVALID_USER_ID` | `X-User-Id` was not a UUID. |
| 502 | `LOOP_ACTION_DISPATCH_FAILED` | Approved but could not be published; the action is now `failed`. Surface this — the operator must not believe their change went out. |

**A double-approve is a 409, never a second dispatch.** The claim is a single atomic UPDATE, so a
double click cannot apply the change twice. Optimistic UI is safe; just treat 409 as "someone got
here first" rather than as an error to show.

## State machine

E2's machine, authoritative:

```
pending_approval ──approve──> approved ──> dispatched ──> applied ──> watching ──> completed
       │                                        │                         │
       └──reject──> rejected (terminal)         ├──> failed               └──> rolled_back
                                                └──> expired
```

Gate outcomes that never reach a card, list-only: `suppressed` (policy was `off`) and
`rejected_by_gate` (the twin judged the change unsafe). `rejected_by_gate` rows carry
`evaluation.reasons`, which is the most useful thing on the whole surface for building trust —
show it.

`watching` is the KPI observation window after a change lands. It ends at `completed` (the network
stayed healthy) or at `rolled_back` (a guardrail breached and the loop reverted the change by
itself, with no operator involved). A `rolled_back` card should link to its rollback action through
the lineage `rollback` slot.

`expires_at` drives a countdown chip. An action nobody acts on ages out to `expired` rather than
sitting pending forever.

## Polling

Poll the list every 30 s while the approvals tab is visible; stop when it is not. Fetch lineage on
card expand rather than for every row. There is no websocket or SSE surface for loop actions and
none is planned in this epic.

## Copy rules for this surface

The product is **CloudlyNet**; the intelligence layer is the **Network Digital Twin** (never a bare
"Digital Twin"). Do not write copy claiming O-RAN, RIC or SMO compliance — the loop actuates
through a TR-069/CWMP device plane, and `artifacts/marketing/claims-guardrails.md` governs any
user-visible string here.

Say what the loop actually does: it evaluates a proposed change against a network twin, holds it for
your approval, applies it, watches the KPIs, and reverts it on its own if they degrade. That claim
is true and is demonstrable — which is more than most of this category can say.
