# `o1_netconf` (placeholder)

## What it would target

The OCUDU companion service `ocudu_netconf`, not the gNB. The OCUDU gNB tree has **no
`lib/o1/`** and no NETCONF or YANG implementation at all; this is code-confirmed, not
inferred. The companion services `ocudu_netconf` and `ocudu_o1_adapter` manage configuration
by REWRITING the gNB config file and RESTARTING the gNB.

## Why it stays a placeholder

The restart semantic. A closed-loop optimisation must not restart a radio, so this plane is
a maintenance-window track, not a live-loop one.

**Binding rule for whoever implements it:** reject live-loop actions with `restart_required`
unless the action is explicitly flagged `maintenance_window=true`. No demo, document or
marketing copy may imply runtime O1 control of OCUDU.

## Intended contract

    config_get(dn, paths) -> dict
    config_set(dn, changes) -> ack

## Claims

Describes a third-party project and a reserved seam. Never assert O1 conformance.
