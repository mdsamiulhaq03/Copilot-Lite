# NanoLink / NybSys — Design Bundle

Design of record for the NybSys NanoLink edge↔cloud integration and the custom PM CSV
ingestion path.

| Doc | Covers |
|---|---|
| [`nanolink_integration_design.md`](./nanolink_integration_design.md) | Canonical design and decision record: Edge-Key auth, unified command queue (claim-on-fetch + lease + auto-rollback), tiered telemetry ingest with dedup, Phase-1 self-optimiser. |
| [`nybsys_data_contract.md`](./nybsys_data_contract.md) | Caller-facing PM CSV input contract: 14-column spec, column-name normalization, error conditions and exact messages. |
| `dmcli.new.conf` | NanoLink firmware parameter dump. Pins the PM `SampleSet.1.Parameter.{index}` mapping used by the edge agent's metric collector. Reference data, not documentation. |

## Where the code lives

| Concern | Location |
|---|---|
| Agent API (`/v1/agent/**`) | `submodule/maveric_platform_smo_sim/app/api/v1/custom/nybsys_agent_router.py` |
| Operator API (`/custom/nybsys/**`) | `submodule/maveric_platform_smo_sim/app/api/v1/custom/nybsys_edge_router.py` |
| PM CSV pipeline | `submodule/maveric_platform_smo_sim/app/lib/nybsys/` |
| Edge agent | `submodule/cloudlynet_edgeagent/` |
| Schema | `artifacts/migration/009_nybsys_nanolink.sql` (+ `010_nybsys_cwmp_id_rename.sql`, which renamed `genieacs_id` → `cwmp_id`), mirrored in [`artifacts/design/schemas.sql`](../design/schemas.sql) |

## Invariants worth knowing

- **`cwmp_id` is opaque.** The agent's in-agent ACS computes the canonical id from the Inform
  `DeviceID`, percent-encoding content hyphens (`ENB-N03002-B3` → `ENB%2DN03002%2DB3`). FastAPI
  decodes a URL path exactly once, so an id containing a literal `%2D` must travel as `%252D` on the
  config-snapshot route. Otherwise the snapshot auto-onboards a second, decoded (`-`) device and the
  operator-selected row stays blank.
- **Config snapshots merge, they do not replace.** SMO Sim ignores empty payloads and merges each
  non-empty periodic snapshot or one-field command read-back over the prior snapshot.
- **Configure is closed-loop.** The agent issues `setParameterValues` with a connection request,
  then polls GPV until the requested value is observed or `command_verify_timeout` (15 s in
  production) expires. A timeout is a failed command carrying `{path, expected, actual, missing}`.
- **Configuration is a separate flow from KPI telemetry.** Healthy KPI ingestion says nothing about
  the config path.

## Related

- [`artifacts/design/HLD.md`](../design/HLD.md) §9.12 — edge↔cloud control-plane data flow
- [`artifacts/design/LLD.md`](../design/LLD.md) §3.1 (edge agent), §5 (SMO Sim / NanoLink control plane)
- [`artifacts/design/openapi.yaml`](../design/openapi.yaml) — `Agent` tag, `edgeKey` security scheme
