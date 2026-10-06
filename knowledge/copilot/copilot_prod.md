# Copilot Production DB Migration Runbook

**Date:** 2026-03-17
**Scope:** Dedicated copilot Postgres bootstrap, tenant-isolation migration, runtime grants, and RLS rollout outside application startup.

Platform note:
- The 2026-03-20 Non-MRO rApp unification changed backend ES/LB/CCO inference outputs to one shared operator contract: `tick + items[{cell_id, el_degree, on_off}]`. This runbook has no schema change for that feature, but any copilot-triggered frontend or tool flow that surfaces Non-MRO recommendations should expect the aligned payload.
- The 2026-03-22 Non-MRO day-scope payload fix also has no schema impact, but day-evaluation consumers can now read `per_tick_recommendations[{tick, items[]}]` and raw tick recommendation mirrors under `raw_tick_data[*].recommendations`.
- The 2026-03-26 data-generation agent rollout and public picker cleanup also have
  no schema impact. `GET /copilot/agents` now returns only the user-selectable
  agents (`debugger_agent`, `data_generation_agent`, `offline_debugging_agent`);
  internal `reactive_agent` and `generic_agent` remain backend-only.

## 1. Target State

- owner role: `netai_copilot_owner`
- runtime role: `netai_copilot_app`
- runtime database: `netai_copilot`
- optional test database: `netai_copilot_test`
- schemas:
  - `conversation`
  - `knowledge`

Use the same separation model in production that root compose now uses locally:
1. bootstrap roles/databases/extensions
2. apply tenant-isolation SQL if upgrading an older database
3. apply schema bundle
4. apply RLS
5. start or restart runtime services

For local parity, root `.env` now carries the same bootstrap inputs under `COPILOT_POSTGRES_OWNER_*`, `COPILOT_POSTGRES_APP_*`, `COPILOT_POSTGRES_RUNTIME_DB`, and `COPILOT_POSTGRES_TEST_DB`.

## 2. Bootstrap Roles, Databases, and Extensions

Run as `postgres` or another superuser.

Recommended command:

```bash
psql -U postgres -d postgres \
  -v copilot_owner_user=netai_copilot_owner \
  -v copilot_owner_password='<owner-password>' \
  -v copilot_app_user=netai_copilot_app \
  -v copilot_app_password='<app-password>' \
  -v copilot_db=netai_copilot \
  -v copilot_test_db=netai_copilot_test \
  -f artifacts/db/init_copilot.sql
```

If you need the SQL inline instead of the script, use:

```sql
\set ON_ERROR_STOP on
\set copilot_owner_user netai_copilot_owner
\set copilot_owner_password '<owner-password>'
\set copilot_app_user netai_copilot_app
\set copilot_app_password '<app-password>'
\set copilot_db netai_copilot
\set copilot_test_db netai_copilot_test

SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L',
  :'copilot_owner_user',
  :'copilot_owner_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'copilot_owner_user'
) \gexec

SELECT format(
  'ALTER ROLE %I WITH LOGIN PASSWORD %L',
  :'copilot_owner_user',
  :'copilot_owner_password'
)
WHERE EXISTS (
  SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'copilot_owner_user'
) \gexec

SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L',
  :'copilot_app_user',
  :'copilot_app_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'copilot_app_user'
) \gexec

SELECT format(
  'ALTER ROLE %I WITH LOGIN PASSWORD %L',
  :'copilot_app_user',
  :'copilot_app_password'
)
WHERE EXISTS (
  SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'copilot_app_user'
) \gexec

SELECT format(
  'CREATE DATABASE %I OWNER %I',
  :'copilot_db',
  :'copilot_owner_user'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = :'copilot_db'
) \gexec

SELECT format(
  'CREATE DATABASE %I OWNER %I',
  :'copilot_test_db',
  :'copilot_owner_user'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = :'copilot_test_db'
) \gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', :'copilot_db', :'copilot_owner_user') \gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'copilot_test_db', :'copilot_owner_user') \gexec
SELECT format('GRANT CONNECT, TEMP ON DATABASE %I TO %I', :'copilot_db', :'copilot_owner_user') \gexec
SELECT format('GRANT CONNECT, TEMP ON DATABASE %I TO %I', :'copilot_test_db', :'copilot_owner_user') \gexec
SELECT format('GRANT CONNECT, TEMP ON DATABASE %I TO %I', :'copilot_db', :'copilot_app_user') \gexec
SELECT format('GRANT CONNECT, TEMP ON DATABASE %I TO %I', :'copilot_test_db', :'copilot_app_user') \gexec
SELECT format('ALTER DATABASE %I SET search_path TO public, conversation, knowledge', :'copilot_db') \gexec
SELECT format('ALTER DATABASE %I SET search_path TO public, conversation, knowledge', :'copilot_test_db') \gexec

\connect :copilot_db
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

\connect :copilot_test_db
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

## 3. Existing-DB Tenant-Isolation Upgrade SQL

Use this only for older databases that still contain `organization_id` in the
conversation tables. Fresh installs can skip this section because the schema
bundle already creates `tenant_id`.

Run as `netai_copilot_owner`:

```sql
ALTER TABLE conversation.conversation_session
  ADD COLUMN IF NOT EXISTS tenant_id varchar(255);

