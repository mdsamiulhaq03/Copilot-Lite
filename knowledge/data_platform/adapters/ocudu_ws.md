# Adapter: `ocudu_ws`

**Status: PLANNED as an adapter; the ingest PATH is implemented.** Registered as a stub with
`available = false` (EPIC-1.S6), because there is no job-style parse for it.

Vendor slot `ocudu`. No feature flag.

## How it actually arrives

This source is a **stream**, not a file, so it does not use the job flow. Metrics reach the
canonical store through the `kind="records"` branch (EPIC-1.S8) with `source_type = "ocudu_ws"` and
`vendor = "ocudu"`. That branch is implemented and tested.

The producer is the `ocudu_ws_collector` placeholder in the actuator framework (HLD 4.5), which is
E4's work. The stub exists so the source name is registered and a job-style submission fails
loudly rather than being silently accepted.

## Store semantics

Per [`../ingest-topic-contract.md`](../ingest-topic-contract.md): `day` and `tick` are NULL,
`raw_ref` is NULL, `labels` carries the producer's labels plus `batch_id`, and `metric` is mapped
through `vendor_dictionaries` for vendor `ocudu`.

**No `ocudu` dictionary rows are seeded yet.** Until they are, every metric falls back to
`ocudu:<source_metric>`, which is correct behaviour rather than a gap: the rows land and can be
reclassified later with a dictionary UPDATE and a re-ingest. The seed rides E4's contract-doc
follow-up.

## Scope boundary

A JSON metrics sink for a WebSocket collector. **Not** an E2 interface, not a RIC integration, and
no O-RAN conformance is implied. See `artifacts/marketing/claims-guardrails.md`.
