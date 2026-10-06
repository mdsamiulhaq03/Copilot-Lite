# EPIC 0: Platform hygiene and unblockers

- **Epic ID:** E0
- **Title:** Platform hygiene: gateway route fix + route split, internal contract docs, CloudlyNet rebrand, secrets follow-up
- **Goal:** Remove the verified gateway startup panic that makes gateway HEAD undeployable, land the one deliberate gateway routing change (the `/custom` split plus `/ingest`/`/data` prefixes) that E1 will consume, and formalize the cross-service contracts (shared tables, S3 keys, EFS, east-west auth) that every later epic depends on. Also complete the 2026-07-16 CloudlyNet rename on non-marketing surfaces and flag the secrets-in-git exposure with a minimal first step.
- **Dependencies:** none. E0 blocks E1, E3, E4 (per frozen HLD §5 epic map).
- **Grounding:** `docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md` (FROZEN; §3 hard constraints, §4 shared contracts), `docs/task_docs/cloudlynet-rearchitecture/00-hld-assessment.md` (evidence base).
- **Definition of done (epic):**
  - `maveric_platform_gateway` builds and starts with all five `*_BASE_URL` env vars set (no gin wildcard panic); `go test ./...` green.
  - Gateway routes `/custom/nybsys/uploads*` to DATA only when `CUSTOM_UPLOADS_TARGET=data`; default behavior is byte-identical to today (everything under `/custom/**` to SMO). New tenant-scoped `/ingest/**` and `/data/**` prefixes proxy to DATA.
  - `artifacts/design/internal-contracts.md` exists, is evidence-stamped (file:line citations), and documents the shared-table ownership matrix, S3 key contract v1, EFS `/app/var/models` sharing, and the east-west API-key pattern including `NDT_BASE_URL`/`NDT_API_KEY`.
  - No non-marketing surface renders the strings `NetAI`, `CloudlyNet AI`, or `Cloudly Netai` to a user or reader, except in the documented freeze list (infra identifiers) and historical archives.
  - Secrets exposure is documented with rotation checklist and a SOPS/sealed-secrets proposal; no chart/pipeline renames.
  - Zero CI/CD change anywhere: no new charts, pipelines, images, ports; env-var additions have safe in-code defaults so no chart edit is required to deploy E0.

---

## E0.S1 - Fix gateway duplicate `/v1/agent/*path` registration (startup panic)

**ID:** E0.S1 · **Title:** Remove the duplicate agent route group so gateway HEAD boots

