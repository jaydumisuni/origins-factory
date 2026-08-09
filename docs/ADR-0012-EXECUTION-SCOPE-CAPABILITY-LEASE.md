# ADR-0012 — Execution Scope and Capability Lease

Status: security-review candidate on draft PR #11. **Not an accepted authority model and not a runtime activation path.**

## Current proof state

The candidate authority model now has executable validators in three runtimes without being registered as an active Origins Contract Spine authority type:

- Python: `python/origins_contracts/authority.py`;
- TypeScript: `typescript/authority.ts`;
- Rust: isolated `rust/origins-authority-contracts` crate;
- shared corpus: `contracts/authority-fixtures.json`.

The three implementations use the frozen Contract Spine canonical JSON/SHA-256 rules. The shared valid scope and lease fixtures are pinned to the same expected hashes in all three test lanes. Shared invalid fixtures require the same error classes. Python/TypeScript/Rust also challenge monotonic child-scope and lease-within-scope rules.

This is **candidate semantic proof only**. It does not prove OS filesystem/network isolation, approval durability, production lease issuance, revocation, process-tree containment, or Sec-Ops acceptance.

## Purpose

Origins already has proven mechanical controls: loopback-only `originsd`, Workspace root ceilings, executable allowlists, cleared process environments, bounded process Sessions, cancellation, restart recovery, read-first Git identity, and hash-chained evidence.

The missing layer is explicit delegated authority between an approved semantic request and those existing mechanical facilities.

This ADR defines the candidate objects Sec-Ops must challenge before browser/MCP/parallel candidate execution or generalized agent terminal authority is implemented.

## Design rule

```text
host policy ceiling
    ∩
ExecutionScope
    ∩
CapabilityLease
    =
effective authority
```

A scope or lease may narrow host policy. It can never widen it.

## Resource references, not raw host paths

Model-facing authority must not contain arbitrary host paths as the primary identity of filesystem authority.

Origins will issue resource identities such as:

```text
workspace:<workspace-id>
repository:<repository-id>
worktree:<candidate-id>
artifact:<artifact-id>
```

A resource grant contains:

```text
resource_id
prefix
```

`prefix` is a normalized relative path beneath the resolved resource. Empty prefix means the resource root. Absolute paths, backslashes, `.`/`..` segments and null bytes are forbidden in the contract.

`originsd` resolves resource identities to canonical host paths at invocation time and then applies the global host policy ceiling. The model does not decide that mapping.

This makes policy portable across Windows/Linux Nodes and avoids leaking machine layout into model-visible authority objects.

## ExecutionScope candidate

An `execution_scope` contains:

- `scope_id`;
- `workspace_id`;
- semantic `operation_id`;
- optional `candidate_id`;
- optional `parent_scope_id`;
- allowed effects;
- resource read grants;
- resource write grants;
- resource denies;
- network mode and exact host allowlist;
- allowed environment variable names, never values;
- process execution flag;
- persistent-process flag;
- delegation flag;
- delegated-remote-authority flag;
- issue/expiry timestamps;
- monotonic revision.

Rules:

- write grants must also be readable;
- `persistent_process_allowed` requires process execution;
- `network_mode=deny` has no hosts and cannot claim delegated remote authority;
- `network_mode=allowlist` requires hosts and is not delegated remote authority;
- `network_mode=delegated_remote` requires hosts and must explicitly mark delegated remote authority;
- expired scopes cannot be used;
- child scopes must be no broader than their parent;
- parent deny grants remain authoritative in all children.

## CapabilityLease candidate

A `capability_lease` contains:

- `lease_id`;
- `scope_id` and `workspace_id`;
- optional `parent_lease_id`;
- capability id;
- holder kind/id;
- effects actually leased;
- resource read/write/deny grants actually leased;
- network mode/hosts actually leased;
- environment names actually leased;
- persistent-process permission;
- delegated-remote-authority flag;
- approval authority/id;
- SHA-256 of the approval record;
- SHA-256 of the exact CapabilityProposal that was approved;
- state: `active | suspended | revoked | expired`;
- monotonically increasing `fence`;
- issue/expiry timestamps;
- monotonic revision.

A lease must fit completely within its ExecutionScope.

Approval does not create a lease by itself.

## Approval durability gate

Current AgentOps approval semantics are correct, but its current in-process `ApprovalService` storage is not durable enough to mint security authority after restart.

Therefore this PR may define and validate lease objects, but **production lease issuance remains disabled** until the owning AgentOps backend provides durable approval evidence that Origins can reference and digest.

Origins must not create a shadow AgentOps approval database to bypass that requirement.

A future issuer must prove:

```text
approved CapabilityProposal digest
+
durable AgentOps approval record digest
+
current parent ExecutionScope
+
current host policy
+
current capability provider
→ bounded CapabilityLease
```

The proposal and approval digests prevent post-approval scope substitution.

## Monotonic delegation

For child scopes and leases:

- effects can only shrink;
- filesystem resource/prefix authority can only shrink;
- parent denies must remain present;
- environment names can only shrink;
- network may move to `deny`, otherwise it must remain in the same authority class with a subset of hosts;
- persistent execution cannot become enabled if the parent forbids it;
- delegated remote authority cannot become enabled if the parent forbids it;
- expiry cannot extend beyond the parent;
- a parent that forbids delegation cannot create child scope authority.

## Revocation model

Future runtime state:

```text
active → suspended → revoked
active → expired
```

Once a lease is suspended/revoked/expired:

- new invocations fail closed;
- stale handles fail at invocation-time policy check;
- Sessions bound to the lease are cancelled;
- persistent local providers and their child process trees are terminated or disconnected according to the platform enforcement provider;
- restart cannot resurrect the lease as active without new authority.

## Existing Origins components that remain authoritative

This ADR does not replace:

- `ProcessPolicy` host ceilings;
- `WorkspaceRootPolicy`;
- Process Sessions and Active Session Control;
- Repository/Git Sessions;
- Hunter intelligence mount;
- AgentOps lifecycle/approval ownership;
- CodeOps engineering/provider routing ownership;
- Sergeant independent review;
- hash-chained Origins evidence.

It inserts delegated authority between approved semantic intent and existing execution.

## Sec-Ops questions

Sec-Ops must challenge at least:

1. lease/proposal/approval substitution and forgery;
2. TOCTOU between approval, lease issuance and invocation;
3. resource-id mapping attacks;
4. path traversal, symlink/junction/reparse-point and mount escape;
5. sibling worktree and main-checkout mutation;
6. stale handle/network/MCP escape;
7. proxy/DNS/redirect authority widening;
8. secret/environment leakage;
9. process-tree survival after revocation;
10. self-disable/config-edit attacks;
11. confused-deputy paths through Hunter, CodeOps, Oracle or remote providers;
12. delegated remote authority labeling;
13. restart/recovery of expired or revoked authority;
14. break-glass owner authority and audit;
15. whether resource-grant prefix semantics are sufficient across supported platforms.

## Non-claims

This ADR does not claim:

- accepted Sec-Ops approval;
- production lease issuance;
- durable AgentOps approval persistence;
- runtime filesystem sandboxing;
- runtime network sandboxing;
- browser control;
- MCP execution;
- parallel candidate worktree mutation;
- React UI;
- Ptah runtime integration.
