# Phase 6 Device Read-Only Freeze

Status: promotion candidate

Phase 6 mounts Huawei Gateway and TTG Device X-Ray as read-only specialist owners. It does not claim or expose production device-write authority.

## Owner revisions

```text
TECHGUYTOOL-Huawei
fd3f7bb1587b65faaa7d37e0057683dcb07975ed

TTG-Device-X-Ray
34feb55ab937fa865726cbb22c44b09b52084114
```

## Implementation proof head

```text
4e788a584505fc5728a07a1bf73ece1e8a6bfd17
```

At that exact source head:

- all seven hosted regression workflows passed;
- the Phase-6 dedicated gate compiled both target-host proof tools;
- the full Phase-6 Python suite passed with reconnect coverage;
- Workspace TypeScript typecheck, Vitest and production build passed;
- Gateway mutation denial remained explicit;
- Stage-2 containment remained green on Windows and Ubuntu.

## Oracle / Kratos proof

Exact-node execution used Oracle Live on:

```text
kratos-HP-290-G4-Microtower-PC
```

No GitHub interactive execution path was used.

### Reconnect/read-only suite

Oracle command result:

```text
8 passed in 2.08s
exitCode = 0
timedOut = false
signal = null
```

The reconnect proof creates a new Origins Huawei client against the same owner state and proves the physical Session ID, Gateway Operation ID, request SHA and recovery counters remain identical. Every observed command remains inside the Phase-6 read-only Gateway allowlist.

### Rendered XRAY acceptance

Oracle result:

```text
PHASE6_WORKSPACE_UI_OK
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

The recovered VOG/P30 handover remains valid historical read-only lineage: Kirin 980, `NO MAIN VERSION`, unreadable vendor/country/OEMINFO version items, and the preserved allowlisted X-Ray capture. That capture predates sealed-bundle v2 and is therefore not represented as a current v2 bundle.

No current physical Huawei attachment is proven in the device registry/recovery evidence. Phase 6 therefore makes no current-device certification or write claim. Lack of a currently attached handset does not invalidate the proven software read-only integration.

## Explicit accepted nonclaims

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

Neither current owner exposes a reversible typed reference that proves AgentOps Operation X owns Huawei Gateway Operation Y. Origins does not create a shadow mapping table or reinterpret hashes as IDs. This is an owner-contract gap, not a Phase-6 software failure.

## Promotion decision

The Phase-6 read-only integration is complete and promotion-ready with the two nonclaims above preserved as truthful unavailable states. Any future device-write authority or cross-owner semantic/mechanical link requires its own owner-approved contract and proof campaign.
