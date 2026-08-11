# ADR-0012 — Execution Scope and Capability Lease

Status: **v1.1 security-review candidate on draft PR #11. Not runtime authority.**

## Purpose

Origins already has proven mechanical ceilings: loopback-only `originsd`, Workspace-root authorization, executable allowlists, cleared process environments, bounded Sessions, cancellation/recovery, read-first Repository/Git truth and tamper-evident evidence.

This ADR defines the delegated-authority contracts that may later sit between approved semantic intent and those mechanical facilities.

```text
host policy ceiling
    ∩ current ExecutionScope
    ∩ current CapabilityLease
    ∩ current capability-provider manifest
    = effective invocation authority
```

Scopes and leases may narrow authority. They never widen the host ceiling.

## Review history

Sec-Ops stage-1 review of v1.0 returned `NEEDS_WORK` with SEC-001 through SEC-005. v1.1 applies those corrections before any runtime activation:

- SEC-001 — remove unenforced lease-to-lease delegation;
- SEC-002 — bind operation/candidate semantic identity across scope delegation;
- SEC-003 — bind the exact capability provider/manifest generation into the lease;
- SEC-004 — give ExecutionScope explicit lifecycle/fence semantics and stale-generation validation;
- SEC-005 — replace ambiguous `host[:port]` network authority with exact protocol/host/port endpoints and explicit redirect policy.

Additional Sec-Ops hardening in v1.1:

- canonical holder UUID + generation;
- relational issuance chronology.

Canonical original findings remain in `docs/SECOPS_STAGE1_VERDICT_PR11.md`.

## Candidate proof implementation

The authority model remains deliberately separated from active Origins Contract Spine/runtime authority:

- Python: `python/origins_contracts/authority.py` → v1.1 validator;
- TypeScript: `typescript/authority.ts` → v1.1 validator;
- Rust: isolated `rust/origins-authority-contracts` crate;
- shared valid/invalid corpus: `contracts/authority-fixtures.json`;
- shared attack corpus: `contracts/authority-adversarial-fixtures.json`.

All three consume the same v1.1 documents, canonical JSON/SHA-256 rules and attack cases.

## Resource authority

Model-facing filesystem authority uses Origins-owned resources rather than model-selected host paths:

```text
workspace:<id>
repository:<id>
worktree:<id>
artifact:<id>
```

A grant is:

```text
resource_id
prefix
```

`prefix` is a normalized relative prefix. Absolute paths, backslashes, empty path segments, `.` / `..`, trailing `/` and NUL are rejected.

This closes simple path-representation traversal. It does **not** claim to solve symlink/junction/reparse/mount/hard-link/special-file races. Those remain stage-2 invocation/OS enforcement obligations.

## ExecutionScope v1.1

An `execution_scope` contains:

- `scope_id`;
- `workspace_id`;
- immutable semantic `operation_id`;
- optional `candidate_id`;
- optional `parent_scope_id`;
- effects;
- resource read/write/deny grants;
- `network_mode`;
- exact `network_endpoints`;
- `network_redirect_policy`;
- environment variable names only;
- process-execution flag;
- persistent-process flag;
- delegation flag;
- delegated-remote-authority flag;
- `state`;
- `fence`;
- issue/update/expiry timestamps;
- revision.

### Scope lifecycle

States are:

```text
active | suspended | revoked | expired
```

A presented scope is authority only when it matches the current stored generation exactly and that current generation is `active`.

Current-generation validation binds:

```text
scope_id
workspace_id
operation_id
candidate_id
revision
fence
canonical document digest
```

A stale/lower-fence/superseded presentation therefore fails. Runtime storage/transition atomicity remains stage-2 work.

### Scope delegation

For child scopes:

- Workspace cannot change;
- `operation_id` cannot change;
- `parent_scope_id` must identify the parent;
- parent must allow delegation;
- effects/resources/environment/network/process/persistence/delegated-remote authority can only shrink;
- parent denies cannot be dropped;
- expiry cannot extend beyond parent;
- child `issued_at` cannot predate the parent's current `updated_at` generation.

Candidate identity follows a bind-once rule:

```text
parent candidate empty
→ child may remain unbound or bind to one candidate

parent candidate non-empty
→ every descendant must retain exactly that candidate
```

Candidate identity cannot switch or clear once bound. Cross-candidate authority requires a separately authorized scope, not relabeling.

## CapabilityLease v1.1

A `capability_lease` contains:

- `lease_id`;
- `scope_id` and `workspace_id`;
- capability id;
- provider id;
- provider manifest SHA-256;
- provider generation;
- canonical holder kind;
- holder UUID;
- holder generation;
- leased effects/resources/network/environment authority;
- persistent-process permission;
- delegated-remote-authority flag;
- approval authority/id;
- durable approval-record SHA-256;
- approved CapabilityProposal SHA-256;
- state;
- fence;
- issue/update/expiry timestamps;
- revision.

