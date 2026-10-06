# Frontend — Design Bundle

Design of record for the Next.js frontend. The code lives in the `maveric_platform_frontend`
repository, registered as a submodule at `submodule/maveric_platform_frontend`.

> The submodule pointer can lag the frontend repo, so these docs can drift from its code.
> When you change frontend behavior, update the doc in the same change.

| Doc | Covers |
|---|---|
| [`HLD.md`](./HLD.md) | Frontend logical architecture: module topology, runtime composition. |
| [`LLD.md`](./LLD.md) | Directory ownership, `ApiClient` internals, auth/session flow. |
| [`route.md`](./route.md) | UI-route ↔ backend-endpoint matrix, incl. NanoLink device management. |
| [`UI_Design.md`](./UI_Design.md) | Page-by-page interaction and behavior spec. |
| [`Brand.md`](./Brand.md) | Brand tokens: color, typography, component rules. |
| [`API_Contracts.md`](./API_Contracts.md) | Envelope, error mapping, pagination, polling — from the consumer's view. |
| [`Test_Strategy.md`](./Test_Strategy.md) | Test pyramid and microservice-aligned coverage matrix. |
| [`ui-label-mapping.md`](./ui-label-mapping.md) | Old → new customer-facing label map. |
| [`Gap_Analysis.md`](./Gap_Analysis.md) | Implementation-vs-runbook gaps and backlog. |
| [`execution_runbook.md`](./execution_runbook.md) | Execution runbook: feature ownership map, integration rules, DoD, NanoLink `/devices` spec. |

## Stack

Next.js 15.5 (App Router) · React 19.1 · Zustand · Axios.

## Integration invariants

- The managed-parameter catalogue is mirrored **client-side** in `lib/nybsys/managed-params.ts`
  because no endpoint exposes param metadata. Keep it in sync with SMO Sim's
  `app/services/nybsys/managed_params.py`.
- Command history treats `rolled_back` as a **terminal** status — the agent ack contract can persist it.
- The Config surface separates **Current value** (last edge-agent-confirmed snapshot) from
  **Proposed update** (the only value that enters a command). Firmware-dump "observed" notes are
  guidance, never runtime data.
- The frontend consumes `artifacts/design/openapi.yaml` unchanged. It does not define its own contract.

## Related

- [`artifacts/upgrade_plans/frontend_agent.md`](../upgrade_plans/frontend_agent.md) — per-microservice frontend runbook
- [`artifacts/upgrade_plans/mro_frontend.md`](../upgrade_plans/mro_frontend.md) — MRO UI contract
- [trial-signup contract → API_Contracts.md §7.0](./API_Contracts.md) — trial-signup contract
