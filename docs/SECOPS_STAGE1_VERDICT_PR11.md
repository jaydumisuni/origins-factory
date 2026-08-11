# Sec-Ops Stage-1 Verdict — Origins PR #11

Review stage: **contract-model authority review**

Verdict: **NEEDS_WORK**

This is not a rejection of the overall `ExecutionScope + CapabilityLease` design. The model is viable, but several contract-level ambiguities must be removed before PR #11 can merge as the authority foundation.

## Summary

The following parts are accepted in principle:

- host policy remains an immutable ceiling;
- `ExecutionScope` and `CapabilityLease` are narrowing authorities;
- model-facing filesystem authority uses Origins-owned resource IDs rather than arbitrary host paths;
- proposal and approval records are digest-bound;
- lease state/fence/revision are intended for stale-handle and revocation control;
- powerful authority remains inactive in PR #11;
- stage-2 implementation red-team remains mandatory before activation.

The stage-1 review found five merge-blocking contract issues and several runtime/provider obligations.

## Merge blockers

### SEC-001 — HIGH — `parent_lease_id` has no enforceable delegation semantics

`capability_lease` contains `parent_lease_id`, but the candidate validators only validate a lease against its `ExecutionScope`. There is no `validate_child_lease` relation and no lease-level delegation ceiling.

Attack path:

```text
narrow parent lease
    -> child lease references parent_lease_id
    -> child still validates directly against broader ExecutionScope
    -> parent lease is informational rather than authoritative
```

Required change before merge:

Choose one of these explicitly:

1. **Preferred v1:** remove `parent_lease_id` and do not support lease-to-lease delegation yet; child authority must be expressed through a child `ExecutionScope` followed by a newly approved lease; or
2. define complete lease delegation semantics, including a child-lease validator proving effects/resources/network/environment/persistence/expiry/remote authority are no broader than the parent lease.

Do not leave `parent_lease_id` as a non-enforced provenance field.

Required proof:

- child lease cannot exceed parent lease while remaining inside the broader scope;
- child lease cannot drop parent denies;
- child lease cannot extend expiry;
- child lease cannot switch network authority class;
- child lease cannot enable persistent/delegated authority absent from parent.

### SEC-002 — HIGH — semantic operation/candidate identity can be laundered across child scopes

`validate_child_scope` binds the child to the same Workspace and `parent_scope_id`, but does not constrain `operation_id` or `candidate_id`.

A child can therefore remain mechanically within the same resource ceiling while relabeling itself as another operation or candidate. That breaks candidate isolation provenance and creates a confused-deputy/audit path.

Required contract semantics:

- `operation_id` must remain immutable across descendants of one operation scope;
- define candidate transition explicitly:
  - root operation scope may have no candidate;
  - delegation may bind once to a specific candidate;
  - once non-empty, `candidate_id` cannot change in descendants;
- cross-candidate authority requires a new explicitly authorized scope, never identity relabeling.

Required proof:

- operation substitution fails;
- candidate A -> candidate B fails;
- empty root candidate -> one explicit candidate transition succeeds only under the defined delegation rule;
- candidate identity cannot be cleared after it becomes bound.

### SEC-003 — HIGH — provider/capability implementation substitution is not bound into the lease

The threat model correctly says issuance must include the current capability provider manifest, but the current lease stores only `capability_id` and no provider identity or manifest digest.

A future provider implementation could change under the same capability ID and the lease would not contain enough information to prove which provider semantics were authorized at issuance.

Required fields or equivalent immutable binding:

- `provider_id` / provider authority identity;
- `provider_manifest_digest`;
- optionally provider generation/version for diagnostics;
- invocation must compare the current manifest digest with the lease-bound digest before use.

A single `authority_inputs_digest` is acceptable only if its canonical preimage is itself durable and independently recoverable; opaque hashing alone is insufficient for audit.

Required proof:

- same `capability_id` + changed provider manifest fails;
- provider identity substitution fails;
- stale provider generation cannot use an otherwise-active lease.

### SEC-004 — HIGH — `ExecutionScope` lifecycle/fencing semantics are incomplete

`ExecutionScope` has `revision` and expiry but no explicit lifecycle state/fence analogous to `CapabilityLease`.

The design repeatedly requires invocation to verify that the current parent scope is still usable and not stale, but the contract does not define how a scope is suspended/revoked or how a stale scope handle is fenced after an update.

Required design decision:

Either:

1. make ExecutionScopes immutable authority generations and require every authority-changing replacement to receive a new `scope_id`; define a separate durable revocation record; or
2. add explicit scope `state` and `fence` semantics equivalent to leases and require invocation-time current-fence validation.

Do not retain a mutable `revision` model without defining how stale scope references are rejected.

Required proof:

- narrowed/revoked parent scope invalidates stale child use;
- lower scope revision/fence replay fails;
- restart cannot resurrect a superseded/revoked scope generation.

### SEC-005 — MEDIUM/HIGH — network authority representation is under-specified

`network_hosts` currently represents a lower-case host with optional port. The contract does not define protocol/scheme semantics, and a host without a port is ambiguous.

DNS rebinding, redirect handling and proxy behavior belong to runtime/provider enforcement, but **protocol and port authority must not be left to each provider to interpret differently**.

