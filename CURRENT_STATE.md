# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Merged checkpoint:** Phase 7 / PR #19 / `2f93f79f78502959fd09b50350b878ab659fee84`
**Active phase:** Phase 8 — Custom OS consumption and later Ptah
**Implementation status:** Phase 7 shipped and proven; Phase 8 not started
**Phase-5 proof:** `proof/phase5-workspace-ui-freeze.md`
**Phase-6 proof:** `proof/phase6-device-readonly-freeze.md`
**Phase-7 proof:** `proof/phase7-capability-evolution-freeze.md`

## Completed authority — do not rebuild

Origins PRs #11–#19 are merged authority. Phase 7 is now part of `main` and closes the canonical controlled capability-evolution vertical.

Ownership remains separate:

- Hunter/Pete — intelligence and model routing;
- AgentOps — semantic Operation/approval truth;
- CodeOps — repository engineering/provider routing;
- Sergeant — independent engineering verdicts;
- Origins/originsd — Workspace/Repository/Session/native application/Artifact, canary, Generation, rollback and Mission-resume mechanical truth;
- Oracle — browser and reviewed remote workstation transport;
- Lumi — acquisition/queue/resume truth;
- TECHGUYTOOL Huawei Gateway — Huawei physical-session/operation/journal truth;
- TTG Device X-Ray — read-first device evidence/certification truth.

Origins coordinates and projects these owners. It does not absorb specialist engines.

## Phase 7 merged authority

PR #19 merged at:

```text
2f93f79f78502959fd09b50350b878ab659fee84
```

Frozen exact candidate:

```text
2a4489e6a64c62a3db42dbbd4aab8fca3ea4560e
```

Construction history is preserved at:

```text
archive/phase7-capability-evolution-construction
```

Owner revisions used by the exact-host proof:

```text
Hunter-AgentOps
0eeb69027aec9d70303e724129ebf5585f373ca1

hunter-codeops
348f133cb72ab6d18a7959d4a954158f7b881068

Sergeant
22879a8c47df379d19fb8537c79b745750df4077
```

Phase 7 now provides:

- evidence-backed capability-gap confirmation;
- AgentOps-owned durable capability approval observed over MCP/RPC;
- AgentOps-owned child capability-upgrade external Operation with no approval-triggered execution dispatch;
- durable exact engineering-subject binding;
- isolated/reversible CodeOps candidate construction under `review_required`;
- independent Sergeant `PASS / NEEDS WORK / BLOCK` verdict binding;
- canary Generation proof against the original Mission/Attempt;
- explicit promote/rollback Generation decision;
- persistent active-generation coordination;
- exact pre-upgrade Mission resume token/state preservation across originsd restart;
- loopback Phase-7 API and Workspace EVOLUTION surface that do not accept client-reasserted approval IDs or engineering subjects.

Authority remains bounded:

```text
capability gate = owner_approval_required
engineering gate = review_required
engineering candidate_only = true
runtime_authority_expansion = false
AgentOps transport = mcp/rpc
AgentOps decision tools exposed by Origins = false
```

The AgentOps MCP credential authenticates the local service caller only. Origins never treats it as owner authorization.

## Phase 7 proof checkpoint

All eight existing hosted Origins regression workflows passed against frozen candidate `2a4489e6a64c62a3db42dbbd4aab8fca3ea4560e`, including Phase 7 Capability Evolution and Stage-2 Authority Containment.

A separate adversarial branch differed from the frozen candidate by exactly one tests-only file and passed:

```text
12 passed in 0.10s
```

The frozen exact-host KRATOS proof returned:

```text
PHASE7_LIVE_OWNER_MCP_OK
exitCode = 0
```

It proved real AgentOps MCP/RPC coordination, pinned CodeOps and Sergeant executable provenance, real CodeOps plan application, Sergeant `PASS` on both promote and rollback campaigns, canary Session recovery across originsd restart, exact Mission resume, no model self-approval, no production credentials and no runtime authority expansion.

Full record: `proof/phase7-capability-evolution-freeze.md`.

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

Phase 7 does not grant physical-device write authority or activate the dormant Stage-2 runtime merely because capability evolution exists.

### Ptah runtime

```text
available = false
reason = PTAH_RUNTIME_NOT_AUTHORIZED
```

Phase 8 may consume accepted Ptah vocabulary and later replace interim Providers only where separately authorised and proven. It must not silently rebuild or activate Ptah runtime.

### Current physical Huawei attachment

Historical VOG/P30 recovery evidence remains lineage and predates sealed-bundle v2. No current attached Huawei target is proven in recovered device/host records, so no current-device certification or write claim is made.

## Exact next action

Recover the **Phase 8 — Custom OS consumption and later Ptah** implementation authority before changing source:

1. identify the canonical custom-OS repository, release/packaging owner and current integration state;
2. recover any existing Origins packaging/install/launcher contracts and do not duplicate them;
3. define the smallest pinned-release consumption boundary that installs/launches Origins without copying its source into the OS;
4. preserve Origins as an independently versioned product with exact release provenance, rollback and health proof;
5. keep Ptah runtime unavailable until a separate authorised/proven Provider replacement exists.

Do not reopen Phases 1–7 unless new reproducible evidence proves a regression.
