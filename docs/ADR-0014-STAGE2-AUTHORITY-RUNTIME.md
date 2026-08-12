# ADR-0014 — Dormant Stage-2 Authority Runtime and Native Containment

Status: **Implementation candidate — runtime activation remains false**

## Decision

Origins Stage-2 implements the production authority mechanics required by the v1.1 `ExecutionScope` / `CapabilityLease` model while keeping model/runtime activation structurally dormant until a separate Stage-2 Sec-Ops implementation red-team approves the real enforcement boundary.

The authority chain is:

```text
AgentOps durable approval + one-time Auth binding
        ↓
Origins eligible preflight receipt
        ↓
atomic durable lease issuance
        ↓
current invocation revalidation
        ↓
Origins durable repository projection
        ↓
existing ProcessPolicy
        ↓
native SandboxSpec
        ↓
Linux / Windows native containment
```

No caller may supply an arbitrary host root to native authority admission. Stage-2 native v1 accepts `worktree:<repository_id>` resources only and resolves them through Origins' durable Repository projection for the same Workspace.

## Implemented authority core

### Durable lease issuer

The Rust `originsd` authority store:

- validates the exact eligible preflight receipt and its SHA-256;
- recomputes the issuance-binding document;
- revalidates current scope digest/revision/fence;
- revalidates provider manifest/generation, host-policy generation/digest and resource generations/digests;
- creates a v1.1 `CapabilityLease` in an immediate SQLite transaction;
- binds durable resource generations to the lease;
- enforces single use of a preflight receipt by a unique durable index;
- verifies persisted authority contracts and digests on restart;
- fails closed on authority-state tamper.

### Invocation evaluator

Every authority decision reloads current durable lease and scope state and rechecks:

- handle revision/fence;
- active state and expiration;
- lease-within-scope relation;
- capability and effect;
- holder identity/generation;
- provider identity/manifest/generation;
- host-policy digest/generation;
- resource generation/digest set;
- filesystem grants/denies and canonical relative paths;
- network grants;
- environment names;
- persistent-process permission.

An authorized decision still reports `runtime_authority_activated = false` in this candidate.

### Durable revocation and fencing

- lease revocation atomically increments lease `revision` and `fence`;
- scope revocation atomically revokes the scope and all non-revoked child leases;
- stale handles fail closed after generation/fence changes;
- restart preserves revoked state;
- process-tree revocation coordination has a fail-closed interface for bound native process trees.

## Native process admission

`authority_process.rs` performs admission only after `authorize_invocation()` succeeds. It then:

- resolves the exact current lease;
- builds the containment plan from that lease;
- accepts executable names through the existing Origins `ProcessPolicy` allowlist;
- resolves resource roots only through durable Repository projections;
- canonicalizes existing grant paths and refuses traversal/escape;
- carries only granted environment names/values into the sandbox spec;
- refuses network-capable leases in native v1 because an exact endpoint broker is not implemented;
- returns a `SandboxSpec` with `runtime_authority_activated = false`.

There is no HTTP/model activation route for this admission surface in this candidate.

## Linux containment

The proven Linux backend is intentionally named by its real mechanisms:

- filesystem: `linux.landlock.v1`;
- process tree: `linux.setsid-process-group-fence.v1`;
- network deny: `linux.seccomp-network-deny.v1`.

The backend uses Landlock with hard-requirement compatibility, `no_new_privs`, a new session/process group, and a seccomp filter that denies socket/network and namespace/process-group escape syscalls required by this v1 boundary.

## Windows containment

The Windows backend uses:

- AppContainer lowbox process creation;
- temporary ACL grants to the unique AppContainer SID;
- no network capability for native v1 network-deny mode;
- a kill-on-close Job Object for the entire descendant tree;
- explicit same-AppContainer descendant creation in the behavioral probe;
- a crash-safe cleanup coordinator.

### Crash-safe cleanup

Normal or abrupt helper death must not strand temporary AppContainer authority.

For every ephemeral AppContainer, Origins writes a cleanup manifest containing only:

- manifest version;
- owner process id;
- unique profile name;
- derived AppContainer SID string;
- exact ACL-touched paths.

An out-of-job watchdog waits for the sandbox helper. On helper death it:

1. re-derives and validates the profile SID;
2. revokes only that unique SID from the exact touched paths;
3. deletes the ephemeral AppContainer profile;
4. deletes the cleanup manifest only after cleanup succeeds.

The next sandbox start also recovers stale manifests whose owner process is no longer alive. Normal cleanup uses the same trustee-scoped SID revocation model and deliberately does not restore a whole saved DACL, avoiding rollback of unrelated concurrent ACL changes.

## Native v1 network boundary

The authority evaluator can reason about exact network endpoints, but **native containment v1 does not implement endpoint allowlisting**. Native process admission and containment planning therefore refuse network-capable leases rather than representing an unimplemented broker as enforcement.

## Proof boundary

The canonical Stage-2 matrix requires both Ubuntu and Windows to pass:

- Rust 1.75 dependency resolution;
- workspace Clippy with `-D warnings`;
- Stage-2 authority runtime tests;
- native sandbox compile;
- behavioral filesystem/network/process-tree containment;
- `originsd` compile.

Windows behavioral proof additionally kills the sandbox helper abruptly and proves:

- the Job Object fences the descendant tree;
- the external watchdog removes the cleanup manifest;
- the unique AppContainer SID is absent from the touched ACLs afterward.

The complete inherited Origins Daemon Foundation proof remains mandatory.

## Explicit non-claims

This implementation does **not** approve or enable:

- a model-facing lease issuance route;
- generalized agent terminal authority;
- browser authority;
- MCP authority;
- network endpoint allowlisting/brokering;
- delegated remote authority;
- candidate worktree mutation by model authority;
- automatic self-expansion of capabilities.

`RUNTIME_AUTHORITY_ACTIVATED` remains false and no activation route is added.

## Promotion gate

This dormant implementation may be merged after its exact-head engineering proof and independent review are green.

**Powerful runtime authority must remain inactive after merge.** A separate Stage-2 Sec-Ops red-team against the merged/real implementation is mandatory before any model-controlled authority can be activated.
