# EPIC 10 — Frontend alignment: the three-solution product surface

**Epic ID:** E10
**Title:** Bring the browser surface up to what E0–E9 shipped and what marketing sells: the three solutions (Simulate · Explain · Actuate), the Network Digital Twin as the home of prediction *and* inference *and* KPI tracking, honest capability rungs, and one brand.
**Owner surface:** `submodule/maveric_platform_frontend` (registered submodule), plus the gateway routes E10 depends on.
**Depends on:** E0–E9 backend work, all of which is shipped and reachable. E10 adds **no new backend capability**; it exposes capability that already exists and is currently invisible.

**Goal:** Close the gap between three things that have drifted apart — what marketing sells, what the backend does, and what a user can see in a browser. Today a prospect reads *"Simulate. Explain. Actuate."* on the marketing site, logs into the product, and finds a differently-branded application organised around services rather than solutions, in which the twin cannot be run, KPI history cannot be seen, the canonical data platform is unreachable, and the actuator layer is a device list.

---

## 1. Why this epic exists

**Marketing is the specification.** `artifacts/marketing/positioning.md` is explicit that it is
"the source of truth every downstream artefact inherits from." Three of its statements are
load-bearing for the UI and none of them are currently true in the browser:

| Marketing says | Where | Frontend today |
|---|---|---|
| Three solutions: **Network Digital Twin (Simulate) · Copilot (Explain) · Actuator Adapters (Actuate)** | positioning §5 | Five sidebar peers organised by service, not by solution |
| The Network Digital Twin "is **also where optimization model-inference and KPI tracking live**" | positioning §5, roadmap §2.1 | `/bdt` and `/rapp` are separate, equal peers |
| "**label every capability with its rung** (Today / Building / Vision)" | positioning §8 | No rung is displayed anywhere |

The roadmap already commits the work and names it (roadmap §3, `frontend` row):

> **frontend** · Today→hardening: *Retire retired brand strings, centralize `lib/brand.ts`* ·
> Building: ***3-solution UX**; device/edge tabs; approve-reject recommendation cards;
> observability tab* · Vision: *Proposal/CAPEX UI, log-replay viewer, topology what-if UX*

