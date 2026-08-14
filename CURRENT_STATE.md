# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`  
**Current merged product checkpoint:** Phase 3 / PR #14 merged at `106cae1172207ce6b1c1d9b9aaeb076e83b3bb3f`  
**Current Phase-4 implementation/proof head:** `ecefbb081cd977c4faed21e0703e80f9de57b6eb`  
**Security state:** Stage-1 and Stage-2 authority mechanics remain proven and merged; generalized model/runtime activation remains false.

## Do not reopen completed work

The following checkpoints are complete and must be treated as existing authority rather than rebuilt:

- Origins PR #11 — Stage-1 `ExecutionScope + CapabilityLease` v1.1 contracts — merge `5a7f3cd6e73eed9326b4c6deedbf4e9658271233`;
- Hunter-AgentOps PR #16 — durable approval/Auth evidence — merge `721be17f1afbdf73cbc4302d89c733596d5160b6`;
- Origins PR #12 — Lease Issuer Preflight v1 — merge `7454f581d9bdde84e030a9b22f9b2f1f41e06a93`;
- Origins PR #13 — dormant Stage-2 authority runtime + native containment — merge `c87a5790d1ea1bcb0393a5a5075c18d503ed9c74`;
- Origins PR #14 — Phase-3 Workspace shell — merge `106cae1172207ce6b1c1d9b9aaeb076e83b3bb3f`;
- Hunter-AgentOps PR #17 — restart-durable generic Department Operations — merge `054a09e7571b08e5865499d66ea6db5ae6eb43a6`;
- Oracle PR #117 — Live terminal exit-status truth — merge `50521d5c215f09a212ffd016f487cacb198ff087`.

Earlier Engineering Assurance / Production Engineering / Live Engineering / Hunter intelligence mounts are also already part of Origins history. Do not create parallel AgentOps, CodeOps, Sergeant, Hunter or Oracle engines inside Origins.

## Ownership lock

Origins Factory remains a model-optional, evidence-native mission operating environment.

Ownership stays separated:

- **Hunter / Pete:** mission intelligence and optional outside reasoning;
- **AgentOps:** semantic Operation lifecycle, approval, authorization evidence and durable semantic evidence;
- **CodeOps:** repository engineering and provider/model/client routing;
- **Sergeant:** independent engineering review and verdict semantics;
- **Origins / originsd:** Workspace, Repository, Session, mechanical execution admission, evidence projection and capability enforcement;
- **Oracle / Lumi / X-Ray / specialist Gateways:** their existing specialist execution and assurance boundaries.

A mounted owner remains the source of truth. Origins may project or coordinate it; Origins must not shadow its database or duplicate its engine.

## Phase 3 — complete and merged

PR #14 closed the Workspace-shell roadmap gate.

The merged client provides the seven core surfaces:

- Factory;
- Workspace;
- Hunter;
- Armoury;
- Evidence;
- Sergeant;
- Recovery.

The client is bound to durable `originsd` truth for:

- Workspace creation/recovery;
- Repository inspection and Git state;
- bounded repository file browse/read/write;
- optimistic SHA conflict refusal;
- journaled write intent/outcome;
- supervised direct-argv process Sessions;
- retained stdout/stderr and restart recovery;
- capability/health/evidence projection;
- Hunter transport with truthful unavailable/degraded states.

The Phase-3 editor remains repository-root confined; it is not a generic host filesystem API.

## Phase 4 — implementation and proof complete, pending PR promotion

Branch:

```text
build/phase4-intelligence-assurance
```

Functional implementation/proof head:

```text
ecefbb081cd977c4faed21e0703e80f9de57b6eb
```

Phase 4 adds the semantic/intelligence assurance plane without widening Stage-2 authority.

### AgentOps semantic mount

Origins mounts AgentOps persistent stores and current owner services for:

- durable Operations;
- durable approval request/decision/evidence;
- approval-to-request binding;
- compact semantic Attempt/tool-result evidence;
- durable restart recovery and exact replay semantics.

The browser cannot inject `owner_approved`, `approval_state` or arbitrary authorization truth. Pending, rejected or mismatched approvals cannot authorize an Operation.

Hunter-AgentOps PR #17 closed the owner-side restart gap. The owner now persists Operation intent before one-time authorization is consumed, persists completion separately, exposes incomplete intent after restart, preserves idempotent exact replay and refuses changed-ID replay.

### CodeOps mount

Origins mounts the current CodeOps owner registry/routing contract rather than copying provider logic.

The Phase-4 Workspace can project provider availability without exposing secret values. The browser supplies bounded semantic inputs; it does not gain arbitrary provider configuration or filesystem authority.

The canonical CodeOps owner config used by the host proof exposed three enabled provider routes. The live proof selected `fireworks-code` from that owner registry.

### Sergeant loop

Sergeant remains independent. Origins sends the CodeOps-produced Sergeant command through a supervised `originsd` Session and records the independent review result.

A valid Phase-4 proof does not require Sergeant to say PASS. The target-host proof returned the canonical verdict `BLOCK`, which proves the review authority remained independent instead of being coerced into approval.

### Capability compilation