Required contract change:

Replace or refine `network_hosts` into normalized endpoint authority with explicit semantics for at least:

- host;
- port or defined bounded port set;
- protocol/transport class relevant to the provider;
- default redirect rule (`deny` outside the approved endpoint set).

Provider-specific browser subresources/websocket behavior may remain stage-2 provider enforcement, but the base lease must have unambiguous endpoint authority.

Required proof:

- omitted port cannot silently mean all ports;
- protocol substitution fails;
- child/lease endpoint authority remains a strict subset;
- allowlist -> delegated-remote switching still fails.

## Required contract hardening — non-blocking if resolved with the blockers above

### CONTRACT-006 — holder identity must be canonical and non-recyclable

`holder_kind + holder_id` currently accepts a free-form non-empty identifier. For Session/provider holders, use canonical Origins subject identity rather than a display/logical name. A lease must not be replayable onto a newly created holder that happens to reuse the same string.

Required semantics:

- kind-specific canonical holder reference;
- Session holder should bind to durable Session identity/generation;
- provider holder should bind to provider instance/generation where applicable.

### CONTRACT-007 — issuance chronology must be relationally valid

Add relation checks so:

- child scope cannot be issued before its parent;
- lease cannot be issued before its scope generation;
- child/lease `updated_at` and expiry remain consistent with parent generation.

This is primarily replay/audit hardening.

## Mitigation classification

| Attack class | Classification | Stage-1 conclusion |
|---|---|---|
| raw absolute path / `..` traversal / backslash path confusion | `CLOSED_BY_CONTRACT` | Current prefix grammar closes the simple representation attack. |
| symlink / junction / reparse point / bind mount / hard-link / special-file escape | `REQUIRES_OS_PROVIDER_ENFORCEMENT` | Contract cannot prove object identity after path resolution. Must be enforced at open/mutation time. |
| resource-ID rebinding | `REQUIRES_RUNTIME_RECHECK` plus possible `OPEN_DESIGN_GAP` | Safe only if resource IDs are non-recyclable and current resource generation is revalidated. If IDs may rebind, add generation/digest binding. |
| sibling worktree / main-checkout mutation | `REQUIRES_RUNTIME_RECHECK` + `REQUIRES_OS_PROVIDER_ENFORCEMENT` | Worktree identity is present, but mutation must resolve current worktree/common-dir and enforce deny boundaries at the write primitive. |
| DNS rebinding / redirects / proxy inheritance | `REQUIRES_PROVIDER_ENFORCEMENT` + `REQUIRES_OS_PROVIDER_ENFORCEMENT` | Must be checked throughout the connection/provider lifetime. |
| ambiguous protocol/port meaning | `OPEN_DESIGN_GAP` | Fix contract before implementation. |
| stale lease handle | `REQUIRES_RUNTIME_RECHECK` | Lease fence/state fields are suitable, provided every invocation reloads current state. |
| stale parent scope | `OPEN_DESIGN_GAP` | Scope lifecycle/fence semantics must be defined first. |
| process-tree survival | `REQUIRES_OS_PROVIDER_ENFORCEMENT` | Stage-2 must prove real Windows/Linux process-tree termination. |
| model edits its own policy/config | `REQUIRES_RUNTIME_RECHECK` + `REQUIRES_OS_PROVIDER_ENFORCEMENT` | Security state must live outside model-writable resources and be reloaded from trusted storage. |
| confused deputy via Hunter/CodeOps/Oracle/provider | `REQUIRES_PROVIDER_ENFORCEMENT` | Every delegated call must propagate and re-check the requester's effective authority; ambient deputy authority is forbidden. |
| approval/proposal substitution | `CLOSED_BY_CONTRACT` only after trusted durable source verification | Digest fields are structurally appropriate, but authenticity comes from trusted durable AgentOps retrieval, not SHA-256 alone. |

## Required stage-2 implementation review

Stage 2 remains mandatory even after these stage-1 findings are corrected.

At minimum attack the real implementation for:

- durable AgentOps approval authenticity and replay resistance;
- atomic/transactional approval-to-lease issuance;
- exact provider-manifest binding;
- current resource-generation resolution;
- real symlink/junction/reparse/mount/hard-link behavior;
- Windows and Linux process-tree revocation;
- network endpoint enforcement, DNS, redirect and proxy behavior;
- local persistent MCP lifetime confinement;
- remote delegated-authority propagation;
- stale lease/scope handles and lower-fence replay;
- daemon restart during issuance/invocation/revocation;
- confused-deputy attempts through Hunter, CodeOps, Oracle and providers;
- self-disable attempts through model-writable configuration.

## Final gate

```yaml
verdict: NEEDS_WORK
stage1_secops_reconciled: false
contract_model_accepted: false
ready_for_sergeant_review: false
ready_for_pr11_merge: false
stage2_secops_required: true
powerful_capability_activation_allowed: false
```

Once SEC-001 through SEC-005 are corrected and shared adversarial proofs are added in Python, TypeScript and Rust, return the exact head for a focused Sec-Ops reconciliation review. Do not implement runtime lease authority while these contract findings remain open.
