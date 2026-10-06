# Canonical incident line table

Every envelope sample in this fixture pack is built from this table, which is why `order_key`
values, cursors and the timeline all agree with each other. If you extend the pack, extend this
table first.

The incident is the worked-example reboot: SCTP peer failure -> S1 setup failure -> FM critical
`0x16010400` raised -> self-reboot -> recovery. Narrative and verdict:
[`../../../nanolink/femtocell_dashboard_data_contract.md`](../../../nanolink/femtocell_dashboard_data_contract.md)
section 4. Envelope walk-through: [`../../mcp-master-payload.md`](../../mcp-master-payload.md) section 7.

## The two boots

| Boot | `boot_epoch` | Why it matters |
|---|---|---|
| A | `2026-06-13T17:56:57Z` | The boot the incident happens in. Reaches seq 169, then reboots |
| B | `2026-06-13T18:00:31Z` | The recovery boot. **`seq` resets, so seq 0 and 12 and 79 here are numerically lower than boot A's 169** |

`order_key = "{boot_epoch}#{seq:010d}"`, so `2026-06-13T18:00:31Z#0000000000` still sorts after
`2026-06-13T17:56:57Z#0000000169`. Sorting by `seq` or by `ts` alone breaks across this boundary,
which is exactly why the pack includes it.

## Line table

`ts` is UTC. `ts_device_local` in the samples is `ts + 05:30`, because the device stamps local time
with no zone (`tz_source: "device_local"`).

| Boot | seq | ts (UTC) | module | stream | class | severity | alarm_id | message | source_ref | template_hash | archive |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 0 | 17:56:57.004 | SCM | errorlog | STATE | info | - | `---------- eHNB power on ----------` | `main/scm_main.c:118` | `t_0aa931` | `ErrorLog_1757.gz` |
| A | 160 | 17:57:31.145 | SON | errorlog | STATE | info | - | `S1SetupRequest sent to MME 10.20.0.4, attempt 10 of 10` | `src/son_s1.c:642` | `t_5c3e88` | `ErrorLog_1758.gz` |
| A | 161 | 17:57:32.010 | SON | errorlog | FAULT | major | `0x16020509` | `Alarm Logged, id: 0x16020509 file: src/son_s1.c line: 705 detail: S1SetupCnf failure!` | `src/son_s1.c:705` | `t_2d55f1` | `ErrorLog_1758.gz` |
| A | 162 | 17:57:32.640 | SON | errorlog | STATE | major | - | `S1 setup retry counter reached 10 of 10, escalating to FM` | `src/son_s1.c:718` | `t_7e0b44` | `ErrorLog_1758.gz` |
| A | 163 | 17:57:33.118 | SCTP | errorlog | STATE | major | - | `sctp connect to peer 10.20.0.4 failed, retry 4` | `src/sctp_app.c:1588` | `t_4b7e10` | `ErrorLog_1758.gz` |
| A | 164 | 17:57:34.402 | SCTP | errorlog | FAULT | major | `0x02120400` | `Alarm Logged, id: 0x02120400 file: src/sctp_app.c line: 1588 detail: SCTP Connect Peer Failed!` | `src/sctp_app.c:1588` | `t_1a0cc9` | `ErrorLog_1758.gz` |
| A | 165 | 17:58:12.431 | FM | errorlog | FAULT | critical | `0x16010400` | `Critical alarm 0x16010400 raised, system reboot will be taken to recover it after 90s.` | `main/informer.c:307` | `t_9f21c4` | `ErrorLog_1758.gz` |
| A | 166 | 17:58:12.905 | FM | errorlog | STATE | critical | - | `S1 retry exhaustion confirmed, RecoveryMechanism=System Reboot, ClearingMechanism=CellSetup` | `main/informer.c:311` | `t_3c07ba` | `ErrorLog_1758.gz` |
| A | 167 | 17:59:42.118 | SCM | errorlog | STATE | major | - | `Reboot command received from FM` | `main/scm_main.c:512` | `t_6b19d0` | `ErrorLog_1800.gz` |
| A | 168 | 17:59:42.640 | SCM | errorlog | STATE | info | - | `module stop order: L1_L2_Wrapper, SON, SCTP, TR69` | `main/scm_main.c:534` | `t_8d4402` | `ErrorLog_1800.gz` |
| A | 169 | 17:59:44.007 | SCM | errorlog | STATE | major | - | `*** force to do power-off` | `main/scm_main.c:561` | `t_1f7ac5` | `ErrorLog_1800.gz` |
| B | 0 | 18:00:31.002 | SCM | errorlog | STATE | info | - | `---------- eHNB power on ----------` | `main/scm_main.c:118` | `t_0aa931` | `ErrorLog_1801.gz` |
| B | 12 | 18:00:38.771 | TR69 | errorlog | FAULT | major | `0x18020400` | `Alarm Logged, id: 0x18020400 file: src/tr69_acs.c line: 902 detail: ACS connect failed, backoff 8s` | `src/tr69_acs.c:902` | `t_5f8e21` | `ErrorLog_1801.gz` |
| B | 79 | 18:01:07.552 | SON | errorlog | STATE | info | - | `S1 setup succeed, cell available` | `src/son_s1.c:688` | `t_4a11c2` | `ErrorLog_1801.gz` |
| B | 80 | 18:01:07.930 | FM | errorlog | FAULT | cleared | `0x16010400` | `Alarm Report, id: 0x16010400 file: main/informer.c line: 307 detail: cleared by CellSetup` | `main/informer.c:307` | `t_2b66d9` | `ErrorLog_1801.gz` |

The reboot arrives 90 seconds after the critical raise, exactly as the alarm line announces
(17:58:12 + 90s = 17:59:42), which is the observable that makes the reboot self-healing rather
than an actuation regression.

`archive_file` in the samples is the full object key,
`nanolink-logs/3f2a1c88/8C1F64-2205609999/20260613/<file>`. The filename stamp is the **upload
minute**, not the content window: each file covers roughly the preceding 60 seconds.

## Which values are real and which are fixture

| Provenance | Values |
|---|---|
| **From tracked docs, verbatim** | boot A `boot_epoch`; seq 163 / 164 / 165 with their `ts`, `ts_device_local`, `message`, `severity`, `class`, `alarm_id`, `source_ref`, `template_hash` and `archive_file`; the alarm ids and their observed counts; the device model, product class and software version; the 24 managed-parameter values; the 15-entry alarm catalogue and vendor policy |
| **Synthesised for the fixture** | boot B `boot_epoch`; every other seq, `ts` and `message`; the `t_` template hashes other than `t_4b7e10` / `t_1a0cc9` / `t_9f21c4`; all `command_id` / `reco_id` values; the tenant uuid (from the payload doc's example) |

Synthesised lines follow the documented line grammar and the documented alarm-id catalogue, so
they parse and classify the same way the real ones do. They are **not** a claim about what the real
capture contains. When item 1 lands, prefer its lines over these.

## Matching behaviour the samples assume

- `q` is a **case-insensitive substring** match on `message`. `q="alarm"` therefore hits
  `Alarm Logged`, `Alarm Report` and `Critical alarm …`. This follows the payload doc's own
  worked example, where `q="alarm"` hits both `Alarm Logged` and `Critical alarm`.
- A line that is both a hit and a neighbour of another hit is emitted **once**, as
  `match: "hit"`. Boot A seq 165 is the case: it is a hit in its own right and the `+1` neighbour
  of the seq-164 hit.
- `hit_group` numbers hits in `order_key` order starting at 1, and context lines carry the
  `hit_group` of the hit they belong to.