**Why:** Gateway HEAD (merge PR #23, commit afee4e1) panics at startup whenever `SMO_BASE_URL` is set: gin v1.10.1 rejects the second wildcard registration of `/v1/agent/*path` (`cmd/gateway/main.go:226` added 2026-06-18 by commit 3fff6fd, versus the original group at `:247` from commit 7dfdef4, 2026-06-12). Verified by building and running the binary (assessment §1.7). Every other E0/E1 gateway change stacks on this fix.

**Size:** S

**Scope:**
- In: delete the 2026-06-18 duplicate block at `cmd/gateway/main.go:224-227` (the un-rate-limited `v1.Any("/agent/*path", ...)` registration).
- In: keep the original `/v1/agent` group at `main.go:240-248` exactly as-is: no Cognito (AuthN early-return at `internal/middleware/middleware.go:179` is untouched), `RateLimitByIP(120)` per minute, `SMO_API_KEY` injection via `ProxyHandler` (`internal/proxy/proxy.go:73-90`).
- In: a registration smoke test that would have caught this class of bug.
- Out: any other route change (that is E0.S2); any middleware or proxy behavior change; any change to the `/v1/agent/**` request/response contract (field-frozen three-party contract with deployed edge agents).

**Files:**
- Modify: `submodule/maveric_platform_gateway/cmd/gateway/main.go` (delete lines 224-227; the surviving block is 236-248)
- Modify: `submodule/maveric_platform_gateway/cmd/gateway/main_test.go` (add route-registration smoke test)

**Contract:** External behavior after the fix is identical to the deployed (pre-3fff6fd) gateway image:
- `ANY /v1/agent` and `ANY /v1/agent/*path` proxy to `SMO_BASE_URL`, Cognito bypassed, 120 req/min/IP, `X-API-Key: $SMO_API_KEY` injected, `X-Edge-Key` passed through.
- All other registrations in `main.go:228-234` unchanged.

**Key snippets:**

```go
// DELETE this block (cmd/gateway/main.go:224-227). It duplicates the rate-limited
// group registered below at :240-248 and panics gin route registration:
//   panic: '/*path' in new path '/v1/agent/*path' conflicts with existing wildcard
if pr.SMO != nil {
    agentHandler := pr.ProxyHandler(pr.SMO, normalizeProxyPath)
    v1.Any("/agent/*path", agentHandler)
}
```

```go
// KEEP (main.go:240-248): the canonical agent group. Behavior contract:
// no Cognito (middleware.AuthN early-return), 120/min/IP, SMO_API_KEY injection.
if pr.SMO != nil {
    agent := r.Group("/v1/agent")
    if rl != nil {
        agent.Use(rl.RateLimitByIP(120))
    }
    agentHandler := pr.ProxyHandler(pr.SMO, normalizeProxyPath)
    agent.Any("", agentHandler)
    agent.Any("/*path", agentHandler)
}
```

```go
// New test (main_test.go): extract route registration into a helper (e.g.
// buildRouter(cfg) or setupProxyRoutes(r, pr, rl)) if needed so this is testable,
// then assert registration does not panic with every *_BASE_URL set.
func TestRouteRegistrationDoesNotPanic(t *testing.T) {
    t.Setenv("BDT_BASE_URL", "http://bdt:8000")
    t.Setenv("RAPP_BASE_URL", "http://rapp:8001")
    t.Setenv("SMO_BASE_URL", "http://smo:8002")
    t.Setenv("DATA_BASE_URL", "http://data:8003")
    t.Setenv("COPILOT_BASE_URL", "http://copilot:8000")
    gin.SetMode(gin.TestMode)
    // must not panic:
    _ = buildTestRouterWithProxies(t)
}
```

**Acceptance criteria:**
- `go build ./...` and running the gateway locally with `SMO_BASE_URL` set starts and serves `GET /v1/health` 200 (previously: immediate panic).
- Exactly one registration of `/v1/agent/*path` remains in `main.go`, inside the rate-limited group.
- `TestAgentProxyForwardsEdgeKeyAndInjectsSMOAPIKey` (existing, `internal/proxy/proxy_test.go:154`) still green: `X-Edge-Key` forwarded, `SMO_API_KEY` injected.
- New registration smoke test fails if a duplicate wildcard is ever reintroduced.

**Test plan:**
- Unit: `cd submodule/maveric_platform_gateway && go test ./...` (new `TestRouteRegistrationDoesNotPanic`, existing proxy + middleware suites).
- Integration (lab): `./scripts/kafka/compose.sh up`, then `curl -s localhost:8080/v1/health` returns 200; `docker logs maveric_gateway` shows "gateway listening" and no panic.

**Coding-agent prompt:**

```text
CONTEXT
You are working in the CloudlyNet backend monorepo (repo root: cloudlynet_ai). The Go API
gateway lives in the git submodule submodule/maveric_platform_gateway (cd into it before any
git operation; commits there are separate from the parent repo). Frozen architecture doc for
background: docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md.

BUG (verified by build+run): cmd/gateway/main.go registers the wildcard route
/v1/agent/*path twice when SMO_BASE_URL is set:
  1) lines 224-227: `if pr.SMO != nil { agentHandler := ...; v1.Any("/agent/*path", agentHandler) }`
     (added 2026-06-18, commit 3fff6fd) - registered on the plain /v1 group, no rate limit.
  2) lines 240-248: the original group `agent := r.Group("/v1/agent")` with
     rl.RateLimitByIP(120), agent.Any("", h) and agent.Any("/*path", h) (commit 7dfdef4).
gin v1.10.1 panics at startup: "'/*path' in new path '/v1/agent/*path' conflicts with
existing wildcard". Deployed images predate the bug; HEAD is undeployable.

TASK
1. Delete the duplicate block at cmd/gateway/main.go:224-227 ONLY. Keep the block at
   lines ~236-248 (comment + rate-limited group) byte-for-byte in behavior: no Cognito
   (the AuthN early-return for /v1/agent/ at internal/middleware/middleware.go:179 must not
   be touched), RateLimitByIP(120), SMO_API_KEY injection via ProxyHandler.
2. Add a route-registration smoke test in cmd/gateway/main_test.go that sets all five
   base-URL envs (BDT_BASE_URL, RAPP_BASE_URL, SMO_BASE_URL, DATA_BASE_URL,
   COPILOT_BASE_URL) via t.Setenv, builds the gin engine with the same registration code
   path main() uses, and fails if registration panics. If the registration code is inlined
   in main(), extract it into an unexported helper (e.g. registerRoutes(r *gin.Engine, ...))
   so it is testable; do not change any route path, middleware order, or handler wiring.

CONSTRAINTS
- Zero behavior change other than removing the panic. The /v1/agent/** contract is frozen:
  field-deployed edge agents (X-Edge-Key auth, {success,message,data} envelope) cannot be
  redeployed atomically.
- No new env vars, ports, images, charts. Go code style: match existing file conventions.
- Commit in the submodule with a concise one-line message, e.g.
  "[fix]: gateway: remove duplicate /v1/agent/*path registration (startup panic)".
  No Claude authorship signature.

DEFINITION OF DONE
- cd submodule/maveric_platform_gateway && go build ./... && go test ./... all green.
- Running the gateway with SMO_BASE_URL set starts cleanly and GET /v1/health returns 200.
- grep -n "agent/\*path" cmd/gateway/main.go shows exactly one wildcard registration,
  inside the rate-limited group.
```

---

## E0.S2 - Gateway `/custom` split + new `/ingest` and `/data` prefixes (designed once here, consumed by E1)

**ID:** E0.S2 · **Title:** Split `/custom/nybsys/uploads*` to DATA behind an env gate; add `/ingest/**` and `/data/**` to DATA

**Why:** Frozen HLD §4.3 relocates PM ingestion to data_sim: gateway must send `custom/nybsys/uploads*` to DATA while every NanoLink device/edge operation under `/custom/nybsys/**` stays on SMO, and must expose the new `/ingest/**` and `/data/**` tenant prefixes to DATA. This is "the one deliberate gateway code change" (HLD §4.3); designing and landing it once in E0, dark by default, means E1 only flips an env value.

**Size:** M

**Scope:**
- In: replace `registerProxy("/custom", pr.SMO, ...)` (`cmd/gateway/main.go:234`) with a per-request dispatch handler implementing the split rule; add `registerProxy("/ingest", pr.DATA, ...)` and `registerProxy("/data", pr.DATA, ...)` on the tenant group.
- In: new env gate `CUSTOM_UPLOADS_TARGET` (values `smo`|`data`, default `smo` in code) so E0 ships with zero behavior change and zero chart edits.
- In: unit tests for the dispatch predicate and proxy targeting.
- Out: any data_sim code (E1 implements the receiving `/custom/nybsys/uploads` + `/ingest` + `/data` endpoints); any change to `/utils/**`, `/baselines/**`, `/ue-data/**`, `/bdt/**`, `/rapps/**`, `/copilot/**`, `/v1/agent/**`; TrialWriteGuard whitelist changes (trial users remain blocked from non-inference writes, matching today's `/custom` behavior); gateway exposure of `/ndt/**` (later optional story per HLD §4.2).

**Files:**
- Modify: `submodule/maveric_platform_gateway/cmd/gateway/main.go` (route registration ~lines 223-234; new `customDispatchHandler` + `isNybsysUploadsPath` helpers)
- Modify: `submodule/maveric_platform_gateway/cmd/gateway/main_test.go` (predicate + registration tests)
- Modify: `submodule/maveric_platform_gateway/internal/proxy/proxy_test.go` (dispatch target test, modeled on `TestProxyInjectsServiceAPIKeyHeader:128`)

**Contract (gateway routing table after this story; conforms to frozen HLD §4.3, never redefines it):**

| Route (all under `/v1/tenants/:tenant_id` unless noted) | Target | Notes |
|---|---|---|
| `/custom`, `/custom/*path` where path is `/nybsys/uploads` or `/nybsys/uploads/...` | DATA iff `CUSTOM_UPLOADS_TARGET=data` and `DATA_BASE_URL` set, else SMO | split rule from HLD §4.3; `DATA_API_KEY` injected when targeting DATA |
| `/custom/*path` everything else (`/nybsys/edge-devices**`, `/nybsys/devices**`, `/nybsys/recommendations**`, `/nybsys/commands**`) | SMO | unchanged; smo_sim routers `app/api/v1/custom/nybsys_edge_router.py` |
| `/ingest`, `/ingest/*path` | DATA | new; E1 serves `POST /v1/tenants/{t}/ingest/uploads`, `GET /v1/tenants/{t}/ingest/jobs/{id}` |
| `/data`, `/data/*path` | DATA | new; E1 serves `GET /v1/tenants/{t}/data/pm` (+`/fm`,`/cm`) |
| all other prefixes | unchanged | `/bdt`→BDT, `/rapps`→RAPP, `/baselines`→SMO, `/ue-data`→SMO, `/utils`→DATA, `/copilot`→COPILOT, `/v1/agent/**`→SMO |

- Upstream path shape is preserved verbatim (passthrough via `normalizeProxyPath`), so data_sim can serve the legacy `/v1/tenants/{t}/custom/nybsys/uploads*` contract byte-compatibly (hard constraint §3.2).
- The uploads sub-tree being split covers exactly the four legacy routes in `smo_sim/app/api/v1/custom/nybsys/router.py`: `POST /uploads` (202), `GET /uploads`, `GET /uploads/{upload_id}`, `DELETE /uploads/{upload_id}` (204).
- Env contract: `CUSTOM_UPLOADS_TARGET` read once at registration; unset/`smo`/unknown value or nil DATA target → SMO (today's behavior). E1 flips it to `data` via chart secretData edit (a "moderate" change per the deployment recon; not a CI/CD change).

**Key snippets:**

```go
// cmd/gateway/main.go

// isNybsysUploadsPath reports whether a /custom wildcard remainder addresses the
// NanoLink PM uploads sub-tree (HLD split rule: custom/nybsys/uploads* -> DATA).
// p is c.Param("path"), e.g. "/nybsys/uploads", "/nybsys/uploads/u-42", "/nybsys/devices/d1".
func isNybsysUploadsPath(p string) bool {
    return p == "/nybsys/uploads" || strings.HasPrefix(p, "/nybsys/uploads/")
}

// customDispatchHandler splits tenant /custom traffic between SMO (device/edge ops)
// and DATA (PM uploads) per docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md §4.3.
// Dark by default: CUSTOM_UPLOADS_TARGET defaults to "smo" (zero behavior change).
func customDispatchHandler(pr *proxy.Router) gin.HandlerFunc {
    smoH := pr.ProxyHandler(pr.SMO, normalizeProxyPath)
    var dataH gin.HandlerFunc
    if pr.DATA != nil {
        dataH = pr.ProxyHandler(pr.DATA, normalizeProxyPath)
    }
    uploadsToData := strings.EqualFold(envOrDefault("CUSTOM_UPLOADS_TARGET", "smo"), "data")
    return func(c *gin.Context) {
        if uploadsToData && dataH != nil && isNybsysUploadsPath(c.Param("path")) {
            dataH(c)
            return
        }
        smoH(c)
    }
}
```

```go
// Registration (replaces registerProxy("/custom", pr.SMO, normalizeProxyPath) at main.go:234;
// /ingest and /data are plain registerProxy calls beside /utils at main.go:232):
registerProxy("/ingest", pr.DATA, normalizeProxyPath) // E1: ingestion jobs API
registerProxy("/data", pr.DATA, normalizeProxyPath)   // E1: canonical PM/FM/CM reads
if pr.SMO != nil {
    customH := customDispatchHandler(pr)
    tg.Any("/custom", customH)
    tg.Any("/custom/*path", customH)
}
```

```go
// main_test.go: predicate table test
func TestIsNybsysUploadsPath(t *testing.T) {
    cases := map[string]bool{
        "/nybsys/uploads":            true,
        "/nybsys/uploads/":           true,
        "/nybsys/uploads/u-42":       true,
        "/nybsys/uploadsfoo":         false, // prefix must be segment-bounded
        "/nybsys/devices/d1":         false,
        "/nybsys/edge-devices":       false,
        "/nybsys/commands/c1":        false,
        "":                           false, // bare /custom
    }
    for p, want := range cases {
        if got := isNybsysUploadsPath(p); got != want {
            t.Errorf("isNybsysUploadsPath(%q) = %v, want %v", p, got, want)
        }
    }
}
```

**Acceptance criteria:**
- With `CUSTOM_UPLOADS_TARGET` unset: every `/custom/**` request (including `/nybsys/uploads*`) reaches the SMO backend with `X-API-Key: $SMO_API_KEY`; observable behavior identical to pre-story gateway (byte-compat constraint §3.2).
- With `CUSTOM_UPLOADS_TARGET=data` and `DATA_BASE_URL` set: `POST/GET/DELETE .../custom/nybsys/uploads*` reach the DATA backend with `X-API-Key: $DATA_API_KEY` and the original path; `/custom/nybsys/edge-devices**`, `/custom/nybsys/devices**`, `/custom/nybsys/recommendations**`, `/custom/nybsys/commands**` still reach SMO.
- `.../ingest/uploads` and `.../data/pm` proxy to DATA with `DATA_API_KEY` injected and `RequireMembership` + `TrialWriteGuard` applied (tenant group middleware, `main.go:212-213`).
- With `CUSTOM_UPLOADS_TARGET=data` but `DATA_BASE_URL` unset: uploads fall back to SMO (no nil deref, no 500).
- No gin registration panic (E0.S1 smoke test still green with the new routes).

**Test plan:**
- Unit: `cd submodule/maveric_platform_gateway && go test ./...`. New tests: `TestIsNybsysUploadsPath` (table above); httptest-backed dispatch test with two fake upstreams (SMO records `X-API-Key`=smo-key, DATA records data-key) asserting target + header per path and per `CUSTOM_UPLOADS_TARGET` value (use `t.Setenv`); registration smoke test extended with the two new prefixes.
- Integration (lab): `./scripts/kafka/compose.sh up`; default env: `curl -s -X GET localhost:8080/v1/tenants/<tid>/custom/nybsys/uploads -H "Authorization: Bearer <jwt>"` hits smo_sim (check `./scripts/kafka/compose.sh logs smo-sim`). Set `CUSTOM_UPLOADS_TARGET=data` on the gateway service and restart (`./scripts/kafka/compose.sh restart gateway`): same call now appears in data-sim logs as a 404 (expected until E1 implements the route; the point is target selection, not response).

**Coding-agent prompt:**

```text
CONTEXT
Repo root: cloudlynet_ai (CloudlyNet backend monorepo). The Go gateway is the git submodule
submodule/maveric_platform_gateway (cd into it for git ops). The frozen re-architecture HLD is
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md; §4.3 defines the routing contract
you are implementing; §3 hard constraints apply (public API byte-compatibility, zero CI/CD
change). PREREQUISITE: the duplicate /v1/agent/*path registration fix (story E0.S1) must
already be merged; if cmd/gateway/main.go still registers /v1/agent/*path twice
(lines ~224-227 and ~247), stop and apply that fix first.

CURRENT STATE (cmd/gateway/main.go:207-248): a tenant group tg = /v1/tenants/:tenant_id with
RequireMembership + TrialWriteGuard registers prefixes via registerProxy(resource, target,
normalizeProxyPath): /bdt->pr.BDT, /rapps->pr.RAPP, /baselines->pr.SMO, /ue-data->pr.SMO,
/utils->pr.DATA, /copilot->pr.COPILOT, /custom->pr.SMO. Targets come from env BDT_BASE_URL /
RAPP_BASE_URL / SMO_BASE_URL / DATA_BASE_URL / COPILOT_BASE_URL
(internal/proxy/proxy.go:32-50); per-target X-API-Key injection is keyed by host equality in
proxy.go:73-90 (BDT_API_KEY/RAPP_API_KEY/SMO_API_KEY/DATA_API_KEY/COPILOT_BACKEND_API).

TASK (the one deliberate gateway routing change of the re-architecture; E1 consumes it):
1. Replace registerProxy("/custom", pr.SMO, normalizeProxyPath) with a dispatch handler
   registered on both tg.Any("/custom", h) and tg.Any("/custom/*path", h) (only when
   pr.SMO != nil):
   - Read env CUSTOM_UPLOADS_TARGET once at registration (default "smo", case-insensitive).
   - If it equals "data" AND pr.DATA != nil AND the wildcard remainder c.Param("path") is
     exactly "/nybsys/uploads" or has prefix "/nybsys/uploads/", proxy to pr.DATA
     (ProxyHandler(pr.DATA, normalizeProxyPath), which injects DATA_API_KEY).
   - Otherwise proxy to pr.SMO (unchanged behavior, SMO_API_KEY injected).
   - Extract the predicate into func isNybsysUploadsPath(p string) bool. It must be
     segment-bounded: "/nybsys/uploadsfoo" -> false; "" (bare /custom) -> false.
2. Add two new tenant-scoped prefixes beside /utils:
   registerProxy("/ingest", pr.DATA, normalizeProxyPath)
   registerProxy("/data", pr.DATA, normalizeProxyPath)
   These are for E1's ingestion/read APIs (POST /v1/tenants/{t}/ingest/uploads,
   GET /v1/tenants/{t}/ingest/jobs/{id}, GET /v1/tenants/{t}/data/pm|fm|cm). Do NOT add any
   handler logic for them; they are plain proxies.
3. Tests (go, stdlib + httptest, follow the style of internal/proxy/proxy_test.go
   TestProxyInjectsServiceAPIKeyHeader and cmd/gateway/main_test.go):
   - Table test for isNybsysUploadsPath (uploads root, trailing slash, child id, uploadsfoo
     false, devices false, edge-devices false, empty false).
   - Dispatch test: two httptest upstreams (fake SMO, fake DATA) capturing X-API-Key and
     path; with t.Setenv for the base URLs + keys + CUSTOM_UPLOADS_TARGET, assert:
     (a) default env -> everything under /custom to SMO; (b) CUSTOM_UPLOADS_TARGET=data ->
     /custom/nybsys/uploads/u-1 to DATA with DATA_API_KEY, /custom/nybsys/devices/d1 to SMO
     with SMO_API_KEY; (c) CUSTOM_UPLOADS_TARGET=data with no DATA_BASE_URL -> uploads to
     SMO, no panic.
   - Extend the route-registration smoke test with the /ingest and /data prefixes.

CONSTRAINTS
- Upstream request path must be preserved verbatim (normalizeProxyPath passthrough): data_sim
  will serve the legacy /v1/tenants/{t}/custom/nybsys/uploads* contract byte-compatibly.
- Default behavior (env unset) must be indistinguishable from today: all /custom to SMO.
- Do not touch: /v1/agent/** group, TrialWriteGuard (middleware.go:498+), BDT-train
  idempotency (proxy.go:135), CORS handling, any other prefix.
- No new env vars in charts, no chart/pipeline/image/port changes. The env gate lives in code
  with a safe default.
- Type-safe, idiomatic Go matching the file's existing style; comment the split rule with a
  reference to docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md §4.3.
- Commit in the submodule, one line, e.g. "[feat]: gateway: split custom/nybsys/uploads to
  DATA behind CUSTOM_UPLOADS_TARGET; add /ingest and /data prefixes". No Claude signature.

DEFINITION OF DONE
- cd submodule/maveric_platform_gateway && go build ./... && go test ./... green.
- All acceptance behaviors above demonstrated by tests; default-env behavior byte-identical.
```

---

## E0.S3 - `artifacts/design/internal-contracts.md`: shared-table ownership, S3 key contract, EFS sharing, east-west auth

**ID:** E0.S3 · **Title:** Write the internal contracts document (evidence-stamped)

**Why:** The mesh's real coupling is not HTTP: it is six shared Postgres tables read via duplicated ORM definitions, hardcoded S3 key conventions in four services, and a shared EFS volume (assessment §1.4). Frozen HLD §3.3 requires these to stay valid during the transition, so they must be written down as versioned contracts before E1/E2 move any owner.

**Size:** M

**Scope:**
- In: new doc `artifacts/design/internal-contracts.md` with the four sections below, every claim carrying a `file:line` citation gathered by grep at authoring time.
- In: a pointer to it from `artifacts/design/HLD.md` (one line in the doc index/related-docs area) and from `artifacts/README.md`-equivalent bundle table in the repo root `CLAUDE.md` is NOT needed (do not edit CLAUDE.md in this story).
- Out: any code change; any schema change (`schemas.sql` untouched); redefining §4 contracts (topic names, API routes, table names are quoted from the frozen HLD verbatim); the `.context/` graph update (E6).

**Files:**
- Create: `artifacts/design/internal-contracts.md`
- Modify: `artifacts/design/HLD.md` (add one "Related documents" line pointing at internal-contracts.md; no other edits)

**Contract (required document structure; section 1 seed rows shown - the coding agent completes and evidence-stamps every cell):**

```markdown
# Internal Contracts (east-west, storage, and data-layer)
Version: 1.0 · Status: binding during the re-architecture transition (frozen HLD §3.3)

## 1. Shared-table ownership matrix
Schema source of truth: artifacts/design/schemas.sql. RLS/trigger/index guards for ALL of
these are (re)applied at gateway boot: maveric_platform_gateway/internal/db/migrate.go:252-334.

| Table (schemas.sql line) | Writer today | Readers today | Owner after re-arch | Transition rule |
|---|---|---|---|---|
| baselines (:153) | smo_sim nybsys pipeline + /baselines API | rapp, bdt_engine (data_loader), gateway (RLS only) | bdt_engine feature builder writes new rows (HLD §4.6); smo_sim legacy writer retained until E2 | additive-only columns; no renames |
| ue_datasets (:169) | smo_sim pipeline (UE placement), data_sim synthetic factory | rapp, bdt_engine | bdt_engine feature builder + data_sim factory | additive-only |
| bdt_models (:187) | bdt_engine | rapp, gateway (RLS) | unchanged | - |
| rapp_models (:222) | rapp | gateway (RLS) | unchanged | - |
| training_jobs (:242) | rapp API/worker, bdt_engine API/worker | gateway (RLS) | unchanged | - |
| inference_runs (:272) | rapp | gateway (RLS) | unchanged | - |

(bdt_inference_runs :205 is bdt-owned and single-writer; listed for completeness.)

## 2. S3 key conventions (contract v1)
All keys are optionally wrapped by a configured bucket prefix (prefixed_key / _apply_prefix).
| Key template | Writers | Readers | Citations |
|---|---|---|---|
| {tenant_id}/baselines/{baseline_id}/topology.csv | ... | ... | rapp app/services/utils/data_loader.py:155; bdt app/services/utils/data_loader.py:142; smo app/lib/s3wrap.py:326; rapp app/workers/rapp_worker.py:642 |
| {tenant_id}/baselines/{baseline_id}/config.csv | ... | ... | rapp data_loader.py:193; bdt data_loader.py:165; rapp_worker.py:653 |
| {tenant_id}/ue/{ue_dataset_id}/synthetic_dataset.csv | ... | ... | rapp data_loader.py:232; rapp_worker.py:633 |
| {tenant_id}/ue/{ue_dataset_id}/synthetic_dataset_mobility.csv | ... | ... | rapp data_loader.py:233; rapp_worker.py:631 |
| {tenant_id}/datasets/{ue_dataset_id}/synthetic_dataset.csv (LEGACY fallback, read-only) | none | rapp, bdt | rapp data_loader.py:234; bdt data_loader.py:188-189 |
| model artifacts (rapp-worker upload; pin exact template by reading rapp_worker.py) | rapp-worker | rapp inference (download-at-first-use) | ... |
| nybsys audit CSV (smo_sim upload audit; pin via app/lib/nybsys/) | smo_sim | - | ... |
Rules: keys are append-only contracts; new artifact types add NEW templates (bump to v1.1);
never repurpose an existing template; feature-builder outputs (E2) MUST reuse the baselines/ue
templates unchanged (frozen HLD §4.6).

## 3. Shared model volume (EFS /app/var/models)
- Mounted by: rapp, rapp-worker, bdt-engine, bdt-worker (cluster: PVC efs-pvc, values.yaml
  rapp:208-215 and bdt_engine:205-212 in maveric-deployment; local: docker-compose app_volume).
- Contents: BDT GP pickles, RL agent zips. Path resolution: rapp app/utils/model_paths.py;
  fallback chain rapp app/services/utils/data_loader.py:892.
- Contract: directory layout is shared state between the two image streams; changes require a
  coordinated release of both; never store per-request temp files there.

## 4. East-west service auth (API-key pattern)
- North-south: gateway injects X-API-Key per upstream target, keyed by host equality
  (gateway internal/proxy/proxy.go:73-90; env BDT_API_KEY/RAPP_API_KEY/SMO_API_KEY/
  DATA_API_KEY/COPILOT_BACKEND_API) and X-Tenant-Id from the path (proxy.go:179).
- Service-to-service (NEW, first HTTP call inside the Python mesh): the caller holds
  <CALLEE>_BASE_URL + <CALLEE>_API_KEY and sends X-API-Key; the callee's existing
  api_key_auth dependency validates it. First instance (E2, declared here): rapp -> NDT
  (bdt_engine :8000) via NDT_BASE_URL + NDT_API_KEY added to rapp app/core/config.py
  Settings; NDT_API_KEY's value IS the bdt service key (the same secret the gateway holds
  as BDT_API_KEY). Local: NDT_BASE_URL=http://bdt-engine:8000. Cluster: the bdt-engine
  service DNS already frozen in gateway secretData. No new key material is minted.
- Edge plane (separate auth domain): X-Edge-Key, validated in smo_sim
  app/services/nybsys/edge_auth.py; gateway bypasses Cognito for /v1/agent/**.

## 5. Kafka topic index (defined in frozen HLD §4.1; listed here verbatim, never redefined)
maveric.bdt.train.v1, maveric.rapp.train.v1 (existing);
maveric.ingest.pm.v1, maveric.loop.proposal.v1, maveric.loop.action.v1,
maveric.loop.feedback.v1 (new; provisioned via existing kafka chart topics-job +
scripts/kafka/init-topics.sh; payload shapes frozen in HLD Appendix A).

## 6. Actuator/adapter key registry (quoted verbatim from frozen HLD Appendix A.4; contract of record)
One namespace shared by the loop-action `adapter` field, the proposal `target_adapter_hint`,
and every executor-side registry:
| Key | Executor | Plane |
|---|---|---|
| nanolink_tr069 | smo_sim NanoLink adapter (E4) | TR-069/CWMP device plane |
| o1_netconf | smo_sim placeholder (E4) | NETCONF/YANG via ocudu_netconf |
| ocudu_ws_collector | smo_sim collector (E4) | data plane only (no apply) |
| open_mplane | smo_sim placeholder (E4) | Open M-Plane |
| sas_domain_proxy | smo_sim placeholder (E4) | CBRS SAS Domain Proxy |
| nms_northbound | smo_sim placeholder (E4) | NMS northbound |
| a1_policy | rapp RIC layer: NONRTRIC A1-PMS connector (E3) | A1 policy intents via the open non-RT RIC |
| nearrt_xapp | RESERVED placeholder, no executor (near-RT track deferred; was flexric_xapp pre-v1.1) | xApp-mediated control |
Bare "nanolink" is NOT a valid key. New keys are added here first (with the owning epic named),
then in code.
```

**Key snippets:** (document is the deliverable; the matrix/table skeletons above are the binding shape). The rapp Settings addition it pre-declares for E2:

```python
# submodule/maveric_platform_rapp/app/core/config.py (E2 wires this; E0 documents it)
class Settings(BaseSettings):
    ...
    NDT_BASE_URL: str | None = Field(default=None, description="Network Digital Twin (bdt_engine) base URL for east-west calls")
    NDT_API_KEY: str | None = Field(default=None, description="bdt_engine service API key (same secret as gateway BDT_API_KEY)")
```

**Acceptance criteria:**
- `artifacts/design/internal-contracts.md` exists with sections 1-6 exactly as structured above; every writer/reader cell in sections 1-2 carries at least one `file:line` citation that resolves (spot-checkable via grep); section 6's adapter-key table matches HLD Appendix A.4 verbatim.
- The six tables named match frozen HLD §3.3 + task list exactly: `baselines`, `ue_datasets`, `bdt_models`, `rapp_models`, `training_jobs`, `inference_runs`.
- Kafka topic names and NDT API routes are quoted verbatim from the frozen HLD (no drift, no redefinition).
- S3 section marks `{tenant_id}/datasets/...` as legacy read-only fallback and states the append-only versioning rule.
- No em dash characters (U+2014) anywhere in the document.
- `artifacts/design/HLD.md` gains exactly one reference line; `git diff --stat` shows only these two files.

**Test plan:**
- Doc-only story; no service tests. Verification commands the author must run and paste into the PR description:
  - `grep -n "baselines/{baseline_id}" submodule/maveric_platform_rapp/app -r` (and bdt/smo equivalents) to confirm citations;
  - `grep -c $'\xe2\x80\x94' artifacts/design/internal-contracts.md` returns 0 (no U+2014);
  - `grep -n "CREATE TABLE" artifacts/design/schemas.sql` line numbers match the matrix column.

**Coding-agent prompt:**

```text
CONTEXT
Repo root: cloudlynet_ai. You are writing a design document, not code. The frozen
re-architecture HLD is docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md: read §3
(hard constraints) and §4 (shared contracts) first; you must QUOTE its contracts (topic
names, NDT routes, table names) verbatim and never redefine them. Evidence base:
docs/task_docs/cloudlynet-rearchitecture/00-hld-assessment.md §1.4 (shared-table + S3 + EFS
coupling facts).

TASK
Create artifacts/design/internal-contracts.md ("Internal Contracts", Version 1.0) with six
sections: (1) shared-table ownership matrix for baselines, ue_datasets, bdt_models,
rapp_models, training_jobs, inference_runs (+ bdt_inference_runs for completeness) - columns:
table + schemas.sql line, writer today, readers today, owner after re-arch, transition rule;
(2) S3 key conventions contract v1 - the known templates are
{tenant_id}/baselines/{baseline_id}/topology.csv, .../config.csv,
{tenant_id}/ue/{ue_dataset_id}/synthetic_dataset.csv, .../synthetic_dataset_mobility.csv,
and the LEGACY read-only fallback {tenant_id}/datasets/{ue_dataset_id}/synthetic_dataset.csv;
also pin the rapp-worker model-artifact upload key and the smo_sim nybsys audit-CSV key by
reading the code; state the append-only versioning rule; (3) shared EFS volume
/app/var/models (mounted by rapp, rapp-worker, bdt-engine, bdt-worker; BDT pickles + RL zips;
cite rapp app/utils/model_paths.py and app/services/utils/data_loader.py:892 and the
maveric-deployment values.yaml mounts); (4) east-west auth: gateway X-API-Key injection
keyed by host equality (gateway internal/proxy/proxy.go:73-90), X-Tenant-Id injection
(proxy.go:179), the NEW rapp->bdt pattern NDT_BASE_URL + NDT_API_KEY (value = the bdt
service key, the same secret the gateway holds as BDT_API_KEY; fields to be added to rapp
app/core/config.py Settings in epic E2 - document, do not implement), and the X-Edge-Key
edge-plane auth domain (smo_sim app/services/nybsys/edge_auth.py); (5) Kafka topic index
quoting frozen HLD §4.1 verbatim; (6) the actuator/adapter key registry quoted verbatim
from frozen HLD Appendix A.4 (nanolink_tr069, o1_netconf, ocudu_ws_collector, open_mplane,
sas_domain_proxy, nms_northbound, a1_policy, nearrt_xapp - the last is a RESERVED
placeholder with no executor, near-RT track deferred; bare "nanolink" invalid; this
doc is the contract of record for adapter keys).

EVIDENCE RULE
Every writer/reader/mount claim carries a file:line citation you verified by grep/Read in
this session. Starting points (verified earlier, re-confirm):
- rapp app/services/utils/data_loader.py:155,193,232-234; app/workers/rapp_worker.py:631-634,642,653
- bdt_engine app/services/utils/data_loader.py:142,165,188-189
- smo_sim app/lib/s3wrap.py:326
- schemas.sql table lines: baselines:153, ue_datasets:169, bdt_models:187,
  bdt_inference_runs:205, rapp_models:222, training_jobs:242, inference_runs:272
- gateway internal/db/migrate.go:252-334 (boot-time RLS on other services' tables)
To fill "writer today" cells, grep each service's ORM/repository layer for INSERT/session.add
on each table and cite what you find. If a cell cannot be evidenced, write "unverified" -
do not guess.

CONSTRAINTS
- Also add exactly one "Related documents" line to artifacts/design/HLD.md pointing at the
  new file. Touch nothing else. Do not edit CLAUDE.md, schemas.sql, openapi.yaml, or any code.
- No em dashes (U+2014) anywhere in the new document. Product name in prose: CloudlyNet.
  Twin naming: Network Digital Twin. Never claim O-RAN/RIC/SMO compliance anywhere.
- Commit in the PARENT repo (this is not a submodule change):
  "[docs]: add artifacts/design/internal-contracts.md (shared tables, S3 keys, EFS, east-west auth)".
  No Claude signature.

DEFINITION OF DONE
- File exists with the five sections; all citations resolve; git diff --stat shows only
  artifacts/design/internal-contracts.md and artifacts/design/HLD.md.
```

---

## E0.S4 - Repo-wide CloudlyNet rebrand of non-marketing surfaces

**ID:** E0.S4 · **Title:** Sweep NetAI to CloudlyNet in READMEs, design docs, and frontend UI strings; freeze infra identifiers

**Why:** Management renamed the product to CloudlyNet on 2026-07-16; the marketing bundle (`artifacts/marketing/`) is already renamed and `positioning.md:36` now retires the names `NetAI`, `CloudlyNet AI`, and `Cloudly Netai`. Non-marketing surfaces (frontend UI strings, service READMEs, design docs) still render the retired names and must follow, without touching frozen infra identifiers.

**Size:** L

**Scope:**
- In (parent repo docs): `README.md`, `CLAUDE.md` (naming paragraph + prose; keep all path/infra identifiers), `artifacts/design/HLD.md`, `artifacts/design/LLD.md`, `artifacts/frontend/API_Contracts.md`, `artifacts/frontend/ui-label-mapping.md`, `artifacts/frontend/UI_Design.md`, `artifacts/deployment/{HLD.md,Runbook.md,env_variable.md,production.md,staging.md,rollout_notes.md}`, `artifacts/upgrade_plans/datamigration.md`, `test/README_Postman.md`, `test/v1.5/README.md`, `.context/pages/frontend.md`, `.context/pages/copilot.md`.
- In (frontend submodule `submodule/maveric_platform_frontend`, display strings only): `app/layout.tsx:17-18` (metadata title/description), `app/(auth)/select-tenant/SelectTenantClient.tsx:19,52,62,72,113,155`, `app/(auth)/trial/page.tsx:35`, `components/app-topbar.tsx:24,29`, `components/auth/AuthHeader.tsx:18,27,36`, `components/auth/TenantForm.tsx:179,201`, `components/trial/TrialSignupForm.tsx:157,232,265,329`, `lib/trial.ts:7` (copy string only), `lib/api/client.ts:120`, `design/ui-label-mapping.md`.
- In (other submodules, prose-only doc edits): `submodule/cloudlynet_edgeagent/{README.md,Agent.md}`, `submodule/maveric_platform_gateway/README.md`, `submodule/maveric_platform_smo_sim/README.md`, `submodule/maveric-deployment/{README.md,Agent.md}` (docs only; zero chart/values/groovy edits), `submodule/cloudlynet_ai_copilot/COPILOT_IMPLEMENTATION_SUMMARY.md` prose (follow that submodule's CLAUDE.md update protocol).
- Out - the FREEZE LIST (identifiers that keep the `netai` string, per deployment freeze and data compatibility):
  - domain `<platform-host>` / `staging.<platform-host>` (ingress hosts; docs reference them as-is),
  - trial tenant identifiers: `lib/trial.ts:1-2` `TRIAL_TENANT_NAME = "NetAI Trial"`, `TRIAL_TENANT_SLUG = "netai-trial"` (match live gateway DB rows), gateway env `NETAI_TRIAL_ORG_UUID` (`cmd/gateway/main.go:134,156`),
  - image/chart/release names (`cloudlyio/*`, `maveric-*`), ports, namespaces,
  - copilot DB `netai_copilot`, minio bucket `netai-copilot-files`,
  - frontend persisted-state key `lib/store/index.ts:49,69` `"netai-app-store"` (renaming resets user UI state),
  - asset filename `public/cloudly-netai.png` (keep file; change `alt` text where referenced),
  - `artifacts/marketing/**` (already renamed; owned by marketing rules, not this story), `artifacts/legacy/**` and `COPILOT_HISTORY.md` (historical archives, untouched), `docs/task_docs/**` (local planning docs).

**Files:** as listed in Scope (exact line references from grep on 2026-07-16; re-grep before editing).

**Contract (string mapping):**

| Old (retired) | New | Where |
|---|---|---|
| `NetAI by Cloudly` (lockup) | `CloudlyNet` (product), `Cloudly / CloudlyIO` (company) | all prose |
| `NetAI` (product mentions) | `CloudlyNet` | all prose + UI strings not in freeze list |
| `CloudlyNet AI`, `Cloudly Netai`, `Cloudly NetAI` | `CloudlyNet` | UI strings (`TenantForm.tsx`, `AuthHeader.tsx`, `SelectTenantClient.tsx`, `layout.tsx:18`, `lib/trial.ts:7`) |
| `Network Digital Twin` | unchanged (mandated solution term) | everywhere |
| Freeze-list identifiers | unchanged | see Scope/Out |

UI copy rules (marketing-bound text): no em dashes (U+2014), humanized sentence-case headings, never claim O-RAN/RIC/SMO compliance, per `artifacts/marketing/claims-guardrails.md` and the marketing copy rules. `CLAUDE.md` naming paragraph becomes: product **CloudlyNet**, company **Cloudly / CloudlyIO**, Maveric is upstream OSS (BDT only); never `NetAI` (retired 2026-07-16), `CloudlyNet AI`, `Cloudly Netai`, or `Maveric Platform` in customer-facing surfaces.

**Key snippets:**

```tsx
// submodule/maveric_platform_frontend/app/layout.tsx:17-18
export const metadata: Metadata = {
	title: "CloudlyNet",
	description: "CloudlyNet by Cloudly",
```

```ts
// submodule/maveric_platform_frontend/lib/trial.ts
// FREEZE: these two constants key live gateway DB rows (tenants.name/slug); renaming them
// breaks trial-tenant lookup. Display copy is rebranded separately below.
export const TRIAL_TENANT_NAME = "NetAI Trial"; // do not change (data contract)
export const TRIAL_TENANT_SLUG = "netai-trial"; // do not change (data contract)
...
export const TRIAL_CONTACT_COPY =
	"Book a call with our team and we'll set up a CloudlyNet workspace for your organization.";
```

Verification gate (run at repo root and in each touched submodule):

```bash
grep -rn "NetAI\|Cloudly Netai\|CloudlyNet AI" --include='*.md' --include='*.ts' --include='*.tsx' . \
  | grep -v node_modules | grep -v artifacts/marketing | grep -v artifacts/legacy \
  | grep -v COPILOT_HISTORY | grep -v docs/task_docs | grep -v '/.agent/' \
  `# meta-docs: these must NAME the retired brand in order to forbid or describe the rename` \
  | grep -v '/epics/EPIC-' | grep -v '02-execution-guide' | grep -v 'AUDIT-2026-07-29' \
  | grep -v '\./CLAUDE\.md' \
  `# freeze list, plus two classes discovered on 2026-07-29 (see note below)` \
  | grep -v "<platform-host>\|netai-trial\|NetAI Trial\|NETAI_TRIAL\|netai_copilot\|netai-copilot-files\|netai-app-store\|cloudly-netai.png" \
  | grep -v "Projects/NetAI" \
  | grep -v "| NetAI (topbar)"
# expected: empty
```

> **Gate correction (2026-07-29, applied while implementing this story).** As originally written
> the gate could never return empty, for two reasons that have nothing to do with the rename:
>
> 1. **The repo's own filesystem path contains the retired name.** The working checkout lives at
>    `~/Projects/NetAI/cloudlynet_ai`, so every doc that cites an absolute path matches the grep
>    (7 hits, all in `EPIC-6`). Excluded via `Projects/NetAI`.
> 2. **Some documents must name the retired brand to do their job.** `CLAUDE.md`'s naming rule
>    (`Never "NetAI", "CloudlyNet AI", ...`), this story's own contract table, `EPIC-6`, `EPIC-8`,
>    and the upgrade-plan audit all quote the retired names deliberately. Renaming them would
>    destroy the rule. Excluded by path.
>
> One content exclusion is also deliberate: in `ui-label-mapping.md` the table is
> `| current label | new label | notes |`, so the row `| NetAI (topbar) | CloudlyNet | Brand
> rename |` documents the rename itself and column 1 must keep the old string. The sibling row
> `| Trial Signup | NetAI trial access |` was NOT exempt (column 2 is the *new* label) and was
> renamed.

**Acceptance criteria:**
- The verification grep above returns empty at repo root and in each touched submodule.
- Every freeze-list identifier is byte-unchanged (grep for each still hits the same files/lines).
- Frontend builds and lints: `npm run lint` clean; `npx tsc --noEmit` clean (or `npm run build` succeeds).
- No file under `artifacts/marketing/`, `artifacts/legacy/`, or `maveric-deployment/argocd|jenkins` is modified.
- UI strings contain no em dash (U+2014) and no compliance claims (O-RAN, RIC, SMO, carrier grade).
- `.context/pages/{frontend,copilot}.md` updated with refreshed stamps; `python .claude/skills/context-agent/tools/graph_check.py .context` passes.

**Test plan:**
- Frontend: `cd submodule/maveric_platform_frontend && npm run lint && npx tsc --noEmit`; manual smoke of `/` (topbar brand), `/select-tenant`, `/trial` pages via `npm run dev` confirming rendered copy says CloudlyNet.
- Gateway/Go and Python services: no code strings changed (docs only), so `go test ./...` in gateway and `uv run pytest` in smo-sim are regression-only, run once to confirm no accidental source edits.
- Repo-wide: the verification grep gate; `git diff --stat` per repo reviewed against the Files list.

**Coding-agent prompt:**

```text
CONTEXT
Repo root: cloudlynet_ai (CloudlyNet backend monorepo with git submodules under submodule/;
always cd into a submodule before git operations there - each touched submodule gets its own
commit/PR). Management renamed the product to CloudlyNet on 2026-07-16. The marketing bundle
artifacts/marketing/ is ALREADY renamed (do not touch it); artifacts/marketing/positioning.md
line 36 retires the names "NetAI", "CloudlyNet AI", "Cloudly Netai". Frozen HLD
docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md §3.4: product name CloudlyNet,
solution term Network Digital Twin. Read artifacts/marketing/claims-guardrails.md before
writing ANY user-facing string; marketing copy rules: no em dashes (U+2014), humanized
headings, never claim O-RAN/RIC/SMO compliance or "carrier grade".

TASK
Sweep the retired names NetAI / NetAI by Cloudly / CloudlyNet AI / Cloudly Netai ->
CloudlyNet on non-marketing surfaces. First re-run the discovery greps to get current lines:
  grep -rn "NetAI\|Netai\|netai" --include='*.md' . | grep -v node_modules
  (repo root and each submodule; plus *.ts/*.tsx in the frontend)
Then edit:
1. Parent repo docs: README.md; CLAUDE.md (rewrite the product-naming paragraph: product
   CloudlyNet, company Cloudly/CloudlyIO, Maveric = upstream OSS for the BDT only; forbidden:
   NetAI (retired 2026-07-16), CloudlyNet AI, Cloudly Netai, Maveric Platform; keep all other
   CLAUDE.md content intact); artifacts/design/HLD.md, LLD.md; artifacts/frontend/
   API_Contracts.md, ui-label-mapping.md, UI_Design.md; artifacts/deployment/HLD.md,
   Runbook.md, env_variable.md, production.md, staging.md, rollout_notes.md;
   artifacts/upgrade_plans/datamigration.md; test/README_Postman.md; test/v1.5/README.md;
   .context/pages/frontend.md, .context/pages/copilot.md (refresh their freshness stamps,
   then run: python .claude/skills/context-agent/tools/graph_check.py .context).
2. Frontend submodule submodule/maveric_platform_frontend (display strings only):
   app/layout.tsx:17-18 -> title "CloudlyNet", description "CloudlyNet by Cloudly";
   app/(auth)/select-tenant/SelectTenantClient.tsx (lines ~19,52,62,72,113,155);
   app/(auth)/trial/page.tsx:35 (alt text); components/app-topbar.tsx:24,29;
   components/auth/AuthHeader.tsx:18,27,36; components/auth/TenantForm.tsx:179,201;
   components/trial/TrialSignupForm.tsx:157,232,265,329; lib/trial.ts:7 (copy string only);
   lib/api/client.ts:120 ("...associated with a CloudlyNet account.");
   design/ui-label-mapping.md.
3. Other submodules, prose-only: cloudlynet_edgeagent README.md + Agent.md;
   maveric_platform_gateway README.md; maveric_platform_smo_sim README.md;
   maveric-deployment README.md + Agent.md (DOCS ONLY: zero edits under argocd/ or jenkins/);
   cloudlynet_ai_copilot COPILOT_IMPLEMENTATION_SUMMARY.md prose (read that submodule's
   CLAUDE.md first and follow its update protocol; leave COPILOT_HISTORY.md untouched).

FREEZE LIST - these strings stay byte-identical everywhere (infra/data identifiers frozen by
the deployment repo policy and live data):
  <platform-host> and staging.<platform-host> (ingress hosts);
  TRIAL_TENANT_NAME "NetAI Trial" and TRIAL_TENANT_SLUG "netai-trial" in
  frontend lib/trial.ts:1-2 (they match live gateway DB tenant rows - add a code comment
  "do not change (data contract)"); gateway env NETAI_TRIAL_ORG_UUID
  (submodule/maveric_platform_gateway/cmd/gateway/main.go:134,156); Docker/chart/release
  names (cloudlyio/*, maveric-*); copilot DB netai_copilot; minio bucket netai-copilot-files;
  frontend persisted-store key "netai-app-store" (lib/store/index.ts:49,69); asset filename
  public/cloudly-netai.png (keep the file, fix alt texts referencing it).
Also untouched: artifacts/marketing/**, artifacts/legacy/**, docs/task_docs/**,
COPILOT_HISTORY.md, any .groovy/values.yaml/chart template.

VERIFICATION GATE (must be empty before you finish; run at repo root and per submodule):
  grep -rn "NetAI\|Cloudly Netai\|CloudlyNet AI" --include='*.md' --include='*.ts' \
    --include='*.tsx' . | grep -v node_modules | grep -v artifacts/marketing \
    | grep -v artifacts/legacy | grep -v COPILOT_HISTORY | grep -v docs/task_docs \
    | grep -v "<platform-host>\|netai-trial\|NetAI Trial\|NETAI_TRIAL\|netai_copilot\|netai-copilot-files\|netai-app-store\|cloudly-netai.png"

DEFINITION OF DONE
- Verification gate empty; freeze-list strings unchanged (spot-check each).
- cd submodule/maveric_platform_frontend && npm run lint && npx tsc --noEmit both clean.
- graph_check.py passes on .context.
- One commit per repo, concise messages, e.g. "[docs]: rebrand NetAI -> CloudlyNet on
  non-marketing surfaces (infra identifiers frozen)". No Claude signature. Do NOT stage
  submodule pointer bumps in the parent repo commit.
```

---

## E0.S5 - Secrets hygiene: rotate exposed credentials, propose SOPS/sealed-secrets (flagged security follow-up)

**ID:** E0.S5 · **Title:** Minimal first step on secrets-in-git: inventory, rotation checklist, encryption proposal

**Why:** The deployment recon verified real credentials committed as base64 `secretData` in `maveric-deployment` chart `values.yaml` files (Postgres DSN with password, Mongo root password, copilot DB creds, AWS keys, Cognito client secret) and Google Chat webhook tokens inline in all 15 Jenkins groovy files. Base64 is not encryption; this is a standing exposure that any epic churn multiplies. This story is deliberately minimal: document, rotate, propose; no chart renames, no pipeline changes.

**Size:** S

**Scope:**
- In: a security note `artifacts/deployment/secrets-hygiene.md` containing (a) the exposure inventory (which values.yaml blocks and groovy files, by path; never paste secret values), (b) a rotation checklist ordered by blast radius (Google Chat webhook tokens, Cognito client secret, AWS keys, DB passwords last since they require coordinated restarts), (c) a proposal comparing SOPS (age key, encrypt `secretData` values in place, decrypt in a pre-sync step) vs Bitnami sealed-secrets (new CRD controller), with the recommendation that fits the zero-CI/CD-change mandate (SOPS in-place encryption of values, since sealed-secrets changes manifest kinds), and (d) an interim handling rule (repo stays private; no new plaintext secrets; new secrets enter via the chosen tool only).
- In: flag in the doc that execution of rotation is an ops action outside the repo (Cognito/AWS consoles, Jenkins credential store) with named owner TBD.
- Out: any edit to `values.yaml`, groovy pipelines, charts, or templates (zero CI/CD change); actually performing rotation (ops runbook item, not a code change); renaming anything; adding CI secret scanning (proposed in the doc as follow-up, not implemented).

**Files:**
- Create: `artifacts/deployment/secrets-hygiene.md`
- Modify: `artifacts/deployment/Runbook.md` (add one line linking the new doc under an "open security actions" note)

**Contract (document outline):**

```markdown
# Secrets Hygiene (flagged security follow-up)
Status: exposure documented 2026-07-16; rotation pending (ops)
## 1. Exposure inventory (paths only, no values)
- maveric-deployment argocd/*/values.yaml secretData blocks: gateway (AWS+Cognito keys,
  POSTGRES_DSN, per-service API keys), bdt-engine/-worker, rapp, data-sim, smo-sim,
  frontend (COGNITO_CLIENT_SECRET), copilot (+ copilot-migration owner creds); plus
  cluster-shared regcred, postgres-secret, mongo-auth-secret.
- jenkins/*.groovy: Google Chat webhook keys/tokens inline (15 files).
## 2. Rotation checklist (ordered, with restart coordination notes)
## 3. Encryption-at-rest proposal: SOPS (recommended) vs sealed-secrets, with migration steps
   that keep chart names, release names, and pipelines unchanged
## 4. Interim rules (no new plaintext secrets; PR review gate; repo visibility)
```

**Key snippets:** n/a (doc-only; outline above is binding).

**Acceptance criteria:**
- `artifacts/deployment/secrets-hygiene.md` exists with sections 1-4; inventory cites file paths (not values); recommendation explicitly preserves chart/release/pipeline names and namespaces (zero CI/CD change).
- No secret value, decoded or encoded, appears in the new doc or in any diff.
- `git diff --stat` shows only the two files in Files.
- The doc carries a "SECURITY FOLLOW-UP" banner and a rotation-owner placeholder so it surfaces in review.

**Test plan:**
- Doc-only. Reviewer checks: `grep -c "secretData" artifacts/deployment/secrets-hygiene.md` > 0 (inventory present); `git diff` contains no base64 blobs (`grep -E "[A-Za-z0-9+/=]{40,}"` on the diff returns nothing).

**Coding-agent prompt:**

```text
CONTEXT
Repo root: cloudlynet_ai. The delivery repo is the submodule submodule/maveric-deployment
(Helm charts under argocd/, 15 Jenkins pipelines under jenkins/). A code recon verified:
(a) chart values.yaml "secretData" blocks contain real base64-encoded credentials (Postgres
DSN with password, Mongo root password, copilot owner/app passwords, AWS keys, Cognito
client secret) on both production (maveric_*) and staging (staging-maveric_*) tracks;
(b) all jenkins/*.groovy files embed Google Chat webhook keys/tokens inline. Base64 is not
encryption. Hard constraint from docs/task_docs/cloudlynet-rearchitecture/01-hld-frozen.md
§3.1: zero CI/CD change (no chart/pipeline/image/port renames). Repo policy additionally
forbids renaming charts/releases (maveric-deployment design/Naming_and_Environment_Mapping.md).

TASK (documentation only; you must NOT edit any values.yaml, groovy, or template file):
Create artifacts/deployment/secrets-hygiene.md in the PARENT repo with:
1. Exposure inventory: enumerate by file path (submodule/maveric-deployment/argocd/<chart>/
   values.yaml secretData; jenkins/<file>.groovy webhook lines) - list paths and secret KINDS
   only; NEVER paste, decode, or re-encode a secret value into the doc or the diff.
2. Rotation checklist ordered by blast radius and coordination cost: (i) Google Chat webhook
   tokens (Jenkins credential store migration), (ii) Cognito client secret (gateway +
   frontend restart), (iii) AWS access keys (S3/SES consumers), (iv) internal service API
   keys (gateway + all five services, coordinated), (v) DB passwords last (all consumers +
   copilot migration creds). Each item: where it lives, who consumes it, restart order.
3. Proposal: SOPS (age) in-place encryption of secretData values vs Bitnami sealed-secrets.
   Recommend the option that requires zero chart renames, zero new pipelines, and zero
   manifest-kind changes (SOPS fits; sealed-secrets changes Secret manifests to SealedSecret
   CRDs - explain the tradeoff). Include a stepwise adoption plan that keeps ArgoCD apps,
   chart paths, release fullnames, namespaces, and the 15 pipelines untouched.
4. Interim rules: no new plaintext secrets in git; secrets-bearing PRs flagged; repo stays
   private; proposed (not implemented) CI secret-scanning follow-up.
Add a "SECURITY FOLLOW-UP - rotation owner: TBD" banner at the top. Then add one line to
artifacts/deployment/Runbook.md linking this doc under open security actions.

DEFINITION OF DONE
- git diff --stat shows exactly artifacts/deployment/secrets-hygiene.md and
  artifacts/deployment/Runbook.md; the diff contains no base64-looking blobs
  (self-check: grep -E "[A-Za-z0-9+/=]{40,}" on your diff -> no matches).
- Commit (parent repo): "[docs]: secrets-hygiene exposure inventory + rotation/SOPS proposal".
  No Claude signature.
```

---

## Rollout / migration notes

1. **Order:** E0.S1 first (everything else in the gateway stacks on it), then E0.S2. E0.S3, E0.S4, E0.S5 are independent of each other and of S2, and can run in parallel after S1. E1 must not start its gateway-dependent stories until S2 is merged.
2. **Gateway deploy note:** deployed gateway images predate the panic commit, so the first image built after S1/S2 jumps several commits at once. Ship via the normal Jenkins flow to the staging track first, verify `GET /v1/health`, an authenticated `/custom/nybsys/uploads` round-trip (still SMO), and an edge-agent `poll` against `/v1/agent/**` before the production-track build. No pipeline or chart change is needed: the new `CUSTOM_UPLOADS_TARGET` env defaults to `smo` in code.
3. **Backward-compat shims:** the `/custom` split ships dark (`CUSTOM_UPLOADS_TARGET=smo` default). E1 flips it to `data` via a gateway chart `secretData` value edit (moderate-cost change per the deployment recon; not CI/CD). Rollback = flip the value back; no code revert needed. `/ingest/**` and `/data/**` 502/404 harmlessly until E1 lands the data_sim endpoints (they are new paths no client uses yet).
4. **Data migration:** none in this epic. The rebrand deliberately keeps the trial-tenant name/slug (`NetAI Trial` / `netai-trial`) matching live DB rows; renaming those rows (and the display name users see in tenant pickers) is an ops/data task to schedule with E6, not a code change here.
5. **Submodule commits:** gateway (S1, S2), frontend + edge agent + smo_sim + deployment + copilot (S4) each commit in their own submodule; parent-repo commits (S3, S4-parent, S5) must not stage submodule pointer bumps (CLAUDE.md commit convention).

## Epic-level risks

- **Naming-rule collision:** `CLAUDE.md` and some marketing files were authored under the "NetAI by Cloudly" mandate; the 2026-07-16 rename inverts it (`positioning.md` now retires `NetAI`). S4 updates CLAUDE.md's naming paragraph; until merged, tooling reading CLAUDE.md will give contributors stale naming guidance. Merge S4's parent-repo commit early.
- **Freeze-list leakage:** an over-eager rebrand that touches `netai-trial`, `NETAI_TRIAL_ORG_UUID`, `netai_copilot`, `netai-copilot-files`, `netai-app-store`, or `<platform-host>` breaks trial login, copilot DB access, or persisted UI state. The grep gate plus explicit code comments on `lib/trial.ts` mitigate.
- **Gateway HEAD gap:** because deployed images are older than HEAD, the first post-E0 gateway release carries unrelated merged-but-never-deployed changes (PR #23 and later). Staging-track soak (rollout note 2) is the mitigation; if a regression surfaces, it may not be from E0's diff.
- **Split-rule drift:** if E1 changes the uploads API shape or adds new sub-paths under `/custom/nybsys/uploads`, the segment-bounded predicate in `isNybsysUploadsPath` still routes them to DATA (prefix rule), but any NEW smo_sim route accidentally named `uploads*` would be misrouted. The internal-contracts doc records the split rule; E1/E4 authors must check it before adding `/custom` routes.
- **Ownership-matrix accuracy:** S3's writer/reader cells depend on grep evidence; duplicated ORM definitions across services make it easy to misattribute a writer. The "unverified" cell rule prevents silent guesses, but E1/E2 should re-verify cells they build on.
- **Secrets story is only a first step:** documenting the exposure without prompt rotation arguably increases risk (the doc points at the paths). Keep `secrets-hygiene.md` free of values, keep the repos private, and treat rotation as an ops action with a named owner before E1 chart edits multiply the churn on those files.