UPDATE conversation.conversation_session
SET tenant_id = COALESCE(tenant_id, organization_id, 'default')
WHERE tenant_id IS NULL;

ALTER TABLE conversation.conversation_session
  ALTER COLUMN tenant_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conv_session_tenant
  ON conversation.conversation_session (tenant_id);

CREATE INDEX IF NOT EXISTS idx_conv_session_tenant_user
  ON conversation.conversation_session (tenant_id, user_id);

ALTER TABLE conversation.conversation_message
  ADD COLUMN IF NOT EXISTS tenant_id varchar(255);

UPDATE conversation.conversation_message AS msg
SET tenant_id = COALESCE(msg.tenant_id, sess.tenant_id, msg.organization_id, 'default')
FROM conversation.conversation_session AS sess
WHERE msg.session_id = sess.id
  AND msg.tenant_id IS NULL;

ALTER TABLE conversation.conversation_message
  ALTER COLUMN tenant_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conv_message_tenant
  ON conversation.conversation_message (tenant_id);

CREATE INDEX IF NOT EXISTS idx_conv_message_tenant_session
  ON conversation.conversation_message (tenant_id, session_id);

ALTER TABLE conversation.conversation_message_version
  ADD COLUMN IF NOT EXISTS tenant_id varchar(255);

UPDATE conversation.conversation_message_version AS ver
SET tenant_id = COALESCE(ver.tenant_id, sess.tenant_id, ver.organization_id, 'default')
FROM conversation.conversation_session AS sess
WHERE ver.session_id = sess.id
  AND ver.tenant_id IS NULL;

ALTER TABLE conversation.conversation_message_version
  ALTER COLUMN tenant_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conv_version_tenant
  ON conversation.conversation_message_version (tenant_id);

DROP INDEX IF EXISTS conversation.idx_conv_session_org;
DROP INDEX IF EXISTS conversation.idx_conv_message_org;
DROP INDEX IF EXISTS conversation.idx_conv_version_org;

ALTER TABLE conversation.conversation_session
  DROP COLUMN IF EXISTS organization_id;

ALTER TABLE conversation.conversation_message
  DROP COLUMN IF EXISTS organization_id;

ALTER TABLE conversation.conversation_message_version
  DROP COLUMN IF EXISTS organization_id;
```

## 4. Apply the Schema Bundle

Run as the owner role:

```bash
psql -U netai_copilot_owner -d netai_copilot \
  -v copilot_app_user=netai_copilot_app \
  -f artifacts/copilot/copilot_schemas.sql
