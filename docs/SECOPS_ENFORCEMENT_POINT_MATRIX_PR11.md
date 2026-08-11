# Sec-Ops Enforcement Point Matrix — PR #11

Status: review-completeness artifact. This document maps candidate authority invariants to existing Origins code and future enforcement points. It does not activate any new authority.

Legend:

- **PROVEN HOST CEILING** — existing runtime control already enforced and covered by Origins proof.
- **CANDIDATE SEMANTIC** — ExecutionScope/CapabilityLease validator exists but is not used to authorize runtime execution.
- **PENDING SEC-OPS** — enforcement design must be accepted before implementation.
- **FUTURE PROVIDER** — OS/provider-specific mechanism is intentionally not implemented in PR #11.

| Invariant / effect | Current owner / hook | Current state | Post-review enforcement point |
|---|---|---|---|
| Workspace path must remain under configured Origins roots | `rust/originsd/src/workspace_roots.rs::WorkspaceRootPolicy` and `rust/originsd/src/process.rs::ProcessPolicy` | PROVEN HOST CEILING | Effective resource grant may only further narrow the canonical authorized root |
| Command executable must be explicitly allowed and not a generic shell | `rust/originsd/src/process.rs::validate_executable` | PROVEN HOST CEILING | Lease capability/effect must intersect with executable/provider manifest before spawn |
| Child process environment starts empty and receives bounded safe variables | `rust/originsd/src/process.rs::run_process` + `apply_safe_environment` | PROVEN HOST CEILING | Environment set becomes host-safe names ∩ ExecutionScope names ∩ CapabilityLease names |
| Timeout/output/argument bounds | `rust/originsd/src/process.rs::prepare_process` | PROVEN HOST CEILING | Lease can only narrow limits; it cannot exceed host maxima |
| Session identity, restart visibility, cancellation and evidence | `rust/originsd/src/sessions.rs` + `ProcessSupervisor` | PROVEN HOST CEILING | Agent-controlled Session projection must later reference `execution_scope_id` and `capability_lease_id` |
| Previously active process becomes interrupted after daemon restart | `rust/originsd/src/sessions.rs::recover_interrupted_sessions` | PROVEN HOST CEILING | Revoked/expired lease must never become active merely because the daemon restarted |
| Repository/worktree/common-dir/HEAD identity | `rust/originsd/src/repository.rs` | PROVEN READ-FIRST TRUTH | Resource resolver uses current Repository/worktree identity before mutation authority is considered |
| Model-facing filesystem identity is not a raw host path | `execution_scope` / `capability_lease` candidate validators | CANDIDATE SEMANTIC | `originsd` resource resolver maps `resource_id + prefix` to current canonical Node path |
| Child authority cannot exceed parent | `validate_child_scope` in Python/TypeScript/Rust candidate validators | CANDIDATE SEMANTIC | Invocation-time evaluator rejects stale or wider child scope regardless of UI/tool state |
| Lease cannot exceed scope | `validate_lease_within_scope` in Python/TypeScript/Rust candidate validators | CANDIDATE SEMANTIC | Every mechanical invocation validates current scope + lease + host policy, not cached UI permission |
| Parent deny cannot be dropped | candidate validators | CANDIDATE SEMANTIC | Resource resolver applies deny set after canonical resolution and before provider invocation |
| Network class/hosts cannot widen | candidate validators | CANDIDATE SEMANTIC | PENDING SEC-OPS | Linux/Windows/network-provider hook; browser/MCP cannot self-open wider network authority |
| Delegated remote authority must be explicit | candidate validators | CANDIDATE SEMANTIC | Remote MCP/remote provider receipt must retain delegated-authority classification |
| Proposal cannot self-approve | `python/origins_integration/capability_proposals.py` | CANDIDATE SEMANTIC | AgentOps durable owner approval is required before a future issuer can mint a lease |
| Proposal/approval substitution | lease `proposal_digest` + `approval_digest` | CANDIDATE SEMANTIC | Future issuer re-hashes exact durable records atomically with parent scope/policy generation |
| Lease state/fence/revision | candidate lease contract | CANDIDATE SEMANTIC | PENDING SEC-OPS | Store + invocation-time fence check; stale holder handles fail closed |
| Lease revocation cancels running work | existing Session cancellation is donor | PENDING SEC-OPS | Lease-to-Session index + ProcessSupervisor / provider-specific revocation |
| Descendant process-tree containment | direct child kill currently exists | PENDING SEC-OPS | FUTURE PROVIDER | OS-specific process group/job/cgroup provider must prove descendants cannot survive revocation |
| Candidate cannot write sibling worktree/main checkout | Repository identity + candidate resource grants | PENDING SEC-OPS | Resource resolver + mutation provider enforce exact candidate worktree write grant |
| Symlink/junction/reparse/mount escape | canonical path checks exist for current roots/cwd | PENDING SEC-OPS | FUTURE PROVIDER | Revalidate resolved object at invocation and mutation boundary; platform-specific no-follow/reparse policy |
| Model cannot disable its own confinement through project files | no active lease runtime yet | PENDING SEC-OPS | Policy/lease state lives outside model-writable project authority; project config may only narrow |
| Local persistent MCP/background process remains confined for lifetime | not implemented | PENDING SEC-OPS | FUTURE PROVIDER | Captured persistent lease + child-tree lifecycle; revocation terminates provider tree |
| Remote MCP is not mislabeled as local sandbox | candidate network class | CANDIDATE SEMANTIC | Provider receipt and UI must retain `delegated_remote_authority=true` |
| Security decisions leave tamper-evident evidence | Origins hash-chained journal/store | PROVEN FOUNDATION | Scope/lease issue/reject/suspend/revoke/expire events use existing metadata-only journal pattern |

## Required architectural ordering

```text
host policy ceiling
    ∩ current ExecutionScope
    ∩ current CapabilityLease
    ∩ current provider capability manifest
    = effective invocation authority
```

No UI, model, stale tool handle, repository file, browser content, MCP response, or remote provider may produce authority outside that intersection.

## PR #11 intentional absence

The following are deliberately absent so Sec-Ops can review the boundary before it becomes an execution path:

- no `origins-authority-contracts` dependency from `originsd`;
- no `/v1/scopes`, `/v1/leases`, `/v1/authority`, or lease-mint endpoint;
- no production lease issuer;
- no runtime process/network/filesystem enforcement from a CapabilityLease;
- no browser/MCP/candidate-worktree mutation activation.
