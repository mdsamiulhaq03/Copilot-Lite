# `ocudu_ws_collector` (implemented, gated off)

## What it does

Connects outbound to OCUDU's `remote_control` WebSocket and turns each JSON metrics frame
into canonical PM records on `maveric.ingest.pm.v1`. Requires `metrics.enable_json` on the
OCUDU side. No RIC, no E2, no ASN.1 is involved: this is plain JSON over a socket, which is
why it could be implemented now while the near-RT track stays deferred.

It is a **data-plane collector**. `capabilities()` reports `collect=True, apply=False`, so a
loop action targeting this key is rejected by `dispatch()` before the adapter is called.

## Configuration (all off by default)

| Setting | Meaning |
| --- | --- |
| `OCUDU_WS_ENABLED` | Start the collector thread. Default false. |
| `OCUDU_WS_URLS` | Comma-separated `ws://` endpoints. |
| `OCUDU_WS_TENANT_ID` | Tenant the collected metrics belong to. |

No listening port is opened; the collector is an outbound client. Reconnects with capped
exponential backoff and never crashes the app on a stream fault.

## The envelope, and two ways to get it wrong

Published shape is HLD Appendix A.5 `kind="records"`, consumed by data_sim's
`RecordsEnvelope`. Both of these were verified against that model, not assumed:

1. **The discriminator is `kind` and the source field is `source_type`**, never `source`.
   data_sim actively rejects the retired dialect.
2. **`InlineRecord` is `extra="forbid"`** with exactly `{dn, metric, value, unit,
   granularity_s, ts, labels}`. One stray key on ONE record rejects the WHOLE batch, so
   `translate_frame` emits exactly those seven keys and routes every non-numeric field into
   `labels` rather than attempting a record.

`metric` carries the SOURCE name unchanged. Mapping to canonical names happens at store time
through `vendor_dictionaries`; the collector must not pre-map, or the dictionary stops being
the single place that knows the translation.

## Claims

Interoperates with an open-source CU/DU project's JSON metrics output. No O-RAN conformance.
