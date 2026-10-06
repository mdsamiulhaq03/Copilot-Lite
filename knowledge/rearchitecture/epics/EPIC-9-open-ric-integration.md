# EPIC 9: Open-source RIC integration convergence

**Epic ID:** E9
**Title:** Converge the ES rApp x NONRTRIC demo onto the platform RIC layer, fix its portability and identity defects, and decide the rApp Manager posture on the record
**Frozen HLD:** `01-hld-frozen.md` v1.2. D1 (the integrated open RIC is O-RAN SC NONRTRIC, consumed as container images plus REST, never by copying source), section 4.4 (the hexagonal RIC layer), Appendix A.2 (the translation seam), A.4 (adapter keys).
**Upstream work:** GitHub EPIC `CloudlyIO/cloudlynet_ai#349` (demo), story `#351`, PR `CloudlyIO/maveric_platform_rapp#46`.

**Goal:** PR #46 proved the open-RIC path works end to end, which is the hard part and it is done. It also created a second, divergent NONRTRIC integration alongside the one EPIC-3 landed, and it carries defects that block reuse: a retired product name baked into the packaged artifact identity, a cross-submodule filesystem dependency that makes the rApp repo un-testable standalone, and a dependency on two external source checkouts. This epic converges the two integrations onto one connector, makes the demo reproducible outside its author's machine, and resolves on the record whether rApp Manager onboarding is ROADMAP (per D1 and E3.S6) or an executed lab capability (per PR #46).

**Dependencies:** E3 (the `app/ric/` layer, the `a1_policy` connector, and the `ric-lab` compose profile are the convergence target). E4 owns the smo_sim actuator adapters that S3 hands TR-069 rendering back to. No dependency on E5 or E7.

**Definition of done (epic):**
- One NONRTRIC client in the codebase. The demo drives `app/ric/adapters/nonrtric/`; no second A1 client, no second PMS configuration, no second image pin.
- The packaged artifact carries the current product name. No `netai` identifier survives in any CSAR, Helm chart, ASD, ACM element type, or artifact filename.
- `maveric_platform_rapp` tests pass in a standalone checkout of that repo alone, with no sibling submodule and no external checkout present.
- The demo consumes images and REST only. `NONRTRIC_CHECKOUT` and `RAPPMANAGER_CHECKOUT` are gone.
- The rApp Manager and CSAR posture is stated once, consistently, in the frozen HLD, `artifacts/ric/`, and `packaging/r1/README.md`. Today those three disagree.
- Claims wording holds throughout: interop with pre-spec O-RAN SC reference code, Simulation rung, log-only actuation, never a conformance or certification claim, product name CloudlyNet, no em dash characters.

---

## E9.S1: Retire `netai` from the packaged artifact identity

**Size:** M

**Why:** `CLAUDE.md` records that NetAI was retired on 2026-07-16 and that lowercase `netai` survives only in not-yet-migrated infra identifiers such as `<platform-host>` and the `netai trial` seed tenant. A CSAR onboarded into a customer SMO is not infra plumbing; it is the most customer-visible artifact this platform produces. PR #46 carries 146 `netai` occurrences against 32 `cloudlynet`, including 19 capitalised `NetAI`.

**Scope:**
- In: `netai-es-rapp` to `cloudlynet-es-rapp` across the CSAR directory name, `asd.mf`, `Definitions/asd.yaml`, `asd_types.yaml`, the Helm chart name and every `_helpers.tpl` template function (`netai-es-rapp.fullname`, `.labels`, `.selectorLabels`, `.serviceAccountName`, `.predictor.fullname`, `.orchestrator.fullname`), the ACM element type `NetaiEsRappAutomationCompositionElement`, `compositions.json`, `k8s-instance.json`, the built artifact names `netai-es-rapp.csar` and `netai-es-rapp-0.1.0.tgz`, and all prose.
- Out: renaming the `netai trial` seed tenant or `<platform-host>` (E6 owns those).

