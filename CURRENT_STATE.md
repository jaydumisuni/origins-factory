# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`  
**Current merged authority checkpoint:** PR #13 merged at `c87a5790d1ea1bcb0393a5a5075c18d503ed9c74`  
**Exact proven PR head:** `8b4f9fa531468783e518f2533daef7b971de3941`  
**Security state:** Stage-1 authority contracts proven; dormant Stage-2 runtime/enforcement implementation proven and merged; model/runtime activation remains false.

## Merged proven authority chain

The current `main` authority path is:

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

Historical checkpoints remain:

- PR #11 — Stage-1 `ExecutionScope + CapabilityLease` v1.1 contract model — merge `5a7f3cd6e73eed9326b4c6deedbf4e9658271233`;
- AgentOps PR #16 — durable approval/Auth evidence — merge `721be17f1afbdf73cbc4302d89c733596d5160b6`;
- Origins PR #12 — non-activating Lease Issuer Preflight v1 — merge `7454f581d9bdde84e030a9b22f9b2f1f41e06a93`;
- Origins PR #13 — dormant Stage-2 authority runtime + native containment — merge `c87a5790d1ea1bcb0393a5a5075c18d503ed9c74`.

Do not reopen those PRs as unfinished work.

## Stage-2 implementation — complete

PR #13 implements:

### Durable issuer / authority state

- durable SQLite `ExecutionScope` / `CapabilityLease` authority state;
- exact preflight SHA/binding revalidation;
- current scope digest/revision/fence revalidation;
- current provider manifest/generation revalidation;
- host-policy and resource-generation/digest revalidation;
- atomic single-use preflight receipts;
- v1.1 lease creation;
- restart integrity/tamper detection.

### Invocation-time evaluator

Every invocation reloads current durable authority and rechecks:

- lease/scope state, revision, fence and expiry;
- holder identity/generation;
- capability/effect;
- provider identity/manifest/generation;
- host-policy digest/generation;
- resource generation/digest set;
- filesystem grant/deny paths;
- network authority;
- environment names;
- persistent-process authority.

### Revocation / fencing

- lease revocation increments revision/fence;
- scope revocation atomically cascades to active child leases;
- stale handles fail closed;
- restart preserves revoked state;
- native process trees have a revocation coordination boundary.

### Origins-native process admission

`authority_process.rs` admits native process execution only after `authorize_invocation()` succeeds and then:

- obtains the current durable lease;
- resolves `worktree:<repository_id>` only through Origins-owned durable Repository projections for the same Workspace;
- refuses caller-supplied arbitrary host roots;
- applies the existing `ProcessPolicy` executable ceiling;
- constructs the native `SandboxSpec` from current granted authority;
- refuses network-capable leases in native v1 because an exact endpoint broker is not yet implemented.

### Linux native containment

Proven mechanisms:

- filesystem — Landlock;
- network deny / escape filtering — seccomp;
- process tree — setsid/process-group fencing.

### Windows native containment

Proven mechanisms:

- AppContainer lowbox process creation;
- unique ephemeral AppContainer SID ACL grants;
- no network capability in native v1 deny mode;
- kill-on-close Job Object descendant fencing;
- same-AppContainer child creation;
- crash-safe cleanup manifest;
- out-of-job cleanup watchdog;
- stale-manifest recovery;
- trustee-scoped SID removal rather than whole-DACL restoration.

The Windows behavioral proof kills the sandbox helper without allowing Rust destructors to run, proves the descendant heartbeat stops, waits for watchdog recovery, and confirms the unique AppContainer SID is absent from touched ACLs.

## Exact Stage-2 proof

Exact reviewed head:

```text
8b4f9fa531468783e518f2533daef7b971de3941
```

Hosted exact-head proof:

- Origins Contract Spine — run `31754845912` — PASS;
- Origins Daemon Foundation — run `31754845880` — PASS;
- Stage-2 Authority Containment — run `31754845894` — Ubuntu PASS + Windows PASS.

The Stage-2 matrix proves on both OS runners:

- Rust 1.75 dependency resolution;
- workspace Clippy `-D warnings`;
- Stage-2 authority runtime tests;
- native sandbox compilation;
- behavioral filesystem/network/process-tree containment;
- `originsd` compilation.

Windows additionally proves abrupt-helper-death cleanup and ACL trustee removal.

Independent Ubuntu Oracle proof on `kratos-HP-290-G4-Microtower-PC` also confirmed:

- Rust 1.75 Clippy `-Dwarnings` PASS — `oracle_control/results/!!!!!!!!!!!!!!origins-stage2-clippy-20260814-0155.json`;
- Stage-2 authority/runtime tests PASS — `oracle_control/results/!!!!!!!!!!!!!!origins-stage2-authority-tests-20260814-0156.json`;
- native sandbox build PASS — `oracle_control/results/!!!!!!!!!!!!!!origins-stage2-build-sandbox-20260814-0157.json`.

The Ubuntu proof node now has a user-local Rust 1.75 toolchain with `rustfmt` and `clippy` under `/home/kratos/.cargo`; no sudo/system toolchain installation was required.

## Review policy

Owner decision dated 2026-08-14 retires the separate external Stage-2 Sec-Ops gate.

`docs/SECOPS_STAGE2_REVIEW_PACKET.md` is retained as a historical/internal adversarial engineering checklist, not as an external blocking authority.

Current promotion authority is:

```text
exact-head engineering proof
+ adversarial verification
+ independent implementation review
+ explicit owner approval
```

## Current dormant boundary

PR #13 deliberately does **not** activate model/runtime authority. The implementation still reports:

```text
runtime_authority_activated = false
```

Still inactive / not yet implemented as model-controlled production surfaces:

- model-facing lease issuance;
- generalized agent terminal authority;
- browser authority;
- MCP authority;
- exact network endpoint allowlist broker;
- delegated remote authority;
- candidate mutation under model authority;
- self-expanding capability authority.

Do not treat the merged Stage-2 mechanics as implicit permission to expose those surfaces.

## Next valid work

Do not re-plan or rebuild the completed Stage-1/Preflight/Stage-2 authority cores.

Any next activation or provider slice must be a distinct owner-approved change that starts from merged `main` >= `c87a5790d1ea1bcb0393a5a5075c18d503ed9c74`, declares the exact surface being enabled, preserves current authority/revocation/containment invariants, and mechanically proves that surface before merge.

Potential future slices remain independent and bounded, including:

- exact endpoint network broker;
- controlled model-facing lease issuance;
- bounded agent terminal provider;
- browser provider;
- MCP provider;
- candidate-worktree mutation;
- remote delegated authority.

No future slice may silently widen the existing dormant boundary.
