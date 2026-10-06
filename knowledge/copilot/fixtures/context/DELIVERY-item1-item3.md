# Delivery pointers: item 1 and item 3's command history

Two parts of the S9 fixture pack are **not** in this directory and never will be, because they are
derived from the real capture. This file is the scaffolding that records where they came from and how
they were handed over. Fill the placeholders in at delivery time.

Register: [`../../HANDOVER-mcp-log-rca.md`](../../HANDOVER-mcp-log-rca.md) section 12.
Story: EPIC-8 S9.

## Why they are not committed

`artifacts/real-data/` holds real customer and network data. It is gitignored and stays that way.
Nothing from it is copied into a tracked file, a commit message, a PR body, a doc, or an artifact.
Derived work inherits that confidentiality unless it has been deliberately aggregated or
anonymised, and **that call belongs to the platform owner, not to whoever is doing the work.**

## Item 1: complete raw logs, one device, one incident window

**What the copilot team asked for:** ALL streams, unfiltered, for the incident window, not the
edge-forwarded subset. That means `Log_*.gz`, `ErrorLog_*.gz` and the continuous-logging ring
together, because `SCTP` and `L1_L2_Wrapper` lines appear only in the ErrorLogs and the routine
CWMP and lifecycle lines appear only in the Logs. A one-file-type delivery loses data whichever
type is chosen.

**Window:** the reboot incident described in [`incident-line-table.md`](incident-line-table.md).
Suggested bracket, wide enough to carry the pre-failure baseline and the recovery:
`2026-06-13T17:30:00Z` to `2026-06-13T18:30:00Z`.

| Field | Value |
|---|---|
| Source path under `artifacts/real-data/` | `<to be filled at delivery>` |
| Files handed over | `<count>` `Log_*.gz`, `<count>` `ErrorLog_*.gz`, `<count>` ring files |
| Delivery mode | in place read-only · anonymised copy |
| Anonymisation applied | `<none / serial -> 2205609999, MAC host parts synthetic>` |
| Anonymisation approved by | `<platform owner>` on `<date>` |
| Delivered on | `<date>` |

**If an anonymised copy is produced,** the rewrite is: real serial -> `2205609999`, MAC host parts
-> synthetic. The OUI `8C1F64` is the public vendor OUI and stays. Verify with a grep for the real
serial across the copy before it leaves the directory.

## Item 3, part 3: the command history for the window

The other two parts of item 3 are already here and need no real data: the 15-entry supported-alarm
catalogue and the vendor policy overlay are in
[`supported-alarm-catalogue.json`](supported-alarm-catalogue.json), and the 24-parameter config
snapshot is [`../get_device_config/01-snapshot-24-params.json`](../get_device_config/01-snapshot-24-params.json).

What remains is the real TR-069 (CWMP) command history for the incident window: every write the
platform issued, its state, and its read-back. The copilot needs it to confirm the RCA verdict
(*transport outage, autonomous recovery, not an actuation regression*) against real command records
rather than the fixture's synthesised one.

| Field | Value |
|---|---|
| Source | `<to be filled at delivery>` |
| Commands in window | `<count>` |
| Delivery mode | in place read-only · anonymised copy |
| Delivered on | `<date>` |

## Checklist before closing the delivery

- [ ] The real serial appears nowhere under `artifacts/copilot/` (grep gate, see the fixtures README)
- [ ] The PR body carries pointers only, never the data
- [ ] `HANDOVER-mcp-log-rca.md` section 12 moved from "requested" to "delivered", with paths and date
- [ ] The copilot team confirmed the stream set is complete, not the extract
