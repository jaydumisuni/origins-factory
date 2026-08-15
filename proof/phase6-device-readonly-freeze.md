# Phase 6 Device Read-Only Freeze

Status: merged

Phase 6 mounts Huawei Gateway and TTG Device X-Ray as read-only specialist owners. It does not claim or expose production device-write authority.

## Merge checkpoint

```text
PR #17
9a9f05a984b0ba5fd2edd8e8c0b27b5645117697
```

Final promotion head:

```text
284b1145fac5e93edd0235c43a6d395db392e78e
```

## Owner revisions

```text
TECHGUYTOOL-Huawei
fd3f7bb1587b65faaa7d37e0057683dcb07975ed

TTG-Device-X-Ray
34feb55ab937fa865726cbb22c44b09b52084114
```

## Hosted proof

All seven hosted regression workflows passed at the final promotion head:

- Phase 6 Device Read-Only Integration;
- Stage-2 Authority Containment;
- Origins Contract Spine;
- Origins Daemon Foundation;
- Origins Phase 3 Workspace;
- Phase 4 Intelligence Plane;
- Phase 5 Oracle Lumi Applications.

The Phase-6 gate compiled both target-host proof tools, ran the complete Phase-6 Python suite including reconnect coverage, denied Gateway mutations, and passed Workspace typecheck, Vitest and production build. Stage-2 containment remained green on Windows and Ubuntu.

## Oracle / Kratos exact-head proof

Exact-node execution used `oracle.live.v1` on:

```text
kratos-HP-290-G4-Microtower-PC
```

No GitHub interactive execution path was used.

### Reconnect/read-only suite

```text
8 passed in 2.09s
exitCode = 0
timedOut = false
signal = null
```

The reconnect proof creates a new Origins Huawei client against the same owner state and proves the physical Session ID, Gateway Operation ID, request SHA and recovery counters remain identical. Every observed command remains inside the Phase-6 read-only Gateway allowlist.

### Rendered XRAY acceptance

```text
PHASE6_WORKSPACE_UI_OK
source_head = 284b1145fac5e93edd0235c43a6d395db392e78e
exitCode = 0
timedOut = false
signal = null
```

Real system Chrome rendered the isolated XRAY proof with:

- `device_authority = none`;
- `xray_authority = read_only`;
- no write controls;
- write execution unavailable;
- AgentOps↔Gateway typed link unavailable;
- no production credentials used;
- fixture bearer absent from rendered text;
- verified X-Ray integrity.

Rendered PNG:

```text
/tmp/origins-phase6-workspace-ui-proof/phase6-xray.png
bytes = 326134
sha256 = 9b5665285ad84d32d229b8dd55fe9bd5c6620b40221b05068e3313acd5bb24af
```

## Historical VOG lineage

The recovered VOG/P30 handover remains valid historical read-only lineage: Kirin 980, `NO MAIN VERSION`, unreadable vendor/country/OEMINFO version items, and the preserved allowlisted X-Ray capture. That capture predates sealed-bundle v2 and is not represented as a current v2 bundle.

No current physical Huawei attachment is proven in the recovered device registry/host evidence. Phase 6 therefore makes no current-device certification or write claim. Lack of a presently attached handset does not invalidate the proven software read-only integration.

## Preserved nonclaims

### Device write

```text
available = false
reason = PHASE6_DEVICE_WRITE_NOT_AUTHORIZED
```

Origins Phase 6 never opens/closes physical sessions, records endpoints, creates/transitions/resumes Gateway Operations, publishes contracts, mutates providers/workers, consumes Execution Leases, invokes executors, flashes, reboots, unlocks or writes device state.

### AgentOps ↔ Huawei Gateway durable link

```text
available = false
reason = AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE
```

Neither current owner exposes a reversible typed reference that proves AgentOps Operation X owns Huawei Gateway Operation Y. Origins does not create a shadow mapping table or reinterpret hashes as IDs. This remains future owner-contract evolution.

## Final disposition

Phase 6 is merged authority. Reopen it only if new evidence proves a regression or a later approved phase deliberately changes the authority boundary.