```

This creates:
- `conversation.*`
- `knowledge.*`
- indexes
- update triggers
- runtime grants for `netai_copilot_app`

## 5. Runtime Grants for the App Role

`artifacts/copilot/copilot_schemas.sql` already applies these grants when run with
`copilot_app_user`. Run them manually only if you created the tables another
way.

Run as `netai_copilot_owner`:

```sql
GRANT USAGE ON SCHEMA conversation, knowledge TO netai_copilot_app;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA conversation
TO netai_copilot_app;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA knowledge
TO netai_copilot_app;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA conversation
TO netai_copilot_app;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA knowledge
TO netai_copilot_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA conversation
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO netai_copilot_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA knowledge
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO netai_copilot_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA conversation
GRANT USAGE, SELECT ON SEQUENCES TO netai_copilot_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA knowledge
GRANT USAGE, SELECT ON SEQUENCES TO netai_copilot_app;
```

## 6. Apply RLS

Run as `postgres` or another superuser:

```bash
psql -U postgres -d netai_copilot \
  -f artifacts/db/init_copilot_rls.sql
```

This enables and forces RLS on:
- `conversation.conversation_session`
- `conversation.conversation_message`
- `conversation.conversation_message_version`

The policy uses:
- `current_setting('app.current_tenant_id', true)`
- `current_setting('app.current_user_id', true)`

## 7. Validation Queries

Run these after bootstrap and migration:

```sql
SELECT rolname
FROM pg_roles
WHERE rolname IN ('netai_copilot_owner', 'netai_copilot_app');

SELECT datname
FROM pg_database
WHERE datname IN ('netai_copilot', 'netai_copilot_test');

SELECT table_schema, table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'conversation'
  AND table_name IN (
    'conversation_session',
    'conversation_message',
    'conversation_message_version'
  )
  AND column_name IN ('tenant_id', 'organization_id')
ORDER BY table_name, column_name;

SELECT schemaname, tablename, rowsecurity, forcerowsecurity
FROM pg_tables
WHERE schemaname = 'conversation';

SELECT grantee, table_schema, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'netai_copilot_app'
  AND table_schema IN ('conversation', 'knowledge')
ORDER BY table_schema, table_name, privilege_type;
```

Expected result:
- both roles exist
- both databases exist
- `tenant_id` exists on all conversation tables
- `organization_id` is absent on upgraded databases
- RLS is enabled and forced on conversation tables
- `netai_copilot_app` has DML privileges on `conversation` and `knowledge`

## 8. Runtime Cutover

For ArgoCD-managed environments, refresh in this order:
1. `maveric_platform_postgres`
2. `maveric_platform_copilot`

After the SQL steps succeed:
1. point runtime `DATABASE_URL` at `netai_copilot` using `netai_copilot_app`
2. refresh or restart `copilot-backend`
3. refresh or restart `copilot-mcp-server`
4. validate:
   - `GET /health`
   - `GET /api/v1/health`
   - `GET /v1/tenants/{tenant_id}/copilot/health`

## 8A. Knowledge-Base Bootstrap

- The production chart now packages a compressed snapshot of `submodule/cloudlynet_ai_copilot/knowledge_base` as `submodule/maveric-deployment/argocd/maveric_platform_copilot/files/knowledge_base.tgz`.
- ArgoCD rollout order is now:
  1. postgres bootstrap app
  2. copilot SQL migration hook (`sync-wave: 1`)
  3. copilot knowledge-base hook (`sync-wave: 2`)
  4. `copilot-backend` + `copilot-mcp-server` Deployments (`sync-wave: 3`)
- The knowledge-base hook runs the same scripts used in local Docker:
  - `uv run python scripts/ingest_knowledge_base.py`
  - `uv run python scripts/contextualize_chunks.py --skip-existing`
- Updating the curated KB source of truth in `submodule/cloudlynet_ai_copilot/knowledge_base` now also requires refreshing the packaged chart artifact `files/knowledge_base.tgz` before syncing the deployment repo.
  - Refresh command:
    - `tar -C submodule/cloudlynet_ai_copilot -czf submodule/maveric-deployment/argocd/maveric_platform_copilot/files/knowledge_base.tgz knowledge_base`

## 9. Notes

- Root local compose follows the same separation model, but defaults the local
  copilot app container to the owner role unless overridden.
- Current tenant-isolation source of truth is this SQL runbook plus the Helm SQL
  migration pack under `submodule/maveric-deployment/argocd/maveric_platform_copilot/files/`.
- The production chart now carries both SQL migration files and the packaged KB archive so the GitOps release is self-contained for RAG bootstrap as well as schema/RLS bootstrap.
