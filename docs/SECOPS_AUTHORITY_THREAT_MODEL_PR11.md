# Sec-Ops Authority Threat Model — PR #11

Status: adversarial review input. No runtime authority activation is introduced by this document.

## Security objective

A CapabilityLease must authorize exactly the capability, resources, effects and lifetime approved for one bounded holder, and must remain valid only while every bound authority input is still current.

## Future issuance transaction to review

A production issuer does not exist in PR #11. The proposed transaction for Sec-Ops review is:

```text
exact CapabilityProposal
    -> canonical proposal SHA-256

durable AgentOps approval record
    -> canonical approval SHA-256

current parent ExecutionScope
    -> scope id + revision + canonical SHA-256

current host policy
    -> policy generation / digest

current capability provider manifest
    -> capability id + provider/version + manifest digest

current resolved authority generation
    -> Workspace / Repository / worktree identities

ALL MATCH APPROVED INPUTS
    -> mint bounded CapabilityLease
```

The issuer must fail closed if any input changes between approval and issuance. Approval itself never executes a provider.

## Invocation transaction to review

Every invocation must re-evaluate current authority rather than trusting a previously rendered tool list or stale client handle:

```text
presented lease id + fence
    -> load current lease
    -> require active state
    -> require current revision/fence
    -> require not expired
    -> load current parent scope
    -> verify scope is still usable
    -> verify proposal/approval binding
    -> verify provider manifest still matches
    -> resolve current Origins resource ids
    -> canonicalize current host paths
    -> intersect with host policy ceiling
    -> apply denies
    -> invoke provider
```

A stale handle is only a reference. It is never authority by itself.

## TOCTOU attack classes

Sec-Ops should challenge at least these transitions:

1. Proposal approved, then proposal content is edited before issuance.
2. Approval record is replaced/replayed against a different proposal.
3. Parent scope is narrowed/revoked after approval but before issuance.
4. Host policy changes after approval but before invocation.
5. Provider version/capability manifest changes after approval.
6. Repository/worktree resource id is rebound to a different physical path.
7. Path is validated, then a symlink/junction/reparse point is swapped before open/write/exec.
8. Lease is suspended/revoked while a client retains a tool handle.
9. Lease fence advances while a queued invocation still carries the old fence.
10. Daemon restarts while a lease/provider/session is active.
11. Network allowlist is changed while browser/MCP connection or DNS result is cached.
12. Persistent local provider forks children before revocation.

Required review question: which checks must be atomic, which may be optimistic with a second check, and which require an OS-specific handle/open-by-identity mechanism?

## Resource identity and path-resolution threat model

Model-facing authority uses `resource_id + normalized relative prefix`; the model does not choose an authoritative raw host path. This removes one class of path confusion but does not by itself solve OS filesystem races.

Sec-Ops must review the resource resolver for:

- symbolic links;
- Windows junctions and reparse points;
- bind mounts / mount-point replacement;
- case-insensitive path aliasing;
- Unicode/path normalization differences;
- short-name / alternate-name behavior where applicable;
- Git worktree `common_dir` versus candidate worktree root;
- repository relocation/rebinding;
- file replacement after canonicalization;
- hard links where write authority could affect an object reachable elsewhere;
- device files, named pipes, sockets or special files under an otherwise allowed directory;
- parent directory rename while an operation is in flight.

The current PR intentionally does not claim these are solved.

## Candidate worktree isolation questions

Future candidate mutation must prove:

```text
candidate A write grant -> candidate A only
candidate A -> sibling candidate B = deny
candidate A -> main checkout = deny
candidate A -> shared Git metadata mutation = explicitly governed, never implied by worktree access
```

Sec-Ops should decide whether Git common metadata requires a separate resource class from the worktree filesystem.

## Network authority threat model

Candidate semantics currently distinguish:

- `deny`;
- `allowlist`;
- `delegated_remote`.

Sec-Ops must define enforcement semantics for:

- DNS rebinding and resolution changes;
- redirects to non-allowlisted hosts;
- HTTP proxy / HTTPS proxy / system proxy inheritance;
- localhost and link-local destinations;
- IP literals versus hostnames;
- IPv4/IPv6 equivalence;
- ports and scheme constraints;
- browser service workers/websockets/subresources;
- local MCP opening its own network sockets;
- remote MCP as delegated authority rather than local confinement.

No network sandbox is activated in PR #11.

## Environment / secret threat model

Authority contracts contain environment **names only**, never values.

Sec-Ops should require that future runtime enforcement:

- intersects requested names with host-safe names;
- never copies secret values into proposals, leases, journal metadata or model-visible receipts;
- distinguishes presence authority from value-disclosure authority if needed;
- prevents inherited proxy/credential variables from silently widening network/service authority;
- audits which provider obtained which environment names without logging their values.

## Revocation / restart threat model

A future runtime must prove:

- revoked/suspended/expired lease rejects new invocation;
- old fence rejects stale invocation;
- restart never converts non-active authority back to active;
- Session/provider children bound to revoked authority are cancelled or disconnected;
- process descendants cannot survive revocation unnoticed;
- persistent provider state does not outlive the lease unless an explicit separate durable authority exists.

## Confused-deputy review

Treat these as potential deputies that may hold broader authority than the requesting model:

- Hunter;
- CodeOps;
- AgentOps;
- Oracle/browser provider;
- local MCP provider;
- remote MCP/service;
- future Ptah provider;
- user-owned terminal/session.

The reviewer should identify every path where a restricted model could cause one of these systems to perform an action using the deputy's broader ambient authority rather than the requester's bounded lease.

## Break-glass owner authority

PR #11 does not define break-glass behavior. Sec-Ops should decide whether emergency owner authority:

- uses a separate authority kind;
- requires explicit interactive owner action;
- is time-limited;
- cannot be delegated to models;
- produces mandatory high-severity journal evidence;
- cannot be confused with a normal CapabilityLease.
