# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Merged checkpoint:** Phase 6 / PR #17 / `9a9f05a984b0ba5fd2edd8e8c0b27b5645117697`
**Active phase:** Phase 7 — capability evolution recovery
**Implementation status:** Phase 7 not started
**Phase-5 proof:** `proof/phase5-workspace-ui-freeze.md`
**Phase-6 proof:** `proof/phase6-device-readonly-freeze.md`

## Completed authority — do not rebuild

Origins PRs #11–#17 are merged authority. Phase 6 is now part of `main` and closes the canonical device read-only integration vertical.

Ownership remains separate:

- Hunter/Pete — intelligence and model routing;
- AgentOps — semantic Operation/approval truth;
- CodeOps — repository engineering/provider routing;
- Sergeant — independent engineering verdicts;
- Origins/originsd — Workspace/Repository/Session/native application/Artifact mechanical truth;
- Oracle — browser and reviewed remote workstation transport;
- Lumi — acquisition/queue/resume truth;
- TECHGUYTOOL Huawei Gateway — Huawei physical-session/operation/journal truth;
- TTG Device X-Ray — read-first device evidence/certification truth.

Origins coordinates and projects these owners. It does not absorb specialist engines.

## Phase 6 merged authority

Owner revisions frozen for the Phase-6 campaign:

```text
TECHGUYTOOL-Huawei
fd3f7bb1587b65faaa7d37e0057683dcb07975ed

TTG-Device-X-Ray
34feb55ab937fa865726cbb22c44b09b52084114
```

Origins mounts only these Huawei Gateway commands:

```text
health
doctor
snapshot
get_physical_session
get_operation
list_events
verify_journal
```

Every other Gateway command is refused before network I/O. Projection fails closed unless:

```text
device_authority = none
xray_authority = read_only
journal_valid = true
```

The merged XRAY surface projects physical Sessions, Gateway Operations/recovery counts, endpoint observations, Device Evidence/Twin, verdicts, leases, Verification Result, Recovery Plan and sealed TTG Device X-Ray evidence. It exposes no device action control.

The Phase-6 HTTP service remains loopback and GET-only for protected device projections. Mutation verbs remain `405 PHASE6_READ_ONLY`.

## Phase 6 proof checkpoint

Final promotion head:

```text
284b1145fac5e93edd0235c43a6d395db392e78e
```

Merge checkpoint:

```text
9a9f05a984b0ba5fd2edd8e8c0b27b5645117697
```

At the final promotion head:

- all seven hosted regression workflows passed;
- Oracle/Kratos backend + reconnect suite passed 8/8;
- reconnect preserved physical Session ID, Gateway Operation ID, request SHA and recovery counters without mutation;
- exact-head isolated real Chrome returned `PHASE6_WORKSPACE_UI_OK`;
- XRAY rendered no write controls and no production credentials;
- `device_authority=none` and `xray_authority=read_only` remained visible truth;
- X-Ray integrity remained verified;
- rendered screenshot SHA-256 is `9b5665285ad84d32d229b8dd55fe9bd5c6620b40221b05068e3313acd5bb24af`.

See `proof/phase6-device-readonly-freeze.md`.

## Preserved truthful nonclaims

### AgentOps ↔ Huawei Gateway durable link

```text
available = false
reason = AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE
```

Neither owner currently exposes a reversible typed semantic↔mechanical reference. Origins does not create a shadow mapping database or infer IDs from hashes. A future link belongs under owner-approved contract evolution.

### Device write execution

```text
available = false
reason = PHASE6_DEVICE_WRITE_NOT_AUTHORIZED
```

Phase 6 does not gain write authority because later Huawei lease/executor code exists.

### Current physical Huawei attachment

Historical VOG/P30 recovery evidence remains lineage and predates sealed-bundle v2. No current attached Huawei target is proven in recovered device/host records, so no current-device certification or write claim is made.

## Exact next action

Recover Phase 7 capability-evolution authority and evidence before implementation. Do not reopen Phase 6 unless new evidence proves a regression.
