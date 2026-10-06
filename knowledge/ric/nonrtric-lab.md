# NONRTRIC lab profile (`ric-lab`)

Part of the [`artifacts/ric/`](./README.md) bundle. Authored by EPIC-3 (RAN Intelligence +
RIC integration layer); owned by the bundle since E6.S2. Status: **Today (Lab)**, bring-up
verified 2026-07-31 on Apple Silicon (see section 2 for the emulation note).

CloudlyNet integrates O-RAN SC NONRTRIC, the open-source non-RT RIC, and carries A1-policy-aligned
intents to it. Nothing here implements or claims conformance with the A1, E2, R1 or O-RAN
interfaces.

---

## 1. What runs

Three containers behind compose profile `ric-lab`, all lab only, all consumed as images from the
Linux Foundation nexus and never built from source.

| Service | Container | Image | Interface |
| --- | --- | --- | --- |
| `nonrtric-a1pms` | `nonrtric_a1pms` | `nexus3.o-ran-sc.org:10002/o-ran-sc/nonrtric-plt-a1policymanagementservice:2.11.0` | northbound v3 (`{apiRoot}/a1-policy-management/v1`) and v2 (`/a1-policy/v2`) |
| `a1-sim-std` | `a1_sim_std` | `nexus3.o-ran-sc.org:10002/o-ran-sc/a1-simulator:2.8.1` | `STD_2.0.0` |
| `a1-sim-osc` | `a1_sim_osc` | `nexus3.o-ran-sc.org:10002/o-ran-sc/a1-simulator:2.8.1` | `OSC_2.1.0` |

The **A1 Policy Management Service** is Apache-2.0. It is developed upstream in ONAP CCSDK-ORAN and
re-released by O-RAN SC (M-release). It gives CloudlyNet one northbound API over any number of
near-RT RICs.

The two **A1 Simulators** stand in for near-RT RIC A1 terminations. State this plainly wherever the
lab is described: the simulators terminate A1 statefully, but they are **not functional RICs**. They
have no E2 interface and run no xApps. Any demo or document that shows this lab must label the RAN
side as simulated.

Deliberately not deployed, per frozen HLD decision D1: Information Coordination Service, Control
Panel, SDNC, rApp Manager, SME/CAPIF, and RANPM. rApp Manager is pre-spec and upstream calls it
"not intended for production use"; RANPM drags in AGPLv3 MinIO. All of it stays roadmap.

## 2. Bring-up runbook

```bash
./scripts/kafka/compose.sh ric-lab      # infra + the three ric-lab containers
./scripts/kafka/compose.sh ps           # ric-lab is included in the profile list
./scripts/kafka/compose.sh down         # also tears down ric-lab
```

The policy service publishes **one** host port, `${A1PMS_PORT:-8081}`. Everything else stays on
the external `maveric` network, and in-network callers still reach it at
`http://nonrtric-a1pms:8081`. The two simulators deliberately publish nothing: only the policy
service talks to them, and it does so in-network.

### Why the policy service has a host port

EPIC-3.S2 originally specified no host ports at all. That was right at the time: the only
consumer was the rApp's connector, which runs in a container on the `maveric` network. It
stopped being right when the NONRTRIC demo driver (EPIC-9) arrived, because that runs on the
HOST and could not reach the policy service at all, leaving the A1 leg verifiable only from
inside a container.

The decision follows this repository's actual convention rather than the story text. Every
service a developer reaches from the host publishes a port as `${VAR:-default}:container`, and
that includes the other lab-only profile: `edgeagent` publishes 7547 and 9100. So "lab-only
profile" has never meant "no host ports" here. What EPIC-3.S2's constraint was really
protecting is **zero CI/CD change** (no charts, no Jenkins pipelines, no registry pushes), and
that is untouched: a compose port mapping is not a deployment artifact.

8081 was verified unclaimed against every other mapping in `docker-compose.yaml` and against
anything listening on the host. Override with `A1PMS_PORT` if it collides locally.

Verify both simulators registered, from any container on the `maveric` network:

```bash
docker exec nonrtric_a1pms wget -q -O - http://localhost:8081/a1-policy-management/v1/rics
```

Expected, and confirmed at bring-up:

```json
{"rics":[{"ricId":"ric-osc","managedElementIds":["cloudlynet-lab-cell-2"],"state":"AVAILABLE","policyTypeIds":[]},
         {"ricId":"ric-std","managedElementIds":["cloudlynet-lab-cell-1"],"state":"AVAILABLE","policyTypeIds":[]}]}
```

`state: AVAILABLE` is the signal that the policy service reached the simulator over compose DNS.
`policyTypeIds` is empty until a policy type is registered (EPIC-3.S3 owns that step).

### The v3 base-path trap

The recommended API is called "V3" in the upstream documentation, but **the served base path segment
is `v1`**: `{apiRoot}/a1-policy-management/v1`. The older API is at `/a1-policy/v2`. Getting this
wrong looks like a plain 404 at bring-up. Both were exercised against the running 2.11.0 service:

| | v3 (default, `A1PMS_API_MODE=v3`) | v2 fallback (`A1PMS_API_MODE=v2`) |
| --- | --- | --- |
| Base path | `/a1-policy-management/v1` | `/a1-policy/v2` |
| Create policy | `POST /policies` | `PUT /policies` |
| Dialect | camelCase | snake_case |
| RIC list fields | `ricId`, `managedElementIds`, `policyTypeIds` | `ric_id`, `managed_element_ids`, `policytype_ids` |

Note the v2 spelling `policytype_ids`, with no underscore between "policy" and "type". The
connector owns this dialect mapping so that callers only ever see the `app/ric/models.py` shapes.

### Facts verified against the images, not inferred from docs

Each of these was flagged in the epic as unpinnable from documentation, and each was read out of the
2.11.0 and 2.8.1 images at bring-up:

| Item | Verified value | Where it came from |
| --- | --- | --- |
| Policy service config path | `/opt/app/policy-agent/data/application_configuration.json` | `config/application.yaml`, key `app.filepath` |
| Policy service HTTP port | `8081` (HTTPS `8433`) | `config/application.yaml`, `server.http-port` |
| Config file schema | `{"config": {"ric": [{name, baseUrl, managedElementIds, customAdapterClass?, controller?}]}}` | the image's own `data/application_configuration.json_example` |
| Simulator port | `8085` HTTP (`8185` HTTPS) | `/usr/src/app/nginx.conf` in the simulator image |
| Healthcheck tooling | `wget` present, `curl` absent | probed in the running image |
| STD dialect adapter | `org.onap.ccsdk.oran.a1policymanagementservice.clients.StdA1ClientVersion2$Factory` | class listing inside `policy-agent.jar` |

`ric-std` pins `customAdapterClass` to the STD v2 factory so the southbound dialect is explicit
rather than left to protocol auto-detection. `ric-osc` uses the default OSC client.

### Apple Silicon note

Both images are `linux/amd64` only, so Docker reports a platform mismatch on arm64 hosts and runs
them under emulation. They start and serve correctly this way; the policy service reached its
healthcheck in about five seconds. No `platform:` override is pinned in compose, because forcing one
would break native amd64 lab hosts.

### Registering the CloudlyNet policy type on the simulators

The connector never assumes its type exists on a real RIC (it discovers and negotiates per
RIC). In the lab we register it ourselves, and **the two simulator interfaces take
structurally different bodies**. Both were read out of the 2.8.1 image source.

`STD_2.0.0` takes a free-string id and a body carrying `policySchema` **and**
`statusSchema`:

```bash
docker exec -i rapp python - <<'PY'
from app.ric.adapters.nonrtric.policy_type import register_type_on_simulator
register_type_on_simulator("http://a1-sim-std:8085", "cloudlynet.cell_config.v1")
register_type_on_simulator("http://a1-sim-osc:8085", 21008)
PY
```

`OSC_2.1.0` requires the id to parse as an **integer**, and the body must carry `name`,
`description`, `policy_type_id` and `create_schema`. `build_registration_body()` picks the
right envelope from the id type, so the call above is all that is needed.

After registration the policy service picks the types up on its next RIC synchronization.
That took about 40 seconds in the lab after a simulator reset, so poll rather than assume:

```bash
docker exec nonrtric_a1pms wget -q -O - http://localhost:8081/a1-policy-management/v1/rics
# ric-std should now report policyTypeIds: ["cloudlynet.cell_config.v1"]
```

### End-to-end verification

Run against the live lab with the real connector:

```bash
docker exec -e PYTHONPATH=/app:/app/app/radplib/dependencies -i rapp python - <<'PY'
from datetime import datetime, timezone
from app.ric.adapters.nonrtric.client import A1PmsClient
from app.ric.adapters.nonrtric.adapter import NonRtRicControlAdapter
from app.ric.models import PolicyIntent

client = A1PmsClient(base_url="http://nonrtric-a1pms:8081", api_mode="v3")
client.register_service(start_keepalive=False)
adapter = NonRtRicControlAdapter(client=client)
intent = PolicyIntent(policy_id="cloudlynet-e2e-1", tenant_id="t-1", adapter="a1_policy",
                      policy_type_id="cloudlynet.cell_config.v1", ric_id="ric-std",
                      policy_object={"scope": {"cell_id": "cell_1"},
                                     "statements": {"el_degree": 4.0, "on_off": True}},
                      created_at=datetime.now(timezone.utc))
print(adapter.submit_policy_intent(intent).status)   # applied
print(adapter.submit_policy_intent(intent).status)   # duplicate
print(adapter.policy_status("cloudlynet-e2e-1").raw)
print(adapter.delete_policy_intent("cloudlynet-e2e-1").status)  # applied
print(adapter.delete_policy_intent("cloudlynet-e2e-1").status)  # duplicate
PY
```

Observed on 2026-07-31, and the source of the status mapping in `client.py`:

| Call | Result | Connector ack |
| --- | --- | --- |
| `PUT /services` | 201 | registration succeeds |
| `POST /policies` | 201 plus `Location` | `applied` |
| `POST /policies` again | **409** "Policy already created with ID" | `duplicate` |
| `GET /policies/{id}/status` | 200 `{"enforceStatus":"NOT_ENFORCED","enforceReason":"OTHER_REASON"}` | `enforced=False` |
| `DELETE /policies/{id}` | 204 | `applied` |
| `DELETE` again | 404 | `duplicate`, so rollback is idempotent |

### Three traps confirmed at bring-up

Each of these produced a confusing failure before it was diagnosed. None of them names
itself in the error message.

1. **`callbackUrl` is mandatory on `PUT /services`.** Omitting it does not default: the
   2.11.0 service dereferences it unconditionally and answers `400` with a raw
   `java.lang.NullPointerException: Cannot invoke "String.isEmpty()"`. The connector always
   sends an empty string.
2. **`STD_2.0.0` needs `statusSchema` at type-registration time.** Its registration handler
   validates only `policySchema`, so a type registered without `statusSchema` is accepted,
   and then **every policy create against it fails** with an opaque `500`. The real cause is
   a `KeyError: 'statusSchema'` at `src/STD_2.0.0/a1.py:162` inside the simulator. Read the
   simulator's own logs (`docker logs a1_sim_std`) to see it; the policy service only
   forwards a generic 500.
3. **A rejected policy body surfaces as `500`, not `4xx`.** The policy service wraps the
   RIC's `400 Bad Request` in a `WebClientResponseException` and returns `500`. Under the
   frozen feedback matrix (Appendix A.3) that maps to `failed` rather than `rejected`, and
   the retry policy will spend its full budget on a request that can never succeed. This is
   a known gap, deliberately not worked around here: the status mapping is a frozen
   cross-epic contract, so changing it belongs to a contract amendment, not to the
   connector. EPIC-4 and EPIC-5 should expect `failed` where they might reason `rejected`.

Recovering a simulator whose state got wedged (for example a type stuck with instances):

```bash
docker exec -i rapp python -c "import httpx; print(httpx.post('http://a1-sim-std:8085/deleteall').status_code)"
```

Then re-register the type and wait for the RIC to return to `AVAILABLE`.

## 3. Tag policy

Our compose file carries **our own pins**, currently policy service 2.11.0 and simulator 2.8.1.

Do not take tags from the upstream `nonrtric/docker-compose` sample `.env`. It is stale: it still
pins the policy service at 2.3.1. When bumping, take tags from the O-RAN SC release notes, update
the compose pins and the table in section 1 in the same commit, and re-run the section 2 and
EPIC-3.S3 verification steps.

If a future release moves the v3 base path or changes a field dialect, the blast radius is confined
by design to `app/ric/adapters/nonrtric/client.py` in the rApp submodule.

## 4. Production posture

This profile is a development lab. It is compose-only, exactly like the `edgeagent` profile, and it
touches no chart, no Jenkins pipeline, and no image registry.

For anything customer-facing:

1. **Mirror the images into our own registry first.** `nexus3.o-ran-sc.org:10002` carries no pull
   SLA, so depending on it at deploy time is an availability risk we do not need to take.
2. **Customer Kubernetes installs use the upstream NONRTRIC charts**, never a chart authored in our
   pipelines. This keeps us a consumer of the open-source project rather than a fork maintainer.
3. Keep this an ops procedure. It is documented here on purpose and stays out of CI/CD.

Upstream health, worth knowing before leaning on it: the policy service is the best-maintained part
of NONRTRIC, but active development sits in ONAP CCSDK-ORAN and O-RAN SC re-releases it. Release
cadence and the exact southbound configuration keys can shift, which is why the connector surface
stays small and `application_configuration.json` stays under our control.

## 5. License and attribution

Every component consumed here is **Apache-2.0**, which is why these images may ship alongside
commercial deployments once mirrored per section 4.

If the `pms-api-v3.yaml` OpenAPI specification file is ever vendored into this repository, keep its
embedded O-RAN ALLIANCE copyright notice intact.

Do not integrate RANPM: it deploys AGPLv3 MinIO. rApp Manager and SME/CAPIF stay roadmap.

## 6. Claims wording

Governed by `artifacts/marketing/claims-guardrails.md`. The approved ceiling for this integration:

- "We integrate O-RAN SC NONRTRIC, the open-source non-RT RIC."
- "A1-policy-aligned intents."

Never assert compliance or certification against O-RAN, A1, E2 or R1, in those words or any
paraphrase, and never describe CloudlyNet as a RIC or an SMO. The simulators are always labeled as
simulators. Product name is CloudlyNet.

## Near-RT tier

The lab is non-RT-only. The near-RT tier is deferred: FlexRIC was evaluated and dropped (its
CSSL v1.0 license is incompatible with our distribution posture), and the registry keeps a
RESERVED `nearrt_xapp` seam instead. Full rationale and the reserved contract:
[`nearrt-placeholder.md`](./nearrt-placeholder.md).
