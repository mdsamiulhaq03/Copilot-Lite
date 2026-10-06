# Test baselines

Recorded so every epic can be held to **no new failures** rather than to a "suite is green" gate
that was never achievable. Several epic stories specify "pytest passes" as their definition of
done; for three of the five Python services that was untrue before any re-architecture work began.

Measured 2026-07-30 against the compose infra (Postgres live; Mongo, Redis, Kafka and the OTEL
exporter unreachable from the host and therefore disabled per the commands below).

| Service | Passed | Failed | Errors | Nature of the failures |
| --- | --- | --- | --- | --- |
| `maveric_platform_data_sim` | 169 | 13 | 0 | Pre-existing code-vs-test drift. Pre-EPIC-1 it was 57 passed / 13 failed; EPIC-1 added 112 passing tests and zero new failures |
| `maveric_platform_bdt_engine` | 31 | 11 | 0 | Pre-existing. Baseline for EPIC-2 |
| `maveric_platform_rapp` | 186 | 8 | 5 | Pre-existing. Baseline for EPIC-2 S2/S3 |
| `maveric_platform_gateway` (Go) | 6 pkgs ok | `internal/db` fails 23 | | Pre-existing, and **only visible with Postgres running** (they skip otherwise). Verified identical at the pre-EPIC-0 commit |

## After EPIC-2 S1 and S2

| Service | Passed | Failed | Skipped | Errors | Delta vs baseline |
| --- | --- | --- | --- | --- | --- |
| `maveric_platform_bdt_engine` | 109 | 11 | 0 | 0 | +78 passing, **no new failures** — the 11 were verified byte-identical by re-running the suite with S1's three modified files stashed |
| `maveric_platform_rapp` | 258 | 0 | 4 | 5 | +72 passing, and the 8 baseline failures **eliminated** |

The 8 rapp failures were not fixed by changing behaviour. `tests/test_rapps_openapi.py` resolved the
canonical spec at `<repo>/design/openapi.yaml`, a path that stopped existing when docs moved into
`artifacts/`, so all 8 conformance checks were failing on `FileNotFoundError` rather than comparing
anything. Repointed at `artifacts/design/openapi.yaml`; the spec was correct all along, and 25 checks
now genuinely verify the rApp endpoints — including the `/infer` endpoints EPIC-2 modifies, which is
exactly where a silent contract drift would have landed.

The 4 skips are the live parity byte-diff (`tests/test_ndt_parity_integration.py`), which needs a
seeded lab tenant; the 5 errors are a pre-existing missing MRO fixture CSV
(`app/radplib/mro/testing_data/UE_data_20UE_100ticks.csv`).

## Reproducing

```bash
# data_sim
cd submodule/maveric_platform_data_sim
.venv/bin/python -m pytest -q

# bdt_engine
cd submodule/maveric_platform_bdt_engine
MONGODB_URL="" REDIS_URL="" KAFKA_BOOTSTRAP_SERVERS="" OTEL_SDK_DISABLED=true \
  DATABASE_URL="postgresql://postgres:postgres@localhost:5432/maveric" \
  .venv/bin/python -m pytest -q

# rapp (vendors its deps)
cd submodule/maveric_platform_rapp
MONGODB_URL="" REDIS_URL="" KAFKA_BOOTSTRAP_SERVERS="" OTEL_SDK_DISABLED=true \
  DATABASE_URL="postgresql://postgres:postgres@localhost:5432/maveric" \
  PYTHONPATH=app:app/radplib/dependencies .venv/bin/python -m pytest -q

# gateway
cd submodule/maveric_platform_gateway && go test -count=1 ./...
```

## Local environment gotchas

Each of these cost real time to diagnose; they are environment defects, not code defects.

1. **No service ships a working local venv.** `data_sim` and `bdt_engine` use `requirements.txt`
   with no lockfile and no `.venv`; `uv venv` defaults to a Python that may be too old
   (`numpy==2.3.2` needs >= 3.11). Create with `uv venv .venv --python 3.11` to match the
   `python:3.11-slim` Dockerfiles.
2. **`opentelemetry-instrumentation` needs `pkg_resources`, which nothing declares.** uv venvs omit
   setuptools, and **setuptools 81+ removed `pkg_resources` entirely**, so `uv pip install
   setuptools` does not fix it. Pin `"setuptools<81"`.
3. **The OTEL exporter blocks tests.** With no collector on `localhost:4318`, spans fail on export
   and surface as connection errors inside tests. Set `OTEL_SDK_DISABLED=true`.
4. **Kafka from the host is `localhost:29092`, not `localhost:9092`.** The broker advertises
   `PLAINTEXT://kafka:9092` for in-network clients and `PLAINTEXT_HOST://localhost:29092` for the
   host. Connecting to 9092 from the host succeeds at the socket then times out on publish, because
   the metadata response points back at the unresolvable `kafka:9092`.
6. **smo_sim's local venv had drifted to Python 3.12 while its Dockerfile is `python:3.11-slim`.**
   `kafka-python==2.0.2` vendors `six.moves`, which relies on an import hook Python 3.12 removed,
   so `from kafka import KafkaProducer` failed and the handler silently set the client classes to
   `None`. Every Kafka path then degraded to a no-op that looked like "Kafka not configured", and
   no test caught it because the tests fake the transport. Rebuild with
   `uv venv .venv --python 3.11 && uv sync` (NOT `pip install -r requirements.txt`: that file is a
   subset of `pyproject.toml` and omits `hypothesis`, which `tests/audit/` needs). Verified: the
   suite returns the identical 595 passed / 3 failed / 1 skipped on 3.11 and 3.12, so the drift
   changed no test outcome, only whether Kafka could be exercised at all.

7. **smo_sim baseline (this was missing entirely).** 424 passed / 3 failed / 44 skipped without
   Postgres; 508 / 3 / 1 with it. All seven `tests/nybsys_edge/*` files are `pytest.mark.pg`, so
   without the compose stack the whole NanoLink suite skips and "tests pass" means very little.
   The 3 failures are pre-existing `test_placement.py::TestSamplerWarnings` drift, unrelated to
   any epic, and identical on both Python versions.

5. **Postgres-dependent tests silently skip when Postgres is down.** The gateway's 23 `internal/db`
   failures are invisible without it, which is how a suite can look green and not be.