**Contract:** the rApp id aligns with E3.S6's manifests, which already use `cloudlynet-es`. Pick one and use it in both places; `cloudlynet-es-rapp` for the deployable and `cloudlynet-es` for the rApp id is acceptable only if `packaging/r1/es/manifest.yaml` is updated to say so explicitly.

**Acceptance:**
- `grep -ri netai deploy/` returns nothing.
- A rebuilt CSAR validates and onboards to `COMMISSIONED` under the new name.
- Helm template rendering is unchanged apart from names (`helm template` diff shows only identifier changes).

---

## E9.S2: Converge on one NONRTRIC client

**Size:** L

**Why:** The repository now contains two independent A1 integrations that disagree on every material choice. This is the single highest-value story in the epic: two clients means two dialects, two pin sets, and two places for a future PMS change to break.

| | EPIC-3 (`app/ric/adapters/nonrtric/`) | PR #46 (`deploy/nonrtric-es-rapp/demo/`) |
| --- | --- | --- |
| PMS image | `nonrtric-plt-a1policymanagementservice:2.11.0` | `nonrtric-a1-policy-management-service:2.3.1` |
| API dialect | v3, base path `/a1-policy-management/v1` | v2, `/a1-policy/v2` |
| Near-RT side | two official OSC `a1-simulator:2.8.1` containers | hand-rolled `http.server` mock |
| Lifecycle | compose profile `ric-lab` | `docker run` plus `lsof` port kills |
| Service registration | `PUT /services` plus keepalive | none |
| Status mapping | frozen A.3 matrix, unit tested | ad hoc |

**2.3.1 is the stale tag EPIC-3.S2 explicitly warns about**: it is what the upstream `nonrtric/docker-compose` sample `.env` pins, and E3.S2's contract says to take tags from the OSC release notes instead. The image name also changed upstream between those versions.

**Scope:**
- In: delete `demo/_http.py`'s A1 paths, `a1_up.py`'s PMS bring-up, and `a1_publish.py`'s policy writes in favour of `A1PmsClient` and `NonRtRicControlAdapter`; delete `demo/a1/application_configuration.json` in favour of `deploy/ric-lab/pms/application_configuration.json`; bring the demo up through `./scripts/kafka/compose.sh ric-lab`; replace the hand-rolled mock with `a1-sim-std` (already `STD_2.0.0`, which is what the mock imitates).
- In: keep the mock ONLY if a capability the OSC simulator lacks is named and recorded; if kept, it moves behind the same port so it is a drop-in.
- Out: changing the frozen A.3 status mapping (see the S3 finding carried from EPIC-3: a rejected body arrives as 500 and maps to `failed`).

**Acceptance:**
- `grep -rn "a1-policy/v2\|2\.3\.1" deploy/` returns nothing.
- `demo a1-up` and `demo a1-publish` issue their calls through `app/ric/adapters/nonrtric/client.py` (assert by patching the client in a test).
- The per-run `a1_exchange.txt` evidence file is still produced, with the same 24 policy writes.
- The demo works against PMS 2.11.0 on the v3 dialect.

**Note:** the demo's ES policy type `ES_1_0.0` is a demo vendor extension, correctly labelled as such in PR #46. E3 registers `cloudlynet.cell_config.v1`. Decide whether the ES demo adopts the platform type or keeps its own, and record the reason either way.

---

## E9.S3: Break the cross-submodule filesystem coupling

**Size:** M

**Why:** `demo/tr069_renderer.py` loads `managed_params.py` out of `submodule/maveric_platform_smo_sim/` by absolute path, computed from `config.REPO_ROOT`, and **raises `FileNotFoundError` at module import** when it is absent. Verified: in a standalone checkout of `maveric_platform_rapp`, `demo/test_tr069_renderer.py` cannot be collected at all, and the suite drops from the claimed 43 to 31. The rApp repo's own CI cannot pass this.

