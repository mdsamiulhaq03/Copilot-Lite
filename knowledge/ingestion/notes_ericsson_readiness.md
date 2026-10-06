# Notes: Ericsson data + actuation readiness

Raised 2026-08-06 in a product Q&A. Follows the confidence-tag convention of the sibling
notes files: [KNOWN] = established in this repo's code/artifacts; [DOMAIN] = standard
Ericsson/3GPP fact, safe to plan on; [VERIFY] = must be confirmed before it is load-bearing
in a sales or build decision.

## What was established

- [KNOWN] The canonical data platform (E1) is vendor-neutral by design: `vendor_dictionaries`
  maps source counter names to canonical ones at store time; only the NanoLink ingest adapter
  exists. [DOMAIN] Ericsson PM arrives as 15-minute ROP XML (TS 32.435) with proprietary
  `pm*` counter names; CM as ENM bulk-CM XML (TS 32.615); per-UE data as CellTrace (CTR/UETR)
  events or MDT.
- [KNOWN] The semi-synthetic feature builder (E2.S4) can produce twin training data from
  PM + topology alone, which is the fallback when an operator will not ship CTR/MDT.
- [KNOWN] Our gap analysis says NybSys delivers ~37% of the counters ES wants; [DOMAIN]
  Ericsson delivers the full set (PRB, volumes, PEE, per-relation HO), so Ericsson data
  should IMPROVE model capability, and per-relation `pmHoExe*` counters are what would turn
  MRO from heuristic HO monitoring into standard per-relation MRO (see notes_mro_xapp.md).
- [KNOWN] Adapter verdict: `nms_northbound` (drive ENM) is the realistic first Ericsson
  adapter; the strategic path is EIAP onboarding via the E3.S6 R1-shaped packaging facade;
  `nanolink_tr069` is irrelevant to macro RAN; `a1_policy` unlikely on Ericsson accounts
  because EIAP occupies the non-RT RIC seat.
- [KNOWN] Claims: everything Ericsson is Building/Vision. Device plane today is single-vendor
  NybSys; no copy may imply a live Ericsson integration.

## To look into (owners unassigned)

1. **Ericsson ingest adapter spec.** [VERIFY] Exact ROP XML variants in scope (measData
   granularity, file naming, compression), and whether ENM's PM subscription NBI or file
   pickup is the assumed transport. Deliverable: a per-adapter contract in
   `artifacts/data-platform/` like the NanoLink one, plus the Ericsson
   `vendor_dictionaries` seed rows (start with the ES/LB/CCO/MRO input set, not all
   counters).
2. **Counter mapping table.** [VERIFY] Confirm the exact Ericsson LTE and NR counter names
   for our canonical inputs (candidates: pmRrcConnEstabSucc/Att, pmPrbUtilDl,
   pmPdcpVolDlDrb, pmHoExeSuccLteIntraF, pmActiveUeDlSum; NR equivalents unverified).
   NR names especially are from memory, not a spec pull.
3. **CM extraction.** [VERIFY] Bulk-CM XML to our topology/config shape: which MOs carry
   site coordinates in practice (often a separate site DB, not the MOM), and RET tilt units
   (tenths of a degree) vs our `cell_el_deg` float.
4. **UE data reality per account.** [VERIFY] Whether target operators will provide
   CTR/UETR or MDT at all; if not, the semi-synthetic path is the default and the demo
   story should say so up front.
5. **ENM northbound for actuation.** [VERIFY] Which ENM NBI (CM REST, scripting, AMOS) is
   licensable/permitted for third-party writes at a given operator, and ENM version spread.
   This decides whether `nms_northbound` for Ericsson is one adapter or several.
6. **EIAP onboarding requirements.** [VERIFY] What EIAP actually requires of an rApp
   package today (CSAR/ASD flavor, signing, marketplace process) vs our R1-shaped
   manifests; we have a real CSAR from the E9 demo to compare against.
7. **MRO upgrade case.** [KNOWN gap, needs a plan] If per-relation HO counters become
   available via Ericsson, MRO's training and action space could target
   `cellIndividualOffset` per relation - today's MRO only does hysteresis/TTT per cell.
   That is a model change, not just an ingest change.
8. **FM story.** [KNOWN] `fm_alarms` has no consumer. Decide whether alarms enter the loop
   (e.g., suppress optimization on cells in active alarm) before any Ericsson pilot.