**This epic exists because every backend epic explicitly deferred it.** Eight stories across
E1–E5 carry an explicit `- Out: … frontend …` line (E2.S5: *"Out: frontend/gateway exposure
(later story)"*; E2.S8: *"Out: gateway/frontend exposure (later optional `/ndt/**` story)"*).
Exactly **one** frontend story exists in the whole re-architecture — E5.S5 — and it is a
*"contract note"*, not a build. The deferral was correct at the time and was never picked up.

---

## 2. The audit: shipped, reachable, and invisible

Method: enumerate every service's live OpenAPI, filter to what the gateway proxies, then grep
the frontend for a caller. **Not read from epic prose** — this epic's own predecessor backlog
warns that story text has drifted repeatedly from shipped code.

### 2.1 Backend surfaces the frontend never calls

| Surface | Shipped by | Marketing pillar it serves | Frontend |
|---|---|---|---|
| `POST /ndt/evaluate`, `GET /ndt/evaluate/{run_id}` | E2.S1 | **NDT · Simulate** — the whole first pillar | **not called** |
| `GET /ndt/kpis` | E2.S5 | **NDT · KPI tracking** | **not called** |
| `POST /ndt/feature-builds`, `GET /{id}` | E2.S4 | NDT · twin feature builder | **not called** |
| `POST /ingest/uploads`, `GET /ingest/jobs/{id}`, `GET /ingest/adapters` | E1 | Data platform | **not called** |
| `GET /data/pm`, `/data/fm`, `/data/cm` | E1 | Canonical PM/FM/CM store | **not called** |
| `GET /v1/actuators`, `GET /v1/actuators/{name}/health` | E4 | **Actuator Adapters · Actuate** — the third pillar | **not called** |
| `POST /utils/pm/generate` | E1 | PM generation for demos | **not called** |

`/ndt/**` has been gateway-routed since **E5.S7** and returns 200 — verified live. There is no
backend blocker on any row above.

### 2.2 Wired to superseded paths

| Screen | Calls | Should call | Consequence |
|---|---|---|---|
| `/actuators` ("Connections") | `useNybsysDeviceService` → `/custom/nybsys/**` | `/v1/actuators` (E4 framework) + nybsys for device detail | The "swappable actuator layer" — a top-three differentiator — renders as a single-vendor device list. The five placeholder adapters E4 shipped are invisible. |
| `/ingest`, `/custom-pm-ingestion` | `/custom/nybsys/uploads` | `/ingest/uploads` + `/ingest/jobs/{id}` | E1's adapter-based ingestion is invisible; the UI still presents ingestion as a NanoLink-specific feature. |

### 2.3 Brand divergence

The marketing surfaces and the product UI are **two different visual systems**:

| | Marketing (`artifacts/marketing/product.html`) | Frontend (`app/globals.css`) |
|---|---|---|
| Accent | `--signal: #004AAD` Cloudly blue, "spent sparingly" | `--primary: #0f766e` teal-700 |
| Display / body type | Montserrat / Rubik | Geist / Open Sans |
| Loop semantics | `--trace #7F38E5` KPI · `--guard #BE123C` breach · `--inflight #B45309` in-flight | none |

The marketing token set already contains **exactly the semantic colours the closed loop needs**
(`trace`, `guard`, `inflight`). The design system anticipated the product surface; the product
surface never adopted it.

Also open, from roadmap §4 #8 (**MEDIUM**, "retired names leak trust and dilute SEO"):
`lib/brand.ts` **does not exist**; `lib/trial.ts` still exports `"NetAI Trial"`; three auth
surfaces load `/cloudly-netai.png`; `<platform-host>` and
`<platform-host>` are hardcoded fallbacks in three files.

### 2.4 Stale in-code claims

`lib/api/services/ndt-loop.ts` still documents `/ndt/**` as un-routed and gives that as the
reason nothing is "wired into a navigation entry yet". Both halves are stale — the route landed
in E5.S7 and `/closed-loop` is in `app.config.ts`. *(Corrected 2026-08-04 ahead of this epic,
along with the 404 copy that told users to wait for a route that already exists.)*

---

## 3. Target information architecture

The sidebar stops mirroring the service topology and starts mirroring the product story. The
route table is deliberately **mostly unchanged** — this is a regrouping plus four new surfaces,
not a rewrite, because every existing route already works.

```
CloudlyNet
│
├── Overview                              /                     (existing)
│
├── SIMULATE  · Network Digital Twin      ← marketing Solution 1
│   ├── Topology & Configuration          /baseline             (existing)
│   ├── Training Data                     /smo                  (existing)
│   ├── Data Platform                     /data          [NEW]  E1: PM/FM/CM + ingest jobs
│   ├── Twin Library                      /bdt                  (existing, relabelled)
│   ├── Evaluate                          /ndt/evaluate  [NEW]  E2.S1: the pillar's core verb
│   ├── Optimization Models               /rapp                 (existing, MOVED under NDT)
│   └── KPI History                       /ndt/kpis      [NEW]  E2.S5
│
│   (EXPLAIN · Copilot lives in the TOP BAR — CopilotModule toggles the drawer from every screen)
│
├── ACTUATE  · Actuator Adapters          ← marketing Solution 3
│   ├── Adapters                          /actuators     [REWIRE] E4: /v1/actuators
│   ├── Connections (devices/edges)       /devices              (existing)
│   ├── Policy & Guardrails               /policy               (existing)
│   └── Closed Loop                       /closed-loop          (existing)
│
└── Administration                        (existing, unchanged)
```

**The one structural move:** `/rapp` becomes a child of the Network Digital Twin. This is not
cosmetic tidying — it is what marketing and the roadmap both already assert, and it is what the
backend already does. rApp has had **no local twin path since E2.S3**; every non-MRO inference
executes `rapp_evaluator._evaluate_day_via_ndt` → `POST /ndt/evaluate` on bdt_engine. The UI is
the only layer still presenting them as two products.

**Copilot stays in the top bar.** `components/topbar/CopilotModule.tsx` is mounted in
`app-topbar.tsx` and toggles the drawer, which is what `ui-label-mapping.md` specifies: *"Route
preserved and entry retained in top bar only."* An assistant that should be reachable from every
screen belongs in persistent chrome, not in a nav list where it competes with destinations. The
`app-sidebar.tsx` filter that removes a `copilot` item is therefore kept, with its rationale
corrected from "not wired yet" to "the top bar owns this entry point". The Explain solution is
represented in the product; it is simply not a sidebar row.

### 3.1 Design spec — deltas only

The repo has a working design system (shadcn/ui + Tailwind + `artifacts/frontend/Brand.md`).
This epic specifies **deltas against it**, not a new visual language.

**Tokens to add** (values from `artifacts/marketing/product.html` `:root`, which is the brand's
own definition — no new colour is invented here):

| Token | Value | Use |
|---|---|---|
| `--signal` | `#004AAD` | primary accent; replaces teal `#0f766e` |
| `--signal-soft` | `#004AAD1F` | selected nav, focus wash |
| `--trace` | `#7F38E5` | KPI series line |
| `--guard` | `#BE123C` | guardrail breach, rollback |
| `--inflight` | `#B45309` | change in flight (`dispatched`, `applied`, `watching`) |
| `--grad-a/b/c` | `#7F38E5` / `#155DFF` / `#31CFE8` | brand gradient, hero and section rules only |

**Type:** Montserrat (display) + Rubik (body), matching the marketing surfaces. Mono unchanged.

**Signature element:** the **rung chip**. A small, uppercase, tabular label — `TODAY`,
`BUILDING`, `VISION` — sitting beside a capability's heading. It is the visual embodiment of
positioning §8 ("we volunteer what we do not do yet, because in telecom that is what makes the
rest believable"), and it is the one element that would make this product recognisably
CloudlyNet rather than a generic RAN dashboard. `BUILDING` and `VISION` surfaces render
read-only with a one-line explanation, never a dead link.

**Five states, specified per new surface** (loading / empty / error / partial / ideal). The
empty state carries the action that fills it — an Evaluate screen with no runs says *"No
evaluations yet. Score a proposed configuration against `<twin>` before it touches a cell,"*
with the form beneath, not a shrug.

**Motion:** one concept only — *settling*. Loop status transitions and KPI series animate on
enter (160 ms, `cubic-bezier(.2,.7,.3,1)`); nothing loops or pulses. Honours
`prefers-reduced-motion`. A network-operations console that animates continuously reads as a toy.

**Mobile-first:** every new surface is specified at 375 px first. The Evaluate form and the KPI
chart are the two that genuinely need a distinct mobile layout (stacked form; chart scrolls
horizontally inside its own container, page body never does).

---

## 4. Stories

Sizes: **S** ≈ ½ day · **M** ≈ 1–2 days · **L** ≈ 3–5 days.
Sequence is deliberate: S1 unblocks everything visual, S2–S3 deliver the missing pillar, S7 is
the restructure that only makes sense once its children exist.

---

### E10.S1 — Brand consolidation: `lib/brand.ts`, marketing tokens, retired strings

**Why:** roadmap §4 #8, priority MEDIUM, unresolved. A prospect who reads the marketing site and
then logs in sees two different companies. This is also the cheapest credibility win in the epic
and every later story inherits its tokens.

**Size:** M

**Scope:**
- In: create `lib/brand.ts` as the single home for product name, company, tagline, lockup, logo
  asset paths, and external URLs; replace the teal palette with the marketing `:root` token set;
  adopt Montserrat/Rubik; delete retired strings; add the three loop-semantic tokens.
- Out: any layout or IA change (S7 owns that); any copy rewrite beyond retired names; the
  marketing HTML files themselves.

**Files:**
- Create: `lib/brand.ts`
- Modify: `app/globals.css` (token block, light + dark)
- Modify: `app/layout.tsx` (font imports Geist → Montserrat + Rubik)
- Modify: `lib/trial.ts` (`"NetAI Trial"` → constant from `lib/brand.ts`)
- Modify: `lib/api/client.ts`, `lib/api/services/copilot.ts`, `components/copilot/useCopilotStream.ts`
  (hardcoded `<platform-host>` fallbacks → `lib/brand.ts`)
- Modify: `lib/breadcrumbs.ts` (`<platform-host>`)
- Modify: `app/(auth)/trial/page.tsx`, `app/(auth)/select-tenant/SelectTenantClient.tsx`,
  `components/auth/AuthHeader.tsx` (`/cloudly-netai.png` → branded asset)
- Modify: `artifacts/frontend/Brand.md` (§3 documents current implementation; update to the new tokens)

**DoD:**
- `grep -rniE "netai|cloudly netai|CloudlyNet AI" lib components app` returns only
  `lib/brand.ts` (if it documents the retirement) and nothing customer-visible.
- No hex colour literal for accent/brand outside `app/globals.css`.
- Light and dark both meet WCAG AA on body text and on `--signal` against `--surface`.
- The seeded tenant still displays correctly (its slug is `netai-trial` in the database — an
  infra identifier CLAUDE.md explicitly permits; **the display name must not be**).

---

### E10.S2 — NDT Evaluate surface (`/ndt/evaluate`)

**Why:** "Simulate" is the first verb of the tagline and the first of three solutions, and there
is no way to do it in the product. E2.S1 shipped the API; nothing calls it.

**Size:** L

**Scope:**
- In: a service module for `POST /ndt/evaluate` + `GET /ndt/evaluate/{run_id}`; a form (baseline,
  BDT, UE dataset, scope tick/day, optional per-cell config overlay); tick-scope synchronous
  render; day-scope 202 + poll; results view (guardrail KPIs, objective KPIs, per-tick table,
  worst-tick, warnings); deep-link by `run_id`.
- Out: the what-if topology map (roadmap Vision); comparison of two evaluations (S6 territory);
  any change to the evaluate contract.

**Files:**
- Create: `lib/api/services/ndt-evaluate.ts`
- Create: `app/(dashboard)/ndt/evaluate/page.tsx`, `.../[runId]/page.tsx`
- Create: `components/ndt/EvaluateForm.tsx`, `EvaluateResult.tsx`, `PerTickKpiTable.tsx`
- Create: `types/ndt.ts`
- Modify: `lib/app.config.ts` (nav entry + breadcrumb labels)

**Contract notes that will otherwise cost a day each:**
- Tick scope returns **200 with the body**; day scope returns **202 + `Location`** and must be
  polled at `GET /ndt/evaluate/{run_id}`. Two different render paths from one form.
- `run_id` is a deterministic UUIDv5 over the request, so **re-submitting an identical request
  returns the cached run** with `metadata.cache_hit: true`. Surface that rather than implying
  fresh compute.
- **The cell ids in `cell_configs` must exist in the baseline topology.** Since 2026-08-04 the
  loop gate rejects unknown cells, but `/ndt/evaluate` itself still silently ignores them and
  returns KPIs for the *untouched* network. The form must therefore populate its cell picker
  from the baseline's topology and never accept free text. This is the single highest-risk
  detail in the story: free-text entry reproduces, in the UI, the exact defect the gate was
  built to stop.
- Day scope evaluates only ticks present in the dataset and reports the rest in `warnings`;
  render warnings, do not drop them.

**DoD:** tick and day both render from the live stack; an unknown cell is impossible to submit;
cache hits are labelled; all five states implemented; deep-linked `run_id` loads.

---

### E10.S3 — KPI history (`/ndt/kpis`)

**Why:** "KPI tracking" is named in positioning §5 and roadmap §2.1 as part of the twin. E2.S5
shipped `ndt_kpi_snapshots` and the trend query; nothing reads it. It is also what makes the
closed loop legible: a rollback with no KPI history is an assertion.

**Size:** M

**Scope:**
- In: trend query service; time-series chart of guardrail KPIs by `source` (`evaluate` vs
  `loop_gate`); filter by baseline/bdt/dataset/scope; annotate loop events on the series.
- Out: alerting; export; custom KPI definitions.

**Files:**
- Create: `lib/api/services/ndt-kpis.ts`, `app/(dashboard)/ndt/kpis/page.tsx`,
  `components/ndt/KpiTrendChart.tsx`
- Modify: `lib/app.config.ts`

**Design:** the KPI line uses `--trace`; guardrail breaches mark in `--guard`. Follow the
`dataviz` skill for the chart — series colour comes from the token set, never from a library
default palette.

**DoD:** a series renders from real snapshots; `loop_gate` and `evaluate` sources are
distinguishable; empty state explains how snapshots are produced.

---

### E10.S4 — Actuator adapters: wire `/actuators` to the E4 framework

**Why:** "A swappable actuator layer" is differentiator #4 in positioning §6 and the third
solution. E4 shipped the framework, a registry, health, and five placeholder adapters. The
screen shows a NanoLink device list, so the differentiator is invisible and the platform looks
single-vendor — the exact impression positioning §7 says we must avoid.

**Size:** M

**Scope:**
- In: call `GET /v1/actuators` and `GET /v1/actuators/{name}/health`; render one tile per
  adapter with its **rung chip**; TR-069/CWMP as `TODAY`, the five placeholders as `BUILDING`;
  keep the device inventory as a child view of the NanoLink adapter.
- Out: any new adapter; device-detail changes; enrollment flow changes.

**Files:**
- Create: `lib/api/services/actuators.ts`
- Modify: `app/(dashboard)/actuators/page.tsx`, `components/actuators/AdapterTile.tsx`
- Modify: `lib/app.config.ts`

**Rung source of truth:** positioning §5 Solution 3 table. TR-069/CWMP = Today; Open M-Plane,
E2/R1-via-RIC, CBRS SAS Domain Proxy, OCUDU = Building. **Do not infer a rung from whether an
endpoint returns 200** — a placeholder adapter answers health checks and is still Building.

**DoD:** every registered adapter appears with a correct rung; a Building adapter is visibly
non-actionable with a one-line explanation; NanoLink devices remain reachable.

---

### E10.S5 — Data platform surface (`/data`) and ingest cutover

**Why:** E1 built the canonical PM/FM/CM store and an adapter-based ingest pipeline. The UI
reaches neither and still presents ingestion as a NanoLink-specific upload, which contradicts
the vendor-neutral positioning.

**Size:** L

**Scope:**
- In: PM/FM/CM query views over `/data/**` (filter by cell, metric, time window); ingest-job
  view over `/ingest/jobs/{id}`; adapter list over `/ingest/adapters`; move upload submission to
  `POST /ingest/uploads`.
- Out: deleting the legacy `/custom/nybsys/uploads` screen (keep until the new path is proven in
  staging — E1 kept the legacy contract deliberately); any ingest-contract change.

**Files:**
- Create: `lib/api/services/data-platform.ts`, `app/(dashboard)/data/page.tsx`,
  `components/data/PmQueryTable.tsx`, `IngestJobStatus.tsx`
- Modify: `app/(dashboard)/ingest/page.tsx`, `app/(dashboard)/custom-pm-ingestion/page.tsx`
- Modify: `lib/app.config.ts`

**DoD:** a PM query returns rows from the canonical store; an upload submitted through
`/ingest/uploads` reaches `pm_measurements` and its job is observable; the legacy path still
works.

---

### E10.S6 — Optimization re-homed under the twin; inference reads as NDT-backed

**Why:** the structural claim of §3. Also the fix for a real user-visible failure: non-MRO
inference was returning **500** because rApp's delegated `/ndt/evaluate` call carried the wrong
API key — proof that inference already *is* an NDT operation. *(Root-caused and fixed
2026-08-04 in `scripts/kafka/compose.sh`; retained here because the UI must now say so.)*

**Size:** M

**Scope:**
- In: move `/rapp` and `/compare` under the Network Digital Twin group; relabel per
  `ui-label-mapping.md`; on an inference result, state that evaluation ran on the twin and link
  to the `run_id` in S2's viewer; MRO labelled as evaluating in-process (it does not delegate).
- Out: moving or renaming routes (`/rapp` stays — the label mapping is explicit that routes do
  not change); training-flow changes; the RIC re-homing of ES/LB/CCO/MRO (roadmap §2.3, E9).

**Files:**
- Modify: `lib/app.config.ts` (nav grouping + breadcrumbs)
- Modify: `components/inference/InferenceResultTable.tsx`, `DayInferenceDashboard.tsx`
- Modify: `lib/api/services/rapps.ts` (surface the NDT `run_id` where the response carries it)

**DoD:** Optimization sits under the Network Digital Twin; a non-MRO inference result names the
twin run it was scored against; MRO is correctly *not* labelled as delegated.

---

### E10.S7 — The three-solution IA and the rung chip

**Why:** the epic's headline. Only sensible once S2–S6 exist, or the new groups would be mostly
empty — which is why it is last, not first.

**Size:** M

**Scope:**
- In: restructure `lib/app.config.ts` to the §3 tree; add the `SIMULATE` and `ACTUATE` section
  headers with their solution names; leave Copilot in the top bar (`CopilotModule`) and keep the
  `app-sidebar.tsx` filter, correcting its stale comment; build the `RungChip` component and apply
  it from a single capability registry; update breadcrumbs.
- Out: new routes; removing Administration or Logging groups; the marketing site.

**Files:**
- Modify: `lib/app.config.ts`, `components/app-sidebar.tsx` (correct the filter's rationale),
  `components/nav-main.tsx` (render the chip), `lib/breadcrumbs.ts`
- Create: `components/common/RungChip.tsx`, `lib/rungs.ts`

**`lib/rungs.ts` is a registry, not a decoration.** One exported map from capability key to
`"today" | "building" | "vision"`, sourced from positioning §5 and roadmap §2, with a comment
naming the source line for each entry. A rung that drifts from the marketing document is a
claims-guardrails violation, not a styling bug — which is why it lives in one file that a
reviewer can diff against `positioning.md`.

**DoD:** the sidebar reads as the three solutions; every capability carries a rung traceable to
a marketing line; nothing that is `Building` is presented as usable.

---

### E10.S8 — `ApiClient.put` and the policy editor

**Why:** `/policy` renders guardrails but cannot change them, because `ApiClient` has **no `put`
verb** while `PUT /ndt/loop/policy` has existed since E2.S6. A guardrail model nobody can tune
is a demo, not a product.

**Size:** S

**Scope:**
- In: add `put` to `ApiClient` alongside the existing verbs and its envelope/error handling; an
  edit form for the two-part guardrails (absolute floor + regression budget, per KPI); optimistic
  update with rollback on failure.
- Out: policy history/audit; per-cell policy overrides.

**Files:**
- Modify: `lib/api/client.ts`, `lib/api/services/ndt-loop.ts`
- Modify: `app/(dashboard)/policy/page.tsx`, `components/policy/*`

**Contract note:** guardrails are **two-part per KPI since 2026-08-04**
(`artifacts/design/loop-guardrails.md`): an absolute floor/ceiling **and** a regression budget
against the evaluated baseline, with per-statistic keys (`sinr_p5_floor_db` vs
`sinr_avg_floor_db` — the gate reads the twin's p5, the watch reads the device's mean; they are
different statistics and a single field for both is the defect that document exists to fix).
The editor must present them as two fields per KPI, per layer. `LoopPolicyIn` validates strictly;
`LoopPolicy` tolerates legacy keys forever because `policy_ref` snapshots are frozen on historical
action rows.

**DoD:** a guardrail edit persists and is visible in the next gate decision's `policy_ref`;
legacy-key policies render without error.

---

### E10.S9 — Loop observability tab

**Why:** named in the roadmap's `frontend` Building cell. E5.S3 shipped
`cloudlynet_loop_stage_events_total{stage,tenant_id,outcome}` on three services plus
`?include=lineage`; none of it is visible.

**Size:** M

**Scope:**
- In: a lineage view on a loop action (proposal → evaluation → action → feedback[] → rollback)
  using the existing `?include=lineage`; stage-funnel counts; `request_id` shown and copyable.
- Out: a metrics/Prometheus browser; log aggregation.

**Files:**
- Create: `components/ndt/LoopLineage.tsx`
- Modify: `components/ndt/LoopActionCard.tsx`, `lib/api/services/ndt-loop.ts`

**DoD:** expanding an action shows its full lineage from the live API; `request_id` correlates a
pass across rapp, bdt_engine and smo_sim.

---

## 5. Out of scope for E10

- **Any new backend capability.** If a story needs an endpoint that does not exist, it stops and
  files against the owning epic. E10 exposes; it does not extend.
- The **RIC re-homing** of ES/LB/CCO/MRO (roadmap §2.3, E9) and any E2/R1 UI. Those stay
  `Building` chips.
- Roadmap **Vision** frontend items: proposal/CAPEX UI, log-replay viewer, topology what-if UX.
- The marketing HTML/site itself.
- Copilot RCA UI — `Building` in roadmap §2.2 and blocked on copilot's own auth and guardrail
  work (roadmap §4 #1, #2, both **HIGH**).

## 6. Epic-level definition of done

- Sidebar presents Simulate and Actuate as solutions; Explain (Copilot) is reachable from the top bar on every screen.
- Every §2.1 surface has a caller, or an explicit story deferring it with a reason.
- `/actuators` reads the E4 framework; adapters carry correct rungs.
- Optimization sits under the Network Digital Twin and inference names its twin run.
- One brand: `lib/brand.ts` exists, marketing tokens are in `globals.css`, no retired name is
  customer-visible.
- Every capability carries a rung traceable to `positioning.md` or `roadmap.md`.
- A guardrail can be edited from the browser.
- `npm run build` clean; no route regressions; existing e2e green.

## 7. Risks

| Risk | Mitigation |
|---|---|
| **Free-text cell entry in S2 reproduces the unknown-cell defect at the UI layer** — `/ndt/evaluate` still silently ignores unknown cells (only the loop gate refuses them) | Cell picker populated from the baseline topology; no free text. Called out in S2's contract notes. Consider a follow-up making `/ndt/evaluate` warn — backend, so not E10. |
| Rung labels drift from marketing and become a claims violation | Single `lib/rungs.ts` registry with per-entry source citations, diffable against `positioning.md` |
| The IA move (S7) breaks deep links or muscle memory | Routes are unchanged by design; only grouping and labels move. `/devices` already precedents this (kept as a redirect) |
| Teal→blue rebrand regresses contrast in dark mode | AA check on both schemes is in S1's DoD |
| Scope creep into Vision items | §5 names them explicitly as out |

## 8. Sequencing

```
S1 (brand)  ─┬─> S2 (evaluate) ─┬─> S7 (IA + rungs) ──> S9 (observability)
             ├─> S3 (kpis)     ─┤
             ├─> S4 (actuators)─┤
             ├─> S5 (data)     ─┤
             └─> S6 (rapp move)─┘
                 S8 (policy put) — independent, any time after S1
```

S1 first (every later story consumes its tokens). S2–S6 in parallel. S7 last of the visual work
so the new groups are populated. S8 is independent.

---

*Sources: `artifacts/marketing/positioning.md` §§4–6, 8 · `artifacts/marketing/roadmap.md` §§2.1–2.4, 3, 4
· `artifacts/marketing/product.html` `:root` · `artifacts/frontend/ui-label-mapping.md` ·
`artifacts/design/loop-guardrails.md` · live OpenAPI of bdt_engine, rapp, smo_sim, data_sim ·
`submodule/maveric_platform_gateway/cmd/gateway/main.go` · frontend audit 2026-08-04.*


---

## 9. Execution status — 2026-08-04

Implemented in one pass, **excluding S1 (brand)** at the user's direction. `npx next build` clean;
container rebuilt; every route verified 200 against the running stack.

| Story | Status | Evidence |
| --- | --- | --- |
| S1 brand | **not started** | excluded by the user ("ignore 2.3 Brand divergence for now") |
| S2 Evaluate | done | `/ndt/evaluate` 200; tick run returned `sinr_p5 -1.018`, `cache_hit` surfaced |
| S3 KPI history | done | `/ndt/kpis` 200; 32 snapshots, both series present (8 `evaluate`, 24 `loop_gate`) |
| S4 Actuators | done | `/v1/actuators` **newly gateway-routed**; 6 adapters render with rungs |
| S5 Data platform | **partial** | query surface done (5 PM rows, 4 ingest adapters); **ingest cutover NOT done** |
| S6 Optimization under twin | **partial** | nav move + provenance note done; **run_id deep link blocked** |
| S7 IA + rungs | done | Simulate/Actuate sidebar sections; Copilot kept in the top bar; `lib/rungs.ts` + `RungChip` |
| S8 policy editor | done | `ApiClient.put` added; `PUT /ndt/loop/policy` → 200 |
| S9 lineage | done | five-slot view + copyable `request_id` |

### Backend changes this required (one, declared)

`/v1/actuators` was **not gateway-routed** — 404 through :8080 — so S4 could not have been built
frontend-only. Added as a non-tenant-scoped group in `cmd/gateway/main.go`, carrying the global
AuthN and rate limit but not `RequireMembership` (which reads `:tenant_id` and cannot apply). The
payload is adapter names, capability flags and health; nothing tenant-specific is exposed.
`go test ./cmd/...` green. This is inside the epic header's scope ("plus the gateway routes E10
depends on"), not new capability.

### NOT DONE — carried forward

1. **S5's ingest cutover.** The `/data` query surface and the adapter list are built, but PM Upload
   still posts to `/custom/nybsys/uploads`. Moving submission to `POST /ingest/uploads` needs that
   endpoint's multipart contract confirmed and a staging soak, and E1 kept the legacy contract
   byte-identical precisely so the cutover could be deliberate. Not attempted rather than
   half-attempted.
2. **S6's link from an inference to its twin run.** rApp's inference response does not carry the
   NDT `run_id` it delegated to — `metadata` holds rApp's own `cache_key` instead — so the UI can
   state that the twin scored the run but cannot deep-link to it. Surfacing that id is a small
   rapp/bdt_engine change and is backend scope. The provenance note is live and correct meanwhile,
   including the MRO exception (MRO evaluates in-process and does not delegate).

### Found while building, worth keeping

- **There is no browser-reachable source for a baseline's cell list.** `GET /baselines/{id}`
  returns `url_to_topo_csv` as an **`s3://` URI**, and `/data/cm` is empty until CM is ingested. So
  the Evaluate cell picker is populated by running a config-free evaluation and reading
  `raw_tick_data[tick].cell_states`, which records every cell in the topology. It works and is
  honest, but it costs a real twin run — **`endpoints/ndt.py` skips the evaluation cache whenever
  `options.include` is set**, so discovery is never a cache hit and is cached client-side per refs
  triple instead. A tiny `GET /ndt/baselines/{id}/cells` would be the better answer.
- **Copilot was never "hidden".** An earlier draft of this epic said the sidebar suppressed it and
  that a third of the product story was invisible. Wrong: `CopilotModule` sits in the top bar and
  opens the drawer from any screen, exactly as `ui-label-mapping.md` specifies. The suppression
  filter exists to keep it there. Corrected after the claim was checked against the running UI.
- **S9 was already half-built.** E5.S5's card already fetched `?include=lineage` and rendered
  feedback + rollback. Only the proposal and evaluation slots and `request_id` were missing, so the
  work was an extension rather than the new component the story implied.
- **Prettier config lives in `eslint.config.mjs`** (`useTabs: true, tabWidth: 4`), not a
  `.prettierrc`. A bare `npx prettier --write` reformats to spaces and the build then fails on
  `prettier/prettier`. Use `npx prettier --use-tabs --tab-width 4`.

---

## 10. Second pass — 2026-08-05

The user's issue list (filed against a 34-hour-stale container that predated the §9 pass)
was reconciled against the tree; the container is rebuilt twice over, and everything §9 left
uncommitted is now committed: frontend `3fb70c9` + `7f4e0f0`, gateway `8e7ee48` (the
`/v1/actuators` route §9 declared).

**S1 done** (was excluded from §9 at the user's direction; the user's brand complaints ended
that exclusion): `lib/brand.ts`, marketing tokens in both themes, Montserrat+Rubik including
the `app/(dashboard)/layout.tsx` Open_Sans override the story's file list missed, the teal
hex sweep (4 components), retired-name sweep. Kept deliberately: the `netai-trial` slug and
the `netai-app-store` persist key (renaming it logs every user out - a migration, not copy).

**S10 added** (user issue 6, absent from this epic): `components/widgets/LoopFlowStrip.tsx`
on the Overview - the closed loop as five clickable stages plus the feedback sentence.
Deliberately static: stage counters exist only as Prometheus metrics, which are not
browser-reachable, and fake liveness is worse than honest navigation.

**Defects fixed:** `/actuators` rendered 4 of the 6 live adapters twice (hardcoded tiles
duplicating the registry) - removed; `a1_policy` added as a declared platform adapter with a
Building rung (it is rApp-executed, so smo_sim's `/v1/actuators` can never list it);
KPI chart series moved onto the semantic tokens (`evaluate`=--signal, `loop_gate`=--trace,
--guard reserved for breaches - the first mechanical token swap got this wrong and was
corrected); S2's missing `[runId]` deep-link page built with a running-state poll.

**User-issue copy:** the Ingest PM card now states both PM roles (twin feature-build input
AND loop validation watch); the device Optimize panel names the two loops and links to
Closed Loop (device EWMA self-optimization is not the platform loop); `/policy` bridges
tenant guardrails to per-device policy modes.

**Verified:** `next build` clean (only the pre-existing CopilotShell hook warning);
`go test ./cmd/...` green; all ten key routes 200 on the rebuilt container;
`/v1/actuators` 200 through the gateway with 6 adapters.

**Still open, deliberately:** S5 ingest cutover (upload still posts to the legacy path;
note the endpoint is JSON+presigned-URL, not multipart as §9 assumed); S6 run_id deep-link
from inference (blocked on rApp surfacing the NDT run id - backend); S3 loop-event
annotations and S9 stage funnel (both need data the browser cannot reach today); visual
(browser) QA of the rebuilt UI - route 200s and a clean build are necessary, not sufficient,
for client-rendered pages.

---

## Appendix: IA realignment execution (2026-08-06, second pass)

A 12-item user-driven IA/UX change list executed across 4 phases (validated by a
10-agent analysis first; plan + per-item verdicts in `docs/task_docs/ia-realignment/`).
Commits: frontend `dff7e05`/`d55ec13`/`fd40b1e`/`887a396`, data_sim
`f895006`/`4848c93`, smo_sim `b6cf461`/`5d31d65`. Legacy inventory + deferred work:
`EPIC-11-legacy-phaseout.md`.

**Shipped:**
1. Loop flow strip global: route-aware, clickable, compact variant on every dashboard
   page (full on Overview), mounted once in the shell.
2–4. PM upload de-branded (vendor-neutral `PmUpload*` family) and **cut over to
   `POST /ingest/uploads`** — this closes the earlier appendix's open item S5. The
   PM→topology/config conversion UI is gone (twin seeding now goes through baselines /
   feature builds). Ingest-adapters card moved from /data onto the upload page. /data
   browse: newest-first, time-window picker, Load more; data_sim gained keyset cursor
   pagination (deterministic `(ts,dn,metric,source)` order — fixed a real OFFSET
   skip/dup bug at ts ties) + a browse index (`016_pm_ts_browse_index.sql`).
5. Baseline training CSV: one label ("BDT training data (CSV)"), optional end-to-end
   (was wrongly required by frontend zod only).
6. Evaluate: "Training data" renamed "UE dataset (evaluation points)" — it is the
   twin's query points, not training input.
7. BDT Simulation page deprecated (banner + LEGACY markers); Twin Library row action
   now opens `/ndt/evaluate?bdt_id=…` (Evaluate honors the param). Removal gated on
   the scatter-plot port (EPIC-11 S2).
8. Tick honesty: datasets now carry `stats.ticks_present`/`tick_variant` (written by
   smo_sim upload AND data_sim generators); Evaluate disables Tick for static
   snapshots and relabels "Hour of day (0-23)" for variant ones.
9. /rapp restructured: primary tabs "Use CloudlyNet Models" | "Connect to RIC"
   (URL-synced), compare embedded as the "Compare Models" view, `/compare` → redirect.
10. KPI history rebuilt: gate baseline→candidate pairs vs evaluate envelope, robust
   p5–p95 y-domain with clipped-outlier affordances, breach marking against the live
   loop policy, time windows + Load older (200-cap gone), every point deep-links to
   its run. Old `KpiTrendChart` kept as LEGACY.
11. `/actuators/tr069` dedicated page owns the edge/device estate; adapter grid tiles
   all interactive (TR-069 links through; others open an info dialog with rung/
   capabilities/health).
12. `/policy` has ONE mode control; Device policies section removed; device Optimize
   tab shows the tenant mode read-only. smo_sim's device self-optimizer now **reads
   `loop_policies.mode`** (tenant `auto` → device `approval` — device auto-apply still
   requires explicit RF sign-off per OD4); `PATCH …/optimize-mode` returns 410;
   device responses carry a derived `optimize_mode`.

**Corrections found during validation:** the adapters card lived on /data (not
/ingest); /data had NO pager at all (50 oldest rows, dead-end footer); the two policy
"modes" were different loops sharing a vocabulary, so centralization = making the
device loop read the tenant policy, not deleting a duplicate.

**Verified:** `npm run build` clean after every phase (only the pre-existing
CopilotShell hook warning); smo_sim 703 passed / 3 pre-existing failures; data_sim 202
passed / 13 pre-existing failures (stash-verified pre-existing in both).

**Still open, deliberately:** browser-visual QA of the rebuilt KPI chart and new pages
(build + code checks only so far); copilot page-context on in-page /rapp view toggles;
KPI filter state not URL-synced; gate pairing is a client-side heuristic until
snapshots carry a pair/proposal identity (EPIC-11 S6).
