# Adapter: `ves_listener`

**Status: PLANNED.** Registered as a stub with `available = false` (EPIC-1.S6). Submissions are
rejected with `422 SOURCE_TYPE_UNAVAILABLE`.

Vendor slot `ves`. No feature flag.

## Intended scope

Accepts **VES-style JSON event payloads** pushed to the ingest API or published to
`maveric.ingest.pm.v1`, and maps their measurement fields into canonical PM rows.

Likely arrives as `kind="records"` batches (see
[`../ingest-topic-contract.md`](../ingest-topic-contract.md)) rather than as a job, since VES is a
push model with no file to fetch.

## Scope boundary

Accepting a JSON shape is not a certification. This is not ONAP or VES certified and must never be
described as such. See `artifacts/marketing/claims-guardrails.md`.

## Open questions before implementation

- Whether the listener terminates HTTP itself or reuses the ingest API, and what authenticates the
  producer
- Which VES domains are in scope (measurement only, or fault as well, which would target `fm_alarms`)
- Batch size and backpressure limits