A lease must fit entirely inside its active ExecutionScope.

### SEC-001 decision — no lease-to-lease delegation in v1.1

`parent_lease_id` is removed.

There is no lease-to-lease delegation in v1.1. An unknown `parent_lease_id` field fails contract validation.

If narrower delegated authority is required, the supported design is:

```text
parent ExecutionScope
→ authorized child ExecutionScope
→ independently issued bounded CapabilityLease
```

Lease-to-lease delegation may only be introduced later with its own complete monotonic semantics and security review.

### SEC-003 provider binding

A lease binds the implementation that was authorized, not merely the logical capability name:

```text
capability_id
provider_id
provider_manifest_digest
provider_generation
```

Invocation must compare the current provider identity, manifest digest and generation with the lease. Same capability id with a different provider implementation/generation is not authorized.

### Holder binding

`holder_id` is an Origins canonical UUID and `holder_generation >= 1`.

Display names/logical external identifiers are not holder authority. A recycled human-readable name cannot inherit an old lease merely by string reuse.

The exact mapping of holder generation to durable Session/provider subjects is stage-2 runtime work.

## Network authority v1.1

`network_hosts` is removed.

Network authority is represented by exact endpoint objects:

```text
protocol
host
port
```

Supported candidate protocol classes are:

```text
http | https | tcp | udp | ws | wss
```

Port is mandatory and must be `1..65535`. Omitted port never means all/default ports.

`network_redirect_policy` is explicit. v1.1 accepts only:

```text
deny_outside_endpoints
```

Delegation rules:

- child/lease may move to `deny`;
- otherwise network authority class cannot change;
- endpoint set must be an exact subset including protocol + host + port;
- redirect policy cannot widen;
- `delegated_remote` must be explicitly labeled delegated remote authority.

DNS resolution, IPv4/IPv6 routing, proxies, redirects, browser subresources/websockets and local-MCP socket behavior remain runtime/provider/OS obligations for stage 2. Unsupported endpoint forms must fail rather than silently widen authority.

## Approval durability gate

Current AgentOps approval semantics are not yet backed by the durable production evidence required to mint security authority.

Therefore PR #11 still has:

- no production CapabilityLease issuer;
- no lease persistence/activation path;
- no volatile approval → durable authority conversion;
- no shadow AgentOps approval database inside Origins.

Future issuance must bind at least:

```text
exact approved CapabilityProposal digest
+ authentic durable AgentOps approval record digest
+ current parent ExecutionScope generation
+ current host-policy generation/digest
+ current capability-provider identity/manifest generation
+ current resolved authority/resource generation
→ bounded CapabilityLease
```

Approval is not execution.

## Invocation and revocation obligations — stage 2

Future runtime invocation must reload current authority rather than trusting a rendered tool list/stale handle:

```text
lease id + fence
→ current lease active/current?
→ current scope active/current?
→ proposal/approval binding authentic?
→ provider binding current?
→ resource identities current?
→ host ceiling intersection
→ denies
→ provider invocation
```

Stage 2 must prove:

- lease and scope stale-fence rejection;
- restart cannot resurrect revoked/expired authority;
- revoked authority blocks new calls;
- bound Sessions/providers are cancelled/disconnected;
- descendant process trees cannot survive unnoticed;
- filesystem/worktree/symlink/junction/reparse/mount/hard-link boundaries hold per OS;
- DNS/proxy/redirect/network behavior holds throughout connection lifetime;
- local persistent MCP remains confined for its complete lifetime;
- remote MCP remains explicit delegated authority;
- privileged deputies propagate requester authority rather than ambient authority;
- model-writable project/config files cannot disable or enlarge policy.

## Existing Origins authorities retained

This ADR does not replace:

- `ProcessPolicy` host ceilings;
- `WorkspaceRootPolicy`;
- Process Sessions / Active Session Control / Live Observation;
- Repository/Git Sessions;
- Hunter intelligence mount;
- AgentOps lifecycle/approval ownership;
- CodeOps engineering/provider routing ownership;
- Sergeant independent review;
- hash-chained Origins evidence.

## Non-claims

This ADR does not claim:

- focused Sec-Ops reconciliation PASS yet;
- production lease issuance;
- durable AgentOps approval persistence;
- runtime filesystem/network sandboxing;
- process-tree revocation implementation;
- browser control;
- MCP execution;
- candidate-worktree mutation;
- generalized agent terminal authority;
- React UI;
- Ptah runtime integration.
