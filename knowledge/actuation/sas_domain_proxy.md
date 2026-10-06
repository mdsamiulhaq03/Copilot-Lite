# `sas_domain_proxy` (logic implemented, no SAS attached)

## What exists

- Pydantic models for the six WINNF-TS-0016 v1.2.7 methods (registration, spectrumInquiry,
  grant, heartbeat, relinquishment, deregistration) with camelCase wire aliases.
- A per-CBSD and per-grant state machine, including the response-code handling table and the
  60 second transmit-shutdown rule.
- An HTTP client behind an interface, with a `MockSas` for tests. mTLS material is
  configuration.

## What does not exist

Connectivity to a certified SAS. WINNF-TS-0122 lab testing is a compliance project with its
own schedule and budget. The adapter reports `disabled` until `SAS_BASE_URL` is set, and
`degraded` if a URL is set without complete mTLS material.

Loop actions targeting this key are rejected. Spectrum authorization is not something a
closed optimisation loop should drive.

## The rule that matters

A CBSD may transmit only while its grant is `AUTHORIZED` **and** the SAS-supplied
`transmitExpireTime` is still in the future. If heartbeats stop succeeding, transmission must
cease within 60 seconds. This is a regulatory obligation, not a quality target.

`must_stop_transmission()` therefore **fails closed**: an unauthorized grant, a missing
expiry, or an expired one all return True. The only path that permits transmission is an
authorized grant with a known deadline still ahead. `shutdown_deadline()` takes the earlier
of the SAS expiry and the 60 second backstop.

Response codes are split into terminal (relinquish: `TERMINATED_GRANT`, `DEREGISTER`,
`BLACKLISTED`) and suspending (stop transmitting, keep heartbeating: `SUSPENDED_GRANT`,
`UNSYNC_OP_PARAM`). An unrecognised non-zero code suspends rather than guessing.

## Reference architecture

Magma's Domain Proxy: radio controller, active-mode reconciliation, config controller. The
split is worth copying if this is ever built out.

## Claims

Never state or imply SAS certification, CBRS certification, or WInnForum approval.