Hunter/semantic capability work remains proposal-only. A capability proposal cannot approve, mint, enlarge or activate its own authority.

Generalized model-facing terminal/browser/MCP/network authority remains dormant.

## Phase-4 proof

### Hosted exact-source proof

GitHub Actions run:

```text
31799458371
```

Result: PASS.

It proves on the reviewed Phase-4 source:

- Python semantic plane compiles;
- Phase-4 semantic/approval/durable-operation tests pass;
- live-owner proof harness compiles;
- Workspace `npm ci` passes;
- Workspace typecheck passes;
- Workspace tests pass;
- Workspace production build passes;
- repository whitespace gate passes.

Phase 4 changes **zero Rust files** relative to merged Phase 3. The Rust/originsd mechanical authority is therefore the already-proven merged Phase-3/Stage-2 implementation rather than a new mechanical runtime.

### Oracle / Kratos AgentOps owner proof

Oracle result:

```text
oracle_control/live_results/origins-phase4-owner-proof-20260814-1203.json
```

Result: exit code 0 / PASS.

Evidence includes:

- `PHASE4_AGENTOPS_OWNER_MOUNT_OK`;
- durable result count `1`;
- `execution_dispatched=false`;
- accepted Operation;
- restart replay idempotent.

### Oracle / Kratos live four-owner stack proof

Oracle Live result is preserved in the workflow evidence for command:

```text
origins-phase4-live-owner-proof-20260814-122210
```

Result: exit code 0 / PASS.

Exact source provenance proved by the harness:

```text
Origins   ecefbb081cd977c4faed21e0703e80f9de57b6eb
AgentOps  054a09e7571b08e5865499d66ea6db5ae6eb43a6
CodeOps   e72afe60ebab41d9f36dc729ad798d5aa4071e83
Sergeant  fe491502a960e6b581a7d07e35683aa28e58b9f8
```

Proof output:

```text
proof                  PHASE4_LIVE_OWNER_STACK_OK
proof_scope            live_owner
mount_status           proven
live_engineering_proven true
selected_provider      fireworks-code
enabled_provider_count 3
project_verdict        BLOCK
receipt_sha256          51daf4fd80c8c4715ffa858617811afdc961b3e8d33974489e73b172820be5d4
review_sha256           f801c6b6e3c6fc91fdc541cf3132c74fdee0aa86d555f8adb16c8ed89d53d563
```

The proof used real owner source checkouts and temporary executable entrypoint shims only to expose their real CLIs to the already-existing `originsd` allowlist. No owner engine was copied and no persistent host PATH/package mutation was required.

## Stage-2 authority runtime — still complete and unchanged

The merged Stage-2 chain remains:

```text
AgentOps durable approval + one-time Auth binding
        ↓
Origins Lease Issuer Preflight v1
        ↓
production durable CapabilityLease issuance
        ↓
current invocation revalidation
        ↓
durable Repository projection
        ↓
existing ProcessPolicy
        ↓
Origins-native SandboxSpec
        ↓
Linux / Windows native containment
```

Stage-2 continues to provide:

- durable SQLite scope/lease state;
- exact preflight binding and single-use receipts;
- restart integrity/tamper detection;
- invocation-time lease/scope/provider/host/resource revalidation;
- revocation, revision/fence advancement and stale-handle failure;
- repository-owned resource resolution;
- Linux Landlock + seccomp + process-group containment;
- Windows AppContainer + ACL + Job Object containment and cleanup recovery.

Historical exact Stage-2 proof remains:

```text
Exact reviewed head: 8b4f9fa531468783e518f2533daef7b971de3941
Contract Spine run: 31754845912 — PASS
Daemon Foundation run: 31754845880 — PASS
Stage-2 Authority Containment run: 31754845894 — Ubuntu PASS + Windows PASS
```

## Dormant activation boundary

The existence of Phase-4 semantic mounts does **not** activate generalized model authority.

The Stage-2 implementation remains explicitly dormant for model/runtime activation. Still not implicitly authorized:

- generalized agent terminal authority;
- model-facing lease issuance;
- browser authority;
- MCP authority;
- exact endpoint network broker;
- delegated remote authority;
- unrestricted candidate mutation;
- self-expanding capability authority.

The Phase-4 live-owner proof is a human-controlled engineering/proof surface exercising already-bounded mechanical paths. It is not permission for a model to inherit those powers.

## Review / promotion policy

Current promotion authority remains:

```text
exact-head engineering proof
+ adversarial verification
+ independent implementation review
+ explicit owner approval
```

The former external Stage-2 Sec-Ops gate remains retired by owner decision. `docs/SECOPS_STAGE2_REVIEW_PACKET.md` is historical/internal adversarial guidance, not a blocking external authority.

## Next valid work

1. Re-prove the documentation-only Phase-4 branch head in hosted CI.
2. Open the Phase-4 PR against `main` with the exact source/owner evidence and explicit dormant-authority nonclaims.
3. Merge only after relevant inherited Origins gates remain green and the PR head has not moved.
4. After Phase 4 merges, recover Phase 5 and existing Oracle/Lumi/application-handoff work before implementing anything new.

Do not re-plan or rebuild completed Phases 1–4 foundations when equivalent merged authority already exists.
