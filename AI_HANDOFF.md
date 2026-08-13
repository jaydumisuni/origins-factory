# Origins Factory — AI Handoff

**Status:** Mandatory recovery entry point  
**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`  
**Current implementation truth:** `CURRENT_STATE.md`  
**Current authority checkpoint:** PR #13 merged; continue from `main` at/after `c87a5790d1ea1bcb0393a5a5075c18d503ed9c74`

## Recover before acting

Read in this order:

1. this file;
2. `CURRENT_STATE.md`;
3. `docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md`;
4. `docs/ADR-0013-LEASE-ISSUER-PREFLIGHT.md`;
5. `docs/ADR-0014-STAGE2-AUTHORITY-RUNTIME.md`;
6. `docs/SECOPS_STAGE2_REVIEW_PACKET.md` as an internal adversarial checklist/historical artifact only;
7. current `main` source/proof;
8. owning external repositories for any mounted capability being changed.

Do not ask the owner to repeat recoverable evidence.

## Product identity lock

Origins Factory is a model-optional, evidence-native mission operating environment. It is not an OS, IDE clone, AI sidebar, dashboard, model router or replacement for its specialist systems.

Three truths remain separate:

- **Semantic:** Hunter + AgentOps.
- **Mechanical:** `originsd`, specialist Gateways, Nodes, later authorized Ptah integration.
- **Assurance:** Sergeant, X-Ray, deterministic proof, specialist governors and human acceptance.

Ownership remains:

- Hunter / Pete — mission intelligence and optional outside reasoning;
- AgentOps — semantic lifecycle/approval/completion and durable approval evidence;
- CodeOps — repository engineering and provider/model/client routing;
- Sergeant — independent engineering review;
- Origins — persistent workspace, mechanical integration and capability enforcement;
- Oracle/Lumi/X-Ray/specialist Gateways — their existing specialist boundaries.

Do not duplicate an owning engine inside Origins.

## Merged authority checkpoints

### Stage-1 contracts

Origins PR #11 merged at:

```text
5a7f3cd6e73eed9326b4c6deedbf4e9658271233
```

It established the v1.1 `ExecutionScope + CapabilityLease` authority contract model plus Hunter intelligence/capability-proposal semantics. Historical Stage-1 Sec-Ops reconciliation remains part of the provenance of that contract model.

### AgentOps durable approval/Auth

Hunter-AgentOps PR #16 merged at:

```text
721be17f1afbdf73cbc4302d89c733596d5160b6
```

AgentOps remains the sole owner of durable approval/authentication evidence. Origins must not create a shadow approval database or infer owner identity from a digest alone.

### Lease Issuer Preflight v1

Origins PR #12 merged at:

```text
7454f581d9bdde84e030a9b22f9b2f1f41e06a93
```

The merged preflight binds durable AgentOps evidence + one-time Auth to the exact current issuance context and remains the source of eligible evidence consumed by the production issuer.

### Dormant Stage-2 authority runtime

Origins PR #13 merged at:

```text
c87a5790d1ea1bcb0393a5a5075c18d503ed9c74
```

Exact proven PR head:

```text
8b4f9fa531468783e518f2533daef7b971de3941
```

It implements and proves:

- durable SQLite scope/lease state;
- exact single-use preflight-to-lease issuance;
- restart integrity/tamper detection;
- invocation-time current-authority revalidation;
- durable revocation and revision/fence advancement;
- stale-handle failure after revocation/restart;
- Origins-native process admission through durable Repository projections + existing ProcessPolicy;
- Linux Landlock + seccomp + process-group containment;
- Windows AppContainer + ACL + Job Object containment;
- Windows crash-safe AppContainer ACL/profile cleanup and stale-manifest recovery.

Exact-head proof:

- Contract Spine run `31754845912` — PASS;
- Daemon Foundation run `31754845880` — PASS;
- Stage-2 Authority Containment run `31754845894` — Ubuntu PASS + Windows PASS.

Independent Ubuntu Oracle proof also passed pinned Rust 1.75 Clippy, Stage-2 authority/runtime tests and native sandbox compilation on `kratos-HP-290-G4-Microtower-PC`.

## Current authority chain

```text
AgentOps durable approval + one-time Auth binding
        ↓
Origins eligible preflight
        ↓
durable single-use CapabilityLease issuance
        ↓
current invocation revalidation
        ↓
durable Repository projection
        ↓
existing ProcessPolicy
        ↓
native SandboxSpec
        ↓
Linux / Windows containment
```

No caller may supply arbitrary host resource roots to native admission.

## Review-policy lock

Owner decision dated 2026-08-14 retires the separate external Stage-2 Sec-Ops gate.

The former `docs/SECOPS_STAGE2_REVIEW_PACKET.md` remains an internal hostile-test checklist and historical review artifact only.

Promotion authority is now:

```text
exact-head proof
+ adversarial verification
+ independent implementation review
+ explicit owner approval
```

Do not resurrect an external Sec-Ops requirement in future planning unless the owner explicitly reintroduces it.

## Dormant activation boundary

The merged Stage-2 implementation still reports:

```text
runtime_authority_activated = false
```

It does not expose a new model/HTTP activation route.

Still inactive / future bounded slices:

- model-facing lease issuance;
- generalized agent terminal authority;
- browser authority;
- MCP authority;
- exact endpoint network broker;
- delegated remote authority;
- candidate-worktree mutation under model authority;
- automatic self-expansion of authority.

The existence of the merged issuer/evaluator/containment mechanics is not itself activation permission.

## Next valid work

Do not reopen PR #11, AgentOps #16, Origins #12 or Origins #13 as unfinished implementation.

Start any future provider/activation work from current `main` and keep each surface explicit and bounded:

```text
recover main >= c87a5790...
→ name one capability/provider surface
→ define exact owner/host authority ceiling
→ bind it to the existing current scope/lease evaluator
→ preserve durable revocation/fencing
→ use native/specialist containment appropriate to that surface
→ adversarially test it
→ exact-head proof
→ independent implementation review
→ explicit owner approval
→ merge
```

Do not activate multiple powerful surfaces implicitly in one unrelated change.

## Anti-drift rules

- Preserve Stage-1 authority provenance, but do not treat its historical Sec-Ops process as an active Stage-2 gate.
- Do not create shadow AgentOps or Hunter storage.
- Do not let a capability approve, mint or enlarge its own authority.
- Do not bypass `originsd`/specialist authority for convenience.
- Failed/partial attempts remain visible.
- Keep model/runtime activation explicit; never infer it from implementation availability.

## Session close rule

After substantial Origins work:

1. preserve exact code/proof checkpoint;
2. update `CURRENT_STATE.md`;
3. update this handoff when the next valid action changes;
4. update the product plan only for owner-accepted architecture changes;
5. update central `TTG-progress` / `TTG-ecosystem` / `TTG-decisions` recovery when ecosystem status or policy changes;
6. preserve unresolved limitations explicitly;
7. leave one clean continuation point.
