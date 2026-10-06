# Adapter: `3gpp_xml_pm`

**Status: PLANNED.** Registered as a stub with `available = false` (EPIC-1.S6). A submission is
rejected at the API with `422 SOURCE_TYPE_UNAVAILABLE`, so unbuildable work is never queued.

Vendor slot `3gpp`. No feature flag.

## Intended scope

Parses the **TS 32.435 XML PM file format** (the `measCollec` document), which is the file layout
most macro-RAN vendors export bulk performance counters in, per the TS 32.432 file-based collection
concept.

Per-vendor counter names differ inside that common envelope, so canonical naming goes through
`vendor_dictionaries` exactly as it does for every other adapter, with the per-file vendor resolved
from the document's `measType` entries rather than hardcoded.

## Scope boundary

This is a **file format parser**. It is not an O1 or O-RAN interface implementation, and its
presence implies no conformance to either. See `artifacts/marketing/claims-guardrails.md`.

## Open questions before implementation

- Which vendors' exports are in scope first, and can we obtain real sample files
- Whether `granularity_s` is always derivable from the document or needs a params override
- How to represent multi-object `measValue` sets that do not decompose to a single `dn`
