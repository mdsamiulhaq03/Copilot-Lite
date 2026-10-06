# `open_mplane` (placeholder)

## What it would target

O-RU management over the Open Fronthaul management plane.

## Why it stays a placeholder

No customer requires it yet, and it is not an increment on what exists. The device plane
today is a single-vendor TR-069/CWMP EMS; an M-Plane adapter is a different southbound
entirely, with its own transport, security model and O-RU inventory.

## Re-open criteria

An O-RU deployment we actually manage, plus a decision about whether we drive the O-RU
directly or through the operator's existing management system (`nms_northbound`).

## Claims

Never assert Open Fronthaul M-Plane conformance.
