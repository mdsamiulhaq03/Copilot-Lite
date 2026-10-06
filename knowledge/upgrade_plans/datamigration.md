# Database Migration Guide

This document describes the simplified, centralised database migration flow for CloudlyNet. The gateway is now the sole component that performs schema migrations, using GORM auto-migration against the canonical DDL stored in `artifacts/design/schemas.sql`.

## Overview

- All schema changes are applied exclusively by `maveric_platform_gateway` at startup.
- `artifacts/design/schemas.sql` remains the single source of truth. The gateway mirrors this DDL in `submodule/maveric_platform_gateway/db/migrations/schemas.sql` and in the GORM models under `submodule/maveric_platform_gateway/internal/db`.
- GORM `AutoMigrate` reconciles the runtime database with the models, then executes any supporting SQL (enums, triggers, indexes, RLS policies) defined in the gateway.
- No Python service (BDT Engine, Data Sim, rApp Engine, SMO Sim) runs Alembic anymore; their deployments rely on the gateway-managed schema.

## Prerequisites

1. Ensure PostgreSQL is reachable (local Docker instance or managed database).
2. Export `POSTGRES_DSN` (or configure the deployment secret) with credentials that can `CREATE`, `ALTER`, and `SELECT` within the target schema, e.g.:
   ```bash
   export POSTGRES_DSN="postgres://user:password@localhost:5432/maveric_dev?sslmode=disable"
   ```
3. Verify Go tooling is available for the gateway (`go version`, `go test`).

## Workflow for Schema Changes

1. **Update the design DDL** – edit `artifacts/design/schemas.sql` to reflect the desired tables, columns, constraints, indexes, triggers, and RLS definitions.
2. **Align gateway models** – adjust the relevant structs, tags, and helper SQL in `submodule/maveric_platform_gateway/internal/db` (typically `migrate.go` and companions) so they mirror the updated schema. GORM field tags should capture constraints, relationships, and indexing hints.
3. **Refresh the gateway SQL snapshot** – copy the revised `artifacts/design/schemas.sql` into `submodule/maveric_platform_gateway/db/migrations/schemas.sql` so the checked-in DDL matches the design document.
4. **Update supporting documentation and contracts** – propagate the change to `artifacts/design/HLD.md`, `artifacts/design/LLD.md`, service `README.md` files, `openapi.yaml`, and any other schema-dependent artefacts.
5. **Run gateway tests** – from `submodule/maveric_platform_gateway`, execute `go test ./...` and run any targeted integration tests that exercise migrations.
6. **Validate locally (optional)** – start the gateway with the new models against a development database (`POSTGRES_DSN=... go run ./cmd/gateway`) and confirm the logs show the expected auto-migration steps.
7. Commit the updated SQL, Go models, and documentation together so CI and deployments pick up the new schema.

## Gateway Auto-Migration Details

- `internal/db/migrate.go` initialises the GORM connection and invokes `AutoMigrate` sequentially for every schema struct. Custom SQL helpers in the same package create enums, indexes, triggers, and RLS policies that are not handled directly by GORM.
- Because the gateway is the only component applying DDL, ensure its deployment runs before or alongside other services that rely on the database. Other services simply wait for the schema to exist; no extra migration step is required in their images or pipelines.
- When introducing destructive changes (column drops, table renames), add explicit SQL in the gateway migrator to maintain backward compatibility during rolling deployments, or plan a maintenance window.

## Production Rollout Checklist

1. Confirm `artifacts/design/schemas.sql`, gateway models, and `db/migrations/schemas.sql` are consistent and reviewed.
2. Update `artifacts/design/HLD.md`, `artifacts/design/LLD.md`, relevant `README.md` files, `openapi.yaml`, and any consumer documentation tied to the schema.
3. Build and deploy the gateway so the new auto-migration logic runs with a valid `POSTGRES_DSN`.
4. Redeploy dependent services after the gateway has finished migrations.
5. Monitor gateway logs for migration output and database warnings.

## Troubleshooting

- **Missing tables/columns after deploy** – verify the gateway binary ran with the new code and that `POSTGRES_DSN` points to the intended database.
- **Permission errors during startup** – grant the gateway database user the necessary DDL privileges or adjust the connection string.
- **GORM auto-migration skipped a change** – double-check struct tags and types; add explicit SQL in the gateway migrator for constraints GORM cannot express.
- **Downtime concerns** – test destructive migrations in a staging environment and consider blue/green or maintenance windows if the change cannot be applied online.

Centralising migrations in the gateway keeps the platform schema consistent and removes the need for service-specific migration tooling.