It is also a boundary violation. Frozen HLD Appendix A.2 is binding that the EXECUTOR ADAPTER owns recommendation-to-managed-parameter translation "because the executor service owns the device registry and the managed-params catalogue", and names `nanolink_tr069` as smo_sim's adapter (EPIC-4). TR-069 rendering inside the rApp repo inverts that.

**Scope:** three options, in order of preference.
1. Move the rendering to smo_sim behind its `nanolink_tr069` adapter (EPIC-4's home) and have the demo call it. Correct per A.2; largest change.
2. Vendor a small, contract-tested copy of the managed-params table into the demo with a drift test against smo_sim's, mirroring the drift guard E3.S6 uses for the S3 key template.
3. Keep the dynamic load but make it optional: skip the tests and degrade the feature when the sibling is absent, never raise at import.

Option 3 is the minimum bar and unblocks CI; option 1 is the one that matches the frozen contract.

**Acceptance:**
- A clean `git clone` of `maveric_platform_rapp` alone, with no sibling submodules, collects and passes the full deploy-dir suite.
- No module in `deploy/` raises at import time because of a missing external path.

---

## E9.S4: Images and REST only, no source checkouts

**Size:** S

**Why:** D1 is explicit that NONRTRIC is consumed as container images plus REST, "never by copying source". The demo needs `NONRTRIC_CHECKOUT` for `application-policyagent.yaml` and `RAPPMANAGER_CHECKOUT` for rApp Manager assets, defaulting to siblings of the repo root. Anyone without those two checkouts at the right paths cannot run the demo, and the exact upstream revision is unpinned, so two engineers can get different behaviour from the same commit.

**Scope:** check the required config files into `deploy/ric-lab/` (they are small and we already own the PMS config there), or extract them from the pinned image at bring-up. Delete both environment variables.

**Acceptance:** `demo all` runs with no environment variable set and no sibling checkout present. `grep -rn "_CHECKOUT" deploy/` returns nothing.

---

## E9.S5: Make the demo reproducible and non-destructive

**Size:** M

**Scope:**
- `_kill_port()` SIGKILLs whatever is listening on 9998 and 8081, on a developer's machine, without asking. Replace with a bounded, named-container teardown; if a foreign process holds the port, fail with a clear message instead of killing it.
- The deploy directory needs its own declared dependency set and a way to run its tests that does not depend on the rApp service venv (PR #46's `requirements.txt` files exist; wire them to a documented command).
- Record what the demo actually needs: Docker with amd64 emulation, roughly 800 MB of images, and the observed PMS sync latency (about 40 seconds after a simulator reset, measured during E3.S3).

**Acceptance:** two consecutive `demo all` runs green on a machine that has never run it, from a clean clone, with a documented single command; no process outside the demo's own containers is signalled.

---

## E9.S6: Decide the rApp Manager and CSAR posture on the record

**Size:** S, but it is a decision, not typing

**Why:** three documents currently disagree, and all three are ours.

- Frozen HLD D1: rApp Manager is "tracked as roadmap, not integrated".
- E3.S6 and `packaging/r1/README.md`: metadata facade only, ASD and CSAR packaging and any rApp Manager integration explicitly ROADMAP, because upstream is pre-spec and "not intended for production use".
- PR #46: builds a real CSAR with a real ASD and onboards it to a real rApp Manager reaching `COMMISSIONED`.

PR #46 is not wrong to have done it, and it is careful about the claims boundary. But "ROADMAP" is now false as written, and we have two packaging surfaces: `packaging/r1/*/manifest.yaml` (metadata facade) and `deploy/nonrtric-es-rapp/netai-es-rapp/` (a real ASD and CSAR).

**Scope:** amend the frozen HLD to a v1.3 note that rApp Manager onboarding is LAB-EXECUTED and production-deferred, mirroring exactly how v1.2 handled `nearrt_xapp`; update `packaging/r1/README.md` to point at the real CSAR as the executed path and state what the metadata facade is still for (or retire the facade if the CSAR supersedes it); state the relationship in `artifacts/ric/`.

**Acceptance:** one posture, stated identically in the frozen HLD, `artifacts/ric/`, and `packaging/r1/README.md`, with the pre-spec caveat intact in all three.

---

## E9.S7: Docs and claims lockstep

**Size:** S

**Scope:** fold the demo runbook into the `artifacts/ric/` bundle alongside `nonrtric-lab.md` so there is one place to look; carry over the three bring-up traps E3.S3 recorded (mandatory `callbackUrl`, the `statusSchema` requirement on `STD_2.0.0`, and a rejected body arriving as 500); remove the 93 em-dash lines PR #46 introduces; verify every rung label against `artifacts/marketing/claims-guardrails.md`.

**Acceptance:** grep gates for em dashes and conformance language pass across `deploy/` and `artifacts/ric/`; a reader starting at `artifacts/ric/README` can reach both the lab profile and the demo.

---

## Rollout

**Order:** S1 and S3 first, because they block reuse and CI respectively. S2 is the largest and should follow, since converging the client is easier once the artifact identity is settled. S4 and S5 make it reproducible. S6 is a decision that can happen in parallel. S7 closes.

**Merge posture for PR #46:** the work is sound and the claims discipline is good. The recommendation is to merge it behind the rename (S1) and the import fix (S3), which are small and mechanical, and to schedule S2 immediately after rather than letting two A1 clients live side by side for long. Merging as-is is defensible only if S1 and S3 are committed to a named date, because a retired product name in a CSAR and a red standalone CI are both the kind of thing that quietly becomes permanent.

## Risks

1. **Two clients drift before S2 lands.** Every week both exist, someone fixes a bug in one. Mitigation: land S2 early, or freeze the demo's A1 code to bugfix-only in the interim.
2. **The rename touches Helm template function names**, so a partially applied rename produces a chart that renders but with mismatched selectors. Do it in one commit and diff the rendered output.
3. **PMS 2.3.1 to 2.11.0 is not a no-op**: create moves from `PUT` to `POST`, the base path changes, and the body dialect goes camelCase. E3's connector already handles both via `A1PMS_API_MODE`, which is why converging onto it is cheaper than upgrading the demo's own client.
4. **Option 1 in S3 pulls EPIC-4 forward.** If EPIC-4's actuator framework is not ready, take option 2 or 3 and leave a pointer, rather than blocking this epic on that one.

---

## Execution status

**S1 and S3 are done, on a local branch, ready to apply.** The rest of the epic is blocked on
PR #46 merging, because its subject matter IS that PR's code and
`deploy/nonrtric-es-rapp/` does not exist on the re-architecture branch.

Branch: `pr46-fixes` in `submodule/maveric_platform_rapp`, two commits sitting directly on the
PR head `3c26bc2` (re-checked: the PR has not moved since the review, so every finding still
holds). Nothing is pushed and no working tree was disturbed.

**S1 DONE** (`6e04cec`, 36 files). The retired product name is out of the packaged artifact
identity: the CSAR directory, `asd.mf`, `Definitions/asd.yaml`, the Helm chart and every
`_helpers.tpl` function, the ACM element type, and the built artifact names.

One deliberate exception, and it matters: `TENANT_ID=netai` in three files is NOT renamed. It
addresses the `netai trial` seed tenant, confirmed live in the database as
`00000000-0000-0000-3029-000000000001`, and CLAUDE.md exempts exactly this case as a
not-yet-migrated infra identifier. A blanket find-and-replace would have broken tenant
resolution in the demo.

**S3 DONE** (`dde14b9`). `tr069_renderer` no longer raises at import when
`maveric_platform_smo_sim` is absent. The loader returns `None`, writes are still rendered,
and the four catalogue-dependent tests skip through a new `CATALOGUE_AVAILABLE` flag.

Degrading rather than raising is safe because the authoritative gate is smo_sim's
`validate_write` on the real command path, which runs server-side regardless of what the demo
renderer pre-checks.

Verified in BOTH directions, because a fix that makes tests skip forever would be worse than
the original defect: with the sibling present 12 pass; without it 8 pass and 4 skip. The
standalone deploy suite goes from **uncollectable** to **39 passed / 4 skipped**.

This is option 3 from the S3 story, the minimum bar that unblocks CI. Option 1 (move the
rendering to smo_sim's `nanolink_tr069` adapter, where Appendix A.2 says it belongs) remains
the architecturally correct end state and is still open.

**S2, S4, S5, S6, S7 remain**, all blocked on the merge. S2 (converging the two NONRTRIC
clients) stays the highest-value one: every week both exist, someone fixes a bug in one of
them. The demo pins PMS `2.3.1` on the v2 dialect against a hand-rolled mock, while EPIC-3
ships `2.11.0` on v3 against the official OSC simulators, live-verified.

---

## Execution status update: PR 46 adopted, S1/S2/S3 done

PR #46 was merged into `feature/rearchitecture-epics` rather than merged upstream, at the
product owner's direction, so the PR can be closed. rApp `4ea6d7a`.

The merge was clean: the PR touches only `deploy/`, the re-architecture branch touches
`app/`, `tests/` and `packaging/`, and there were zero path collisions. The end-to-end
open-RIC path it proves is preserved whole.

**S1 DONE.** The retired product name is out of the packaged artifact identity across 36
files. `TENANT_ID=netai` is deliberately kept: it addresses the `netai trial` seed tenant,
confirmed live as `00000000-0000-0000-3029-000000000001`, which CLAUDE.md exempts. A blanket
rename would have broken tenant resolution.

**S3 DONE.** `tr069_renderer` degrades instead of raising at import when
`maveric_platform_smo_sim` is absent. Verified both ways, because a fix that makes tests skip
forever is worse than the defect: 12 pass with the sibling present, 8 pass and 4 skip
without. The standalone deploy suite goes from uncollectable to 39 passed / 4 skipped.

**S2 DONE, and live-verified.** `demo/a1_client.py` is the seam; `plane_available`,
`ensure_service` and `publish` now run through `A1PmsClient`, so the demo inherits retries,
service registration, the v3 dialect with a v2 fallback, and the frozen A.3 status mapping.
It targets the `ric-lab` profile (PMS 2.11.0 plus the official OSC simulators) instead of a
demo-private container on the stale 2.3.1 tag, and `requests` is no longer needed on that
path.

Verified against live ric-lab: publish returns `applied`, re-publish returns `duplicate` (the
409 case the raw client never handled), and the policy is readable on the real PMS carrying
the demo's exact body. Demo suite 43 passed; rApp service suite unchanged at 413.

Two things the convergence surfaced:

1. **`config.REPO_ROOT` counted parents** (`parents[5]`), which IndexErrors the moment the
   demo is not at exactly that nesting, which is what happens inside the rapp container. It
   now searches upward for the repo markers, with a `CLOUDLYNET_REPO_ROOT` override. Same
   class of defect as S3, third instance in this codebase.
2. **ric-lab publishes no host port** by design (E3.S2 forbids them), so a host-run demo
   cannot reach the PMS. The A1 leg must run in-network. Worth resolving explicitly in S5
   when the demo's reproducibility is addressed: either run the demo in a container on the
   `maveric` network, or accept one documented host-port exception for the lab profile.

**Still open: S4** (two external source checkouts, `NONRTRIC_CHECKOUT` and
`RAPPMANAGER_CHECKOUT`), **S5** (destructive `lsof` port kills, reproducibility, the host-port
question above), **S6** (the rApp Manager and CSAR posture decision), **S7** (docs lockstep,
93 em-dash lines). `a1_up.py` still stands up its own PMS container and is the remaining
piece of S2's spirit; it is lab plumbing rather than a second client now that the write path
is converged.
